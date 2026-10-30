// Dedicated test main process: never imports the production backend manager.
const { app, BrowserWindow, session } = require('electron');
const path = require('node:path');
app.commandLine.appendSwitch('use-fake-device-for-media-stream');
app.commandLine.appendSwitch('use-fake-ui-for-media-stream');
app.whenReady().then(() => {
  session.defaultSession.setPermissionRequestHandler((_contents, permission, callback, details) => callback(permission === 'media' && !details.mediaTypes?.includes('video')));
  const window = new BrowserWindow({ show: false, width: 1160, height: 820, webPreferences: { preload: path.join(__dirname, 'test-preload.cjs'), nodeIntegration: false, contextIsolation: true, sandbox: true } });
  window.loadURL('http://127.0.0.1:5178');
});
app.on('window-all-closed', () => app.quit());
