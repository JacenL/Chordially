"""Does the rubric agree with an editor who graded this music by hand?

Chordially's 0.0-10.0 scale is its own invention. Nothing in this repository
validates it, and no violinist has reviewed it. But the fixture page happens to
carry an external reference: Wohlfahrt's Op. 45 studies are printed in
increasing order of difficulty, and this page contains Etude 2 and Etude 3. So
there is one thing that can be checked without asking anybody — whether the app
orders those two studies the same way Wohlfahrt did.

**What this establishes, precisely:** ordinal agreement with one editor, on one
pair of adjacent studies, from one page. Etude 3 contributes only 7 rated
measures against Etude 2's 25, because much of the second half of the page could
not be read. It is a real signal and a weak one.

**What it does not establish:** that 1.2 and 3.0 are the right numbers, that the
gap between them is the right size, that the category labels cut the scale in
the right places, or that any of this transfers to repertoire outside a
beginner's etude book. A passing test here is evidence, not validation.

The tests below the ordering ones check something weaker but still worth
pinning: that an absolute scale puts a beginner method page near the bottom of
itself, and that it is not quietly stretched to fill the ribbon.

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


def test_a_beginner_study_lands_in_the_beginner_region(bundle):
    """Where the rubric says this page sits, against the book it came from.

    Wohlfahrt Op. 45 Book 1 is a first-position beginner method. Both studies on
    this page are detache runs in first position at a walking tempo, and the
    only defensible place for them on a 0-10 scale whose top is concerto writing
    is the bottom two categories.

    Before C16 the same notation rated 3.2-5.1 -- "Advanced Beginner" through
    "Competent level" -- from seven separate counting errors, each fixed at its
    source in `tests/unit/test_rubric_20.py`. This test is the end-to-end
    consequence, measured on the real scan rather than on constructed notes.
    """
    retuned = retune(bundle, None)
    rated = [
        d.score
        for d in retuned.measure_difficulty.values()
        if d.score is not None
    ]
    assert rated, "the fixture must contribute rated measures"
    assert max(rated) < 4.0, (
        f"the hardest measure on a beginner method page rates {max(rated):.1f}, "
        "which is outside the beginner and advanced-beginner region"
    )
    assert mean(rated) < 2.5, f"page mean {mean(rated):.2f}"


def test_the_easier_study_stays_in_the_lowest_category(bundle):
    """Etude 2 is straight eighths in first position in C major."""
    first, _, _, _ = study_means(bundle, None)
    assert first < 2.0, f"Etude 2 mean {first:.2f} is above Beginner-friendly"


def test_ratings_do_not_stretch_to_fill_the_scale(bundle):
    """One piece must not be normalized against itself.

    An easy page is supposed to look easy. If the ribbon on this page ever
    spanned the whole scale, the number under it would have stopped meaning the
    same thing it means on another score -- which is the one property that lets
    two uploads be compared at all.
    """
    retuned = retune(bundle, None)
    rated = [d.score for d in retuned.measure_difficulty.values() if d.score is not None]
    assert max(rated) - min(rated) < 5.0, (
        "this page spans more of the scale than a single beginner method page "
        "should, which is what per-piece normalization would look like"
    )


def test_a_faster_tempo_moves_the_page_up_the_scale(bundle):
    """The scale is absolute, but the tempo is an input to it.

    Same notes, a real tempo a player might choose: the ratings have to move,
    because the rubric measures demand per second and says so.
    """
    slow = study_means(bundle, 60.0)[0]
    fast = study_means(bundle, 160.0)[0]
    assert fast > slow + 0.5, (slow, fast)


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
