/* Drives the real static/site.js against a minimal DOM stub.
 *
 * The point of the stub is that the code under test is the shipped file rather
 * than a reimplementation of it. The facet logic — OR inside a group, AND across
 * groups, and "nothing ticked means no filter" — is the part most likely to be
 * subtly wrong, and without a browser there is no other way to exercise it.
 *
 * Run with: node tests/filter.test.js
 *
 * The stub is only as complete as these tests need. If site.js starts touching
 * more of the DOM, a missing stub surfaces as a TypeError, not a silent pass.
 */
const fs = require("fs");

function el(attrs = {}, children = []) {
  return {
    _attrs: attrs, _children: children, hidden: false, textContent: "", _on: {},
    getAttribute(n) { return n in this._attrs ? this._attrs[n] : null; },
    setAttribute(n, v) { this._attrs[n] = v; },
    removeAttribute(n) { delete this._attrs[n]; },
    addEventListener(t, fn) { (this._on[t] ||= []).push(fn); },
    fire(t, ev = {}) { (this._on[t] || []).forEach(fn => fn(ev)); },
    get children() { return this._children; },
    querySelectorAll(sel) {
      if (sel === "input[type=checkbox]") return this._children.filter(c => c._attrs.type === "checkbox");
      return [];
    },
    querySelector() { return null; },
    appendChild(c) {
      const i = this._children.indexOf(c);
      if (i >= 0) this._children.splice(i, 1);
      this._children.push(c);
    },
    focus() {}, select() {},
    classList: { add() {}, remove() {}, toggle() { return false; } },
  };
}

/* Real skill data, so the assertions mean something. */
const card = (name, trigger, tags, text) =>
  el({ "data-name": name, "data-trigger": trigger, "data-tag": tags, "data-text": text });

const cards = [
  card("artisanal-slop", "you", "github|automation|sub-agents|worktrees",
       "artisanal-slop works your open github issues end to end bash 4+ git gh coreutils"),
  card("pr-status", "you|auto", "github|reporting|workflow",
       "pr-status triage your open pull requests gh python3"),
  card("writing-skills", "you|auto", "authoring|reference|meta",
       "writing-skills how to write a skill.md that claude invokes"),
];

const grid = el({}, cards.slice());
const input = el(); input.value = "";
const count = el(), empty = el(), reset = el(), filters = el();
/* Chips carry their own facet name now, and all live in one container. */
const box = (facet, v) => {
  const b = el({ type: "checkbox", "data-facet": facet });
  b.value = v; b.checked = false; return b;
};
const chipYou = box("trigger", "you"), chipAuto = box("trigger", "auto");
const chipGithub = box("tag", "github"), chipAuthoring = box("tag", "authoring");
const allBoxes = [chipYou, chipAuto, chipGithub, chipAuthoring];
const chipRow = el();

const catalog = el();
const inside = { "#skill-search": input, "#card-grid": grid, "#result-count": count,
                 "#empty-state": empty, "#filter-reset": reset, ".filters": filters,
                 ".chips": chipRow };
catalog.querySelector = (s) => (s in inside ? inside[s] : null);
catalog.querySelectorAll = (s) =>
  s === ".chip input[type=checkbox]" ? allBoxes : [];

global.document = {
  body: { getAttribute: () => null },
  querySelector: (s) => (s === ".catalog" ? catalog : null),
  querySelectorAll: () => [],
  addEventListener() {}, activeElement: null,
};
global.window = { location: { href: "https://calebstew.art/ai-slop/" },
                  history: { replaceState() {} }, clearTimeout() {}, setTimeout() {} };
global.navigator = {};

new Function(fs.readFileSync("static/site.js", "utf8"))();

const shown = () => cards.filter(c => !c.hidden).map(c => c.getAttribute("data-name"));
const order = () => grid._children.filter(c => !c.hidden).map(c => c.getAttribute("data-name"));
let fail = 0;
const check = (label, got, want) => {
  if (JSON.stringify(got) !== JSON.stringify(want)) {
    fail++;
    console.log(`FAIL  ${label}\n        got  ${JSON.stringify(got)}\n        want ${JSON.stringify(want)}`);
  } else console.log(`ok    ${label} -> ${JSON.stringify(got)}`);
};
const type = (v) => { input.value = v; input.fire("input"); };
const toggle = (chip, on) => { chip.checked = on; chipRow.fire("change"); };

check("filter controls revealed by JS", filters.hidden, false);
check("no filters: all three shown", shown(), ["artisanal-slop", "pr-status", "writing-skills"]);
check("initial count", count.textContent, "3 skills");

type("pr");
check('search "pr" ranks pr-status first', order(), ["pr-status"]);
type("skills");
check('search "skills"', order(), ["writing-skills"]);
type("python3");
check('search "python3" hits the tagline/deps, not the name', order(), ["pr-status"]);
type("wsk");
check('subsequence "wsk"', order(), ["writing-skills"]);
type("");

toggle(chipGithub, true);
check("tag: github", shown(), ["artisanal-slop", "pr-status"]);
toggle(chipAuthoring, true);
check("tag: github OR tag: authoring (OR within a facet)", shown(), ["artisanal-slop", "pr-status", "writing-skills"]);
toggle(chipAuto, true);
check("+ trigger: auto (AND across facets)", shown(), ["pr-status", "writing-skills"]);

toggle(chipGithub, false); toggle(chipAuthoring, false); toggle(chipAuto, false);
check("nothing ticked means no filter, not no results", shown(), ["artisanal-slop", "pr-status", "writing-skills"]);

toggle(chipYou, true);
check("trigger: you matches all three", shown(), ["artisanal-slop", "pr-status", "writing-skills"]);
toggle(chipYou, false);

type("zzzz");
check("no match: empty state shown", empty.hidden, false);
check("no match: count text", count.textContent, "Nothing matches");
type("");
check("cleared: authored order restored", order(), ["artisanal-slop", "pr-status", "writing-skills"]);
check("cleared: empty state hidden", empty.hidden, true);

console.log(fail ? `\n${fail} FAILURES` : "\nall filter assertions pass");
process.exit(fail ? 1 : 0);
