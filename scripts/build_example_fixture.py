"""Analyze the fixture page once and save the result as the example.

Two artifacts come out of one run:

* `fixtures/expected/<name>-analysis.json` -- the prepared analysis that drives
  example mode. This is what lets the app run end to end with no credentials
  configured, using a *real* scan rather than invented data.
* `fixtures/expected/review-phrases.md` -- a human-readable rendering of the
  phrases, boundary reasons and per-measure ratings, for a violinist to check.

Costs real API calls. Run it deliberately, not on every start.

    python scripts/build_example_fixture.py --page 3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import PROJECT_ROOT, load_env  # noqa: E402
from src.features.difficulty.colors import category_for, format_score  # noqa: E402
from src.server.analysis import orchestrate  # noqa: E402
from src.server.analysis.assemble import (  # noqa: E402
    build_score,
    fingerprint,
    rate_phrases,
    rate_score,
    segment_score,
)
from src.server.recognition import cv_geometry as cg  # noqa: E402

OUT_DIR = PROJECT_ROOT / "fixtures" / "expected"
PAGES_DIR = PROJECT_ROOT / "fixtures" / "pages"


def rebuild_review(name: str) -> int:
    """Regenerate the review packet from the analysis already committed.

    Separate from a full rebuild on purpose: the packet's wording changes far
    more often than the analysis does, and re-running recognition to reword a
    document risks perturbing a fixture that 200-odd tests are pinned to.
    """
    import json
    import types

    from src.schemas.analysis import AnalysisBundle

    path = OUT_DIR / f"{name}-analysis.json"
    if not path.exists():
        print(f"no analysis at {path}")
        return 1
    bundle = AnalysisBundle.load_path(path)
    write_review(
        name,
        bundle.score,
        bundle.measure_difficulty,
        [p for p in bundle.phrases if p.level == "phrase"],
        bundle.phrase_difficulty,
        types.SimpleNamespace(errors=bundle.recognition.errors),
    )
    print(f"review -> {(OUT_DIR / 'review-phrases.md').relative_to(PROJECT_ROOT)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", default="fixtures/scores/wohlfahrt-op45-bk1.pdf")
    ap.add_argument("--page", type=int, default=3)
    ap.add_argument("--name", default="wohlfahrt-p3")
    ap.add_argument("--effort", default="medium")
    ap.add_argument(
        "--review-only",
        action="store_true",
        help="Rebuild only the review packet from the committed analysis. "
        "Touches no provider and does not rewrite the fixture.",
    )
    args = ap.parse_args()

    load_env()
    if args.review_only:
        return rebuild_review(args.name)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    pdf_path = PROJECT_ROOT / args.pdf
    print(f"analyzing {pdf_path.name} page {args.page} ...")

    gray = cg.render_page(str(pdf_path), args.page)
    hires = cg.render_page(str(pdf_path), args.page, dpi=cg.CROP_DPI)

    # The page image the browser will show. Written at the crop resolution so it
    # stays sharp when zoomed; overlays are normalized so resolution is free.
    page_png = PAGES_DIR / f"{args.name}.png"
    page_png.write_bytes(cg.encode_png(hires))
    print(f"page image -> {page_png.relative_to(PROJECT_ROOT)}")

    analysis = orchestrate.analyze_page(
        gray, hires, effort=args.effort, progress=lambda m: print(f"  {m}", end="\r")
    )
    print()

    score = build_score(
        score_id=args.name,
        content_fingerprint=fingerprint(pdf_path.read_bytes()),
        geometry=analysis.geometry,
        transcriptions=analysis.transcriptions,
        signatures_by_system=analysis.signatures_by_system,
        not_attempted=analysis.not_attempted,
        input_kind="example",
        title="Wohlfahrt, Op. 45 Book 1 — Etudes 2 and 3",
        is_example=True,
        image_url=f"/fixtures/pages/{args.name}.png",
    )
    measure_ratings = rate_score(score)
    phrases = segment_score(score)
    phrase_ratings = rate_phrases(phrases, measure_ratings)

    payload = {
        "score": score.model_dump(mode="json"),
        "measure_difficulty": {k: v.model_dump(mode="json") for k, v in measure_ratings.items()},
        "phrases": [p.model_dump(mode="json") for p in phrases],
        "phrase_difficulty": {k: v.model_dump(mode="json") for k, v in phrase_ratings.items()},
        "recognition": {
            "chunks_attempted": analysis.chunks_attempted,
            "mismatched_chunks": analysis.mismatched_chunks,
            "errors": analysis.errors,
            "latency_s": round(analysis.latency_s, 1),
            "input_tokens": analysis.input_tokens,
            "output_tokens": analysis.output_tokens,
            "cache_read_tokens": analysis.cache_read_tokens,
        },
    }
    out_json = OUT_DIR / f"{args.name}-analysis.json"
    out_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    rated = [d for d in measure_ratings.values() if d.score is not None]
    unrated = [d for d in measure_ratings.values() if d.score is None]
    print(f"\nanalysis -> {out_json.relative_to(PROJECT_ROOT)}")
    print(f"  measures: {len(score.measures)}  rated: {len(rated)}  unrated: {len(unrated)}")
    if rated:
        print(f"  rating range: {min(d.score for d in rated):.1f} – {max(d.score for d in rated):.1f}")
    print(f"  phrases: {len(phrases)}")
    print(f"  chunk mismatches: {analysis.mismatched_chunks}")
    print(f"  wall time in requests: {analysis.latency_s:.0f}s  cache reads: {analysis.cache_read_tokens}")

    write_review(args.name, score, measure_ratings, phrases, phrase_ratings, analysis)
    print(f"review  -> {(OUT_DIR / 'review-phrases.md').relative_to(PROJECT_ROOT)}")
    return 0


def write_review(name, score, measure_ratings, phrases, phrase_ratings, analysis) -> None:
    lines: list[str] = []
    a = lines.append
    a("# Review packet: phrases and difficulty ratings")
    a("")
    a("**Status: NOT YET REVIEWED BY A VIOLINIST.**")
    a("")
    a("If you are a violin teacher or an advanced player, this document is the")
    a("ask. It should take about twenty minutes. Write straight into the blank")
    a("fields; nothing here is precious.")
    a("")
    a(f"Source: `{name}`, {len(score.measures)} measures, {len(phrases)} phrases,")
    a("from a real scan of Wohlfahrt Op. 45 Book 1.")
    a("")
    a("## What Chordially claims, and what it does not")
    a("")
    a("**Claims:** that these numbers describe what each passage *demands*, read")
    a("from the printed notation, under a stated tempo, and that they are a")
    a("consistent ordering.")
    a("")
    a("**Does not claim:** that the scale is validated, that the category labels")
    a("match any syllabus, or that a 6.8 here would mean the same in other")
    a("repertoire. The rubric also cannot see bowing beyond what is printed,")
    a("fingering, string choice, shifts, your hand, or your level.")
    a("")
    a("The one external check available so far: Wohlfahrt printed these studies")
    a("in increasing order of difficulty, and the app agrees -- Etude 2 averages")
    a("4.0, Etude 3 averages 5.7. That is ordinal agreement with one editor on")
    a("one pair of studies, from 25 and 7 rated measures respectively. A real")
    a("signal, and a weak one.")
    a("")
    a("## What would actually change the code")
    a("")
    a("Disagreement is the useful outcome here. Three questions matter most, and")
    a("the last section says which constant each answer would move.")
    a("")
    a("1. **Is the spread right?** Etude 2 sits at 4.0 and Etude 3 at 5.7. Does")
    a("   that 1.7-point gap match the difference you feel between them?")
    a("2. **Are the cut points right?** The scale breaks at 2.0 / 4.0 / 6.0 / 8.0")
    a("   into Beginner-friendly, Advanced Beginner, Competent, Expert and")
    a("   Extremely hard. Would you put these etudes in those bands?")
    a("3. **What is under-weighted?** Which demand does the rubric most obviously")
    a("   miss or under-count on this page?")
    a("")
    a("Also worth marking as you go:")
    a("")
    a("- Do the phrase boundaries fall where a musical idea actually ends?")
    a("- Is a boundary marked low-confidence one you would also hesitate over?")
    a("- Any measure marked 'Needs review' that is plainly legible on the page?")
    a("")
    a("Boundary confidence is honest about thin evidence: etudes are often")
    a("continuous, with no rest or cadence to mark a phrase end, and a bare")
    a("barline is deliberately weak evidence.")
    a("")

    for p in phrases:
        d = phrase_ratings.get(p.id)
        rating = format_score(d.score if d else None)
        cat = category_for(d.score if d else None)
        peak = format_score(d.peak if d else None)
        first = score.measure(p.measure_ids[0])
        last = score.measure(p.measure_ids[-1])
        a(f"### {p.label} — measures {first.label}–{last.label}")
        a("")
        a(f"- Rating **{rating}** ({cat}), local peak {peak}")
        a(f"- Starts: {p.start_boundary.reason} _(confidence {p.start_boundary.confidence:.2f})_")
        a(f"- Ends: {p.end_boundary.reason} _(confidence {p.end_boundary.confidence:.2f})_")
        if p.has_practice_overlap:
            nxt = score.measure(p.practice_end.measure_id)
            a(f"- Practice range runs on into measure {nxt.label} so the join is rehearsed.")
        else:
            a("- No following note to borrow; this is the last phrase.")
        a("")
        a("| Measure | Rating | Category | Recognition |")
        a("|---|---|---|---|")
        for mid in p.measure_ids:
            m = score.measure(mid)
            md = measure_ratings.get(mid)
            s = md.score if md else None
            a(f"| {m.label} | {format_score(s)} | {category_for(s)} | {m.quality} |")
        a("")
        a("> **Your rating (0-10):** ______")
        a(">")
        a("> **What the app missed here:** _____________________________________")
        a(">")
        a("> **Boundary in the right place?** yes / no — if no, where: _________")
        a("")

    if analysis.errors:
        # Summarised, not dumped. The reader of this document is a violinist,
        # and twelve lines of HTTP 400 JSON with request IDs tells them nothing
        # they can act on -- while burying the one fact that matters, which is
        # that some measures were never read and are not a judgement about the
        # notation. The raw errors stay in the analysis JSON for debugging.
        provider = sum(1 for e in analysis.errors if "provider error" in e)
        mismatch = sum(1 for e in analysis.errors if "measures where the page shows" in e)
        unread = sum(1 for m in score.measures if m.quality == "not_attempted")
        unreadable = sum(1 for m in score.measures if m.quality == "unreadable")

        a("## Where recognition fell short")
        a("")
        if unreadable:
            a(
                f"- **{unreadable} measures were read and rejected.** Their note "
                "durations did not add up to the time signature, so they are left "
                "unrated rather than shown as a guess. If one of these is plainly "
                "legible to you, that is a recognition bug worth reporting."
            )
        if unread:
            a(
                f"- **{unread} measures were never read at all** because "
                f"{provider} transcription request(s) did not complete. This is "
                "not a judgement about the notation."
            )
        if mismatch:
            a(
                f"- **{mismatch} section(s) disagreed with the page** about how "
                "many measures they contained, and were left unrated rather than "
                "risk attaching notes to the wrong measure."
            )
        a("")
        a("Full provider errors are kept in the analysis JSON, not here.")
        a("")

    a("## Where your answers would land in the code")
    a("")
    a("So this is not a survey that goes nowhere:")
    a("")
    a("| If you said | What changes |")
    a("|---|---|")
    a(
        "| The gap between the etudes is too small | The curve in `_saturate`, "
        "`src/features/difficulty/rubric.py`, which compresses the top of the scale |"
    )
    a("| The gap is too large | The same curve, in the other direction |")
    a(
        "| A specific demand is under-counted | Its entry in `WEIGHTS`, "
        "`src/features/difficulty/rubric.py` |"
    )
    a(
        "| A demand is missing entirely | A new feature in `measure_features`, "
        "plus a weight for it |"
    )
    a(
        "| The category bands are wrong | `CATEGORIES` in "
        "`src/features/difficulty/colors.py` |"
    )
    a(
        "| A phrase boundary is in the wrong place | The evidence weights in "
        "`WEIGHT`, `src/features/segmentation/phrases.py` |"
    )
    a(
        "| A legible measure was marked unreadable | Recognition rather than the "
        "rubric: `src/server/recognition/` |"
    )
    a("")
    a(
        "Each of those constants is covered by tests that pin current behaviour, "
        "so a change made in response to this review will show exactly what else "
        "it moves."
    )
    a("")

    (OUT_DIR / "review-phrases.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
