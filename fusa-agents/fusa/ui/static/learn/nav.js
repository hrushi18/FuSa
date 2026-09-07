// The nav IS the V-model: groups in lifecycle order, so a practitioner needs no legend.
import { state } from "./app.js";
import { esc } from "./esc.js";

export const STATUS_ICON = {
  not_started: "○", in_progress: "◐", passed: "✓", needs_review: "⚑",
};

const statusOf = id => state.progress[id]?.status || "not_started";
const modulesOf = gid => state.modules.filter(m => m.group === gid);

export function drawNav(onSelect, filter = "") {
  const q = filter.trim().toLowerCase();
  const nav = document.getElementById("learn-nav");
  nav.innerHTML = state.groups.map(g => {
    const mods = modulesOf(g.id).filter(m => !q || m.title.toLowerCase().includes(q));
    if (q && !mods.length) return "";
    const done = modulesOf(g.id).filter(m => statusOf(m.id) === "passed").length;
    const total = modulesOf(g.id).length;
    const open = q || state.openGroups.has(g.id);
    return `<div class="grp ${open ? "open" : ""}" data-g="${esc(g.id)}">
      <div class="g-top" tabindex="0" role="button" aria-expanded="${open}">
        <span class="g-caret">▸</span>
        <span class="g-title">${esc(g.order)} · ${esc(g.title)}</span>
        <span class="ring">${total ? `${done}/${total}` : "—"}</span>
      </div>
      <div class="g-mods">${mods.map(m => {
        const st = statusOf(m.id);
        return `<div class="mod ${state.current === m.id ? "on" : ""}" data-m="${esc(m.id)}"
                     tabindex="0" role="button" title="${esc(st.replace("_", " "))}">
          <span class="ico st-${st}">${STATUS_ICON[st]}</span>
          <span>${esc(m.title)}</span></div>`;
      }).join("") || `<div class="mod" style="color:var(--dim);cursor:default">no modules yet</div>`}
      </div></div>`;
  }).join("");

  nav.querySelectorAll(".g-top").forEach(el => {
    const gid = el.parentElement.dataset.g;
    const toggle = () => {
      state.openGroups.has(gid) ? state.openGroups.delete(gid) : state.openGroups.add(gid);
      drawNav(onSelect, filter);
    };
    el.onclick = toggle;
    el.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } };
  });
  nav.querySelectorAll(".mod[data-m]").forEach(el => {
    const go = () => onSelect(el.dataset.m);
    el.onclick = go;
    el.onkeydown = e => { if (e.key === "Enter") go(); };
  });
}
