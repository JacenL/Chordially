"""Run one upload analysis in the background and report honest progress.

Analysis takes seconds when the cache is warm and minutes when it is not, so it
cannot block the request. The browser polls for a stage name.

What it reports is a stage and, where a count genuinely exists, that count --
"read 12 of 34 sections". There is deliberately no percentage bar: the stages
take wildly different times and a bar sweeping smoothly to 90% and stopping is
a lie told by most upload screens. Stage names are the truth that is available.

State lives in memory for the life of the process. Durable storage of uploaded
scores is out of scope for the MVP, and pretending otherwise would mean writing
users' scores to disk without a retention story.
"""

from __future__ import annotations

import dataclasses
import threading
import uuid
from typing import Literal

from src.schemas.analysis import AnalysisBundle
from src.server.analysis.upload import Provenance, UploadRejected, analyze_upload
from src.server.recognition.audiveris_source import AudiverisUnavailable

JobState = Literal["queued", "running", "done", "failed"]


@dataclasses.dataclass
class Job:
    id: str
    filename: str
    state: JobState = "queued"
    stage: str = "Waiting to start"
    score_id: str = ""
    error: str = ""
    recovery: str = ""

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "state": self.state,
            "stage": self.stage,
            "scoreId": self.score_id,
            "error": self.error,
            "recovery": self.recovery,
        }


_lock = threading.Lock()
_jobs: dict[str, Job] = {}
_bundles: dict[str, AnalysisBundle] = {}
_provenance: dict[str, Provenance] = {}


def get_job(job_id: str) -> Job | None:
    with _lock:
        return _jobs.get(job_id)


def get_bundle(score_id: str) -> AnalysisBundle | None:
    with _lock:
        return _bundles.get(score_id)


def get_provenance(score_id: str) -> Provenance | None:
    with _lock:
        return _provenance.get(score_id)


def start(data: bytes, filename: str, content_type: str | None) -> Job:
    """Queue an analysis and return immediately with its job."""
    job = Job(id=uuid.uuid4().hex[:12], filename=filename or "upload")
    with _lock:
        _jobs[job.id] = job

    def run() -> None:
        def progress(message: str) -> None:
            with _lock:
                job.stage = message

        with _lock:
            job.state = "running"
            job.stage = "Reading the file"
        try:
            bundle, provenance = analyze_upload(
                data, filename, content_type, progress=progress
            )
        except (UploadRejected, AudiverisUnavailable) as exc:
            # Both carry a sentence and an action. A recognition engine that is
            # missing or that read nothing is a stated condition with something
            # the user can do about it, not an internal fault.
            with _lock:
                job.state = "failed"
                job.stage = ""
                job.error = exc.message
                job.recovery = exc.recovery
            return
        except Exception as exc:  # noqa: BLE001 - surfaced, never swallowed
            with _lock:
                job.state = "failed"
                job.stage = ""
                job.error = f"Analysis failed: {type(exc).__name__}: {exc}"
                job.recovery = (
                    "This is a fault in PracticeMap rather than in your file. "
                    "Try the example score, or try a different page."
                )
            return

        with _lock:
            _bundles[bundle.score.id] = bundle
            _provenance[bundle.score.id] = provenance
            job.score_id = bundle.score.id
            job.state = "done"
            job.stage = "Ready"

    threading.Thread(target=run, name=f"analyze-{job.id}", daemon=True).start()
    return job
