// Every tool in the nav, reached the way a learner reaches it: through the hash router.
//
// This exists because the other harnesses import a view's render function by name and call it
// directly, which skips app.js entirely. A tool whose export the router did not know about
// therefore rendered a blank pane with the whole suite green. Here nothing is imported by name:
// the hash is set, route() runs, and the pane either has content or it does not.
import { installDom } from "./dom.mjs";

const LEARN = process.argv[2];

const els = installDom(["#search", "#banner", "#learn-nav", "#learn-crumb", "#learn-progress",
                        "#learn-main"]);
globalThis.fetch = (url) => {
  // Enough of a body for any tool to draw something; each view has its own harness for content.
  const body = String(url).includes("/gaps")
    ? {verdict: "NOT_RELEASABLE", asil: "B", generated: "now", basis: "b",
       totals: {ok: 1, warn: 0, missing: 0},
       phases: [{phase: 1, title: "Concept", rows: [
         {work_product: "HARA", agent: "sys-hara", state: "ok", why: ["fine"],
          checklist_ref: "HARA", module_id: null}]}]}
    : {groups: [], modules: [], paths: [], glossary: {}, content_errors: [], pass_mark: 0.8,
       ready: true, seed: 1, scenarios: [], items: [],
       goal: {id: "SG-01", text: "goal", work_product: "SG"}, rows: [],
       questions: {link: {title: "t", prompt: "p", options: [{text: "o", why: "w"}], answer: 0},
                   phase: {title: "t", prompt: "p", options: [{text: "o", why: "w"}], answer: 0},
                   evidence: {title: "t", prompt: "p", options: [{text: "o", why: "w"}], answer: 0}},
       table: {}, keys: []};
  return Promise.resolve({ok: true, status: 200, headers: {get: () => null},
                          json: () => Promise.resolve(body),
                          text: () => Promise.resolve(JSON.stringify(body))});
};

const app = await import(`${LEARN}/app.js`);
const { TOOLS } = await import(`${LEARN}/nav.js`);
await new Promise(r => setTimeout(r, 20));

const drawn = {};
for (const t of TOOLS) {
  els["#learn-main"].innerHTML = "";
  globalThis.location.hash = `#/tool/${t.id}`;
  await app.route();
  await new Promise(r => setTimeout(r, 20));
  drawn[t.id] = {chars: els["#learn-main"].innerHTML.length,
                 crumb: els["#learn-crumb"].textContent};
}
console.log(JSON.stringify(drawn, null, 2));
