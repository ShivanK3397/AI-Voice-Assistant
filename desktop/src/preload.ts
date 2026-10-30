import { contextBridge, ipcRenderer } from 'electron';
import type { BackendEvent, DesktopApi, Preferences } from './shared';

const api: DesktopApi = {
  getConfiguration: () => ipcRenderer.invoke('jarvis:configuration'),
  startSession: () => ipcRenderer.invoke('jarvis:start'),
  endSession: (sessionId: string) => ipcRenderer.invoke('jarvis:end', sessionId),
  savePreferences: (preferences: Partial<Preferences>) => ipcRenderer.invoke('jarvis:preferences', preferences),
  getDiagnostics: () => ipcRenderer.invoke('jarvis:diagnostics'),
  onBackendEvent: callback => {
    const listener = (_event: unknown, event: BackendEvent) => callback(event);
    ipcRenderer.on('jarvis:backend', listener);
    return () => ipcRenderer.removeListener('jarvis:backend', listener);
  },
};
contextBridge.exposeInMainWorld('jarvis', api);
