/* Phrase boundary editing.
 *
 * Segmentation reports its own confidence, often low, and this is what makes
 * that number actionable rather than merely apologetic.
 *
 * After a successful edit the page reloads. That is deliberate: an edit changes
 * phrase membership, which changes ratings, region fragments, trouble spots and
 * every exercise derived from them. Re-deriving all of that in the browser
 * would duplicate the server's logic and could disagree with it; reloading
 * cannot.
 */

export function createEditor(scoreKey, tempoBpm) {
  const el = (id) => document.getElementById(id);
  const row = el("edit-row");
  const select = el("split-at");
  const note = el("edit-note");
  const pill = el("edited-pill");

  if (!row) return { show: () => {}, hide: () => {} };

  let current = null;

  function hide() {
    row.hidden = true;
    if (note) note.hidden = true;
  }

  function show(phrase, measureLabels) {
    // Only whole phrases are editable. A trouble spot is derived from ratings,
    // so "splitting" one would be meaningless -- the next retune rebuilds it.
    if (!phrase || phrase.level !== "phrase") {
      hide();
      return;
    }
    current = phrase;
    row.hidden = false;
    if (note) note.hidden = true;
    if (pill) pill.hidden = !phrase.userEdited;

    select.replaceChildren();
    // The first measure is excluded: a phrase already begins there, and
    // offering it would only produce a refusal.
    for (const measureId of phrase.measureIds.slice(1)) {
      const option = document.createElement("option");
      option.value = measureId;
      option.textContent = "before measure " + (measureLabels[measureId] || "?");
      select.append(option);
    }
    select.disabled = select.options.length === 0;
    el("split-btn").disabled = select.options.length === 0;
  }

  async function post(path, params) {
    const query = new URLSearchParams(params).toString();
    const response = await fetch(
      "/api/phrases/" + encodeURIComponent(scoreKey) + path + "?" + query,
      { method: "POST" }
    );
    if (response.ok) {
      // Keep the tempo across the reload; it is part of what the user is seeing.
      const url = new URL(window.location.href);
      if (tempoBpm) url.searchParams.set("tempo", tempoBpm);
      window.location.replace(url.toString());
      return;
    }
    let message = "That edit could not be applied.";
    try {
      const body = await response.json();
      if (body && body.detail) message = body.detail;
    } catch (err) {
      /* keep the default message */
    }
    if (note) {
      note.hidden = false;
      note.textContent = message;
    }
  }

  el("split-btn").addEventListener("click", () => {
    if (!current || !select.value) return;
    post("/split", { phrase_id: current.id, at_measure_id: select.value });
  });

  el("merge-btn").addEventListener("click", () => {
    if (!current) return;
    post("/merge", { phrase_id: current.id });
  });

  const reset = el("reset-edits");
  if (reset) {
    reset.addEventListener("click", (event) => {
      event.preventDefault();
      post("/reset", {});
    });
  }

  return { show, hide };
}
