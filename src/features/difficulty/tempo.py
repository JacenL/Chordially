"""Tempo words, read as an assumed beat rate when no metronome mark is printed.

The rubric measures demand per second, so the tempo it assumes decides every
number on the page. Before this module a Mozart *Presto* with no metronome mark
was rated at the 90 BPM fallback -- about half its real speed -- and came out
"Beginner-friendly" in 138 of 145 measures. The word was on the page the whole
time.

A tempo word is evidence, not a measurement. Metronome conventions for the
Italian terms have varied by a wide margin across two centuries of editions, so
the values here sit in the lower-middle of the commonly published ranges rather
than at their top: a rating should not be inflated by an aggressive reading of
"Allegro". Whatever is chosen is disclosed as an assumption and stays
retunable, exactly as the fixed fallback always was.

The table is deliberately short and matched longest-phrase-first, so "Allegro
moderato" is not read as "Allegro". Modifiers that do not name a tempo of their
own ("ma non troppo", "assai", "molto") are ignored rather than guessed at.
"""

from __future__ import annotations

import dataclasses
import re

# Beats per minute, in the notated beat, for the tempo words most often printed
# at the head of a movement. Lower-middle of the customary published ranges.
TEMPO_WORDS: dict[str, float] = {
    # Italian, slowest to fastest
    "grave": 40.0,
    "largo": 50.0,
    "lento": 55.0,
    "larghetto": 60.0,
    "adagio": 70.0,
    "adagietto": 75.0,
    "andante": 84.0,
    "andantino": 90.0,
    "andante moderato": 96.0,
    "moderato": 108.0,
    "allegretto": 116.0,
    "allegro moderato": 120.0,
    "allegro": 132.0,
    "allegro assai": 144.0,
    "allegro vivace": 150.0,
    "vivace": 156.0,
    "vivo": 160.0,
    "presto": 172.0,
    "prestissimo": 200.0,
    # German and French, as printed in the repertoire they come from
    "langsam": 60.0,
    "mässig": 108.0,
    "maessig": 108.0,
    "bewegt": 120.0,
    "lebhaft": 140.0,
    "schnell": 150.0,
    "sehr schnell": 170.0,
    "lent": 55.0,
    "modéré": 108.0,
    "modere": 108.0,
    "vif": 150.0,
    "vite": 160.0,
    # English
    "slowly": 60.0,
    "slow": 60.0,
    "moderately": 108.0,
    "lively": 140.0,
    "fast": 144.0,
    "quickly": 150.0,
}

# Longest phrases first, so a two-word marking wins over its first word.
_ORDERED_WORDS = sorted(TEMPO_WORDS, key=len, reverse=True)
_WORD_PATTERNS = [
    (word, re.compile(r"(?<![a-zà-ü])" + re.escape(word) + r"(?![a-zà-ü])"))
    for word in _ORDERED_WORDS
]


@dataclasses.dataclass(frozen=True)
class TempoReading:
    """A tempo the file establishes, with how firmly it does so.

    `printed` is True only for a metronome number -- a `<per-minute>` mark or a
    MusicXML `<sound tempo>` value. A tempo inferred from a word is not printed
    in that sense: it is an assumption the page invites, and it is disclosed
    and retunable as one.
    """

    bpm: float
    printed: bool
    evidence: str


def tempo_from_words(text: str | None) -> tuple[float, str] | None:
    """The tempo a marking's words imply, as (bpm, matched word), or None.

    Case-insensitive, and tolerant of the punctuation and typography editions
    add: "Allegro." "ALLEGRO" and "Allegro (ma non troppo)" all read as
    "allegro".
    """
    if not text:
        return None
    lowered = " ".join(str(text).lower().split())
    for word, pattern in _WORD_PATTERNS:
        if pattern.search(lowered):
            return TEMPO_WORDS[word], word
    return None
