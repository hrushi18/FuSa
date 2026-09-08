// A branch of the project's own safety case, with one `parent:` link taken out. The case is
// built by the server from `_generated/`, walking the links the traceability agent walks, so a
// learner who finds the break here has read the same structure the chain reports on.
//
// The whole reason the three questions are scored apart: a break high in a branch empties every
// level under it, so a reviewer who names the lowest empty level has spotted a symptom and
// missed the cause. That is a different mistake from knowing the break and not knowing who owns
// the fix, and a single percentage would hide which one the learner made.
import { api, banner } from "../app.js";
import { esc } from "../esc.js";

export const PARTS = ["link", "phase", "evidence"];

const NAMES = {link: "the broken link", phase: "the phase that owns the fix",
               evidence: "the evidence that closes it"};

const verdictLine = (parts, right) => {
  if (right === parts.length) return "All three right — the break, its owner and its remedy.";
  const got = parts.filter(p => p.right).map(p => NAMES[p.key]);
  const missed = parts.filter(p => !p.right).map(p => NAMES[p.key]);
  if (!got.length) return `None of the three yet — not ${missed.join(", not ")}.`;
  return `${right} of ${parts.length} — right about ${got.join(" and ")}, `
       + `wrong about ${missed.join(" and ")}.`;
};

/** Three independent judgements, never one number. Each part carries the reason for what the
 *  learner picked and, when that was wrong, the reason for what was right. */
export function scoreTrace(kase, picked) {
  const parts = PARTS.map(key => {
    const q = kase.questions[key];
    const chose = picked[key];
    const answered = Number.isInteger(chose) && chose >= 0 && chose < q.options.length;
    return {
      key, title: q.title, answered, chose: answered ? chose : null, answer: q.answer,
      right: answered && chose === q.answer,
      why: answered ? q.options[chose].why : "This part went unanswered.",
      keyText: q.options[q.answer].text, keyWhy: q.options[q.answer].why,
    };
  });
  const right = parts.filter(p => p.right).length;
  return {parts, right, of: parts.length, score: right / parts.length,
          verdict: verdictLine(parts, right)};
}

const head = `<h2 style="font-size:16px;margin:0 0 4px">Traceability Lab</h2>
  <p style="color:var(--dim);font-size:11px;margin:0 0 16px">
    One safety goal of your project, carried down the V with a link removed. The branch is read
    from <code>_generated/</code> over the same <code>parent:</code> links the traceability
    agent walks.</p>`;

export function renderTrace(host) {
  let kase = null, picked = {}, result = null;
  let seed = Math.floor(Math.random() * 100000);

  const notReady = (r) => {
    host.innerHTML = head + `
      <div class="card">
        <span class="kind">nothing to trace yet</span>
        <h3>Run the chain first</h3>
        <p>This lab breaks a link in your project's real safety case, so there has to be one:
        ${esc(r.reason || "no work products have been generated")}.</p>
        <p class="hint" style="margin-top:10px">Missing from
        <code>_generated/</code>: ${esc((r.missing || []).join(", ") || "everything")}.</p>
        <div class="pager" style="margin:14px 0 0">
          <a href="/" style="color:var(--accent)">Open the board and run the chain →</a>
        </div>
      </div>`;
  };

  const matrixHtml = () => `
    <div class="card">
      <span class="kind">${esc(kase.goal.work_product)} · ${esc(kase.goal.id)}${
        kase.goal.asil ? ` · ASIL ${esc(kase.goal.asil)}` : ""}</span>
      <h3>${esc(kase.goal.text || kase.goal.id)}</h3>
      <table class="trace">
        <tr><th>level</th><th>owner</th><th>phase</th><th>traces to the goal</th></tr>
        ${kase.rows.map(r => `
          <tr class="${r.id ? "" : "gapped"}">
            <td><code>${esc(r.work_product)}</code></td>
            <td title="${esc(r.title)}">${esc(r.agent)}</td>
            <td>${esc(r.phase)}</td>
            <td>${r.id ? `<code>${esc(r.id)}</code>` : "—"}</td></tr>`).join("")}
      </table>
      <p class="hint" style="margin-top:10px">Empty cells are what a break looks like: the
      matrix is derived from the links, so a missing link is silence rather than a claim.</p>
    </div>`;

  const questionHtml = (key, n) => {
    const q = kase.questions[key];
    const part = result?.parts.find(p => p.key === key);
    return `<div class="card">
      <span class="kind">part ${"abc"[n]} · ${esc(q.title)}</span>
      <p>${esc(q.prompt)}</p>
      <div class="answer">${q.options.map((o, i) => {
        const mark = !result ? (picked[key] === i ? "picked" : "")
                   : i === q.answer ? "right" : (picked[key] === i ? "wrong" : "");
        return `<button class="opt ${mark}" data-q="${esc(key)}" data-i="${i}"
                  ${result ? "disabled" : ""}>${esc(o.text)}</button>`;
      }).join("")}</div>
      ${part ? `<div class="why-line"><b>${part.right ? "right" : "not this one"}</b> —
        ${esc(part.why)}${part.right ? "" :
          ` <br><b>${esc(part.keyText)}</b> — ${esc(part.keyWhy)}`}</div>` : ""}
    </div>`;
  };

  const verdictHtml = () => `
    <div class="verdict">
      <b>${esc(result.verdict)}</b>
      <div class="parts">${result.parts.map(p => `
        <span class="${p.right ? "ok" : "no"}">${p.right ? "✓" : "✗"}
          ${esc(NAMES[p.key])}</span>`).join("")}</div>
      <p class="hint" style="margin-top:10px">Scored a part at a time on purpose — naming the
      break and naming its owner are two different things to have learned.</p>
    </div>`;

  const draw = () => {
    const answered = PARTS.every(k => Number.isInteger(picked[k]));
    host.innerHTML = head + matrixHtml()
      + PARTS.map((k, n) => questionHtml(k, n)).join("")
      + (result ? verdictHtml() : "")
      + `<div class="pager" style="margin-top:14px">
          ${result ? "" : `<button id="check" ${answered ? "" : "disabled"}>Check my answers</button>`}
          <button id="again">Another case</button>
          <label class="dots" for="seed">seed</label>
          <input id="seed" class="seedbox" type="number" value="${esc(kase.seed)}">
          <button id="load">Load it</button>
        </div>
        <p class="hint">The seed picks the case, so a class can all be given the same one.</p>`;
    wire();
  };

  const wire = () => {
    host.querySelectorAll(".opt[data-q]").forEach(el => {
      el.onclick = () => { picked[el.dataset.q] = Number(el.dataset.i); draw(); };
    });
    const check = host.querySelector("#check");
    if (check) check.onclick = () => { result = scoreTrace(kase, picked); draw(); };
    host.querySelector("#again").onclick = () => load(Math.floor(Math.random() * 100000));
    host.querySelector("#load").onclick = () => {
      const wanted = Number(host.querySelector("#seed").value);
      load(Number.isFinite(wanted) ? Math.trunc(wanted) : seed);
    };
  };

  const load = (want) => {
    seed = want;
    picked = {}; result = null;
    host.innerHTML = head + `<p class="hint">building a case from your project…</p>`;
    api(`/api/learn/trace?seed=${encodeURIComponent(seed)}`).then(r => {
      if (!r.ready) { notReady(r); return; }
      kase = r;
      draw();
    }).catch(err => {
      host.innerHTML = head + `<p class="hint">the case could not be built</p>`;
      banner(`the traceability lab could not build a case — ${err.message}`);
    });
  };

  load(seed);
}
