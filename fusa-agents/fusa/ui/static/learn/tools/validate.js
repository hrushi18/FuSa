// This project's own safety file, phase by phase — ✅ / ⚠️ / ❌ against every work product the
// release report already assesses.
//
// The view adds no judgement of its own. Every state, every reason and the verdict come from
// /api/learn/gaps, which is `report.validate()` joined to the phase each agent sits in and to
// the module that teaches its checklist. If a mark here disagreed with /report.pdf this file
// would be the one that is wrong, so nothing below re-decides anything: it renders what came.
import { api, banner } from "../app.js";
import { esc } from "../esc.js";

const ICON = {ok: "✅", warn: "⚠️", missing: "❌"};

const WORD = {ok: "in order", warn: "needs work", missing: "not there yet"};

const head = `<h2 style="font-size:16px;margin:0 0 4px">Validate My FuSa System</h2>
  <p style="color:var(--dim);font-size:11px;margin:0 0 16px">
    Your project read down the V-model, one row per work product. These are the assessments
    <code>/report.pdf</code> renders — the course and the release report are one list, not two
    kept in step by hand.</p>`;

const rowHtml = (r) => `
  <tr class="gap-row gap-${esc(r.state)}" data-wp="${esc(r.work_product)}">
    <td class="gap-ico">${ICON[r.state] ?? "❔"}</td>
    <td class="gap-wp"><code>${esc(r.work_product)}</code>
        <span class="dots">${esc(r.agent)}</span></td>
    <td>${(r.why || []).map(w => esc(w)).join("<br>") || esc(WORD[r.state] ?? r.state)}</td>
    <td class="gap-lesson">${r.module_id
      ? `<a href="#/${esc(r.module_id)}">learn what this checks →</a>`
      : `<span class="dots">no lesson yet</span>`}</td></tr>`;

const phaseHtml = (p) => `
  <section class="gap-phase">
    <h3>Phase ${esc(p.phase)} · ${esc(p.title)}</h3>
    <table class="trace">${p.rows.map(rowHtml).join("")}</table>
  </section>`;

// Every row missing is a project nobody has run yet. Stamping NOT_RELEASABLE on that reads as a
// finding about the learner's safety file when it is really a starting point, so it is not shown.
const firstRun = (rep) => head + `
  <div class="card">
    <span class="kind">nothing to validate yet</span>
    <h3>Nothing has been generated yet</h3>
    <p>All ${esc(rep.totals.missing)} work products are still unwritten, so there is no gap to
    report — only a chain that has not been run.</p>
    <div class="pager" style="margin:14px 0 0">
      <a href="/" style="color:var(--accent)">Open the board and run the chain →</a>
    </div>
  </div>`;

const summary = (rep) => `
  <div class="verdict">
    <b>${esc(rep.verdict)}</b> at ASIL ${esc(rep.asil)}
    <div class="parts">
      <span class="ok">✅ ${esc(rep.totals.ok)} in order</span>
      <span class="warn">⚠️ ${esc(rep.totals.warn)} need work</span>
      <span class="no">❌ ${esc(rep.totals.missing)} not there yet</span>
    </div>
    <p class="hint" style="margin-top:10px">${esc(rep.basis)}</p>
  </div>`;

export function renderValidate(host) {
  host.innerHTML = head + `<p class="hint">reading your project…</p>`;
  api("/api/learn/gaps").then(rep => {
    const rows = rep.phases.flatMap(p => p.rows);
    if (rows.length && rows.every(r => r.state === "missing")) {
      host.innerHTML = firstRun(rep);
      return;
    }
    host.innerHTML = head + summary(rep) + rep.phases.map(phaseHtml).join("")
      + `<p class="hint" style="margin-top:14px">Generated ${esc(rep.generated)}. A row that
         disagrees with <code>/report.pdf</code> is a bug in this page, not in the report.</p>`;
  }).catch(err => {
    host.innerHTML = head + `<p class="hint">your project could not be read</p>`;
    banner(`the gap report could not be built — ${err.message}`);
  });
}
