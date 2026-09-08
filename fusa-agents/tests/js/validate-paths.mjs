// Drives "Validate My FuSa System" under node against a scripted gap report.
//
// The report is written here rather than built from a project on purpose: the view's whole job
// is to say what the server said, so the interesting inputs are the ones a real run rarely
// produces together — all three states side by side, a row with a lesson next to one without,
// and a phase list that must come out in lifecycle order rather than in map order.
import { installDom } from "./dom.mjs";

const LEARN = process.argv[2];                       // path to static/learn

installDom(["#search", "#banner", "#learn-nav", "#learn-crumb", "#learn-progress", "#learn-main"]);
let fetchPlan = [];
globalThis.fetch = () => {
  const next = fetchPlan.shift() ?? {ok: true, body: {}};
  return Promise.resolve({
    ok: next.ok, status: next.status ?? (next.ok ? 200 : 500),
    headers: {get: () => null},
    json: () => Promise.resolve(next.body),
    text: () => Promise.resolve(typeof next.body === "string" ? next.body : JSON.stringify(next.body)),
  });
};
fetchPlan = [{ok: true, body: {groups: [], modules: [], paths: [], glossary: {},
                               content_errors: [], pass_mark: 0.8}},
             {ok: true, body: {modules: {}, pass_mark: 0.8}}];
await import(`${LEARN}/app.js`);
const { renderValidate } = await import(`${LEARN}/tools/validate.js`);
await new Promise(r => setTimeout(r, 20));

const BASIS = "No language model produced or judged any part of this report: 16 table, "
            + "derived from input tables and analyser output.";

// Three states, two phases, and one row of each kind of lesson link.
const REPORT = {
  verdict: "NOT_RELEASABLE", asil: "B", generated: "2026-09-08T10:00:00+00:00", basis: BASIS,
  totals: {ok: 1, warn: 1, missing: 1},
  phases: [
    {phase: 1, title: "Concept & Requirements", rows: [
      {work_product: "HARA", agent: "sys-hara", state: "ok",
       why: ["the gate passed and the review accepted it"],
       checklist_ref: "HARA", module_id: "concept.hara"},
      {work_product: "HSR", agent: "sys-hsr", state: "warn",
       why: ["1 [PENDING] marker", "a minor finding is still open"],
       checklist_ref: "generic", module_id: null},
    ]},
    {phase: 2, title: "System Analysis", rows: [
      {work_product: "SADS", agent: "sys-arch", state: "missing",
       why: ["has not been written yet"],
       checklist_ref: "SADS", module_id: "system.sads"},
    ]},
  ],
};

// A project on which nothing has been run: every row missing, which is a starting point rather
// than a finding about the learner's safety file.
const FIRST_RUN = {
  verdict: "NOT_RELEASABLE", asil: "B", generated: "2026-09-08T10:00:00+00:00", basis: BASIS,
  totals: {ok: 0, warn: 0, missing: 2},
  phases: [
    {phase: 1, title: "Concept & Requirements", rows: [
      {work_product: "HARA", agent: "sys-hara", state: "missing",
       why: ["has not been written yet"], checklist_ref: "HARA", module_id: "concept.hara"},
    ]},
    {phase: 2, title: "System Analysis", rows: [
      {work_product: "SADS", agent: "sys-arch", state: "missing",
       why: ["has not been written yet"], checklist_ref: "SADS", module_id: null},
    ]},
  ],
};

function fakeHost() {
  return {innerHTML: "", querySelector: () => ({onclick: null, value: "", disabled: false}),
          querySelectorAll: () => []};
}

async function draw(body) {
  const host = fakeHost();
  fetchPlan = [{ok: true, body}];
  renderValidate(host);
  await new Promise(r => setTimeout(r, 20));
  return host.innerHTML;
}

// Splitting on the row marker bounds each row's markup: a chunk runs to the start of the next
// row, so a link found in it is that row's link and not the one below it.
function rowsOf(html) {
  return html.split('data-wp="').slice(1).map(chunk => {
    const wp = chunk.slice(0, chunk.indexOf('"'));
    const icon = (chunk.match(/class="gap-ico"[^>]*>\s*([^\s<]*)\s*</) || [])[1] ?? null;
    const link = (chunk.match(/href="#\/([^"]*)"/) || [])[1] ?? null;
    // Counted apart from the href: a lesson link with an empty target is still a link on the
    // page, and a row that should have none must not offer one to click.
    const offered = chunk.includes("learn what this checks");
    return {wp, icon, link, offered};
  });
}

const sectionsOf = html =>
  [...html.matchAll(/<section class="gap-phase">\s*<h3>([^<]*)<\/h3>/g)].map(m => m[1].trim());

const results = {};
results.html = await draw(REPORT);
results.rows = rowsOf(results.html);
results.sections = sectionsOf(results.html);

results.first_run_html = await draw(FIRST_RUN);
results.first_run_rows = rowsOf(results.first_run_html);

// Every field the server sends is spliced into markup, so one hostile work product and one
// hostile reason are enough to tell whether they go through esc().
results.hostile_html = await draw({...REPORT, basis: '<script>alert("basis")</script>',
  phases: [{phase: 1, title: "Concept & Requirements", rows: [
    {work_product: '<script>alert("wp")</script>', agent: "sys-hara", state: "warn",
     why: ['<script>alert("why")</script>'], checklist_ref: "HARA", module_id: null}]}]});

console.log(JSON.stringify(results, null, 2));
