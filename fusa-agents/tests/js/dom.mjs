// Minimum DOM the learn modules touch, so the real ES modules can run under node.
export function installDom(elementIds = []) {
  const make = id => ({
    id, className: "", textContent: "", innerHTML: "", hidden: false,
    dataset: {}, style: {}, tabIndex: 0,
    onclick: null, onkeydown: null, oninput: null,
    classList: { add() {}, remove() {}, contains: () => false, toggle() {} },
    querySelector: () => make("child"), querySelectorAll: () => [],
    appendChild() {}, remove() {},
  });
  const els = Object.fromEntries(elementIds.map(i => [i, make(i)]));
  globalThis.document = {
    querySelector: sel => els[sel] ?? make(sel),
    getElementById: id => els["#" + id] ?? make(id),
    createElement: () => make("created"),
    body: make("body"),
  };
  globalThis.window = { addEventListener() {}, location: { hash: "" } };
  globalThis.location = globalThis.window.location;
  return els;
}
