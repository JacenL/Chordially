/* Chordially viewer.
 *
 * This module does selection, keyboard navigation and sidebar text. It does no
 * coordinate arithmetic: every overlay was positioned in percentages by the
 * server, so zoom and resize are handled entirely by the browser's own layout
 * and an annotation cannot drift off its measure.
 *
 * Selection has one rule, and C17 made it simpler than it was. **Clicking
 * anywhere on the score selects the practice section that contains it.**
 * Sections tile the piece, so every measure belongs to exactly one, and two
 * clicks inside the same passage give the same selection and the same guidance.
 *
 * Phrases and trouble spots are still selectable, from the sidebar list and
 * from their own outlines when those are shown. They are detail inside the
 * selected passage, and they no longer intercept a click on the score: a hard
 * spot hijacking a measure click was the behaviour that made "click a measure,
 * get advice about this passage" untrue.
 */

import { createPractice } from "./practice.js";
import { createEditor } from "./edits.js";

const metaEl = document.getElementById("score-meta");
const SCORE_KEY = metaEl ? JSON.parse(metaEl.textContent).scoreId : null;

const dataEl = document.getElementById("score-data");
if (dataEl) {
  const DATA = JSON.parse(dataEl.textContent);
  init(DATA);
}

function init(data) {
  const TEMPO = metaEl ? JSON.parse(metaEl.textContent).tempo : null;
  const practice = createPractice(SCORE_KEY, TEMPO);
  const editor = createEditor(SCORE_KEY, TEMPO);
  const pane = document.getElementById("score-pane");
  const hoverCard = document.getElementById("hover-card");
  const measureEls = Array.from(document.querySelectorAll(".measure"));
  const phraseItems = Array.from(document.querySelectorAll(".phrase-item"));
  const sectionEls = Array.from(document.querySelectorAll(".section-outline"));
  const highlightEls = Array.from(document.querySelectorAll(".difficulty-highlight"));
  const outlines = Array.from(
    document.querySelectorAll(".phrase-outline, .trouble-outline")
  );

  const measureById = new Map(measureEls.map((el) => [el.dataset.measureId, el]));
  const order = data.measureOrder.filter((id) => measureById.has(id));

  let selectedMeasureId = null;
  let selectedId = null;

  // -------------------------------------------------------------- selection

  // What a click on the score resolves to. The section, always: it is the unit
  // the ribbon is coloured by and the unit the sidebar is written for, and
  // resolving to anything finer would mean two clicks a few millimetres apart
  // could load different advice about the same passage.
  function sectionIdOf(measureId) {
    const m = data.measures[measureId];
    if (!m) return null;
    return m.sectionId || m.phraseId || null;
  }

  function selectMeasure(measureId, opts = {}) {
    if (!data.measures[measureId]) return;
    selectedMeasureId = measureId;
    selectedId = sectionIdOf(measureId);
    paint();
    renderSidebar();
    if (opts.focus !== false) focusMeasure(measureId, opts.scroll !== false);
    else if (opts.scroll !== false) scrollIntoPane(measureById.get(measureId));
  }

  // Selecting a named passage: a section, a phrase inside one, or a hard spot.
  function selectEntry(entryId, opts = {}) {
    const entry = data.phrases[entryId];
    if (!entry) return;
    selectedId = entryId;
    // Land on its first measure, so the score and the sidebar always agree
    // about where you are.
    const first = entry.measureIds.find((id) => measureById.has(id));
    selectedMeasureId = first || null;
    paint();
    renderSidebar();
    if (first) {
      scrollIntoPane(measureById.get(first));
      if (opts.focus) focusMeasure(first, false);
      else setRovingTarget(first);
    }
  }

  function setRovingTarget(measureId) {
    // One tab stop for 61 measures: tab reaches the score, arrows move inside
    // it. Tabbing through every measure would make the sidebar unreachable.
    measureEls.forEach((el) => {
      el.tabIndex = el.dataset.measureId === measureId ? 0 : -1;
    });
  }

  function focusMeasure(measureId, scroll) {
    const el = measureById.get(measureId);
    if (!el) return;
    setRovingTarget(measureId);
    el.focus({ preventScroll: true });
    if (scroll) scrollIntoPane(el);
  }

  // Walk to the nearest ancestor-or-self at the given level. The chain is
  // section <- phrase <- trouble spot, so a spot's section is two steps up.
  function ancestorAt(id, level) {
    let entry = id ? data.phrases[id] : null;
    while (entry && entry.level !== level) {
      entry = entry.parentId ? data.phrases[entry.parentId] : null;
    }
    return entry || null;
  }

  function paint() {
    const section = ancestorAt(selectedId, "section");
    const sectionId = section ? section.id : null;
    const inSection = new Set(section ? section.measureIds : []);

    for (const el of measureEls) {
      const id = el.dataset.measureId;
      el.classList.toggle("is-selected", id === selectedMeasureId);
      el.classList.toggle(
        "in-selected-section",
        inSection.has(id) && id !== selectedMeasureId
      );
      if (id === selectedMeasureId) el.setAttribute("aria-current", "true");
      else el.removeAttribute("aria-current");
    }

    // Every fragment of the selected section lights up, on every system it
    // touches. That is what "clearly highlight its full extent" means when the
    // extent is not a rectangle.
    for (const el of sectionEls) {
      const on = el.dataset.sectionId === sectionId;
      el.classList.toggle("is-selected", on);
      el.tabIndex = on ? 0 : -1;
    }
    for (const el of highlightEls) {
      el.classList.toggle("is-selected", el.dataset.sectionId === sectionId);
    }

    for (const el of outlines) {
      const id = el.dataset.phraseId;
      el.classList.toggle("is-selected", id === selectedId);
      el.classList.toggle(
        "is-context",
        id !== selectedId && inSection.has((data.phrases[id] || {}).measureIds?.[0])
      );
    }
    for (const el of phraseItems) {
      const id = el.dataset.phraseId;
      const on = id === selectedId;
      el.classList.toggle("is-selected", on);
      el.classList.toggle("is-context", !on && id === sectionId);
      el.setAttribute("aria-pressed", on ? "true" : "false");
    }
  }

  function scrollIntoPane(el) {
    if (!el || !pane) return;
    const paneBox = pane.getBoundingClientRect();
    const box = el.getBoundingClientRect();
    const margin = 60;
    if (box.top < paneBox.top + margin) {
      pane.scrollTop -= paneBox.top + margin - box.top;
    } else if (box.bottom > paneBox.bottom - margin) {
      pane.scrollTop += box.bottom - (paneBox.bottom - margin);
    }
  }

  // ---------------------------------------------------------------- sidebar

  const el = (id) => document.getElementById(id);

  function show(node, on) {
    if (node) node.hidden = !on;
  }

  const EYEBROW = {
    section: "Selected passage",
    phrase: "Phrase inside this passage",
    trouble_spot: "Hard spot inside this passage",
  };

  function renderSidebar() {
    const measure = selectedMeasureId ? data.measures[selectedMeasureId] : null;
    const entry = selectedId ? data.phrases[selectedId] : null;

    if (!measure && !entry) return;

    if (entry) {
      const isSpot = entry.level === "trouble_spot";
      const isSection = entry.level === "section";
      const section = ancestorAt(selectedId, "section");
      const phrase = ancestorAt(selectedId, "phrase");

      el("sel-eyebrow").textContent = EYEBROW[entry.level] || "Selected passage";

      // Only the levels above this one, and only if they exist.
      const trail = [];
      if (!isSection && section) trail.push(section.label);
      if (isSpot && phrase) trail.push(phrase.label);
      show(el("sel-breadcrumb"), trail.length > 0);
      if (trail.length) {
        el("sel-breadcrumb").textContent = trail.join(" › ") + " ›";
      }

      el("sel-title").textContent = isSpot ? "Hard spot" : entry.label;
      // Only name the selected measure when it adds something. On a one-measure
      // hard spot "measure 2 · measure 2 selected" is just noise.
      // The heading already says the range; repeating it here was the first
      // thing a reader saw twice. This line says the one thing the heading
      // cannot: which measure the click landed on. On a single-measure passage
      // even that is redundant, so it goes away entirely.
      const spansSeveral = (entry.measureIds || []).length > 1;
      el("sel-range").textContent =
        measure && spansSeveral ? `measure ${measure.label} selected` : "";
      show(el("sel-range"), Boolean(measure && spansSeveral));

      show(el("sel-rating-row"), true);
      el("sel-score").textContent = entry.isRated ? entry.scoreText : "—";
      el("sel-category").textContent = entry.isRated ? entry.category : data.unratedLabel;
      el("sel-peak").textContent =
        entry.isRated && entry.peakMeasureLabel
          ? `hardest bar here is measure ${entry.peakMeasureLabel}, at ${entry.peakText}`
          : "";

      // A section says in one line what it is asking for. The number alone does
      // not distinguish a fast passage from a high one.
      show(el("sel-demand"), isSection && Boolean(entry.endReason));
      if (isSection) el("sel-demand").textContent = capitalize(entry.endReason) + ".";

      show(el("sel-unrated"), !entry.isRated);
      el("sel-unrated").textContent = entry.unratedReason;

      // A rated passage can still contain a measure nobody could read. The
      // ribbon hatches it, and so must the sidebar: otherwise the passage's
      // number looks like it covers music it was never computed from.
      const flagged = measure && !measure.isRated;
      show(el("sel-measure-note"), Boolean(flagged));
      if (flagged) {
        el("sel-measure-note").textContent =
          `Measure ${measure.label} is unrated — ${measure.qualityNote}. ` +
          "This passage's rating comes from the measures around it.";
      }

      const hasFactors = entry.factors.length > 0;
      show(el("why-panel"), hasFactors);
      if (hasFactors) {
        // A collapsed panel should say whether it is worth opening. The top
        // demand, in the player's words, is the most useful thing that fits.
        const hint = el("why-hint");
        if (hint) hint.textContent = entry.factors[0].plain || "";
        renderFactors(entry.factors);
        el("sel-factors-note").textContent = entry.peakMeasureLabel
          ? `Measured on measure ${entry.peakMeasureLabel}, the most demanding measure in this passage.`
          : "";
      }

      renderInside(isSection ? entry : section);

      show(el("boundary-panel"), true);
      el("sel-start").textContent = `${entry.startReason} — ${entry.startConfidence}`;
      el("sel-end").textContent = `${entry.endReason} — ${entry.endConfidence}`;
      el("sel-practice").textContent = entry.practiceText;

      practice.load(selectedId);
      // Editing acts on the passage, even when something inside it is selected.
      editor.show(section, data.measureLabels || {});
    } else if (measure) {
      show(el("sel-breadcrumb"), false);
      el("sel-eyebrow").textContent = "Selected measure";
      el("sel-title").textContent = `Measure ${measure.label}`;
      el("sel-range").textContent = "Not part of an analyzed passage.";
      show(el("sel-rating-row"), false);
      show(el("sel-demand"), false);
      show(el("sel-unrated"), true);
      el("sel-unrated").textContent = `${data.unratedLabel} — ${measure.qualityNote}`;
      show(el("sel-measure-note"), false);
      show(el("why-panel"), false);
      show(el("inside-panel"), false);
      show(el("boundary-panel"), false);
      practice.clear(
        "This measure is not part of an analyzed passage, so there is no music to build an exercise from."
      );
      editor.hide();
    }
  }

  function capitalize(text) {
    return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
  }

  // The phrases and hard spots inside the selected passage. Secondary by
  // construction: they sit below the passage's own guidance, and selecting one
  // keeps the passage in the breadcrumb rather than replacing it.
  function renderInside(section) {
    const panel = el("inside-panel");
    const list = el("inside-list");
    if (!panel || !list) return;

    const children = section ? section.childPhraseIds || [] : [];
    const spots = section ? section.childSpotIds || [] : [];
    if (!section || (!children.length && !spots.length)) {
      panel.hidden = true;
      return;
    }

    list.textContent = "";
    const spotsByPhrase = new Map();
    for (const spotId of spots) {
      const spot = data.phrases[spotId];
      if (spot) spotsByPhrase.set(spot.parentId, spotId);
    }

    for (const phraseId of children) {
      list.append(insideRow(phraseId, "phrase-item--nested"));
      const spotId = spotsByPhrase.get(phraseId);
      if (spotId) list.append(insideRow(spotId, "phrase-item--spot"));
    }
    const hint = el("inside-hint");
    if (hint) {
      const parts = [`${children.length} phrase${children.length === 1 ? "" : "s"}`];
      if (spots.length) {
        parts.push(`${spots.length} hard spot${spots.length === 1 ? "" : "s"}`);
      }
      hint.textContent = parts.join(", ");
    }
    panel.hidden = false;
  }

  function insideRow(entryId, extraClass) {
    const entry = data.phrases[entryId];
    const li = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = `phrase-item ${extraClass}`;
    button.dataset.phraseId = entryId;
    button.classList.toggle("is-selected", entryId === selectedId);
    button.setAttribute("aria-pressed", entryId === selectedId ? "true" : "false");

    const text = document.createElement("span");
    text.className = "phrase-item-text";
    const label = document.createElement("span");
    label.className = "phrase-item-label";
    label.textContent = entry.level === "trouble_spot" ? "Hard spot" : entry.label;
    const range = document.createElement("span");
    range.className = "phrase-item-range";
    range.textContent = entry.rangeText;
    text.append(label, range);

    const score = document.createElement("span");
    score.className =
      "phrase-item-score" + (entry.isRated ? "" : " phrase-item-score--unrated");
    score.textContent = entry.scoreText;

    button.append(text, score);
    button.addEventListener("click", () => selectEntry(entryId));
    li.append(button);
    return li;
  }

  function renderFactors(factors) {
    const list = el("sel-factors");
    list.textContent = "";
    for (const factor of factors) {
      const li = document.createElement("li");
      const label = document.createElement("span");
      // The player's words lead. The feature's own name and its point
      // contribution are still exact and still reachable, one disclosure down
      // in "How this number was worked out".
      const plain = factor.plain || factor.label;
      label.textContent = factor.detail ? `${plain} — ${factor.detail}` : plain;

      const weight = document.createElement("span");
      weight.className = "factor-weight";
      weight.textContent = factor.contribution;
      weight.title = `${factor.label}: ${factor.contribution} of a possible ${factor.weight}`;
      // A contribution with no scale is a number nobody can judge. Showing what
      // it was drawn from turns "+0.8" into something a violinist can disagree
      // with: a quarter of everything note rate could have contributed.
      if (factor.weight) {
        const scale = document.createElement("span");
        scale.className = "factor-weight-of";
        scale.textContent = ` of ${factor.weight}`;
        weight.append(scale);
      }
      li.append(label, weight);
      list.append(li);
    }
  }

  // The rubric is the same for the whole score, so it is rendered once.
  function renderRubric() {
    const rubric = data.rubric;
    const body = el("rubric-body");
    if (!rubric || !body) return;

    body.replaceChildren();
    body.append(para("rubric-scale", rubric.scale));
    body.append(
      para("source-line", `Rubric version ${rubric.version} · tempo used: ${rubric.tempo}`)
    );

    body.append(para("exercise-subheading", "Weights, in points of the 10"));
    const weights = document.createElement("ul");
    weights.className = "rubric-weights";
    for (const entry of rubric.weights) {
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.textContent = entry.label;
      const value = document.createElement("span");
      value.className = "rubric-weight";
      value.textContent = entry.weight;
      li.append(name, value);
      weights.append(li);
    }
    body.append(weights);

    body.append(para("exercise-subheading", "What this rating cannot see"));
    const blind = document.createElement("ul");
    blind.className = "rubric-blind";
    for (const item of rubric.blindSpots) {
      const li = document.createElement("li");
      li.textContent = item;
      blind.append(li);
    }
    body.append(blind);
    body.append(para("rubric-review", rubric.review));
  }

  function para(className, text) {
    const node = document.createElement("p");
    node.className = className;
    node.textContent = text;
    return node;
  }

  // ------------------------------------------------------------- hover card

  function showHover(measureEl) {
    const info = data.measures[measureEl.dataset.measureId];
    if (!info || !hoverCard) return;
    hoverCard.textContent = "";

    const title = document.createElement("strong");
    title.textContent = `Measure ${info.label}`;
    const rating = document.createElement("div");
    rating.className = "hover-score";
    rating.textContent = info.isRated
      ? `${info.scoreText} / 10 · ${info.category}`
      : `${data.unratedLabel} · ${info.qualityNote}`;
    hoverCard.append(title, rating);

    // The measure's own rating is local detail; the passage is what a click
    // will select, so the card says which passage that is.
    const section = info.sectionId ? data.phrases[info.sectionId] : null;
    if (section) {
      const context = document.createElement("div");
      context.className = "hover-section";
      context.textContent = `in ${section.label} · ${section.scoreText}`;
      hoverCard.append(context);
    }

    if (info.factors.length) {
      const factors = document.createElement("div");
      factors.textContent = info.factors.map((f) => `${f.label} ${f.contribution}`).join(" · ");
      hoverCard.append(factors);
    }

    const box = measureEl.getBoundingClientRect();
    hoverCard.hidden = false;
    const cardBox = hoverCard.getBoundingClientRect();
    const left = Math.min(
      Math.max(8, box.left),
      window.innerWidth - cardBox.width - 8
    );
    const above = box.top - cardBox.height - 8;
    hoverCard.style.left = `${left}px`;
    hoverCard.style.top = `${above > 8 ? above : box.bottom + 8}px`;
  }

  function hideHover() {
    if (hoverCard) hoverCard.hidden = true;
  }

  // -------------------------------------------------------------- listeners

  for (const measureEl of measureEls) {
    measureEl.addEventListener("click", () => selectMeasure(measureEl.dataset.measureId));
    measureEl.addEventListener("mouseenter", () => showHover(measureEl));
    measureEl.addEventListener("mouseleave", hideHover);
    measureEl.addEventListener("focus", () => showHover(measureEl));
    measureEl.addEventListener("blur", hideHover);
    measureEl.addEventListener("keydown", (event) => onMeasureKey(event, measureEl));
  }

  function onMeasureKey(event, measureEl) {
    const index = order.indexOf(measureEl.dataset.measureId);
    if (index < 0) return;
    let next = null;

    if (event.key === "ArrowRight") next = order[index + 1];
    else if (event.key === "ArrowLeft") next = order[index - 1];
    else if (event.key === "Home") next = order[0];
    else if (event.key === "End") next = order[order.length - 1];
    else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      next = neighbourInAdjacentSystem(measureEl, event.key === "ArrowDown" ? 1 : -1);
    } else return;

    if (!next) {
      event.preventDefault();
      return;
    }
    event.preventDefault();
    selectMeasure(next);
  }

  function neighbourInAdjacentSystem(measureEl, direction) {
    const systemIndex = Number(measureEl.dataset.systemIndex) + direction;
    const siblings = measureEls.filter((m) => Number(m.dataset.systemIndex) === systemIndex);
    if (!siblings.length) return null;
    // Keep the horizontal position: moving down a system should land under
    // roughly where you were, the way an eye tracks down a page.
    const box = measureEl.getBoundingClientRect();
    const centre = box.left + box.width / 2;
    let best = siblings[0];
    let bestDistance = Infinity;
    for (const sibling of siblings) {
      const sBox = sibling.getBoundingClientRect();
      const distance = Math.abs(sBox.left + sBox.width / 2 - centre);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = sibling;
      }
    }
    return best.dataset.measureId;
  }

  for (const item of phraseItems) {
    item.addEventListener("click", () => selectEntry(item.dataset.phraseId));
  }

  // Section fragments select the same passage as their measure hit targets.
  for (const sectionEl of sectionEls) {
    sectionEl.addEventListener("click", () => selectEntry(sectionEl.dataset.sectionId));
    sectionEl.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectEntry(sectionEl.dataset.sectionId);
      }
    });
  }
  for (const outline of outlines) {
    outline.addEventListener("click", (event) => {
      event.stopPropagation();
      selectEntry(outline.dataset.phraseId);
    });
    outline.style.pointerEvents = "auto";
  }

  // ------------------------------------------------------------------ zoom

  const ZOOM_STEPS = [100, 125, 150, 200, 300];
  let zoomIndex = 0;
  const zoomValue = document.getElementById("zoom-value");
  const pages = Array.from(document.querySelectorAll(".page"));

  function applyZoom() {
    const percent = ZOOM_STEPS[zoomIndex];
    for (const page of pages) page.style.setProperty("--zoom", `${percent}%`);
    if (zoomValue) zoomValue.textContent = `${percent}%`;
    hideHover();
  }

  document.querySelectorAll("[data-zoom]").forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.dataset.zoom;
      if (action === "in") zoomIndex = Math.min(ZOOM_STEPS.length - 1, zoomIndex + 1);
      else if (action === "out") zoomIndex = Math.max(0, zoomIndex - 1);
      else zoomIndex = 0;
      applyZoom();
      if (selectedMeasureId) scrollIntoPane(measureById.get(selectedMeasureId));
    });
  });
  applyZoom();

  // -------------------------------------------------------- phrase outlines

  const phraseToggle = document.getElementById("toggle-phrases");
  if (phraseToggle) {
    phraseToggle.addEventListener("change", () => {
      document
        .querySelectorAll(".layer--phrases")
        .forEach((layer) => layer.classList.toggle("is-hidden", !phraseToggle.checked));
    });
  }

  // ---------------------------------------------------------------- startup

  const noticesToggle = document.getElementById("notices-toggle");
  if (noticesToggle) {
    noticesToggle.addEventListener("click", () => {
      const notices = document.getElementById("notices");
      const collapsed = notices.classList.toggle("is-collapsed");
      noticesToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
      document.getElementById("notices-toggle-label").textContent = collapsed
        ? "Show notes about this score"
        : "Hide notes about this score";
    });
  }

  renderRubric();

  if (data.defaultSelectionId) selectEntry(data.defaultSelectionId, { focus: false });
  else if (order.length) setRovingTarget(order[0]);
}
