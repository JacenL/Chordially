/* Practice-section boundary editing.
 *
 * Grouping reports its own reason for every boundary, often a thin one, and
 * this is what makes that honesty actionable rather than merely apologetic.
 *
 * The controls act on the *passage*, which is what the score is coloured by and
 * what a click selects. Selecting a phrase or a hard spot inside a passage
 * still leaves these pointing at the passage around it: splitting "the phrase
 * you happen to have highlighted" would move a boundary the user cannot see.
 *
 * After a successful edit the page reloads. That is deliberate: an edit changes
 * passage membership, which changes ratings, colours, region fragments and every
 * exercise derived from them. Re-deriving all of that in the browser would
 * duplicate the server's logic and could disagree with it; reloading cannot.
 */

export function createEditor(scoreKey, tempoBpm) {
  const el = (id) => document.getElementById(id);
  const row = el("edit-row");
  // The whole panel hides with the controls. An "Adjust this passage" heading
  // that opens onto nothing is worse than no heading.
  const panel = el("adjust-panel");
  const select = el("split-at");
  const note = el("edit-note");
  const pill = el("edited-pill");
  const current_note = el("edit-current");

  if (!row) return { show: () => {}, hide: () => {} };

  let current = null;

  function hide() {
    row.hidden = true;
    if (panel) panel.hidden = true;
    if (note) note.hidden = true;
  }

  function show(section, measureLabels) {
    if (!section || section.level !== "section") {
      hide();
      return;
    }
    current = section;
    row.hidden = false;
    if (panel) panel.hidden = false;
    // Name what is about to change. "Split into two here" is only predictable
    // if you can see what "this" currently covers.
    if (current_note) {
      current_note.textContent = `Now: ${section.rangeText}.`;
    }
    if (note) note.hidden = true;
    if (pill) pill.hidden = !section.userEdited;

    select.replaceChildren();
    // The first measure is excluded: a passage already begins there, and
    // offering it would only produce a refusal.
    for (const measureId of section.measureIds.slice(1)) {
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
      "/api/sections/" + encodeURIComponent(scoreKey) + path + (query ? "?" + query : ""),
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
    post("/split", { at_measure_id: select.value });
  });

  el("merge-btn").addEventListener("click", () => {
    if (!current) return;
    post("/merge", { section_id: current.id });
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
