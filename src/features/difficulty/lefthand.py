"""Left-hand demands estimated from pitch alone, and labelled as estimates.

The notation does not print where a note is played. CLAUDE.md is explicit that
Chordially must not *assert* a shift, a string or a fingering the page does not
establish, and the rubric honours that: nothing here is reported as what the
player does. What it reports is what the pitches *require at minimum* under one
disclosed model -- the lowest workable position -- which is the reading a
teacher grading a piece for a syllabus uses too. A passage that a virtuoso
would keep on one string in a high position is counted here as crossings in a
low position; that alternative is also demanding, so the estimate is a floor on
the work, not a claim about the fingering.

Three quantities come out of the model, and every one of them names a demand
that graded violin syllabi grade by (see docs/music-pedagogy.md, "Difficulty
rubric anchors"):

* **Likely string** -- the highest open string at or below the pitch -- and
  from it the string crossings between consecutive notes. Fluency in string
  crossing is what separates a level 3 study from a level 2 one in the ASTA
  descriptions, and until now the rubric could not see it at all.
* **Minimum position**, from the pitch a fourth finger can reach in each
  position on the E string, and from it the position changes between
  consecutive notes. "Some shifting to third position" and "shifting through
  fifth position" are how the ASTACAP levels describe themselves.
* **Double-stop hardness**, from the interval and whether an open string is
  involved. A fingered third is a different problem from a melody over an open
  D, and every double-stop method treats them as different problems.

Fingering systems that solve this properly (Viterbi over string, finger and
position with costs for shifts and crossings) exist; this is deliberately the
cheap monotone version, because "light processing" is a constraint of the
product and because a rating should be explainable in a sentence.
"""

from __future__ import annotations

from src.schemas.music import NoteEvent

# Open strings as MIDI numbers: G3, D4, A4, E5.
OPEN_STRINGS: tuple[int, ...] = (55, 62, 69, 76)
STRING_NAMES: tuple[str, ...] = ("G", "D", "A", "E")

# Where first position ends: the fourth finger on the E string, B5.
FIRST_POSITION_TOP = 83

# First-finger pitch offsets above the open E for positions 1, 2, 3, ...,
# following the natural-note ladder F G A B C D E F G A B C D E. Positions are
# diatonic, not chromatic, which is why this is a table and not a multiplier.
_FIRST_FINGER_OFFSETS: tuple[int, ...] = (1, 3, 5, 7, 8, 10, 12, 13, 15, 17, 19, 20, 22, 24)

# How far above the first finger the fourth finger reaches without an
# extension, in semitones. In first position on the E string the first finger
# sits on F5 and the fourth on B5: six semitones, the whole-tone hand frame.
FOURTH_FINGER_REACH = 6


def likely_string(midi: int) -> int:
    """Index (0=G ... 3=E) of the string a pitch sits on in the lowest position.

    The highest open string at or below the pitch. A pitch below the open G is
    a recognition error upstream and is placed on the G string rather than
    raising here; the range gate in `schemas.music` is where that is rejected.
    """
    index = 0
    for candidate, open_midi in enumerate(OPEN_STRINGS):
        if midi >= open_midi:
            index = candidate
    return index


def minimum_position(midi: int) -> int:
    """The lowest position whose fourth finger reaches this pitch. 1 up to B5."""
    if midi <= FIRST_POSITION_TOP:
        return 1
    for position, offset in enumerate(_FIRST_FINGER_OFFSETS, start=1):
        if OPEN_STRINGS[3] + offset + FOURTH_FINGER_REACH >= midi:
            return position
    return len(_FIRST_FINGER_OFFSETS) + 1


def string_crossings(midis: list[int]) -> tuple[int, int]:
    """(crossings, skips) between consecutive pitches under the string model.

    A skip is a crossing over an intervening string -- G to A, D to E -- which
    costs more than a neighbour crossing because the bow has to clear a string
    it does not play and the arm level changes by two steps.
    """
    crossings = skips = 0
    for a, b in zip(midis, midis[1:]):
        distance = abs(likely_string(a) - likely_string(b))
        if distance:
            crossings += 1
        if distance >= 2:
            skips += 1
    return crossings, skips


