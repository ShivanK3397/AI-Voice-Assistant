import { test } from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { PassThrough } from 'node:stream';
import { mkdtempSync, mkdirSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { type spawn } from 'node:child_process';
import { BackendManager } from '../src/backend';

function fixture(timeout = 500) {
  const directory = mkdtempSync(path.join(tmpdir(), 'jarvis-backend-test-'));
  mkdirSync(path.join(directory, '.venv', 'Scripts'), { recursive: true });
  mkdirSync(path.join(directory, 'src'));
  writeFileSync(path.join(directory, '.venv', 'Scripts', 'python.exe'), 'fixture');
  writeFileSync(path.join(directory, 'src', 'desktop_runner.py'), 'fixture');
  writeFileSync(path.join(directory, '.env.local'), 'LIVEKIT_URL=wss://example.livekit.cloud\nLIVEKIT_API_KEY=test-key\nLIVEKIT_API_SECRET=test-secret\nGOOGLE_API_KEY=test-google\n');
  const process = Object.assign(new EventEmitter(), { stdout: new PassThrough(), stderr: new PassThrough(), stdin: new PassThrough(), exitCode: null as number | null, pid: 999999, kill: () => {} });
  process.stdin.on('data', data => {
    if (data.toString().includes('shutdown')) setImmediate(() => { process.exitCode = 0; process.emit('exit', 0); });
  });
  let spawns = 0;
  const spawnProcess = (() => { spawns++; return process; }) as unknown as typeof spawn;
  const manager = new BackendManager(directory, () => {}, () => {}, spawnProcess, timeout);
  return { directory, process, manager, spawns: () => spawns, cleanup: () => rmSync(directory, { recursive: true, force: true }) };
}

test('start waits for registered readiness and duplicate starts share one process', async () => {
  const f = fixture();
  try {
    const first = f.manager.start(), second = f.manager.start();
    assert.equal(first, second);
    let resolved = false; void first.then(() => { resolved = true; });
    await new Promise(resolve => setTimeout(resolve, 30));
    assert.equal(resolved, false);
    f.process.stdout.write('{"version":1,"type":"worker.ready"}\n');
    const connection = await first;
    assert.ok(connection.participantToken);
    assert.equal(f.spawns(), 1);
    await f.manager.end(connection.sessionId);
    assert.equal(f.process.exitCode, 0);
  } finally { await f.manager.stop(); f.cleanup(); }
});
test('startup timeout shuts down the owned process', async () => {
  const f = fixture(30);
  try { await assert.rejects(f.manager.start(), /timed out/); assert.equal(f.process.exitCode, 0); }
  finally { await f.manager.stop(); f.cleanup(); }
});
test('malformed lifecycle output fails startup and cleans up', async () => {
  const f = fixture();
  try {
    const start = f.manager.start();
    setTimeout(() => f.process.stdout.write('malformed\n'), 30);
    await assert.rejects(start, /Malformed/);
    assert.equal(f.process.exitCode, 0);
  } finally { await f.manager.stop(); f.cleanup(); }
});
test('crash before registration never returns a connection token', async () => {
  const f = fixture();
  try {
    const start = f.manager.start();
    setTimeout(() => { f.process.exitCode = 1; f.process.emit('exit', 1); }, 30);
    await assert.rejects(start, /exited/);
  } finally { await f.manager.stop(); f.cleanup(); }
});
