"use strict";
const MAX_INPUT = 20000;
const samples = [
  "Fictional observatory\nNorth station: available\nNext review: Monday",
  "Fictional observatory\nNorth station: maintenance\nNext review: Tuesday",
];
const definitions = [
  {
    id: "status",
    name: "Status journal",
    url: "status.example.test",
    sequence: [
      "North station available",
      "North station available",
      "North station maintenance",
    ],
    kind: "change",
  },
  {
    id: "guide",
    name: "Release notes",
    url: "docs.example.test/releases",
    sequence: ["Release 2.4", "Release 2.4", "Release 2.5"],
    kind: "delivery",
  },
  {
    id: "retry",
    name: "Request recovery",
    url: "health.example.test/check",
    sequence: [],
    kind: "retry",
  },
];
function normalizeSnapshot(text) {
  return String(text).replace(/\s+/g, " ").trim();
}
function classify(previous, current) {
  if (previous === null) return "baseline";
  return normalizeSnapshot(previous) === normalizeSnapshot(current)
    ? "unchanged"
    : "changed";
}
function nextSnapshot(target, cycle) {
  return target.sequence[Math.min(cycle - 1, target.sequence.length - 1)];
}
function retryScenario(cycle) {
  return cycle === 1
    ? {
        ok: false,
        attempts: 3,
        message: "Timed out after 2 retries · target needs attention",
      }
    : {
        ok: true,
        attempts: cycle === 2 ? 2 : 1,
        message: "Recovered · response snapshot is stable",
      };
}
function compareSnapshots(before, after) {
  if (before.length > MAX_INPUT || after.length > MAX_INPUT)
    throw new RangeError(
      "Use at most 20,000 characters per snapshot. Shorten the input and compare again.",
    );
  const left = normalizeSnapshot(before),
    right = normalizeSnapshot(after);
  if (!left || !right)
    throw new RangeError(
      "Enter non-whitespace text in both snapshots, then compare again.",
    );
  let start = 0,
    end = 0;
  // Linear common-prefix/suffix summary; avoids quadratic edit-distance processing.
  while (
    start < left.length &&
    start < right.length &&
    left[start] === right[start]
  )
    start++;
  while (
    end < left.length - start &&
    end < right.length - start &&
    left[left.length - end - 1] === right[right.length - end - 1]
  )
    end++;
  return {
    changed: left !== right,
    formattingOnly: before !== after && left === right,
    left,
    right,
    removed: left.slice(start, left.length - end),
    added: right.slice(start, right.length - end),
    offset: start,
  };
}
function createSimulation({
  schedule = (fn) => setTimeout(fn, 180),
  cancel = clearTimeout,
  onUpdate = () => {},
} = {}) {
  let cycle = 0,
    busy = false,
    generation = 0,
    timer = null;
  const states = new Map(),
    events = [];
  function snapshot() {
    return {
      cycle,
      busy,
      states: new Map([...states].map(([id, s]) => [id, { ...s }])),
      events: events.map((e) => ({ ...e })),
    };
  }
  function update() {
    onUpdate(snapshot());
  }
  function reset() {
    generation++;
    if (timer !== null) cancel(timer);
    timer = null;
    busy = false;
    cycle = 0;
    events.length = 0;
    for (const t of definitions)
      states.set(t.id, {
        snapshot: null,
        status: "Waiting",
        attempts: 0,
        explanation: "The first successful observation establishes a baseline.",
      });
    update();
  }
  function log(target, type, message) {
    events.unshift({ cycle, target: target.name, type, message });
    if (events.length > 60) events.pop();
  }
  function advance() {
    cycle++;
    for (const target of definitions) {
      const previous = states.get(target.id);
      if (target.kind === "retry" && cycle === 1) {
        states.set(target.id, {
          ...previous,
          status: "Request failure",
          attempts: 3,
          explanation:
            "Three synthetic timeouts exhaust the retry budget. No baseline is committed.",
        });
        log(
          target,
          "failure",
          "Request failed after 3 attempts (backoff: 1s, 2s, represented without waiting). No state committed.",
        );
        continue;
      }
      const content =
          target.kind === "retry"
            ? "Station response stable"
            : nextSnapshot(target, cycle),
        result = classify(previous.snapshot, content),
        recovery = target.kind === "retry" && cycle === 2;
      if (recovery)
        log(
          target,
          "recovery",
          "Second attempt succeeds after a synthetic 503. First success: establish a baseline, no alert.",
        );
      if (target.kind === "delivery" && cycle === 3) {
        states.set(target.id, {
          snapshot: previous.snapshot,
          status: "Pending retry",
          attempts: 1,
          explanation:
            "Change eligible for an alert. Synthetic delivery fails; keep Release 2.4 committed so the next cycle retries.",
        });
        log(
          target,
          "delivery",
          "Delivery failure. Changed snapshot is NOT committed; retry delivery on the next check.",
        );
        continue;
      }
      const explanation =
        result === "baseline"
          ? "First success: baseline recorded, no alert eligible."
          : result === "unchanged"
            ? "Matches the committed snapshot. No alert eligible."
            : "Changed snapshot: synthetic delivery succeeds before state commit. No real notification is sent.";
      states.set(target.id, {
        snapshot: content,
        status:
          result === "baseline"
            ? "Baseline"
            : result === "changed"
              ? "Changed"
              : "Unchanged",
        attempts: recovery ? 2 : 1,
        explanation,
      });
      log(target, result, explanation);
    }
    busy = false;
    timer = null;
    update();
  }
  function run() {
    if (busy) return false;
    busy = true;
    const token = generation;
    update();
    timer = schedule(() => {
      if (token === generation) advance();
    });
    return true;
  }
  reset();
  return { run, reset, snapshot };
}
function filterEvents(events, filter) {
  return events.filter(
    (e) =>
      filter === "all" ||
      (filter === "changes"
        ? e.type === "changed"
        : filter === "failures"
          ? ["failure", "delivery"].includes(e.type)
          : e.type === filter),
  );
}
if (typeof module !== "undefined")
  module.exports = {
    definitions,
    MAX_INPUT,
    samples,
    normalizeSnapshot,
    classify,
    nextSnapshot,
    retryScenario,
    compareSnapshots,
    createSimulation,
    filterEvents,
  };
