// Boot, routing and the one piece of shared state. Routing is the URL hash so a module is
// linkable and the back button works, with no router library to install.
import { drawNav } from "./nav.js";

export const state = {
  groups: [], modules: [], paths: [], glossary: {}, passMark: 0.8,
  progress: {}, openGroups: new Set(), current: null,
};

const $ = s => document.querySelector(s);

// An error body is not always JSON — a 500 can arrive as an HTML page — and the server takes
// real trouble to name the offending file, so the message is worth recovering either way.
export const api = (p, opt) => fetch(p, opt).then(r => r.ok ? r.json()
  : r.text().then(t => {
      let detail = t;
      try { detail = JSON.parse(t).detail ?? t; } catch { /* not JSON: keep the raw text */ }
      return Promise.reject(new Error(`${r.status} — ${detail}`.slice(0, 300)));
    }));

// The one place a problem becomes visible. A learner who sees nothing has no way to know the
// page is broken rather than empty.
export function banner(message) {
  const b = $("#banner");
  b.className = "on";
  b.textContent = message;
}

export async function load() {
  const [content, progress] = await Promise.all([
    api("/api/learn/content"), api("/api/learn/progress")]);
  Object.assign(state, content);
  state.progress = progress.modules;
  state.passMark = content.pass_mark;
  if (content.content_errors?.length) {
    banner(`${content.content_errors.length} content problem(s): `
           + content.content_errors.slice(0, 3).join(" · "));
  }
  if (state.groups.length) state.openGroups.add(state.groups[0].id);
}

export function setProgress(moduleId, rec) {
  state.progress[moduleId] = rec;
  drawNav(select);
  drawOverall();
}

function drawOverall() {
  const total = state.modules.length;
  const passed = state.modules.filter(m => state.progress[m.id]?.status === "passed").length;
  $("#learn-progress").textContent = total ? `${passed} of ${total} passed` : "no content yet";
}

export function select(moduleId) {
  location.hash = moduleId ? `#/${moduleId}` : "";
}

export async function route() {
  if (location.hash.startsWith("#/tool/")) {
    const id = location.hash.slice("#/tool/".length);
    const mod = {asil: "./tools/asil.js", hara: "./tools/hara.js", trace: "./tools/trace.js"}[id];
    state.current = `tool:${id}`;
    $("#learn-crumb").textContent = `Tools → ${id}`;
    drawNav(select);
    if (!mod) { $("#learn-main").innerHTML = `<p style="color:var(--dim)">No such tool.</p>`; return; }
    const m = await import(mod);
    (m.renderAsil || m.renderHara || m.renderTrace)($("#learn-main"));
    return;
  }
  const id = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
  const mod = state.modules.find(m => m.id === id);
  state.current = mod ? mod.id : null;
  const group = state.groups.find(g => g.id === mod?.group);
  if (mod) state.openGroups.add(mod.group);
  $("#learn-crumb").textContent = mod ? `${group ? group.title : mod.group} → ${mod.title}`
                                      : "Pick a module to begin";
  drawNav(select);
  const main = $("#learn-main");
  if (!mod) {
    main.innerHTML = `<p style="color:var(--dim)">This course follows the lifecycle in the
      order it actually runs. Start at the top of the panel, or search for a term.</p>`;
    return;
  }
  const { renderModule } = await import("./module.js");
  renderModule(mod, main);
}

$("#search").oninput = e => drawNav(select, e.target.value);
window.addEventListener("hashchange", route);
load().then(() => { drawOverall(); route(); })
      .catch(err => banner(`the course could not be loaded — ${err.message}`));
