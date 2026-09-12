"""Audiveris as the scan recognition engine: local, offline, deterministic.

Audiveris is a mature open-source optical music recognition program. It reads a
scanned page and exports MusicXML -- which is the format `musicxml_source.py`
already reads exactly. So this module does one job and nothing else: run the
program, hand back the bytes it exported. Everything downstream is the MusicXML
path that has been shipping since C12.

**Why this route rather than joining Audiveris notes to our OpenCV boxes.** The
B2a spike found Audiveris reporting 56 measures where `cv_geometry` reports 61,
as exactly one missing measure in each of systems 1, 4, 5, 7 and 8. Joining by
index would have misaligned notes against regions on five of eleven systems --
precisely the failure `assemble.build_score` refuses to commit. Sending the
export through `load_musicxml` instead sidesteps the disagreement completely,
because that path takes its geometry from the Verovio engraving of the same
MusicXML the notes came from. The notes and the boxes are then two readings of
one document rather than two documents that have to be reconciled.

The cost, and it is a real one: the page the user sees is a re-engraving, not
their scan. That is disclosed in the provenance line and the re-engraved view is
labelled, exactly as the MusicXML import already is.

What this buys over the vision path: no API key, no network call, no credit
balance to exhaust, and the same input produces the same output every time.
Measured on the fixture scan in B2a: 20.2s a page, 50 of 56 measures passing the
duration gate against 32 of 61 on the cached vision run.

**Not bundled.** Audiveris is a Java application and is not pip-installable, so
`pip install -r requirements-dev.txt` is no longer the whole setup for the scan
path. When it is absent this module says so with a recovery action; it never
falls back to a provider silently, and it never pretends a page was read.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.config import PROJECT_ROOT

# Where the unpacked app-image lives by default. The Windows console MSI expands
# with `msiexec /a <msi> /qn TARGETDIR=<dir>`, which needs no administrator and
# writes nothing to the registry -- the image carries its own JDK. `work/` is
# gitignored, so the binary is never committed.
DEFAULT_EXE = PROJECT_ROOT / "work" / "audiveris" / "extracted" / "Audiveris" / "Audiveris.exe"

ENV_VAR = "PRACTICEMAP_AUDIVERIS_EXE"

# A page takes about 20 seconds. This is generous enough for a dense page on a
# slow machine and short enough that a wedged process is reported rather than
# holding an upload open indefinitely.
TIMEOUT_SECONDS = 180

INSTALL_HINT = (
    "Install Audiveris and set "
    f"{ENV_VAR} to its executable, or place the unpacked app image at "
    f"{DEFAULT_EXE.relative_to(PROJECT_ROOT)}."
)


class AudiverisUnavailable(RuntimeError):
    """Recognition could not run, with a sentence and a recovery action.

    Carries the same shape as `UploadRejected`: the message says what happened
    and `recovery` says what to do about it, because an upload screen that
    reports a failure without an action is just an apology.
    """

    def __init__(self, message: str, recovery: str) -> None:
        super().__init__(message)
        self.message = message
        self.recovery = recovery


def executable() -> Path | None:
    """The Audiveris binary to use, or None when there isn't one.

    Checked in order: the environment variable, the default unpacked location,
    then `PATH`. Returning None rather than raising lets callers report
    availability without treating absence as an error.
    """
    configured = os.environ.get(ENV_VAR, "").strip()
    if configured:
        candidate = Path(configured)
        return candidate if candidate.exists() else None
    if DEFAULT_EXE.exists():
        return DEFAULT_EXE
    found = shutil.which("audiveris") or shutil.which("Audiveris")
    return Path(found) if found else None


def is_available() -> bool:
    return executable() is not None


def transcribe(data: bytes, filename: str) -> bytes:
    """Run Audiveris over these bytes and return the MusicXML it exported.

    The input is written to a temporary file because Audiveris takes a path, and
    both the input and the export are cleaned up on the way out -- an uploaded
    score belongs to the user and has no business outliving the request.
    """
    exe = executable()
    if exe is None:
        raise AudiverisUnavailable(
            "This instance cannot read scanned notation: Audiveris is not installed.",
            INSTALL_HINT + " MusicXML import and the example score work without it.",
        )

    suffix = Path(filename or "upload.pdf").suffix.lower() or ".pdf"
    with tempfile.TemporaryDirectory(prefix="practicemap-omr-") as workdir:
        root = Path(workdir)
        source = root / f"page{suffix}"
        source.write_bytes(data)
        out_dir = root / "out"
        out_dir.mkdir()

        command = [
            str(exe),
            "-batch",
            "-transcribe",
            "-export",
            "-output",
            str(out_dir),
            "--",
            str(source),
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                timeout=TIMEOUT_SECONDS,
                check=False,
            )
        except OSError as exc:
            raise AudiverisUnavailable(
                "Audiveris could not be started.",
                f"{INSTALL_HINT} The system reported: {exc}.",
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise AudiverisUnavailable(
                f"Reading that page took longer than {TIMEOUT_SECONDS} seconds and was stopped.",
                "Try a single page at a lower resolution, or import MusicXML instead.",
            ) from exc

        exported = _find_export(out_dir)
        if exported is None:
            # Audiveris reports its own reasons on stderr. Surfacing the tail of
            # it is more use than "recognition failed", and it is the program's
            # own words rather than our guess about them.
            detail = _tail(completed.stderr) or _tail(completed.stdout)
            raise AudiverisUnavailable(
                "Audiveris read that file but produced no notation.",
                "Chordially reads clear printed notation. Check the page is "
                "upright, in focus and not handwritten, then try again."
                + (f" Audiveris reported: {detail}" if detail else ""),
            )
        return exported.read_bytes()


def _find_export(out_dir: Path) -> Path | None:
    """The exported score. `.mxl` is preferred; a plain `.xml` is accepted."""
    for pattern in ("*.mxl", "*.musicxml", "*.xml"):
        matches = sorted(out_dir.rglob(pattern))
        if matches:
            return matches[0]
    return None


def _tail(stream: bytes | None, limit: int = 200) -> str:
    if not stream:
        return ""
    text = stream.decode("utf-8", errors="replace").strip()
    lines = [line for line in text.splitlines() if line.strip()]
    return lines[-1][:limit] if lines else ""
