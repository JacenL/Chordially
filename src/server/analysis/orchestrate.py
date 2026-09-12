"""Drive a page through the whole recognition pipeline.

Concurrency detail worth stating: the first chunk is sent alone and awaited
before the rest fan out. A cached prompt prefix only becomes readable once the
first response has begun, so firing every chunk at once would have them all miss
the cache and each pay full price for the shared system prompt.
"""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import anthropic

from src.config import PROJECT_ROOT
from src.schemas.music import MeasureTranscription, WireSystem
from src.server.recognition import claude_adapter as ca
from src.server.recognition import cv_geometry as cg

# Transcription cache. Keyed by the exact image bytes plus the model and prompt
# that read them, so re-analyzing an unchanged page costs nothing and changing
# either the prompt or the model correctly invalidates every entry. Lives under
# work/, which .gitignore already excludes -- cached provider output is derived
# data and does not belong in the repository.
CACHE_DIR = PROJECT_ROOT / "work" / "transcription-cache"


def _cache_key(png: bytes, model: str, effort: str) -> str:
    h = hashlib.sha256()
    h.update(png)
    h.update(model.encode())
    h.update(effort.encode())
    h.update(ca.TRANSCRIBE_SYSTEM_PROMPT.encode())
    return h.hexdigest()[:32]


def _cache_read(key: str) -> WireSystem | None:
    path = CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        return WireSystem.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None  # A stale or corrupt entry is simply a miss.


def _cache_write(key: str, wire: WireSystem) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.json").write_text(
        wire.model_dump_json(indent=1), encoding="utf-8"
    )

# Concurrency for chunk requests. Modest on purpose: enough to turn a 13-minute
# serial page into about two minutes, low enough to stay well inside rate limits.
MAX_CONCURRENCY = 6

# Hard ceiling on requests for a single upload, so a pathological page cannot
# run up an unbounded bill.
MAX_CHUNKS_PER_UPLOAD = 60


@dataclass
class PageAnalysis:
    geometry: cg.PageGeometry
    transcriptions: dict[tuple[int, int], MeasureTranscription] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    # Clef/key/meter in force for each system, established only where actually
    # printed. This, not the per-measure transcription fields, is the source of
    # truth for meter when rating and validating.
    signatures_by_system: dict[int, dict[str, int | None]] = field(default_factory=dict)
    # (system_index, measure_index) pairs whose request never completed. Distinct
    # from measures recognition read and rejected.
    not_attempted: set[tuple[int, int]] = field(default_factory=set)
    provider_unavailable: str = ""
    mismatched_chunks: int = 0
    chunks_attempted: int = 0
    cache_hits: int = 0
    latency_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def transcribed_measures(self) -> int:
        return len(self.transcriptions)


