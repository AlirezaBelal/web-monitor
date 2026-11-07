const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const {
  MAX_INPUT,
  definitions,
  normalizeSnapshot,
  classify,
  nextSnapshot,
  compareSnapshots,
  createSimulation,
  filterEvents,
} = require("../docs/app.js");
function fixture() {
  const pending = [];
  const sim = createSimulation({
    schedule: (fn) => {
      pending.push(fn);
      return pending.length;
    },
    cancel: () => {},
  });
  return {
    sim,
    next: () => {
      sim.run();
      pending.shift()();
    },
    pending,
  };
}
test("baseline, whitespace equivalence and meaningful changes", () => {
  assert.equal(classify(null, "first"), "baseline");
  assert.equal(classify("same\n text", "same   text"), "unchanged");
  assert.equal(classify("North", "South"), "changed");
  assert.equal(normalizeSnapshot(" A\n B "), "A B");
  assert.equal(nextSnapshot(definitions[0], 3), "North station maintenance");
});
test("local comparison describes equivalence without hiding case or punctuation", () => {
  assert.equal(compareSnapshots(" A\nB ", "A B").formattingOnly, true);
  assert.equal(compareSnapshots("same", "same").changed, false);
  for (const pair of [
    ["A", "a"],
    ["hello", "hello!"],
    ["é", "e\u0301"],
  ])
    assert.equal(compareSnapshots(...pair).changed, true);
});
test("linear changed-span summary handles insertions, deletion, replacement and no common text", () => {
  for (const [a, b, removed, added] of [
    ["abc", "abXc", "", "X"],
    ["abXc", "abc", "X", ""],
    ["North ready", "South ready", "Nor", "Sou"],
    ["aaa", "bbb", "aaa", "bbb"],
  ]) {
    const d = compareSnapshots(a, b);
    assert.equal(d.removed, removed);
    assert.equal(d.added, added);
  }
});
test("input limits, empty text and literal markup", () => {
  for (const pair of [
    ["", "x"],
    [" \n", "x"],
    ["x", "x".repeat(MAX_INPUT + 1)],
  ])
    assert.throws(() => compareSnapshots(...pair), RangeError);
  assert.equal(
    compareSnapshots("x".repeat(MAX_INPUT), "y".repeat(MAX_INPUT)).changed,
    true,
  );
  assert.equal(
    compareSnapshots("before", "<img src=x onerror=alert(1)>").added,
    "<img src=x onerror=alert(1)>",
  );
});
test("first run records baselines and request failure, without changed events", () => {
  const { sim, next } = fixture();
  assert.equal(sim.snapshot().cycle, 0);
  next();
  const s = sim.snapshot();
  assert.equal(s.states.get("status").status, "Baseline");
  assert.equal(s.states.get("retry").status, "Request failure");
  assert.equal(s.events.filter((e) => e.type === "changed").length, 0);
});
test("recovery is not a change and first successful response establishes baseline", () => {
  const { sim, next } = fixture();
  next();
  next();
  const s = sim.snapshot();
  assert.equal(s.states.get("retry").status, "Baseline");
  assert.equal(s.states.get("retry").attempts, 2);
  assert.equal(filterEvents(s.events, "recovery").length, 1);
  assert.equal(filterEvents(s.events, "changes").length, 0);
});
test("failed delivery preserves committed content and next check retries before commit", () => {
  const { sim, next } = fixture();
  next();
  next();
  next();
  let s = sim.snapshot();
  assert.equal(s.states.get("guide").snapshot, "Release 2.4");
  assert.equal(s.states.get("guide").status, "Pending retry");
  assert.equal(filterEvents(s.events, "changes").length, 1);
  next();
  s = sim.snapshot();
  assert.equal(s.states.get("guide").snapshot, "Release 2.5");
  assert.equal(filterEvents(s.events, "changes").length, 2);
  assert.equal(filterEvents(s.events, "failures").length, 2);
});
test("reset invalidates queued callback, permits immediate new run and prevents double advance", () => {
  const { sim, pending } = fixture();
  assert.equal(sim.run(), true);
  assert.equal(sim.run(), false);
  sim.reset();
  assert.equal(sim.snapshot().busy, false);
  assert.equal(sim.run(), true);
  pending.shift()();
  assert.equal(sim.snapshot().cycle, 0);
  pending.shift()();
  assert.equal(sim.snapshot().cycle, 1);
  assert.equal(sim.snapshot().busy, false);
});
test("repeated cycles stabilize, filtering is pure, ledger is bounded and reset is repeatable", () => {
  const { sim, next } = fixture();
  for (let i = 0; i < 100; i++) next();
  const s = sim.snapshot();
  assert.equal(s.events.length, 60);
  assert.equal(s.states.get("guide").status, "Unchanged");
  assert.equal(filterEvents(s.events, "recovery").length, 0);
  assert.equal(sim.snapshot().events.length, 60);
  sim.reset();
  next();
  assert.equal(sim.snapshot().events.length, 3);
});
test("static CSP, synthetic targets, no networking, storage or HTML injection sinks", () => {
  const html = fs.readFileSync("docs/index.html", "utf8"),
    app = fs.readFileSync("docs/app.js", "utf8");
  assert.match(html, /connect-src 'none'/);
  assert.doesNotMatch(
    app,
    /fetch\s*\(|XMLHttpRequest|WebSocket|sendBeacon|localStorage|sessionStorage|innerHTML|insertAdjacentHTML/,
  );
  assert(definitions.every((t) => t.url.includes(".example.test")));
  assert.match(html, /maxlength="20000"/);
});

test("product presentation and installation precede optional educational tools", () => {
  const html = fs.readFileSync("docs/index.html", "utf8");
  const hero = html.match(/<section class="hero"[\s\S]*?<\/section>/)[0];
  assert.match(hero, /href="#install"[\s\S]*?Get Started/);
  assert.match(hero, /View on GitHub/);
  assert.doesNotMatch(hero, /Try local comparison/);
  assert(html.indexOf('id="install"') < html.indexOf('id="compare-workbench"'));
  assert(html.indexOf('id="notifications"') < html.indexOf('id="demos"'));
  for (const value of [
    "Windows PowerShell",
    "macOS &amp; Linux",
    ".\\.venv\\Scripts\\Activate.ps1",
    "source .venv/bin/activate",
    "--validate-config",
    "--once",
    "python -m http.server 8000 --bind 127.0.0.1 --directory demo",
  ])
    assert(html.includes(value), value);
  assert.match(html, /Optional educational experiences/);
});
