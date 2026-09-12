/* PracticeMap viewer.
 *
 * This module does selection, keyboard navigation and sidebar text. It does no
 * coordinate arithmetic: every overlay was positioned in percentages by the
 * server, so zoom and resize are handled entirely by the browser's own layout
 * and an annotation cannot drift off its measure.
 *
 * Selection has one rule worth naming. Clicking a measure selects the phrase
 * that owns that measure's first note, which the server decided; the browser
 * only looks it up. A measure that recognition could not read owns no phrase,
 * and the sidebar says so instead of attaching it to a neighbour.
 */

import { createPractice } from "./practice.js";

const metaEl = document.getElementById("score-meta");
const SCORE_KEY = metaEl ? JSON.parse(metaEl.textContent).scoreId : null;

const dataEl = document.getElementById("score-data");
if (dataEl) {
  const DATA = JSON.parse(dataEl.textContent);
  init(DATA);
}

function init(data) {
  const practice = createPractice(SCORE_KEY, metaEl ? JSON.parse(metaEl.textContent).tempo : null);
  const pane = document.getElementById("score-pane");
  const hoverCard = document.getElementById("hover-card");
  const measureEls = Array.from(document.querySelectorAll(".measure"));
  const phraseItems = Array.from(document.querySelectorAll(".phrase-item"));
  const outlines = Array.from(
    document.querySelectorAll(".phrase-outline, .trouble-outline")
  );

  const measureById = new Map(measureEls.map((el) => [el.dataset.measureId, el]));
  const order = data.measureOrder.filter((id) => measureById.has(id));

  let selectedMeasureId = null;
  let selectedPhraseId = null;

  // -------------------------------------------------------------- selection

  // Most specific wins. A measure a hard spot is marked on selects that spot;
  // every other measure selects its phrase. Either way the parent phrase stays
  // in context, so nothing is lost by the more specific choice.
  function phraseOf(measureId) {
    const m = data.measures[measureId];
    if (!m) return null;
    return m.spotId || m.phraseId;
  }

  function selectMeasure(measureId, opts = {}) {
    if (!data.measures[measureId]) return;
    selectedMeasureId = measureId;
    selectedPhraseId = phraseOf(measureId);
    paint();
    renderSidebar();
    if (opts.focus !== false) focusMeasure(measureId, opts.scroll !== false);
    else if (opts.scroll !== false) scrollIntoPane(measureById.get(measureId));
  }

  function selectPhrase(phraseId, opts = {}) {
    const phrase = data.phrases[phraseId];
    if (!phrase) return;
    selectedPhraseId = phraseId;
    // Selecting a phrase from the list lands on its first measure, so the
    // score and the sidebar always agree about where you are.
    const first = phrase.measureIds.find((id) => measureById.has(id));
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

  // A trouble spot lives inside a phrase, and selecting it must not throw the
  // phrase away -- "explore a local trouble spot without losing the parent
  // phrase context" is the requirement. So selection carries both: the thing
  // selected, and the phrase it belongs to. For a plain phrase they are equal.
  function parentOf(id) {
    const entry = id ? data.phrases[id] : null;
    return entry && entry.parentId ? entry.parentId : id;
  }

  function paint() {
    const contextPhraseId = parentOf(selectedPhraseId);

    for (const el of measureEls) {
      const id = el.dataset.measureId;
      el.classList.toggle("is-selected", id === selectedMeasureId);
      el.classList.toggle(
        "in-selected-phrase",
        contextPhraseId != null && el.dataset.phraseId === contextPhraseId && id !== selectedMeasureId
      );
      if (id === selectedMeasureId) el.setAttribute("aria-current", "true");
      else el.removeAttribute("aria-current");
    }
    for (const el of outlines) {
      const id = el.dataset.phraseId;
      // The parent stays outlined while a spot inside it is selected.
      el.classList.toggle("is-selected", id === selectedPhraseId || id === contextPhraseId);
      el.classList.toggle(
        "is-context",
        id === contextPhraseId && id !== selectedPhraseId
      );
    }
    for (const el of phraseItems) {
      const id = el.dataset.phraseId;
      const on = id === selectedPhraseId;
      el.classList.toggle("is-selected", on);
      el.classList.toggle("is-context", !on && id === contextPhraseId);
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

  function renderSidebar() {
    const measure = selectedMeasureId ? data.measures[selectedMeasureId] : null;
    const phrase = selectedPhraseId ? data.phrases[selectedPhraseId] : null;

    if (!measure && !phrase) return;

    if (phrase) {
      const parentId = phrase.parentId;
      const parent = parentId ? data.phrases[parentId] : null;
      show(el("sel-breadcrumb"), Boolean(parent));
      if (parent) el("sel-breadcrumb").textContent = `${parent.label} ›`;

      el("sel-title").textContent = parent ? "Hard spot" : phrase.label;
      // Only name the selected measure when it adds something. On a one-measure
      // trouble spot "measure 2 · measure 2 selected" is just noise.
      const alreadyNamed = phrase.rangeText === `measure ${measure ? measure.label : ""}`;
      el("sel-range").textContent =
        phrase.rangeText +
        (measure && !alreadyNamed ? ` · measure ${measure.label} selected` : "");
      show(el("sel-rating-row"), true);
      el("sel-score").textContent = phrase.isRated ? phrase.scoreText : "—";
      el("sel-category").textContent = phrase.isRated ? phrase.category : data.unratedLabel;
      el("sel-peak").textContent =
        phrase.isRated && phrase.peakMeasureLabel
          ? `hardest measure ${phrase.peakMeasureLabel}: ${phrase.peakText}`
          : "";
      show(el("sel-unrated"), !phrase.isRated);
      el("sel-unrated").textContent = phrase.unratedReason;

      // A rated phrase can still contain a measure nobody could read. The
      // ribbon hatches it, and so must the sidebar: otherwise the phrase's
      // number looks like it covers music it was never computed from.
      const flagged = measure && !measure.isRated;
      show(el("sel-measure-note"), Boolean(flagged));
      if (flagged) {
        el("sel-measure-note").textContent =
          `Measure ${measure.label} is unrated — ${measure.qualityNote}. ` +
          "This phrase's rating comes from the measures around it.";
      }

      const hasFactors = phrase.factors.length > 0;
      show(el("why-panel"), hasFactors);
      if (hasFactors) {
        renderFactors(phrase.factors);
        el("sel-factors-note").textContent = phrase.peakMeasureLabel
          ? `Measured on measure ${phrase.peakMeasureLabel}, the most demanding measure in this phrase.`
          : "";
      }

      show(el("boundary-panel"), true);
      el("sel-start").textContent = `${phrase.startReason} — ${phrase.startConfidence}`;
      el("sel-end").textContent = `${phrase.endReason} — ${phrase.endConfidence}`;
      el("sel-practice").textContent = phrase.practiceText;

      practice.load(selectedPhraseId);
    } else if (measure) {
      // An unreadable or never-attempted measure. It belongs to no phrase, and
      // saying which of those it is matters: one is a judgement about the
      // notation, the other is a judgement about us.
      show(el("sel-breadcrumb"), false);
      el("sel-title").textContent = `Measure ${measure.label}`;
      el("sel-range").textContent = "Not part of an analyzed phrase.";
      show(el("sel-rating-row"), false);
      show(el("sel-unrated"), true);
      el("sel-unrated").textContent = `${data.unratedLabel} — ${measure.qualityNote}`;
      show(el("sel-measure-note"), false);
      show(el("why-panel"), false);
      show(el("boundary-panel"), false);
      practice.clear(
        "This measure is not part of an analyzed phrase, so there is no passage to build an exercise from."
      );
    }
  }

  function renderFactors(factors) {
    const list = el("sel-factors");
    list.textContent = "";
    for (const factor of factors) {
      const li = document.createElement("li");
      const label = document.createElement("span");
      label.textContent = factor.detail ? `${factor.label} — ${factor.detail}` : factor.label;
      const weight = document.createElement("span");
      weight.className = "factor-weight";
      weight.textContent = factor.contribution;
      li.append(label, weight);
      list.append(li);
    }
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
    item.addEventListener("click", () => selectPhrase(item.dataset.phraseId));
  }

  for (const outline of outlines) {
    outline.addEventListener("click", () => selectPhrase(outline.dataset.phraseId));
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

  if (data.defaultPhraseId) selectPhrase(data.defaultPhraseId, { focus: false });
  else if (order.length) setRovingTarget(order[0]);
}
