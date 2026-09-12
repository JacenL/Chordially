/* Upload and poll for analysis progress.
 *
 * The one rule this file exists to keep: an upload that fails says so and stays
 * on this screen with a recovery action. It never quietly hands the user the
 * example score, which would look like success and teach them nothing true
 * about their own file.
 */

const form = document.getElementById("upload-form");
if (form) {
  const input = document.getElementById("file-input");
  const submit = document.getElementById("upload-submit");
  const label = document.querySelector(".file-field-label");
  const progress = document.getElementById("upload-progress");
  const stage = document.getElementById("upload-stage");
  const bar = document.getElementById("upload-progress-bar");
  const progressDetail = document.getElementById("upload-progress-detail");
  let busy = false;

  // Percentages describe only the named phase. Stages with no measurable
  // total stay indeterminate; no timer advances the bar.
  function status(title, detail, percent = null) {
    stage.textContent = title;
    progressDetail.textContent = detail;
    if (percent === null) bar.removeAttribute("value");
    else bar.value = Math.max(0, Math.min(100, percent));
  }

  function sendUpload(body) {
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open("POST", "/upload");
      request.responseType = "json";
      request.timeout = 120000;
      request.upload.onprogress = (event) => {
        if (!event.lengthComputable || event.total <= 0) return;
        const percent = Math.floor(event.loaded / event.total * 100);
        status("Uploading your sheet music", `${percent}% of upload transferred`, percent);
      };
      request.upload.onload = () => status(
        "Upload sent — waiting for the server",
        "The file has been transferred. Analysis starts after the server accepts it."
      );
      request.onload = () => resolve({
        ok: request.status >= 200 && request.status < 300,
        payload: request.response,
      });
      request.onerror = request.ontimeout = request.onabort = () => reject(new Error("Upload interrupted"));
      request.send(body);
    });
  }
  const errorBox = document.getElementById("upload-error");
  const errorMessage = document.getElementById("upload-error-message");
  const errorRecovery = document.getElementById("upload-error-recovery");

  function showChosen() {
    const file = input.files && input.files[0];
    submit.disabled = !file;
    if (label) label.textContent = file ? file.name : "Choose a file";
    form.classList.toggle("has-file", Boolean(file));
    errorBox.hidden = true;
  }

  input.addEventListener("change", showChosen);

  // Drag and drop, as a convenience over the file picker rather than instead of
  // it. The picker stays the accessible path and is what the keyboard reaches;
  // this only saves a dialog for someone who already has the scan in a folder.
  // `DataTransfer` is assigned to the input rather than kept aside so there is
  // one source of truth for "which file are we about to send".
  if (window.DataTransfer) {
    let depth = 0;

    const stop = (event) => {
      event.preventDefault();
      event.stopPropagation();
    };

    form.addEventListener("dragenter", (event) => {
      stop(event);
      depth += 1;
      form.classList.add("is-dragging");
    });
    form.addEventListener("dragover", (event) => {
      stop(event);
      if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
    });
    form.addEventListener("dragleave", (event) => {
      stop(event);
      depth = Math.max(0, depth - 1);
      if (depth === 0) form.classList.remove("is-dragging");
    });
    form.addEventListener("drop", (event) => {
      stop(event);
      depth = 0;
      form.classList.remove("is-dragging");
      if (busy) return;
      const dropped = event.dataTransfer && event.dataTransfer.files;
      if (!dropped || !dropped.length) return;
      // One page per upload, so a multi-file drop takes the first rather than
      // silently analyzing something the user did not point at.
      const transfer = new DataTransfer();
      transfer.items.add(dropped[0]);
      input.files = transfer.files;
      showChosen();
    });

    // A file dropped anywhere else on the page would otherwise be opened by the
    // browser, replacing the app with a PDF viewer.
    for (const type of ["dragover", "drop"]) {
      window.addEventListener(type, (event) => {
        if (!form.contains(event.target)) event.preventDefault();
      });
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = input.files && input.files[0];
    if (!file || busy) return;

    busy = true;
    form.setAttribute("aria-busy", "true");
    submit.disabled = true;
    input.disabled = true;
    errorBox.hidden = true;
    progress.hidden = false;
    status("Uploading your sheet music", "Starting the file transfer…", 0);

    const body = new FormData();
    body.append("file", file);

    let job;
    try {
      const response = await sendUpload(body);
      const payload = response.payload || {};
      if (!response.ok) {
        const detail = payload.detail || {};
        fail(detail.error || "That upload was rejected.", detail.recovery || "");
        return;
      }
      if (!payload.id) throw new Error("Missing job ID");
      job = payload;
    } catch (err) {
      fail("The upload did not reach the server.", "Check that PracticeMap is still running, then try again.");
      return;
    }

    poll(job.id);
  });

  async function poll(jobId) {
    try {
      const response = await fetch(`/api/jobs/${jobId}`);
      if (!response.ok) {
        fail("Lost track of that analysis.", "Upload the file again.");
        return;
      }
      const job = await response.json();
      const count = /^read (\d+) of (\d+) sections$/i.exec(job.stage || "");
      if (count && Number(count[2]) > 0 && Number(count[1]) <= Number(count[2])) {
        const completed = Number(count[1]), total = Number(count[2]);
        status("Reading the notation", `${completed} of ${total} recognition requests completed · ${Math.floor(completed / total * 100)}% of this stage. Some results may need review.`, completed / total * 100);
      } else if ((job.stage || "").includes("Audiveris")) {
        status("Reading your sheet music", "Audiveris is recognizing the notation on the server. It reports completion when ready, so there is no percentage for this stage.");
      } else {
        status(job.stage || "Analyzing your score", "This stage has no measurable percentage yet. Status updates automatically.");
      }

      if (job.state === "done") {
        status("Ready — opening your score", "Processing complete. Any unread measures will be marked on the score.", 100);
        window.location.href = `/score/${job.scoreId}`;
        return;
      }
      if (job.state === "failed") {
        fail(job.error, job.recovery);
        return;
      }
      setTimeout(() => poll(jobId), 700);
    } catch (err) {
      fail("Lost contact with the server while analyzing.", "Check that PracticeMap is still running, then try again.");
    }
  }

  function fail(message, recovery) {
    busy = false;
    form.removeAttribute("aria-busy");
    bar.removeAttribute("value");
    progress.hidden = true;
    errorBox.hidden = false;
    errorMessage.textContent = message || "Something went wrong.";
    errorRecovery.textContent = recovery || "";
    submit.disabled = false;
    input.disabled = false;
  }
}
