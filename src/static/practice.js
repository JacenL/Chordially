/* Practice instruction for the selected passage.
 *
 * Every string rendered here was decided on the server, against that phrase's
 * own notes. This file arranges it; it does not compose advice, and it never
 * invents a fallback when the server says no technique fits. The rhythm
 * variants in particular are printed exactly as computed, because their whole
 * point is that the durations add up.
 */

export function createPractice(scoreKey, tempoBpm) {
  const el = (id) => document.getElementById(id);
  let token = 0;

  function clear(message) {
    const loading = el("practice-loading");
    const body = el("practice-body");
    const nofit = el("practice-nofit");
    if (body) body.hidden = true;
    if (nofit) nofit.hidden = true;
    if (loading) {
      loading.hidden = false;
      loading.textContent = message;
    }
  }

  async function load(phraseId) {
    if (!scoreKey || !phraseId) return;
    const mine = ++token;
    clear("Reading this passage…");
    try {
      // The active tempo goes with the request: rating factors drive technique
      // selection, and those move with tempo. Advice for a passage at 160 BPM
      // is not necessarily the advice for it at 90.
      const query = tempoBpm ? "?tempo=" + encodeURIComponent(tempoBpm) : "";
      const response = await fetch(
        "/api/practice/" + encodeURIComponent(scoreKey) + "/" +
          encodeURIComponent(phraseId) + query
      );
      if (mine !== token) return; // a newer selection has already won
      if (!response.ok) {
        clear("Practice instruction is unavailable for this passage.");
        return;
      }
      render(await response.json());
    } catch (err) {
      if (mine === token) clear("Could not reach the server for practice instruction.");
    }
  }

  function render(guidance) {
    const loading = el("practice-loading");
    const body = el("practice-body");
    const nofit = el("practice-nofit");
    if (loading) loading.hidden = true;

    if (!guidance.primary) {
      if (body) body.hidden = true;
      if (nofit) {
        nofit.hidden = false;
        nofit.textContent = guidance.noFitReason;
      }
      return;
    }
    if (nofit) nofit.hidden = true;
    if (body) body.hidden = false;

    el("practice-primary").replaceChildren(exerciseNode(guidance.primary, true));

    const alts = el("practice-alternatives");
    alts.replaceChildren();
    if (guidance.alternatives.length) {
      alts.append(para("exercise-alt-heading", "If that is not the problem"));
      for (const alternative of guidance.alternatives) {
        alts.append(exerciseNode(alternative, false));
      }
    }
  }

  function exerciseNode(exercise, primary) {
    const root = document.createElement(primary ? "div" : "details");
    root.className = "exercise-card" + (primary ? " exercise-card--primary" : "");

    const title = document.createElement(primary ? "h4" : "summary");
    title.className = "exercise-title";
    title.append(document.createTextNode(exercise.title));
    const badge = document.createElement("span");
    badge.className = "evidence-badge";
    // An app heuristic is marked differently from something a teacher or a
    // study actually backs. The reader should be able to tell at a glance.
    if (exercise.evidenceCategory === "app heuristic") {
      badge.classList.add("evidence-badge--heuristic");
    }
    badge.textContent = exercise.evidenceCategory;
    title.append(badge);
    root.append(title);

    root.append(
      para(
        "exercise-why",
        "Chosen because " + exercise.triggerReason + ". Applies to " + exercise.appliesTo + "."
      )
    );

    if (exercise.variants && exercise.variants.length) {
      const variants = document.createElement("div");
      variants.className = "variants";
      for (const variant of exercise.variants) {
        const block = document.createElement("div");
        block.className = "variant";
        block.append(para("variant-name", variant.name));
        block.append(para("variant-description", variant.description));

        const row = document.createElement("div");
        row.className = "variant-notes";
        for (const note of variant.notes) {
          const chip = document.createElement("span");
          chip.className = "variant-note variant-note--" + note.role;
          const pitch = document.createElement("b");
          pitch.textContent = note.pitch;
          const duration = document.createElement("i");
          duration.textContent = note.duration;
          chip.append(pitch, duration);
          row.append(chip);
        }
        block.append(row);
        variants.append(block);
      }
      root.append(variants);
      if (exercise.variantNote) root.append(para("panel-note", exercise.variantNote));
    }

    root.append(listBlock("Steps", exercise.steps, "ol"));
    root.append(listBlock("Listen for", exercise.listeningGoals, "ul"));

    const dl = document.createElement("dl");
    dl.className = "boundary-list";
    appendPair(dl, "Pace", exercise.tempoRule);
    appendPair(dl, "Ready to move on", exercise.successCriteria);
    appendPair(dl, "Back to the music", exercise.returnToContext);
    root.append(dl);

    for (const caution of exercise.cautions) root.append(para("panel-note", caution));

    if (exercise.sources.length) {
      root.append(sourcesNode(exercise.sources));
    }
    return root;
  }

  function sourcesNode(sources) {
    const details = document.createElement("details");
    details.className = "sources";
    const summary = document.createElement("summary");
    summary.textContent = "Sources (" + sources.length + ")";
    details.append(summary);

    for (const source of sources) {
      const item = document.createElement("div");
      item.className = "source";
      const link = document.createElement("a");
      link.href = source.url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = source.author + " — " + source.title;
      item.append(link);
      item.append(para("source-line", source.publication + " · " + source.evidenceCategory));
      item.append(para("source-line", "Supports: " + source.supports));
      // Printed with the same weight as what it does support. A source that is
      // allowed to carry only part of a claim should say so where it is cited.
      item.append(para("source-line source-line--limit", "Does not support: " + source.doesNotSupport));
      details.append(item);
    }
    return details;
  }

  function para(className, text) {
    const node = document.createElement("p");
    node.className = className;
    node.textContent = text;
    return node;
  }

  function appendPair(dl, term, value) {
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = value;
    dl.append(dt, dd);
  }

  function listBlock(heading, items, tag) {
    const wrapper = document.createElement("div");
    wrapper.append(para("exercise-subheading", heading));
    const list = document.createElement(tag);
    list.className = "exercise-list";
    for (const item of items) {
      const li = document.createElement("li");
      li.textContent = item;
      list.append(li);
    }
    wrapper.append(list);
    return wrapper;
  }

  return { load, clear };
}