if (typeof document !== "undefined") {
  const $ = (s) => document.querySelector(s);
  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }
  const filter = $("#filter"),
    labels = {
      baseline: "Baseline",
      unchanged: "Unchanged",
      changed: "Content change",
      failure: "Request failure",
      recovery: "Recovery",
      delivery: "Delivery failure",
    };
  function render(data) {
    $("#run").disabled = data.busy;
    $("#cycle-state").textContent = data.busy
      ? "Preparing synthetic observations…"
      : data.cycle
        ? `Cycle ${data.cycle} complete · no external requests`
        : "Ready · no checks have run";
    $("#targets").replaceChildren(
      ...definitions.map((t) => {
        const s = data.states.get(t.id),
          card = el("article", "target"),
          top = el("div", "target-top"),
          identity = el("div");
        identity.append(el("h3", "", t.name), el("code", "", t.url));
        top.append(
          identity,
          el(
            "span",
            `state ${s.status.toLowerCase().replaceAll(" ", "-")}`,
            s.status,
          ),
        );
        card.append(
          top,
          el(
            "p",
            "snapshot",
            s.snapshot === null
              ? "No committed snapshot"
              : `Committed: ${s.snapshot}`,
          ),
          el("p", "explanation", s.explanation),
        );
        if (s.attempts)
          card.append(
            el(
              "small",
              "attempts",
              `${s.attempts} simulated attempt${s.attempts === 1 ? "" : "s"}`,
            ),
          );
        return card;
      }),
    );
    const visible = filterEvents(data.events, filter.value);
    $("#events").replaceChildren(
      ...visible.map((e) => {
        const row = el("article", `event ${e.type}`);
        row.append(
          el("strong", "event-type", labels[e.type]),
          el("p", "", `${e.target} · ${e.message}`),
          el("small", "", `Cycle ${e.cycle}`),
        );
        return row;
      }),
    );
    $("#event-count").textContent =
      `${visible.length} ${visible.length === 1 ? "event" : "events"}`;
    $("#empty").hidden = visible.length > 0;
    $("#guide-step").textContent = [
      "01 · Establish baselines and exhaust a request retry budget.",
      "02 · Observe unchanged content and recovery without a change alert.",
      "03 · Detect changes and preserve state after a delivery failure.",
      "04 · Retry the pending delivery, then commit the changed state.",
    ][Math.min(data.cycle, 3)];
  }
  const simulator = createSimulation({ onUpdate: render });
  $("#run").addEventListener("click", simulator.run);
  $("#reset").addEventListener("click", () => {
    filter.value = "all";
    simulator.reset();
  });
  filter.addEventListener("change", () => render(simulator.snapshot()));
  const before = $("#before"),
    after = $("#after"),
    result = $("#comparison-status");
  function invalidate() {
    result.textContent = "Inputs edited · compare to update the result.";
    clearDifference();
    before.removeAttribute("aria-invalid");
    after.removeAttribute("aria-invalid");
  }
  function clearDifference() {
    $("#difference").hidden = true;
    for (const id of ["#removed", "#added", "#comparison-detail"])
      $(id).textContent = "";
  }
  for (const input of [before, after])
    input.addEventListener("input", invalidate);
  function clear() {
    before.value = "";
    after.value = "";
    result.textContent =
      "Cleared · enter two snapshots or restore the fictional sample.";
    clearDifference();
    before.removeAttribute("aria-invalid");
    after.removeAttribute("aria-invalid");
  }
  $("#clear").addEventListener("click", clear);
  $("#restore").addEventListener("click", () => {
    before.value = samples[0];
    after.value = samples[1];
    invalidate();
    result.textContent = "Fictional sample restored · ready to compare.";
  });
  $("#compare").addEventListener("click", () => {
    try {
      const c = compareSnapshots(before.value, after.value);
      result.textContent = c.changed
        ? "Changed · normalized text differs."
        : c.formattingOnly
          ? "Equivalent · only whitespace formatting differs."
          : "Equivalent · the inputs are identical.";
      $("#difference").hidden = false;
      $("#comparison-detail").textContent = c.changed
        ? `One changed span after ${c.offset} matching characters. Common prefix and suffix omitted; multiple edits may be grouped. ${c.left.length} → ${c.right.length} normalized characters.`
        : "Whitespace runs collapse to one space; outer whitespace is removed. Case, punctuation, and character order remain significant.";
      for (const [id, value] of [
        ["#removed", c.removed],
        ["#added", c.added],
      ])
        $(id).textContent = value
          ? value.slice(0, 500) +
            (value.length > 500 ? "… [preview limited to 500 characters]" : "")
          : "(none)";
      before.removeAttribute("aria-invalid");
      after.removeAttribute("aria-invalid");
    } catch (error) {
      result.textContent = error.message;
      clearDifference();
      const input = [before, after].find(
        (x) => x.value.length > MAX_INPUT || !normalizeSnapshot(x.value),
      );
      if (input) {
        input.setAttribute("aria-invalid", "true");
        input.focus();
      }
    }
  });
  window.addEventListener("pagehide", () => {
    clear();
    simulator.reset();
  });
  before.value = samples[0];
  after.value = samples[1];
}
