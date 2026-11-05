const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { definitions, normalizeSnapshot, classify, nextSnapshot, retryScenario } = require('../docs/app.js');

test('content comparison ignores only formatting whitespace', () => {
  assert.equal(classify(null, ' first '), 'baseline');
  assert.equal(classify('same\n text', 'same   text'), 'unchanged');
  assert.equal(classify('North ready', 'South ready'), 'changed');
  assert.equal(normalizeSnapshot(' A\n B '), 'A B');
});

test('sample target snapshots change deterministically and then stabilize', () => {
  const status = definitions.find(x => x.id === 'status');
  assert.equal(classify(null, nextSnapshot(status, 1)), 'baseline');
  assert.equal(classify(nextSnapshot(status, 1), nextSnapshot(status, 2)), 'unchanged');
  assert.equal(classify(nextSnapshot(status, 2), nextSnapshot(status, 3)), 'changed');
});

test('retry budget and recovery are deterministic', () => {
  assert.deepEqual(retryScenario(1), { ok: false, attempts: 3, message: 'Timed out after 2 retries · target needs attention' });
  assert.equal(retryScenario(2).ok, true);
  assert.equal(definitions.every(x => x.url.endsWith('.example.test') || x.url.includes('.example.test/')), true);
});

test('demo blocks external calls and uses fixed synthetic targets', () => {
  const page = fs.readFileSync('docs/index.html', 'utf8');
  const app = fs.readFileSync('docs/app.js', 'utf8');
  assert.match(page, /connect-src 'none'/);
  assert.doesNotMatch(app, /fetch\s*\(|XMLHttpRequest|WebSocket|sendBeacon/);
  assert.match(page, /example\.test/);
});

