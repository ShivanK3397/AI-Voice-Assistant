import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { randomUUID } from 'node:crypto';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { createInterface } from 'node:readline';
import { parse } from 'dotenv';
import { AccessToken, RoomConfiguration, RoomAgentDispatch, TrackSource } from 'livekit-server-sdk';
import type { BackendEvent, SessionConnection } from './shared';
import { parseLifecycle, redact } from './protocol';

export function readCredentials(directory: string): Record<string, string> {
  const filename = path.join(directory, '.env.local');
  const values = existsSync(filename) ? parse(readFileSync(filename)) : {};
  const credentials: Record<string, string> = {};
  for (const key of ['LIVEKIT_URL', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET', 'GOOGLE_API_KEY']) {
    const value = process.env[key] || values[key];
    if (!value) throw new Error(`Set ${key} in ${path.join(directory, '.env.local')}.`);
    credentials[key] = value;
  }
  const url = new URL(credentials.LIVEKIT_URL);
  if (!['wss:', 'ws:'].includes(url.protocol) || (url.protocol === 'ws:' && !['localhost', '127.0.0.1'].includes(url.hostname))) {
    throw new Error('LIVEKIT_URL must use wss:// (ws:// is allowed only for localhost).');
  }
  return credentials;
}

export async function createConnection(credentials: Record<string, string>, sessionId: string): Promise<SessionConnection> {
  const identity = `desktop-user-${sessionId}`;
  const token = new AccessToken(credentials.LIVEKIT_API_KEY, credentials.LIVEKIT_API_SECRET, { identity, ttl: '10m' });
  token.addGrant({ roomJoin: true, room: `jarvis-desktop-${sessionId}`, canPublish: true, canSubscribe: true, canPublishData: true, canPublishSources: [TrackSource.MICROPHONE] });
  token.roomConfig = new RoomConfiguration({ agents: [new RoomAgentDispatch({ agentName: `jarvis-desktop-${sessionId}` })] });
  return { sessionId, serverUrl: credentials.LIVEKIT_URL, participantIdentity: identity, participantToken: await token.toJwt() };
}

export class BackendManager {
  private child?: ChildProcessWithoutNullStreams;
  private connection?: SessionConnection;
  private starting?: Promise<SessionConnection>;
  private stopping?: Promise<void>;
  private secrets: string[] = [];
  private ending = false;
  constructor(private directory: string, private event: (event: BackendEvent) => void, private log: (line: string) => void, private spawnProcess: typeof spawn = spawn, private startupTimeout = 45000) {}

  start(): Promise<SessionConnection> {
    if (this.starting) return this.starting;
    if (this.connection) return Promise.resolve(this.connection);
    this.starting = this.launch().finally(() => { this.starting = undefined; });
    return this.starting;
  }

  private async launch(): Promise<SessionConnection> {
    if (this.stopping) await this.stopping;
    this.ending = false;
    const python = path.join(this.directory, '.venv', 'Scripts', 'python.exe');
    const runner = path.join(this.directory, 'src', 'desktop_runner.py');
    if (!existsSync(python) || !existsSync(runner)) throw new Error(`Python environment missing. In ${this.directory}, run uv sync.`);
    const credentials = readCredentials(this.directory);
    this.secrets = Object.entries(credentials).filter(([key]) => key !== 'LIVEKIT_URL').map(([, value]) => value);
    const sessionId = randomUUID();
    this.event({ type: 'worker.starting', sessionId });
    const connection = await createConnection(credentials, sessionId);
    if (this.ending) throw new Error('Agent startup was cancelled.');
    const child = this.spawnProcess(python, ['-u', runner], {
      cwd: this.directory, windowsHide: true,
      env: { ...process.env, ...credentials, PYTHONIOENCODING: 'utf-8', LIVEKIT_AGENT_NAME_OVERRIDE: `jarvis-desktop-${sessionId}`, JARVIS_DESKTOP_SESSION_ID: sessionId, JARVIS_DESKTOP_IDENTITY: connection.participantIdentity, JARVIS_DESKTOP_ROOM: `jarvis-desktop-${sessionId}` },
      stdio: ['pipe', 'pipe', 'pipe'],
    });
    this.child = child;
    child.stdin.on('error', () => {});
    const errors = createInterface({ input: child.stderr });
    errors.on('line', line => {
      if (/lk\.pii|conversation_item_added|executing tool|transcript|arguments/i.test(line)) return;
      this.log(redact(line.slice(0, 4000), this.secrets));
    });
    try {
      await new Promise<void>((resolve, reject) => {
        let ready = false;
        const timer = setTimeout(() => reject(new Error('Agent startup timed out. Check your network and credentials.')), this.startupTimeout);
        const lines = createInterface({ input: child.stdout });
        const fail = (message: string) => {
          clearTimeout(timer);
          const safe = redact(message, this.secrets);
          this.event({ type: 'worker.error', sessionId, message: safe });
          if (!ready) reject(new Error(safe));
        };
        lines.on('line', line => {
          try {
            const message = parseLifecycle(line);
            if (!message) return;
            if (message.type === 'worker.ready') {
              ready = true; clearTimeout(timer);
              this.event({ type: 'worker.ready', sessionId }); resolve();
            } else if (message.type === 'worker.error' || message.type === 'protocol.error') {
              fail(message.message || 'Agent lifecycle protocol failed.');
            }
          } catch (error) { fail((error as Error).message); }
        });
        child.once('error', error => fail(error.message));
        child.once('exit', code => {
          clearTimeout(timer);
          lines.close(); errors.close();
          if (this.child === child) { this.child = undefined; this.connection = undefined; }
          if (!this.ending) fail(`Agent exited${code === null ? '' : ` with code ${code}`}. Use Reconnect.`);
          else if (!ready) reject(new Error('Agent startup was cancelled.'));
          this.event({ type: 'worker.stopped', sessionId });
        });
      });
      if (this.ending) throw new Error('Agent startup was cancelled.');
      this.connection = connection;
      return connection;
    } catch (error) {
      await this.stop();
      throw error;
    }
  }

  end(sessionId: string): Promise<void> {
    if (this.connection && this.connection.sessionId !== sessionId) throw new Error('Session ID does not match.');
    return this.stop();
  }

  stop(): Promise<void> {
    if (this.stopping) return this.stopping;
    this.stopping = this.shutdown().finally(() => { this.stopping = undefined; });
    return this.stopping;
  }

  private async shutdown(): Promise<void> {
    this.ending = true;
    const child = this.child;
    this.connection = undefined;
    if (!child || child.exitCode !== null) return;
    child.stdin.end(JSON.stringify({ type: 'shutdown' }) + '\n');
    const exited = await new Promise<boolean>(resolve => {
      const timer = setTimeout(() => resolve(false), 10000);
      child.once('exit', () => { clearTimeout(timer); resolve(true); });
    });
    if (!exited && child.pid) {
      await new Promise<void>(resolve => {
        const killer = this.spawnProcess('taskkill', ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true });
        killer.once('exit', () => resolve()); killer.once('error', () => { child.kill(); resolve(); });
      });
    }
    if (this.child === child) this.child = undefined;
  }
}
