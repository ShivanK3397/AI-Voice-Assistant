import { test } from 'node:test';
import assert from 'node:assert/strict';
import { applyEvent, initialState, visibleState } from '../src/renderer/state';
import { parseLifecycle, redact } from '../src/protocol';
import { validatePreferences } from '../src/preferences';
import type { DesktopEvent } from '../src/shared';

function event(sequence: number, type: string, payload: Record<string, unknown>, sessionId = 'current'): DesktopEvent {
  return { version: 1, sessionId, sequence, type, payload, timestamp: 1 };
}
test('stale sessions, duplicate events and out-of-order updates cannot overwrite state', () => {
  const state = applyEvent(initialState('current'), event(4, 'session.state', { state: 'listening' }));
  assert.equal(applyEvent(state, event(5, 'session.state', { state: 'speaking' }, 'old')), state);
  assert.equal(applyEvent(state, event(4, 'session.state', { state: 'speaking' })), state);
  assert.equal(applyEvent(state, event(3, 'session.state', { state: 'speaking' })), state);
});
test('snapshot replaces stale approval and repairs missed action updates', () => {
  let state = initialState('current');
  state = applyEvent(state, event(1, 'approval.pending', { actionId: 'stale', delivered: true }));
  state = applyEvent(state, event(9, 'session.snapshot', { state: 'listening', approval: null, action: { id: 'operation', operation: 'execute', status: 'uncertain' }, transcripts: [] }));
  assert.equal(state.approval, null);
  assert.equal(state.action?.status, 'uncertain');
});
test('an assistant intention statement does not mark a browser action complete', () => {
  let state = applyEvent(initialState('current'), event(1, 'session.state', { state: 'listening' }));
  state = applyEvent(state, event(2, 'action.started', { id: 'one', operation: 'act', status: 'running' }));
  state = applyEvent(state, event(3, 'transcript.updated', { id: 'reply', role: 'assistant', text: 'I will search now.', final: true }));
  assert.equal(visibleState(state, false), 'working');
  state = applyEvent(state, event(4, 'action.finished', { id: 'one', operation: 'act', status: 'uncertain' }));
  assert.equal(state.action?.status, 'uncertain');
});
test('provider error takes precedence over approval and work indicators', () => {
  let state = applyEvent(initialState('current'), event(1, 'approval.pending', { actionId: 'one', delivered: false }));
  state = applyEvent(state, event(2, 'session.error', { recoverable: true, message: 'Reconnecting' }));
  assert.equal(visibleState(state, false), 'recovering');
});
test('committed transcripts replace duplicates and clear interim speech', () => {
  let state = applyEvent(initialState('current'), event(1, 'transcript.updated', { id: 'interim', role: 'user', text: 'Find', final: false }));
  state = applyEvent(state, event(2, 'transcript.updated', { id: 'message', role: 'user', text: 'Find hoodies', final: true }));
  state = applyEvent(state, event(3, 'transcript.updated', { id: 'message', role: 'user', text: 'Find hoodies on Amazon', final: true }));
  assert.equal(state.transcripts.length, 1); assert.equal(state.interim, '');
});
test('lifecycle messages are bounded, versioned and reject invalid JSON', () => {
  assert.equal(parseLifecycle('{"version":1,"type":"worker.ready"}')?.type, 'worker.ready');
  assert.equal(parseLifecycle('{"version":2,"type":"worker.ready"}'), null);
  assert.equal(parseLifecycle('null'), null);
  assert.throws(() => parseLifecycle('not JSON'), /Malformed/);
  assert.throws(() => parseLifecycle('x'.repeat(65537)), /size limit/);
});
test('diagnostics redact configured credentials, query tokens and authorization headers', () => {
  const safe = redact('secret-value https://example.com?key=another-secret Bearer third-secret eyJabcd.efgh.ijkl', ['secret-value']);
  for (const value of ['secret-value', 'another-secret', 'third-secret', 'eyJabcd.efgh.ijkl']) assert.ok(!safe.includes(value));
});
test('renderer cannot write credentials, grant consent or choose invalid settings', () => {
  assert.throws(() => validatePreferences({ GOOGLE_API_KEY: 'key' }));
  assert.throws(() => validatePreferences({ microphoneConsent: true }));
  assert.throws(() => validatePreferences({ volume: NaN }));
  assert.throws(() => validatePreferences({ volume: 2 }));
  assert.deepEqual(validatePreferences({ inputDevice: 'microphone', volume: 0.5 }), { inputDevice: 'microphone', volume: 0.5 });
});
