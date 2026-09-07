// Scoring lives here; what counts as a pass lives on the server. The engine posts a fraction
// and lets the server decide, so the threshold is one configurable value rather than a number
// duplicated in the browser.
import { state } from "./app.js";
import { saveProgress } from "./progress.js";
import { esc } from "./esc.js";

const same = (a, b) => a.length === b.length && a.every(x => b.includes(x));

export function startQuiz(mod, host) {
  const questions = mod.quiz || [];
  const picked = questions.map(q => (q.type === "multi" ? [] : null));
  let submitted = false;

  const scoreOf = () => questions.reduce((n, q, i) => {
    const want = q.type === "multi" ? q.answer : [q.answer];
    const got = q.type === "multi" ? picked[i] : (picked[i] === null ? [] : [picked[i]]);
    return n + (same(want, got) ? 1 : 0);
  }, 0);

  const answered = () => picked.filter(p => (Array.isArray(p) ? p.length : p !== null)).length;

  const draw = () => {
    const score = scoreOf();
    const passed = score / questions.length >= state.passMark;
    host.innerHTML = `<h2 style="font-size:16px;margin:0 0 4px">${esc(mod.title)} — quiz</h2>
      <p style="color:var(--dim);font-size:11px;margin:0 0 16px">
        ${questions.length} question${questions.length === 1 ? "" : "s"} ·
        ${Math.round(state.passMark * 100)}% to pass · retakes keep your best score</p>
      <div class="qz">${questions.map((q, i) => {
        const want = q.type === "multi" ? q.answer : [q.answer];
        return `<div class="card">
          <span class="kind">${esc(q.type === "multi" ? "Choose all that apply" : "Question")} ${i + 1}</span>
          <h3>${esc(q.prompt)}</h3>
          ${q.options.map((o, oi) => {
            const chosen = q.type === "multi" ? picked[i].includes(oi) : picked[i] === oi;
            let cls = chosen ? "picked" : "";
            if (submitted) cls = want.includes(oi) ? "right" : chosen ? "wrong" : "";
            return `<button class="opt ${cls}" data-q="${i}" data-o="${oi}"
                      ${submitted ? "disabled" : ""}>${esc(o)}</button>`;
          }).join("")}
          ${submitted ? `<div class="why-line">${esc(q.explanation)}</div>` : ""}
        </div>`;
      }).join("")}</div>
      <div class="pager">
        ${submitted
          ? `<button id="retake">Retake</button><button id="back">Back to the cards</button>
             <span class="dots">${score} / ${questions.length} — ${passed ? "passed" : "needs review"}</span>`
          : `<button id="submit">Submit</button>
             <span class="dots">${answered()} of ${questions.length} answered</span>`}
      </div>`;

    host.querySelectorAll(".opt:not([disabled])").forEach(el => {
      el.onclick = () => {
        const qi = Number(el.dataset.q), oi = Number(el.dataset.o);
        if (questions[qi].type === "multi") {
          const idx = picked[qi].indexOf(oi);
          idx === -1 ? picked[qi].push(oi) : picked[qi].splice(idx, 1);
        } else picked[qi] = oi;
        draw();
      };
    });
    if (submitted) {
      host.querySelector("#retake").onclick = () => {
        submitted = false;
        questions.forEach((q, i) => { picked[i] = q.type === "multi" ? [] : null; });
        draw();
      };
      host.querySelector("#back").onclick = async () => {
        const { renderModule } = await import("./module.js");
        renderModule(mod, host);
      };
    } else {
      host.querySelector("#submit").onclick = () => {
        submitted = true;
        draw();
        saveProgress(mod.id, {score: scoreOf() / questions.length});
      };
    }
  };

  draw();
}
