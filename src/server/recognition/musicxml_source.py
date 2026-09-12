"""Read a MusicXML file into the same shapes recognition produces.

A MusicXML upload has no scan to annotate, which is the whole design problem:
the viewer positions every overlay against a page image. Verovio solves it by
engraving the file, and its SVG turns out to be the better page in two ways --
the browser renders it natively at any zoom without resampling, and the measure
geometry can be *read* out of it rather than detected, because Verovio draws
staff lines and barlines as plain two-point paths.

So this module produces exactly what `build_score` already consumes:

    PageGeometry                                  from the SVG, exact
    dict[(system, measure)] -> MeasureTranscription   from music21, exact

and every stage downstream -- rating, segmentation, trouble spots, the ribbon,
practice instruction, phrase editing -- runs unchanged.

What that buys, and it is the point of the feature: a MusicXML score carries no
recognition risk at all. There is nothing to misread, no duration that fails to
add up, no measure left unrated because a crop was ambiguous, and no provider
call. Next to a scan where a fifth of the measures are hatched, the difference
is the honest argument that this app is not an OCR demo.

Three routes to a page were tried before this one. Rasterising the SVG with
PyMuPDF renders a blank page -- its SVG support does not handle Verovio's
`<use>`/defs output. Rasterising through headless Chromium works but would make
a browser a runtime dependency. Reading the geometry directly is both cheaper
and more exact than either.
"""

from __future__ import annotations

import dataclasses
import io
import re
import threading
import xml.etree.ElementTree as ET
import zipfile
from fractions import Fraction

from src.schemas.music import NOTE_VALUE_FRACTIONS, MeasureTranscription, NoteEvent
from src.server.recognition.cv_geometry import (
    BOX_MARGIN_STAVESPACE,
    Box,
    DetectedMeasure,
    DetectedSystem,
    PageGeometry,
)

# Engraving options. A fixed page rather than Verovio's default single strip, so
# the result is a page a musician recognises and the existing per-system ribbon
# has systems to sit under.
PAGE_OPTIONS = {
    "pageWidth": 2100,
    "pageHeight": 2970,
    "adjustPageHeight": False,
    "scale": 40,
    "footer": "none",
    "header": "none",
    "breaks": "auto",
}

# The nominal render resolution recorded on the Page. Nothing rasterises at it --
# the SVG is resolution-independent -- but the field is part of the contract and
# a plausible value keeps any consumer of it honest.
NOMINAL_DPI = 200

# A two-point SVG path, which is how Verovio draws staff lines and barlines.
_LINE = re.compile(r"M\s*(-?[\d.]+)\s+(-?[\d.]+)\s+L\s*(-?[\d.]+)\s+(-?[\d.]+)")

SUPPORTED_EXTENSIONS = (".musicxml", ".xml", ".mxl")


class MusicXmlRejected(ValueError):
    """The file is not usable as a score, with what to do about it."""

    def __init__(self, message: str, recovery: str) -> None:
        super().__init__(message)
        self.message = message
        self.recovery = recovery


@dataclasses.dataclass
class MusicXmlPage:
    geometry: PageGeometry
    transcriptions: dict[tuple[int, int], MeasureTranscription]
    svg: bytes
    title: str
    part_name: str
    part_count: int
    page_count: int
    measures_in_part: int
    measures_on_page: int
    # Meter and key in force at each system's first measure. `build_score`
    # treats this as the authority on meter -- a per-measure transcription is
    # not trusted for it, because on a scan a mid-staff crop cannot see a
    # signature. From MusicXML the signature is known exactly, so this is where
    # it has to be supplied or every measure ends up unrated.
    signatures_by_system: dict[int, dict[str, int | None]] = dataclasses.field(
        default_factory=dict
    )


# --------------------------------------------------------------------------
# Reading the file
# --------------------------------------------------------------------------


def uncompress(data: bytes) -> bytes:
    """Return the MusicXML inside a .mxl container, or the data unchanged.

    A .mxl is a zip whose META-INF/container.xml names the real score file.
    Guessing the first entry instead would pick the container itself often
    enough to matter.
    """
    if not data[:2] == b"PK":
        return data
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as bundle:
            root_path = None
            if "META-INF/container.xml" in bundle.namelist():
                container = ET.fromstring(bundle.read("META-INF/container.xml"))
                element = container.find(".//{*}rootfile")
                if element is not None:
                    root_path = element.get("full-path")
            if root_path is None:
                candidates = [n for n in bundle.namelist() if not n.startswith("META-INF")]
                if not candidates:
                    raise MusicXmlRejected(
                        "That compressed MusicXML file contains no score.",
                        "Re-export it from your notation software and try again.",
                    )
                root_path = candidates[0]
            return bundle.read(root_path)
    except zipfile.BadZipFile as exc:
        raise MusicXmlRejected(
            "That file looks compressed but could not be opened.",
            "Re-export it as uncompressed MusicXML (.musicxml) and try again.",
        ) from exc


