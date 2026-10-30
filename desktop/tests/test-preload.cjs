const { contextBridge } = require('electron');
let preferences = { inputDevice: '', outputDevice: '', volume: 0.8, microphoneConsent: true, width: 1160, height: 820 };
let count = 0;
contextBridge.exposeInMainWorld('jarvis', {
  getConfiguration: async () => ({ agentDirectory: 'deterministic-fixture', preferences }),
  startSession: async () => ({ sessionId: `fixture-${++count}`, participantIdentity: 'fixture-user', participantToken: 'fixture-token', serverUrl: 'fixture://local' }),
  endSession: async () => {},
  savePreferences: async values => (preferences = { ...preferences, ...values }),
  getDiagnostics: async () => 'Fixture diagnostics: no external services were called.',
  onBackendEvent: () => () => {},
});
