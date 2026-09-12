"""C1 go/no-go spike: does a real scan become validated musical events?

Proves or disproves the one thing planning cannot settle -- whether a scanned
page survives the whole path from ink to checked notation:

    PDF page -> staff/barline geometry -> system crops -> vision transcription
             -> duration validation against the time signature

Transcription is per SYSTEM, not per measure. An early version of this spike
cropped individual measures and the model reported low confidence on nearly all
of them, for a good reason: pitch is read against the five staff lines, and a
measure-sized crop does not reliably show them. Validation is still per measure.

    python scripts/spike_recognition.py --page 3 --systems 2
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_env  # noqa: E402
from src.schemas.music import validate_measure  # noqa: E402
from src.server.recognition import claude_adapter as ca  # noqa: E402
from src.server.recognition import cv_geometry as cg  # noqa: E402


def describe(n) -> str:
    if n.is_rest:
        return "rest"
    acc = "#" if n.alter > 0 else "b" if n.alter < 0 else ""
    return f"{n.step}{acc}{n.octave}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default="Wohlfahrt_Op_45_Bk_1.pdf")
    ap.add_argument("--page", type=int, default=3)
    ap.add_argument("--systems", type=int, default=2, help="how many systems to try")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--chunk", type=int, default=2, help="measures per crop")
    args = ap.parse_args()

    load_env()

    print(f"rendering {args.pdf} page {args.page} ...")
    gray = cg.render_page(args.pdf, args.page)
    geom = cg.analyze_page(gray)
    hires = cg.render_page(args.pdf, args.page, dpi=cg.CROP_DPI)
    print(
        f"geometry: {len(geom.systems)} systems, {geom.measure_count} measures, "
        f"skew {geom.skew_deg:+.2f} deg\n"
    )

    try:
        client = ca.build_client()
    except ca.MissingCredentials as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 3

    beats = beat_value = key_fifths = None
    passed = rejected = 0
    count_mismatches = 0
    total_lat = 0.0
    tin = tout = tcache = 0

    chunk_n = 0
    for system in geom.systems[: args.systems]:
        if not system.measures:
            continue
        print(f"system {system.index}: {len(system.measures)} measures by geometry")

        for ch in cg.system_chunks(system, max_measures=args.chunk):
            img = cg.crop(hires, ch.box, pad_frac=0.004)
            png = cg.encode_png(img)
            chunk_n += 1

            bits = []
            if beats and beat_value:
                bits.append(f"time signature {beats}/{beat_value}")
            if key_fifths is not None:
                bits.append(f"key signature {key_fifths} sharps/flats")
            bits.append("treble clef, solo violin")

            res = ca.transcribe_system(
                client,
                png,
                expected_measures=ch.count,
                context="; ".join(bits),
                effort=args.effort,
            )
            total_lat += res.latency_s
            tin += res.input_tokens
            tout += res.output_tokens
            tcache += res.cache_read_tokens

            tag = f"  [{ch.start_measure}..{ch.start_measure + ch.count - 1}] {img.shape[1]}x{img.shape[0]}"
            if res.error or res.transcription is None:
                print(f"{tag} ERROR {res.error}")
                continue

            t = res.transcription
            if t.beats and t.beat_value:
                beats, beat_value = t.beats, t.beat_value
            if t.key_fifths is not None:
                key_fifths = t.key_fifths

            measures, problems = t.to_measures()
            for p in problems:
                print(f"    unparseable: {p}")

            got = len(measures)
            flag = "" if got == ch.count else f"  <-- COUNT MISMATCH (geometry says {ch.count})"
            if got != ch.count:
                count_mismatches += 1
            print(f"{tag}{flag}  {res.latency_s:.0f}s")
            if t.note:
                print(f"    note: {t.note[:130]}")

            for i, m in enumerate(measures):
                v = validate_measure(m, beats, beat_value)
                if v.non_musical:
                    verdict = "SKIP  "
                elif v.ok:
                    passed += 1
                    verdict = f"OK{'?' if v.low_confidence else ' '}   {m.total_duration}"
                else:
                    rejected += 1
                    verdict = f"REJECT {v.reason} (got {v.actual} want {v.expected})"
                pitches = " ".join(describe(n) for n in m.notes)
                print(f"    m{ch.start_measure + i}: {verdict:<26} {len(m.notes):2d} ev  {pitches[:62]}")

    total = passed + rejected
    rate = (passed / total * 100) if total else 0.0
    print(f"\nRESULT: {passed}/{total} measures validated ({rate:.0f}%)")
    print(f"systems with a measure-count mismatch: {count_mismatches}")
    print(
        f"tokens: in={tin} out={tout} cache_read={tcache}; "
        f"{total_lat / max(1, chunk_n):.0f}s per chunk over {chunk_n} chunks"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