def looks_like_musicxml(data: bytes) -> bool:
    """Cheap sniff, so a misnamed file fails with a sentence not a stack trace."""
    head = uncompress(data)[:4096].lower()
    return b"<score-partwise" in head or b"<score-timewise" in head


# --------------------------------------------------------------------------
# Notes, from music21
# --------------------------------------------------------------------------

_VALUE_BY_TYPE = {
    "whole": "whole",
    "half": "half",
    "quarter": "quarter",
    "eighth": "eighth",
    "16th": "16th",
    "32nd": "32nd",
    "64th": "64th",
}

_ARTICULATION = {
    "staccato": "staccato",
    "accent": "accent",
    "tenuto": "tenuto",
}


def _note_event(element) -> NoteEvent | None:
    """One music21 note, rest or chord as a NoteEvent, or None if unusable.

    A chord becomes its highest note. That is a deliberate simplification with a
    reason: this is a solo-violin tool, the rubric counts double stops as a
    feature of the measure rather than of a voice, and the top note is the one a
    violinist reads the line from. The chord is still visible on the engraved
    page, so nothing is hidden -- only the event list is flattened.
    """
    duration = element.duration
    if duration.type not in _VALUE_BY_TYPE or duration.quarterLength <= 0:
        return None

    tuplet_actual = tuplet_normal = None
    if duration.tuplets:
        tuplet = duration.tuplets[0]
        tuplet_actual, tuplet_normal = tuplet.numberNotesActual, tuplet.numberNotesNormal

    if element.isRest:
        return NoteEvent(
            is_rest=True,
            value=_VALUE_BY_TYPE[duration.type],
            dots=min(2, duration.dots),
            tuplet_actual=tuplet_actual,
            tuplet_normal=tuplet_normal,
        )

    pitch = max(element.pitches, key=lambda p: p.ps) if element.isChord else element.pitch
    tie = "none"
    if element.tie is not None:
        tie = {"start": "start", "stop": "stop", "continue": "continue"}.get(
            element.tie.type, "none"
        )

    articulation = "none"
    for mark in element.articulations:
        name = type(mark).__name__.lower()
        if name in _ARTICULATION:
            articulation = _ARTICULATION[name]
            break

    alter = int(pitch.alter) if pitch.alter else 0
    return NoteEvent(
        is_rest=False,
        step=pitch.step,
        alter=max(-2, min(2, alter)),
        octave=pitch.octave if pitch.octave is not None else 4,
        value=_VALUE_BY_TYPE[duration.type],
        dots=min(2, duration.dots),
        tuplet_actual=tuplet_actual,
        tuplet_normal=tuplet_normal,
        tie=tie,
        articulation=articulation,
    )


def read_part(data: bytes):
    """Parse the file and return (part, title, part_name, part_count)."""
    from music21 import converter

    try:
        score = converter.parse(uncompress(data))
    except MusicXmlRejected:
        raise
    except Exception as exc:  # noqa: BLE001 - reported to the user
        raise MusicXmlRejected(
            "That file could not be read as MusicXML.",
            "Check it opens in your notation software, then re-export it.",
        ) from exc

    parts = list(score.parts) if hasattr(score, "parts") else []
    if not parts:
        raise MusicXmlRejected(
            "That MusicXML file contains no parts.",
            "Export a score with at least one instrument and try again.",
        )

    # The first part. A solo-violin tool reading a quartet should say which line
    # it took rather than silently analysing a cello part.
    part = parts[0]
    if not list(part.getElementsByClass("Measure")):
        raise MusicXmlRejected(
            "The first part of that file contains no measures.",
            "Check the export includes the music, not just a title page.",
        )

    metadata = score.metadata
    title = (metadata.title if metadata and metadata.title else "") or (
        metadata.composer if metadata and metadata.composer else ""
    )
    return part, title, (part.partName or "Part 1"), len(parts)


