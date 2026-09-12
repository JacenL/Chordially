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
  const errorBox = document.getElementById("upload-error");
  const errorMessage = document.getElementById("upload-error-message");
  const errorRecovery = document.getElementById("upload-error-recovery");

  input.addEventListener("change", () => {
    const file = input.files && input.files[0];
    submit.disabled = !file;
    if (label) label.textContent = file ? file.name : "Choose a file";
    errorBox.hidden = true;
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const file = input.files && input.files[0];
    if (!file) return;

    submit.disabled = true;
    input.disabled = true;
    errorBox.hidden = true;
    progress.hidden = false;
    stage.textContent = "Uploading the file";

    const body = new FormData();
    body.append("file", file);

    let job;
    try {
      const response = await fetch("/upload", { method: "POST", body });
      const payload = await response.json();
      if (!response.ok) {
        const detail = payload.detail || {};
        fail(detail.error || "That upload was rejected.", detail.recovery || "");
        return;
      }
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
      if (job.stage) stage.textContent = job.stage;

      if (job.state === "done") {
        stage.textContent = "Ready — opening your score";
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
    progress.hidden = true;
    errorBox.hidden = false;
    errorMessage.textContent = message || "Something went wrong.";
    errorRecovery.textContent = recovery || "";
    submit.disabled = false;
    input.disabled = false;
  }
}
