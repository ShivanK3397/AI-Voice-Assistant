export interface Preferences {
  inputDevice: string; outputDevice: string; volume: number; microphoneConsent: boolean;
  width: number; height: number;
}
export const defaultPreferences: Preferences = { inputDevice: '', outputDevice: '', volume: 0.8, microphoneConsent: false, width: 1160, height: 820 };
export interface Configuration { agentDirectory: string; preferences: Preferences }
export interface SessionConnection { sessionId: string; serverUrl: string; participantIdentity: string; participantToken: string }
export interface BackendEvent { type: string; sessionId?: string; message?: string }
export interface Action { id: string; operation: string; status: string; message?: string; page?: { url: string }; verify?: string }
export interface Approval { actionId: string; description: string; delivered: boolean; page: { url: string }; operation: Record<string, unknown> }
export interface Transcript { id: string; role: 'user' | 'assistant'; text: string; final: boolean }
export interface DesktopEvent { version: number; sessionId: string; sequence: number; type: string; timestamp: number; payload: Record<string, unknown> }
export interface DesktopApi {
  getConfiguration(): Promise<Configuration>;
  startSession(): Promise<SessionConnection>;
  endSession(sessionId: string): Promise<void>;
  savePreferences(preferences: Partial<Preferences>): Promise<Preferences>;
  getDiagnostics(): Promise<string>;
  onBackendEvent(callback: (event: BackendEvent) => void): () => void;
}
declare global { interface Window { jarvis: DesktopApi } }
