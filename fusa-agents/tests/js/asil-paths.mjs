// Runs the real ASIL calculator under node against a scripted server.
//
// The point is the third case. The S+E+C mnemonic reproduces the determination table exactly,
// so a calculator that derives its answer looks identical to one that reads the table — for
// every real value. These stub the server with answers the mnemonic would NOT produce, so a
// derivation is caught however it is spelled, renamed or hidden.
import { installDom } from "./dom.mjs";

const LEARN = process.argv[2];
installDom(["#search", "#banner", "#learn-nav", "#learn-crumb", "#learn-progress", "#learn-main"]);

let plan = [];
globalThis.fetch = () => {
  const next = plan.shift() ?? {ok: true, body: {}};
  return Promise.resolve({
    ok: next.ok, status: next.status ?? 200, headers: {get: () => null},
    json: () => Promise.resolve(next.body),
    text: () => Promise.resolve(JSON.stringify(next.body)),
  });
};
// app.js calls load() at import time
plan = [{ok: true, body: {groups: [], modules: [], paths: [], glossary: {},
                          content_errors: [], pass_mark: 0.8}},
        {ok: true, body: {modules: {}, pass_mark: 0.8}}];
await import(`${LEARN}/app.js`);
const { renderAsil } = await import(`${LEARN}/tools/asil.js`);
await new Promise(r => setTimeout(r, 20));

// a host that remembers what was written into it, including into #asil-out
function makeHost() {
  const out = {innerHTML: "", querySelectorAll: () => []};
  return {
    innerHTML: "",
    querySelector: sel => (sel === "#asil-out" ? out : {innerHTML: "", onchange: null}),
    querySelectorAll: () => [],
    get rendered() { return this.innerHTML + " " + out.innerHTML; },
  };
}

async function ask(body) {
  const host = makeHost();
  plan = [{ok: true, body}];
  renderAsil(host);
  await new Promise(r => setTimeout(r, 30));
  return host.rendered;
}

const results = {};
// the table says A where the mnemonic would say D
results.surprising = await ask({asil: "A", why: "S3-E4-C3 from the S×E×C table",
                                key: "S3-E4-C3", file: "asil-table.yaml", filled: 3, total: 36});
// the table says D where the mnemonic would say QM
results.surprising_low = await ask({asil: "D", why: "S1-E1-C1 from the S×E×C table",
                                    key: "S1-E1-C1", file: "asil-table.yaml", filled: 3, total: 36});
// an untranscribed cell must stay untranscribed
results.unfilled = await ask({asil: null, why: "S3-E4-C3", key: "S3-E4-C3",
                              file: "asil-table.yaml", filled: 0, total: 36});
console.log(JSON.stringify(results));