def analyze_page(
    gray_for_geometry,
    gray_for_crops,
    *,
    client: anthropic.Anthropic | None = None,
    chunk_size: int = 2,
    effort: str = "medium",
    use_cache: bool = True,
    progress: Callable[[str], None] | None = None,
) -> PageAnalysis:
    """Detect geometry, then transcribe every chunk and key results by measure."""
    geometry = cg.analyze_page(gray_for_geometry)
    result = PageAnalysis(geometry=geometry)

    def say(msg: str) -> None:
        if progress:
            progress(msg)

    chunks: list[cg.Chunk] = []
    for system in geometry.systems:
        if system.measures:
            chunks.extend(cg.system_chunks(system, max_measures=chunk_size))

    if len(chunks) > MAX_CHUNKS_PER_UPLOAD:
        result.errors.append(
            f"page has {len(chunks)} chunks, above the {MAX_CHUNKS_PER_UPLOAD} "
            "limit for one upload; later chunks were not transcribed"
        )
        chunks = chunks[:MAX_CHUNKS_PER_UPLOAD]

    if client is None:
        client = ca.build_client()

    payloads = [(ch, cg.encode_png(cg.crop(gray_for_crops, ch.box, pad_frac=0.004))) for ch in chunks]
    result.chunks_attempted = len(payloads)

    # Per-system clef/key/meter context.
    #
    # Two passes, not one, and the reason is structural rather than stylistic.
    # A key signature is printed only at the start of a system, so only a
    # system-start chunk can establish one. Running every chunk concurrently in
    # a single pass meant later chunks read the context before earlier ones had
    # written it, so nothing after the first chunk ever learned that the page
    # changes key and meter partway down -- a 2/4 G-major etude was analyzed as
    # 4/4 in C. Pass one reads the system starts, pass two reads the remainder
    # with its own system's signature already known.
    context_by_system: dict[int, tuple[int | None, int | None, int | None]] = {}

    def context_for(system_index: int) -> str:
        beats, beat_value, key = context_by_system.get(system_index, (None, None, None))
        bits = []
        if beats and beat_value:
            bits.append(f"time signature {beats}/{beat_value}")
        if key is not None:
            bits.append(f"key signature {key} sharps/flats")
        bits.append("treble clef, solo violin")
        return "; ".join(bits)

    model = ca.model_id()

    def run(item: tuple[cg.Chunk, bytes]) -> tuple[cg.Chunk, ca.SystemResult]:
        ch, png = item
        if use_cache:
            key = _cache_key(png, model, effort)
            hit = _cache_read(key)
            if hit is not None:
                result.cache_hits += 1
                return ch, ca.SystemResult(hit, None, 0.0)
        res = ca.transcribe_system(
            client,
            png,
            expected_measures=ch.count,
            context=context_for(ch.system_index),
            effort=effort,
        )
        if use_cache and res.transcription is not None:
            _cache_write(_cache_key(png, model, effort), res.transcription)
        return ch, res

    def absorb(ch: cg.Chunk, res: ca.SystemResult) -> None:
        result.latency_s += res.latency_s
        result.input_tokens += res.input_tokens
        result.output_tokens += res.output_tokens
        result.cache_read_tokens += res.cache_read_tokens

        if res.error or res.transcription is None:
            result.errors.append(f"system {ch.system_index} measures {ch.start_measure}+: {res.error}")
            for i in range(ch.count):
                result.not_attempted.add((ch.system_index, ch.start_measure + i))
            low = (res.error or "").lower()
            if "credit balance" in low or "quota" in low or "billing" in low:
                result.provider_unavailable = (
                    "the Anthropic account funding PRACTICEMAP_ANTHROPIC_API_KEY has no "
                    "remaining credit, so these sections were never read"
                )
            elif "rate" in low and "limit" in low:
                result.provider_unavailable = "the provider rate limit was reached"
            return

        wire = res.transcription
        # Only a chunk that actually shows a printed signature may set one.
        # Anything else is inference, and inference here silently overwrites a
        # real reading.
        if wire.signature_visible:
            prev = context_by_system.get(ch.system_index, (None, None, None))
            context_by_system[ch.system_index] = (
                wire.beats or prev[0],
                wire.beat_value or prev[1],
                wire.key_fifths,
            )

        measures, problems = wire.to_measures()
        for p in problems:
            result.errors.append(f"system {ch.system_index}: {p}")

        if len(measures) != ch.count:
            # Do not shift measures into place. A misalignment would attach the
            # wrong notes to a real region and look entirely convincing.
            result.mismatched_chunks += 1
            result.errors.append(
                f"system {ch.system_index}: transcription found {len(measures)} "
                f"measures where the page shows {ch.count}; left unrated"
            )
            return

        for i, m in enumerate(measures):
            result.transcriptions[(ch.system_index, ch.start_measure + i)] = m

    if not payloads:
        return result

    openers = [p for p in payloads if p[0].start_measure == 0]
    rest = [p for p in payloads if p[0].start_measure != 0]
    total = len(payloads)
    done = 0

    # Pass one, system starts. The very first is sent alone: a cached prompt
    # prefix is only readable once a response has begun, so fanning out
    # immediately would have every request miss the cache and pay full price for
    # the shared system prompt.
    if openers:
        ch, res = run(openers[0])
        absorb(ch, res)
        done += 1
        say(f"read {done} of {total} sections")

        if len(openers) > 1:
            with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
                for ch, res in pool.map(run, openers[1:]):
                    absorb(ch, res)
                    done += 1
                    say(f"read {done} of {total} sections")

    # A system that never printed its own signature inherits the one in force
    # above it, which is how a continuation system is read by a musician too.
    carried: tuple[int | None, int | None, int | None] = (None, None, None)
    for sysd in geometry.systems:
        if sysd.index in context_by_system:
            carried = context_by_system[sysd.index]
        elif any(c is not None for c in carried):
            context_by_system[sysd.index] = carried

    # Pass two, the remainder, now that each system's signature is known.
    if rest:
        with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
            for ch, res in pool.map(run, rest):
                absorb(ch, res)
                done += 1
                say(f"read {done} of {total} sections")

    result.signatures_by_system = {
        k: {"beats": v[0], "beat_value": v[1], "key_fifths": v[2]}
        for k, v in sorted(context_by_system.items())
    }
    return result