def transcribe_part(part, measure_limit: int) -> list[MeasureTranscription]:
    """Every measure of the part as a MeasureTranscription, in playing order."""
    from music21 import key as m21key
    from music21 import meter as m21meter

    out: list[MeasureTranscription] = []
    beats = beat_value = None
    fifths = None

    for measure in list(part.getElementsByClass("Measure"))[:measure_limit]:
        for signature in measure.getElementsByClass(m21meter.TimeSignature):
            beats, beat_value = signature.numerator, signature.denominator
        for signature in measure.getElementsByClass(m21key.KeySignature):
            fifths = signature.sharps

        events: list[NoteEvent] = []
        for element in measure.recurse().notesAndRests:
            event = _note_event(element)
            if event is not None:
                events.append(event)

        out.append(
            MeasureTranscription(
                contains_music=bool(events),
                beats_in_measure=beats,
                beat_value=beat_value,
                key_fifths=fifths,
                notes=events,
            )
        )
    return out


# --------------------------------------------------------------------------
# Geometry, from the engraved SVG
# --------------------------------------------------------------------------


def _class_of(element) -> str:
    return element.get("class") or ""


def _lines(group) -> list[tuple[float, float, float, float]]:
    found = []
    for child in group.iter():
        if child.tag.endswith("path"):
            match = _LINE.match((child.get("d") or "").strip())
            if match:
                found.append(tuple(float(v) for v in match.groups()))
    return found


def _view_box(root) -> tuple[float, float]:
    for element in root.iter():
        box = element.get("viewBox")
        if box:
            parts = box.split()
            if len(parts) == 4:
                return float(parts[2]), float(parts[3])
    raise MusicXmlRejected(
        "The engraved page had no coordinate system.",
        "This is a fault in PracticeMap rather than in your file.",
    )


def geometry_from_svg(svg: str) -> PageGeometry:
    """Exact systems and measures, read from what Verovio drew.

    Staff lines and barlines are two-point paths, so a measure's box is arithmetic
    rather than detection: its left edge is the previous barline, its right edge
    its own. Vertical extent follows the same rule `cv_geometry` uses on scans --
    staff plus margin, clamped halfway to the neighbouring system -- so a box
    means the same thing whichever input produced it.
    """
    root = ET.fromstring(svg)
    width, height = _view_box(root)

    raw_systems = []
    for system in (e for e in root.iter() if _class_of(e) == "system"):
        staff_groups = [e for e in system.iter() if _class_of(e) == "staff"]
        if not staff_groups:
            continue
        horizontals = [
            line for group in staff_groups for line in _lines(group) if line[1] == line[3]
        ]
        if len(horizontals) < 2:
            continue
        staff_top = min(line[1] for line in horizontals)
        staff_bottom = max(line[1] for line in horizontals)
        staff_left = min(min(line[0], line[2]) for line in horizontals)
        staff_right = max(max(line[0], line[2]) for line in horizontals)
        spacing = (staff_bottom - staff_top) / 4.0 if staff_bottom > staff_top else 8.0

        measures = []
        for measure in (e for e in system.iter() if _class_of(e) == "measure"):
            verticals = [
                line
                for group in measure.iter()
                if _class_of(group) == "barLine"
                for line in _lines(group)
                if line[0] == line[2]
            ]
            right = max((line[0] for line in verticals), default=None)
            measures.append(right)
        raw_systems.append(
            (staff_top, staff_bottom, staff_left, staff_right, spacing, measures)
        )

    if not raw_systems:
        raise MusicXmlRejected(
            "The engraved page contained no staves.",
            "Check the file contains notes rather than only a title or layout.",
        )

    systems: list[DetectedSystem] = []
    for index, (top, bottom, left, right, spacing, bar_rights) in enumerate(raw_systems):
        previous_bottom = raw_systems[index - 1][1] if index > 0 else None
        next_top = raw_systems[index + 1][0] if index + 1 < len(raw_systems) else None
        want = spacing * BOX_MARGIN_STAVESPACE
        top_limit = (top + previous_bottom) / 2 if previous_bottom is not None else 0.0
        bottom_limit = (bottom + next_top) / 2 if next_top is not None else height
        box_top = max(0.0, top_limit, top - want)
        box_bottom = min(height, bottom_limit, bottom + want)

        detected: list[DetectedMeasure] = []
        cursor = left
        for measure_index, bar_right in enumerate(bar_rights):
            edge = bar_right if bar_right is not None else right
            if edge <= cursor:
                continue
            detected.append(
                DetectedMeasure(
                    system_index=index,
                    index_in_system=len(detected),
                    box=Box(
                        x=cursor / width,
                        y=box_top / height,
                        w=(edge - cursor) / width,
                        h=(box_bottom - box_top) / height,
                    ),
                )
            )
            cursor = edge

        systems.append(
            DetectedSystem(
                index=index,
                box=Box(
                    x=left / width,
                    y=box_top / height,
                    w=max(1e-6, (max(right, cursor) - left) / width),
                    h=(box_bottom - box_top) / height,
                ),
                staff_space_px=spacing,
                measures=detected,
            )
        )

    return PageGeometry(
        width_px=int(round(width)),
        height_px=int(round(height)),
        render_dpi=NOMINAL_DPI,
        skew_deg=0.0,
        systems=systems,
    )


