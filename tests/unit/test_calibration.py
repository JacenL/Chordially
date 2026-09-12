"""Does the rubric agree with an editor who graded this music by hand?

PracticeMap's 0.0-10.0 scale is its own invention. Nothing in this repository
validates it, and no violinist has reviewed it. But the fixture page happens to
carry an external reference: Wohlfahrt's Op. 45 studies are printed in
increasing order of difficulty, and this page contains Etude 2 and Etude 3. So
there is one thing that can be checked without asking anybody — whether the app
orders those two studies the same way Wohlfahrt did.

**What this establishes, precisely:** ordinal agreement with one editor, on one
pair of adjacent studies, from one page. Etude 3 contributes only 7 rated
measures against Etude 2's 25, because much of the second half of the page could
not be read. It is a real signal and a weak one.

**What it does not establish:** that 4.0 and 5.7 are the right numbers, that the
gap between them is the right size, that the category labels cut the scale in
the right places, or that any of this transfers to repertoire outside a
beginner's etude book. A passing test here is evidence, not validation.

If this test ever fails, the rubric has started disagreeing with the one external
reference available to it, and that is worth knowing before showing anyone.
"""

from __future__ import annotations

from statistics import mean

import pytest

from src.schemas.analysis import AnalysisBundle
from src.server.analysis.example import EXAMPLE_PATH
from src.server.analysis.recompute import retune

# Tempos to check across. The ordering must not be an artifact of the assumed 90.
TEMPOS = [60.0, 90.0, 160.0]


@pytest.fixture(scope="module")
def bundle() -> AnalysisBundle:
    return AnalysisBundle.load_path(EXAMPLE_PATH)


def etude_boundary(bundle: AnalysisBundle) -> int:
    """The ordinal where the second study starts, read from the page.

    Located by the printed key and meter change rather than a hard-coded measure
    number, so this test keeps meaning what it says if segmentation or
    recognition changes. The page moves from 4/4 in C to 2/4 in G.
    """
    ordered = bundle.score.measures_in_order()
    first = (ordered[0].beats, ordered[0].beat_value, ordered[0].key_fifths)
    for measure in ordered:
        signature = (measure.beats, measure.beat_value, measure.key_fifths)
        if signature != first and all(v is not None for v in signature):
            return measure.ordinal
    raise AssertionError("no key or meter change found; the fixture should contain one")


def study_means(bundle: AnalysisBundle, tempo: float | None) -> tuple[float, float, int, int]:
    """(mean of study 1, mean of study 2, n1, n2) at the given tempo."""
    retuned = retune(bundle, tempo)
    split = etude_boundary(retuned)

    first: list[float] = []
    second: list[float] = []
    for measure in retuned.score.measures_in_order():
        rating = retuned.measure_difficulty.get(measure.id)
        if rating is None or rating.score is None:
            continue
        (first if measure.ordinal < split else second).append(rating.score)

    assert first and second, "both studies must contribute rated measures"
    return mean(first), mean(second), len(first), len(second)


def test_the_page_contains_two_studies(bundle):
    split = etude_boundary(retune(bundle, None))
    assert 0 < split < len(bundle.score.measures)


@pytest.mark.parametrize("tempo", TEMPOS)
def test_the_later_study_is_not_rated_easier(bundle, tempo):
    """Wohlfahrt printed these in increasing order of difficulty."""
    first, second, _, _ = study_means(bundle, tempo)
    assert second >= first, (
        f"at {tempo:.0f} BPM the app rates Etude 3 ({second:.2f}) below Etude 2 "
        f"({first:.2f}), reversing the order the editor printed them in"
    )


def test_the_ordering_does_not_depend_on_the_tempo(bundle):
    """A result that only holds at one tempo would be an artifact of that tempo."""
    for tempo in TEMPOS:
        first, second, _, _ = study_means(bundle, tempo)
        assert second >= first, tempo


def test_the_gap_is_large_enough_to_be_a_signal(bundle):
    """Two studies an editor separated should not come out indistinguishable.

    A quarter of a point is a deliberately low bar. The claim is only that the
    rubric can tell these apart at all, not that the size of the gap is right.
    """
    first, second, _, _ = study_means(bundle, None)
    assert second - first >= 0.25


def test_the_sample_is_reported_honestly(bundle):
    """The evidence is thin on one side, and the numbers should show it.

    This asserts the imbalance rather than hiding it: if the second study ever
    gains enough rated measures for the comparison to be strong, this test fails
    and the honest caveat in docs/demo.md should be revised upward.
    """
    _, _, n_first, n_second = study_means(bundle, None)
    assert n_second < n_first, (
        "the second study now has as many rated measures as the first; the "
        "'small sample' caveat in docs/demo.md and this test's docstring are "
        "out of date and should be strengthened"
    )