def reachable(midi: int, position: int) -> bool:
    """Whether a pitch lies under the hand in this position on some string.

    In position p the first finger sits `_FIRST_FINGER_OFFSETS[p-1]` semitones
    above each open string and the fourth finger `FOURTH_FINGER_REACH` above
    that. Open strings are reachable from anywhere. Third position, for
    instance, covers C4 to D6 without a gap across the four strings, which is
    why a descending scale from D6 needs no shift until it falls below C4.
    """
    if midi in OPEN_STRINGS:
        return True
    if position < 1 or position > len(_FIRST_FINGER_OFFSETS):
        return False
    offset = _FIRST_FINGER_OFFSETS[position - 1]
    return any(
        open_midi + offset <= midi <= open_midi + offset + FOURTH_FINGER_REACH
        for open_midi in OPEN_STRINGS
    )


def position_changes(midis: list[int]) -> tuple[int, int]:
    """(relocations, total distance in positions) for a lazy hand.

    The hand starts where the first note needs it and stays put while the
    notes remain under it. When a note is out of reach it moves once, to the
    lowest position that reaches the highest note of the unreachable run
    ahead -- the way a player shifts once for a figure rather than creeping
    up a semitone at a time. A line that climbs from first to third position
    and comes back therefore counts two relocations, not four rungs.

    Counted only from pitch: a line that stays within one position -- however
    much it leaps -- shows none here, because leaps are a separate feature.
    Nothing asserts which shift the player takes; only that the pitches
    cannot all be reached from one place.
    """
    if len(midis) < 2:
        return 0, 0
    position = minimum_position(midis[0])
    changes = distance = 0
    index = 1
    while index < len(midis):
        if reachable(midis[index], position):
            index += 1
            continue
        run_end = index
        while run_end < len(midis) and not reachable(midis[run_end], position):
            run_end += 1
        target = minimum_position(max(midis[index:run_end]))
        if target != position:
            changes += 1
            distance += abs(target - position)
            position = target
        index += 1
    return changes, distance


# Hardness of a two-note interval, in semitones, when both notes are fingered.
# Ordered by the consensus of double-stop methods: sixths are the friendly
# interval, thirds and octaves demand a fixed frame and exact intonation,
# fifths need one finger across two strings, tenths and unisons stretch or
# cramp the hand.
_FINGERED_INTERVAL_HARDNESS: dict[int, float] = {
    0: 0.9,   # unison
    1: 0.9,
    2: 0.85,  # seconds
    3: 0.85,  # minor third
    4: 0.85,  # major third
    5: 0.7,   # fourth
    6: 0.75,  # tritone
    7: 0.8,   # fifth
    8: 0.6,   # minor sixth
    9: 0.6,   # major sixth
    10: 0.7,  # sevenths
    11: 0.7,
    12: 0.85,  # octave
    13: 0.8,
    14: 0.8,   # ninths
    15: 1.0,   # tenths
    16: 1.0,
}
_OPEN_STRING_DOUBLE_STOP = 0.35
_TRIPLE_STOP_EXTRA = 0.1
_QUADRUPLE_STOP_EXTRA = 0.2


def double_stop_hardness(event: NoteEvent) -> float:
    """0 for a single note; 0-1 for how demanding this chord is to place.

    A fingered note over an open string is the double stop a second-year
    student plays; a fingered tenth is not. Chords of three and four notes add
    to the hardness of their widest fingered pair, because they are struck as
    a broken pair and demand a hand frame for every finger at once.
    """
    midis = event.all_midis
    if len(midis) < 2:
        return 0.0

    fingered = [m for m in midis if m not in OPEN_STRINGS]
    if len(midis) == 2 and len(fingered) <= 1:
        return _OPEN_STRING_DOUBLE_STOP

    pairs = list(zip(midis, midis[1:]))
    hardness = 0.0
    for low, high in pairs:
        if low in OPEN_STRINGS or high in OPEN_STRINGS:
            hardness = max(hardness, _OPEN_STRING_DOUBLE_STOP)
            continue
        interval = high - low
        hardness = max(
            hardness, _FINGERED_INTERVAL_HARDNESS.get(interval, 0.9 if interval > 16 else 0.85)
        )
    if len(midis) == 3:
        hardness += _TRIPLE_STOP_EXTRA
    elif len(midis) >= 4:
        hardness += _QUADRUPLE_STOP_EXTRA
    return min(1.0, hardness)


def describe_interval(low: int, high: int) -> str:
    """A musician's name for a double-stop interval, for the sidebar."""
    names = {
        0: "unison", 1: "minor second", 2: "major second", 3: "minor third",
        4: "major third", 5: "fourth", 6: "tritone", 7: "fifth", 8: "minor sixth",
        9: "major sixth", 10: "minor seventh", 11: "major seventh", 12: "octave",
        13: "minor ninth", 14: "major ninth", 15: "minor tenth", 16: "major tenth",
    }
    return names.get(high - low, f"{high - low} semitones")