# One shared Verovio toolkit, created on the main thread at import.
#
# Verovio resolves its font resources when a toolkit is constructed, and that
# resolution fails outright on a worker thread: "Bravura font could not be
# loaded", and every subsequent load returns False. Uploads are analysed on a
# background thread, so a toolkit built there would engrave nothing. Building it
# once at import time -- which happens on the main thread -- sidesteps that, and
# the lock is needed regardless because a Verovio toolkit holds the loaded score
# as mutable state and two concurrent uploads would interleave inside it.
_TOOLKIT = None
_TOOLKIT_LOCK = threading.Lock()


def _toolkit():
    global _TOOLKIT
    if _TOOLKIT is None:
        import verovio

        _TOOLKIT = verovio.toolkit()
    return _TOOLKIT


def engrave(part) -> tuple[str, int]:
    """Engrave one part with Verovio. Returns (page-1 SVG, total page count)."""
    try:
        exported = part.write("musicxml")
        source = open(exported, "rb").read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        raise MusicXmlRejected(
            "That part could not be prepared for engraving.",
            "Try exporting a single instrument's part from your notation software.",
        ) from exc

    with _TOOLKIT_LOCK:
        toolkit = _toolkit()
        toolkit.setOptions(PAGE_OPTIONS)
        if not toolkit.loadData(source):
            raise MusicXmlRejected(
                "That score could not be engraved.",
                "Re-export it as MusicXML 3.1 or later and try again.",
            )
        return toolkit.renderToSVG(1), toolkit.getPageCount()


# --------------------------------------------------------------------------
# The whole path
# --------------------------------------------------------------------------


def load_musicxml(data: bytes) -> MusicXmlPage:
    """A MusicXML file as geometry, transcriptions and a page to draw them on."""
    part, title, part_name, part_count = read_part(data)
    svg, page_count = engrave(part)
    geometry = geometry_from_svg(svg)

    total_measures = len(list(part.getElementsByClass("Measure")))
    on_page = geometry.measure_count
    transcriptions_list = transcribe_part(part, on_page)

    # Key by (system, measure) the way build_score expects, walking the detected
    # measures in reading order. The two counts agree by construction -- both
    # come from the same engraving of the same part -- and any shortfall leaves
    # the trailing measures without a transcription rather than misaligning the
    # ones before them.
    transcriptions: dict[tuple[int, int], MeasureTranscription] = {}
    signatures: dict[int, dict[str, int | None]] = {}
    cursor = 0
    for system in geometry.systems:
        for measure in system.measures:
            if cursor >= len(transcriptions_list):
                break
            entry = transcriptions_list[cursor]
            transcriptions[(system.index, measure.index_in_system)] = entry
            if measure.index_in_system == 0:
                signatures[system.index] = {
                    "beats": entry.beats_in_measure,
                    "beat_value": entry.beat_value,
                    "key_fifths": entry.key_fifths,
                }
            cursor += 1

    return MusicXmlPage(
        geometry=geometry,
        transcriptions=transcriptions,
        svg=svg.encode("utf-8"),
        title=title,
        part_name=part_name,
        part_count=part_count,
        page_count=page_count,
        measures_in_part=total_measures,
        measures_on_page=on_page,
        signatures_by_system=signatures,
    )


def _exact_duration(event: NoteEvent) -> Fraction:
    """Exposed for tests: the duration the schema computes for an event."""
    del NOTE_VALUE_FRACTIONS  # the schema owns the table; this is just a handle
    return event.duration


# Construct the toolkit at import so the font initialisation happens here, on
# the importing thread, rather than lazily inside a worker where it would fail.
try:  # pragma: no cover - depends on the environment's verovio install
    _toolkit()
except Exception:  # noqa: BLE001
    # Leave it to the first engrave call to report a usable error rather than
    # breaking import of the whole application.
    _TOOLKIT = None
