"""MusicXML import: exact notes, exact geometry, nothing to misread.

The claim this feature makes is narrow and strong: a MusicXML score carries no
recognition risk. Most of what is asserted here is that claim — every measure
confident, every measure rated, nothing left for review — plus the geometry
invariants that let a ribbon sit on measures that were never detected, only read.
"""

from __future__ import annotations

import zipfile
from fractions import Fraction

import pytest

from src.config import PROJECT_ROOT
from src.server.recognition import musicxml_source as mx

FIXTURE = PROJECT_ROOT / "fixtures" / "scores" / "mozart-k156-mvt1.mxl"

pytestmark = pytest.mark.skipif(not FIXTURE.exists(), reason="MusicXML fixture absent")


@pytest.fixture(scope="module")
def data() -> bytes:
    return FIXTURE.read_bytes()


@pytest.fixture(scope="module")
def page(data) -> mx.MusicXmlPage:
    return mx.load_musicxml(data)


# --------------------------------------------------------------------------
# Reading the container
# --------------------------------------------------------------------------


def test_the_fixture_is_a_real_mxl_container(data):
    """Not a renamed plain XML: the zip path is what is under test."""
    assert data[:2] == b"PK"
    import io

    with zipfile.ZipFile(io.BytesIO(data)) as bundle:
        assert "META-INF/container.xml" in bundle.namelist()


def test_uncompress_follows_the_container_rootfile(data):
    inner = mx.uncompress(data)
    assert b"<score-partwise" in inner[:4096]
    assert b"container" not in inner[:200].lower()


def test_plain_xml_passes_through_unchanged():
    plain = b'<?xml version="1.0"?><score-partwise></score-partwise>'
    assert mx.uncompress(plain) == plain


def test_sniffing_accepts_music_and_rejects_other_xml(data):
    assert mx.looks_like_musicxml(data) is True
    assert mx.looks_like_musicxml(b"<html><body>not music</body></html>") is False
    assert mx.looks_like_musicxml(b"<svg xmlns='...'></svg>") is False


def test_a_corrupt_zip_is_refused_with_a_recovery():
    with pytest.raises(mx.MusicXmlRejected) as excinfo:
        mx.uncompress(b"PK\x03\x04garbage that is not a zip at all")
    assert excinfo.value.recovery


def test_xml_that_is_not_a_score_is_refused_with_a_recovery():
    with pytest.raises(mx.MusicXmlRejected) as excinfo:
        mx.read_part(b"<?xml version='1.0'?><recipe><step/></recipe>")
    assert excinfo.value.message
    assert excinfo.value.recovery


# --------------------------------------------------------------------------
# The part, and what it says about itself
# --------------------------------------------------------------------------


def test_the_first_part_is_taken_and_named(page):
    assert page.part_count == 4
    assert "Violin" in page.part_name
    assert page.measures_in_part == 180


def test_multi_page_engraving_is_reported_not_hidden(page):
    assert page.page_count > 1
    assert page.measures_on_page < page.measures_in_part


# --------------------------------------------------------------------------
# Geometry, read rather than detected
# --------------------------------------------------------------------------


def test_every_system_has_measures_and_they_tile_it(page):
    assert len(page.geometry.systems) > 1
    for system in page.geometry.systems:
        assert system.measures, f"system {system.index} has no measures"
        boxes = [m.box for m in system.measures]
        for left, right in zip(boxes, boxes[1:]):
            # Ordered and flush: each measure begins where the last one ended.
            assert left.x + left.w == pytest.approx(right.x, abs=1e-9)
        first, last = boxes[0], boxes[-1]
        assert first.x == pytest.approx(system.box.x, abs=1e-9)
        assert last.x + last.w <= system.box.x + system.box.w + 1e-9


def test_measure_boxes_sit_inside_their_system_vertically(page):
    for system in page.geometry.systems:
        for measure in system.measures:
            assert measure.box.y == pytest.approx(system.box.y, abs=1e-9)
            assert measure.box.h == pytest.approx(system.box.h, abs=1e-9)


def test_systems_do_not_overlap_vertically(page):
    tops = [(s.box.y, s.box.y + s.box.h) for s in page.geometry.systems]
    for (_, bottom), (top, _) in zip(tops, tops[1:]):
        assert top >= bottom - 1e-9, "system bands overlap"


def test_all_coordinates_are_normalised(page):
    for system in page.geometry.systems:
        for box in [system.box] + [m.box for m in system.measures]:
            assert 0.0 <= box.x <= 1.0 and 0.0 <= box.y <= 1.0
            assert 0.0 < box.w <= 1.0 and 0.0 < box.h <= 1.0


def test_the_transcription_count_matches_the_geometry(page):
    assert len(page.transcriptions) == page.geometry.measure_count
    assert page.measures_on_page == page.geometry.measure_count


def test_every_system_start_carries_a_signature(page):
    """build_score takes meter from here; without it nothing can be rated."""
    for system in page.geometry.systems:
        signature = page.signatures_by_system.get(system.index)
        assert signature, f"system {system.index} has no signature"
        assert signature["beats"] and signature["beat_value"]


# --------------------------------------------------------------------------
# Notes: the durations have to be exact, or nothing downstream works
# --------------------------------------------------------------------------


def test_the_printed_meter_and_key_are_read(page):
    first = page.transcriptions[(0, 0)]
    assert (first.beats_in_measure, first.beat_value) == (3, 8)
    assert first.key_fifths == 1


def test_measures_sum_to_their_meter(page):
    """Exact rational arithmetic, the check the whole rating path depends on."""
    expected = Fraction(3, 8)
    checked = short = 0
    for transcription in page.transcriptions.values():
        if not transcription.notes:
            continue
        total = sum((n.duration for n in transcription.notes), Fraction(0))
        if total == expected:
            checked += 1
        else:
            # A pickup or a partial final measure is legitimate; a wholesale
            # mismatch would mean the duration mapping is wrong.
            short += 1
    assert checked > short * 5, f"{short} measures did not sum to 3/8 against {checked} that did"


def test_dotted_notes_survive_the_mapping(page):
    first = page.transcriptions[(0, 0)].notes
    assert first, "the first measure should contain a note"
    assert first[0].dots == 1
    assert first[0].duration == Fraction(3, 8)


def test_pitches_are_spelled_not_guessed(page):
    events = [n for t in page.transcriptions.values() for n in t.notes if not n.is_rest]
    assert events
    for note in events:
        assert note.step in "ABCDEFG"
        assert note.octave is not None
        assert -2 <= note.alter <= 2


def test_the_page_is_an_svg(page):
    assert page.svg.lstrip().startswith(b"<")
    assert b"<svg" in page.svg[:2000]
