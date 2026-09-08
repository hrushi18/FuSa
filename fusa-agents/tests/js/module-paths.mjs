// Runs renderModule for real, so "a tool card launches a tool" is proven by executing the
// renderer rather than grepping module.js for a substring that could sit in a dead branch.
import { installDom } from "./dom.mjs";
const LEARN = process.argv[2];
installDom(["#search", "#banner", "#learn-nav", "#learn-crumb", "#learn-progress", "#learn-main"]);
// Scripted by URL rather than by a queue. Every draw writes progress, so a queue hands the
// lesson's gap-report response to a progress write and leaves the lesson reading `{}` — which
// is exactly what happened the first time this was written as a queue.
const BOOT = {
  "/api/learn/content": {groups: [], modules: [], paths: [], glossary: {},
                         content_errors: [], pass_mark: 0.8},
  "/api/learn/progress": {modules: {}, pass_mark: 0.8},
};
let responses = {};
globalThis.fetch = (url) => {
  const body = responses[String(url).split("?")[0]] ?? BOOT[String(url).split("?")[0]] ?? {};
  return Promise.resolve({
    ok: true, status: 200, headers: {get: () => null},
    json: () => Promise.resolve(body),
    text: () => Promise.resolve(JSON.stringify(body)),
  });
};
await import(`${LEARN}/app.js`);
const { renderModule } = await import(`${LEARN}/module.js`);
await new Promise(r => setTimeout(r, 20));

function makeHost() {
  return {
    innerHTML: "",
    querySelector: () => ({onclick: null, querySelectorAll: () => []}),
    querySelectorAll: () => [],
  };
}

const mod = {
  id: "concept.hara", title: "Hazard Analysis", clauses: [],
  cards: [{type: "tool", tool: "hara", title: "Build this hazard as a row",
           body: "Open the HARA Builder and finish the row."}],
};
const host = makeHost();
renderModule(mod, host);

// ---- the loop back: how this project's own file fares against the checklist just taught ----
//
// Rendered against a scripted /api/learn/gaps rather than a real project, because the three
// cases that matter — a lesson with a work product, one without, and a project nobody has run
// — do not occur together in any single run.
const REPORT = {
  verdict: "NOT_RELEASABLE", asil: "B", generated: "now", basis: "b",
  totals: {ok: 1, warn: 1, missing: 0},
  phases: [{phase: 1, title: "Concept & Requirements", rows: [
    {work_product: "HARA", agent: "sys-hara", state: "warn",
     why: ["1 unresolved [PENDING] marker(s)"], checklist_ref: "HARA", module_id: "concept.hara"},
    {work_product: "TSC", agent: "sys-tsc", state: "ok", why: [],
     checklist_ref: "TSC", module_id: null}]}]};

const FRESH = {...REPORT, totals: {ok: 0, warn: 0, missing: 2},
  phases: [{phase: 1, title: "Concept & Requirements", rows: REPORT.phases[0].rows.map(
    r => ({...r, state: "missing", why: ["status is not_started, expected reviewed"]}))}]};

async function drawWith(m, body) {
  const h = makeHost();
  responses = {"/api/learn/gaps": body};
  renderModule(m, h);
  await new Promise(r => setTimeout(r, 20));
  return h.innerHTML;
}

const lesson = (extra) => ({id: "concept.hara", title: "Hazard Analysis", clauses: [],
  cards: [{type: "concept", title: "t", body: "b"}], ...extra});

const out = {html: host.innerHTML};
out.taught = await drawWith(lesson({work_products: ["HARA"], checklist_ref: "HARA"}), REPORT);
out.untaught = await drawWith(lesson({work_products: [], checklist_ref: null}), REPORT);
out.fresh = await drawWith(lesson({work_products: ["HARA"], checklist_ref: "HARA"}), FRESH);
// A lesson naming a work product the report has no row for: normal while content runs ahead
// of the chain, and it must not put a mark on the page it cannot support.
out.unknown = await drawWith(lesson({work_products: ["NOPE"], checklist_ref: "NOPE"}), REPORT);
// The report is server data spliced into the lesson footer like any other.
out.hostile = await drawWith(lesson({work_products: ["HARA"], checklist_ref: "HARA"}),
  {...REPORT, phases: [{phase: 1, title: "c", rows: [
    {work_product: "HARA", agent: "a", state: "warn", why: ['<script>alert("why")</script>'],
     checklist_ref: "HARA", module_id: null}]}]});

console.log(JSON.stringify(out));
