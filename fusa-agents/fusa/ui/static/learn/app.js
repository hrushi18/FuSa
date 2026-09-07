// Boot, routing and the one piece of shared state. Routing is the URL hash so a module is
// linkable and the back button works, with no router library to install.
import { drawNav } from "./nav.js";

export const state = {
  groups: [], modules: [], paths: [], glossary: {}, passMark: 0.8,
  progress: {}, openGroups: new Set(), current: null,
};

const $ = s => document.querySelector(s);
const api = (p, opt) => fetch(p, opt).then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e)));

export async function load() {
  const [content, progress] = await Promise.all([
    api("/api/learn/content"), api("/api/learn/progress")]);
  Object.assign(state, content);
  state.progress = progress.modules;
  state.passMark = content.pass_mark;
  if (content.content_errors?.length) {
    const b = $("#banner");
    b.className = "on";
    b.textContent = `${content.content_errors.length} content problem(s): `
                  + content.content_errors.slice(0, 3).join(" · ");
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
load().then(() => { drawOverall(); route(); });
