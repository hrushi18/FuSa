// One card at a time. The brief asks for flashcards, not a specification: the pager exists to
// stop a lesson becoming a wall of text.
import { saveProgress } from "./progress.js";
import { PHASES, vmodelSvg } from "./vmodel.js";
import { esc } from "./esc.js";

const KIND = { concept: "Concept", example: "Worked example",
               why: "Why it matters", diagram: "Where this sits", tool: "Try it" };

function cardHtml(card) {
  if (card.type === "diagram") {
    const reveal = PHASES.includes(card.reveal) ? card.reveal : "all";
    return `<div class="card diagram"><span class="kind">${KIND.diagram}</span>
      ${vmodelSvg(reveal, card.alt || "")}</div>`;
  }
  if (card.type === "tool") {
    // The launch is a plain hash link — the router already handles #/tool/<id>, so no
    // click handler needs writing here, and the back button works like everywhere else.
    return `<div class="card tool">
      <span class="kind">${KIND.tool}</span>
      ${card.title ? `<h3>${esc(card.title)}</h3>` : ""}
      <p>${esc(card.body)}</p>
      <a class="tool-launch" href="#/tool/${esc(card.tool)}">Open the tool →</a></div>`;
  }
  return `<div class="card ${esc(card.type)}">
    <span class="kind">${KIND[card.type] || ""}</span>
    ${card.title ? `<h3>${esc(card.title)}</h3>` : ""}
    <p>${esc(card.body)}</p></div>`;
}

function inlineCheckHtml(check) {
  return `<div class="card"><span class="kind">Quick check — not scored</span>
    <h3>${esc(check.prompt)}</h3>
    ${check.options.map((o, i) => `<button class="opt" data-i="${i}">${esc(o)}</button>`).join("")}
    <div class="why-line" id="ic-why" hidden></div></div>`;
}

export function renderModule(mod, host) {
  let at = 0;
  let best = 0;
  const cards = mod.cards || [];
  const total = cards.length + (mod.inline_check ? 1 : 0);

  const record = () => {
    if (at + 1 <= best) return;                 // only ever report forward progress
    best = at + 1;
    saveProgress(mod.id, {cards_seen: best});
  };

  // A module with no cards and no inline check is not a content-rule error, so it reaches the
  // renderer intact — and cards[0] would be undefined here. Hence an explicit empty state.
  const draw = () => {
    if (total === 0) {
      const hasQuiz = (mod.quiz || []).length > 0;
      host.innerHTML = `<h2 style="font-size:16px;margin:0 0 4px">${esc(mod.title)}</h2>
        <p style="color:var(--dim);font-size:11px;margin:0 0 16px">
          ${esc((mod.clauses || []).join(" · ") || "no clause reference")}</p>
        <div class="card"><span class="kind">No content yet</span>
          <p>This module has no cards yet.</p></div>
        ${hasQuiz ? `<div class="pager"><button id="next">Take the quiz →</button></div>` : ""}`;
      if (hasQuiz) {
        host.querySelector("#next").onclick = async () => {
          const { startQuiz } = await import("./quiz.js");
          startQuiz(mod, host);
        };
      }
      return;
    }
    const isCheck = mod.inline_check && at === cards.length;
    host.innerHTML = `<h2 style="font-size:16px;margin:0 0 4px">${esc(mod.title)}</h2>
      <p style="color:var(--dim);font-size:11px;margin:0 0 16px">
        ${esc((mod.clauses || []).join(" · ") || "no clause reference")}</p>
      ${isCheck ? inlineCheckHtml(mod.inline_check) : cardHtml(cards[at])}
      <div class="pager">
        <button id="prev" ${at === 0 ? "disabled" : ""}>← back</button>
        <span class="dots">${at + 1} / ${total}</span>
        <button id="next">${at + 1 === total
          ? ((mod.quiz || []).length ? "Take the quiz →" : "Done")
          : "next →"}</button>
      </div>
      ${mod.work_products?.length ? `<div class="wp">In a real safety file this becomes
        ${mod.work_products.map(w => `<code>${esc(w)}</code>`).join(", ")} — the workbench
        checks it against <code>${esc(mod.checklist_ref || "generic")}</code>.</div>` : ""}`;

    host.querySelector("#prev").onclick = () => { at--; draw(); };
    host.querySelector("#next").onclick = async () => {
      if (at + 1 < total) { at++; draw(); return; }
      if ((mod.quiz || []).length) {
        const { startQuiz } = await import("./quiz.js");
        startQuiz(mod, host);
      }
    };
    if (isCheck) {
      host.querySelectorAll(".opt").forEach(el => {
        el.onclick = () => {
          const right = Number(el.dataset.i) === mod.inline_check.answer;
          el.classList.add(right ? "right" : "wrong");
          const why = host.querySelector("#ic-why");
          why.hidden = false;
          why.textContent = mod.inline_check.explanation;
        };
      });
    }
    record();
  };

  draw();
}
