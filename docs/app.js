const definitions = [
  { id: 'status', name: 'Status journal', url: 'status.example.test', sequence: ['All systems available · region North', 'All systems available · region North', 'Maintenance window posted · region North'], kind: 'change' },
  { id: 'guide', name: 'Release notes', url: 'docs.example.test/releases', sequence: ['Version 2.4 · setup guide refreshed', 'Version 2.4 · setup guide refreshed', 'Version 2.5 · retry guide added'], kind: 'change' },
  { id: 'retry', name: 'Retry scenario', url: 'health.example.test/check', sequence: [], kind: 'retry' }
];
function normalizeSnapshot(text) { return String(text).replace(/\s+/g, ' ').trim(); }
function nextSnapshot(target, cycle) { return target.kind === 'retry' ? null : target.sequence[Math.min(cycle - 1, target.sequence.length - 1)]; }
function classify(previous, current) { if (previous === null) return 'baseline'; return normalizeSnapshot(previous) === normalizeSnapshot(current) ? 'unchanged' : 'changed'; }
function retryScenario(cycle) { return cycle === 1 ? { ok: false, attempts: 3, message: 'Timed out after 2 retries · target needs attention' } : { ok: true, attempts: 1, message: 'Recovered · response snapshot is stable' }; }
if (typeof module !== 'undefined') module.exports = { definitions, normalizeSnapshot, classify, nextSnapshot, retryScenario };
if (typeof document !== 'undefined') {
  const state = new Map(definitions.map(target => [target.id, { snapshot: null, status: 'Waiting', attempts: 0 }]));
  const events = [], targets = document.querySelector('#targets'), eventHost = document.querySelector('#events'), filter = document.querySelector('#filter'), empty = document.querySelector('#empty'), run = document.querySelector('#run');
  let cycle = 0, busy = false;
  function el(tag, cls, text) { const node = document.createElement(tag); if (cls) node.className = cls; if (text !== undefined) node.textContent = text; return node; }
  function renderTargets() {
    targets.replaceChildren(...definitions.map(target => {
      const current = state.get(target.id), card = el('article', 'target'), top = el('div', 'target-top'), identity = el('div'), badge = el('span', `state ${current.status.toLowerCase().replaceAll(' ', '-')}`, current.status), title = el('h3', '', target.name), url = el('code', '', target.url), snapshot = el('div', 'snapshot', current.snapshot || (current.status === 'Needs attention' ? 'No response received after the retry budget.' : 'Waiting for the first sample observation.'));
      identity.append(title, url); top.append(identity, badge); card.append(top, snapshot); if (current.attempts > 1) card.append(el('p', 'retry', `${current.attempts} simulated attempts`)); return card;
    }));
  }
  function renderEvents() {
    const visible = events.filter(event => filter.value === 'all' || (filter.value === 'changes' ? event.type === 'change' : event.type === 'failure'));
    eventHost.replaceChildren(...visible.map(event => { const row = el('article', 'event'), type = el('strong', `event-type ${event.type === 'failure' ? 'failure' : ''}`, event.type === 'failure' ? 'Retry result' : 'Content change'), text = el('p', '', `${event.target} · ${event.message}`), time = el('small', '', `Cycle ${event.cycle}`); row.append(type, text, time); return row; }));
    document.querySelector('#event-count').textContent = `${visible.length} ${visible.length === 1 ? 'event' : 'events'}`; empty.hidden = visible.length > 0;
  }
  function performCycle() {
    cycle++; document.querySelector('#cycle-state').textContent = `Cycle ${cycle} · checking synthetic snapshots`;
    for (const target of definitions) {
      const previous = state.get(target.id);
      if (target.kind === 'retry') {
        const outcome = retryScenario(cycle); state.set(target.id, { snapshot: outcome.ok ? 'Recovery confirmed · sample response received' : null, status: outcome.ok ? 'Healthy' : 'Needs attention', attempts: outcome.attempts });
        if (!outcome.ok || previous.status === 'Needs attention') events.push({ cycle, type: outcome.ok ? 'change' : 'failure', target: target.name, message: outcome.message });
        continue;
      }
      const snapshot = nextSnapshot(target, cycle), result = classify(previous.snapshot, snapshot);
      state.set(target.id, { snapshot, status: result === 'changed' ? 'Changed' : 'Healthy', attempts: 1 });
      if (result === 'changed') events.push({ cycle, type: 'change', target: target.name, message: `Snapshot changed: “${normalizeSnapshot(snapshot)}”` });
    }
    renderTargets(); renderEvents();
    document.querySelector('#cycle-state').textContent = `Cycle ${cycle} complete · no external requests made`;
    run.disabled = false; busy = false;
  }
  run.addEventListener('click', () => { if (busy) return; busy = true; run.disabled = true; document.querySelector('#cycle-state').textContent = 'Checking synthetic targets…'; window.setTimeout(performCycle, 180); });
  filter.addEventListener('change', renderEvents);
  document.querySelector('#reset').addEventListener('click', () => { cycle = 0; events.length = 0; for (const target of definitions) state.set(target.id, { snapshot: null, status: 'Waiting', attempts: 0 }); renderTargets(); renderEvents(); document.querySelector('#cycle-state').textContent = 'Ready · no checks have run'; run.disabled = false; });
  renderTargets(); renderEvents();
}

