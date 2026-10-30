import { app, BrowserWindow, dialog, ipcMain, net, protocol, session } from 'electron';
import { appendFileSync, existsSync, readFileSync, renameSync, writeFileSync, mkdirSync } from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { BackendManager } from './backend';
import { defaultPreferences, type Preferences } from './shared';
import { validatePreferences } from './preferences';

declare const MAIN_WINDOW_VITE_DEV_SERVER_URL: string | undefined;
declare const MAIN_WINDOW_VITE_NAME: string;
declare const JARVIS_DEFAULT_AGENT_DIR: string;

protocol.registerSchemesAsPrivileged([{ scheme: 'jarvis', privileges: { standard: true, secure: true, supportFetchAPI: true, stream: true } }]);
app.setName('Jarvis');
let window: BrowserWindow | undefined;
let backend: BackendManager;
let preferences: Preferences = { ...defaultPreferences };
let exiting = false;
let preferencePath: string;
let logPath: string;
const agentDirectory = path.resolve(process.env.JARVIS_AGENT_DIR || JARVIS_DEFAULT_AGENT_DIR);
const devUrl = typeof MAIN_WINDOW_VITE_DEV_SERVER_URL === 'string' ? MAIN_WINDOW_VITE_DEV_SERVER_URL : undefined;
function trusted(url: string): boolean {
  try { const parsed = new URL(url); return devUrl ? parsed.origin === new URL(devUrl).origin : parsed.protocol === 'jarvis:' && parsed.host === 'app'; } catch { return false; }
}
function persist() { writeFileSync(preferencePath, JSON.stringify(preferences, null, 2)); }
function log(line: string) {
  try {
    if (existsSync(logPath) && Buffer.byteLength(readFileSync(logPath)) > 512 * 1024) {
      renameSync(logPath, logPath + '.previous');
    }
    appendFileSync(logPath, `${new Date().toISOString()} ${line}\n`);
  } catch { /* Diagnostics must not crash an otherwise working voice session. */ }
}

if (!app.requestSingleInstanceLock()) app.quit();
else {
  app.on('second-instance', () => { window?.restore(); window?.focus(); });
  app.whenReady().then(async () => {
    mkdirSync(app.getPath('userData'), { recursive: true });
    preferencePath = path.join(app.getPath('userData'), 'preferences.json');
    logPath = path.join(app.getPath('userData'), 'backend.log');
    try {
      const stored = JSON.parse(readFileSync(preferencePath, 'utf8'));
      const { microphoneConsent, ...rest } = stored;
      preferences = { ...defaultPreferences, ...validatePreferences(rest), microphoneConsent: microphoneConsent === true };
    } catch { /* Missing or invalid preferences use defaults. */ }
    backend = new BackendManager(agentDirectory, event => window?.webContents.send('jarvis:backend', event), log);
    const root = path.resolve(__dirname, '../renderer', MAIN_WINDOW_VITE_NAME);
    protocol.handle('jarvis', request => {
      const url = new URL(request.url);
      const target = path.resolve(root, '.' + decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname));
      const relative = path.relative(root, target);
      if (url.host !== 'app' || relative.startsWith('..') || path.isAbsolute(relative)) return new Response('Forbidden', { status: 403 });
      return net.fetch(pathToFileURL(target).toString());
    });
    session.defaultSession.setPermissionCheckHandler((_contents, permission, origin, details) => trusted(origin) && preferences.microphoneConsent && permission === 'media' && details.mediaType !== 'video');
    session.defaultSession.setPermissionRequestHandler(async (contents, permission, callback, details) => {
      if (contents !== window?.webContents || !trusted(details.requestingUrl || contents.getURL()) || permission !== 'media' || !('mediaTypes' in details) || details.mediaTypes?.includes('video')) { callback(false); return; }
      if (!preferences.microphoneConsent) {
        const answer = await dialog.showMessageBox(window!, {
          type: 'question', title: 'Allow microphone access?',
          message: 'Jarvis listens while this app is open.', detail: 'Your speech is sent through LiveKit to Gemini to understand and carry out your commands. You can mute at any time. Closing the window ends the session.',
          buttons: ['Allow microphone', 'Use text only'], defaultId: 0, cancelId: 1,
        });
        preferences.microphoneConsent = answer.response === 0;
        persist();
      }
      callback(preferences.microphoneConsent);
    });
    const handle = (name: string, callback: (...args: any[]) => unknown) => ipcMain.handle(name, (event, ...args) => {
      if (event.sender !== window?.webContents || !event.senderFrame || event.senderFrame !== event.sender.mainFrame || !trusted(event.senderFrame.url)) throw new Error('Untrusted IPC caller.');
      return callback(...args);
    });
    handle('jarvis:configuration', () => ({ agentDirectory, preferences }));
    handle('jarvis:start', () => backend.start());
    handle('jarvis:end', (id: unknown) => { if (typeof id !== 'string' || id.length > 100) throw new Error('Invalid session ID.'); return backend.end(id); });
    handle('jarvis:preferences', (values: unknown) => { preferences = { ...preferences, ...validatePreferences(values) }; persist(); return preferences; });
    handle('jarvis:diagnostics', () => existsSync(logPath) ? readFileSync(logPath, 'utf8').slice(-30000) : 'No backend diagnostics yet.');
    window = new BrowserWindow({ width: preferences.width, height: preferences.height, minWidth: 760, minHeight: 620, backgroundColor: '#101318', title: 'Jarvis', autoHideMenuBar: true, webPreferences: { preload: path.join(__dirname, 'preload.cjs'), nodeIntegration: false, contextIsolation: true, sandbox: true } });
    window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
    window.webContents.on('will-navigate', (event, url) => { if (!trusted(url)) event.preventDefault(); });
    window.on('close', event => {
      if (exiting) return;
      event.preventDefault();
      const [width, height] = window!.getSize(); preferences.width = width; preferences.height = height; persist();
      app.quit();
    });
    await window.loadURL(devUrl || 'jarvis://app/index.html');
  }).catch(error => { dialog.showErrorBox('Jarvis could not start', String(error)); app.quit(); });
  app.on('before-quit', event => {
    if (exiting) return;
    event.preventDefault(); exiting = true;
    window?.webContents.send('jarvis:backend', { type: 'app.closing' });
    Promise.resolve(backend?.stop()).finally(() => app.quit());
  });
  app.on('window-all-closed', () => app.quit());
}
