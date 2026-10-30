export const Track = { Kind: { Audio: 'audio' }, Source: { Microphone: 'microphone' } };
export const RoomEvent = {
  ParticipantConnected: 'participant', TrackSubscribed: 'track', TrackUnsubscribed: 'untrack',
  Reconnecting: 'reconnecting', Reconnected: 'reconnected', Disconnected: 'disconnected',
  MediaDevicesError: 'mediaerror', LocalTrackUnpublished: 'unpublished', ParticipantDisconnected: 'left',
};
export class Room {
  state = 'disconnected';
  remoteParticipants = new Map([['fixture-agent', { identity: 'fixture-agent', isAgent: true }]]);
  private callbacks = new Map<string, Array<(...args: any[]) => void>>();
  private handler?: (reader: any, sender: any) => Promise<void>;
  private sessionId = '';
  private sequence = 0;
  private stream?: MediaStream;
  private approval: Record<string, unknown> | null = null;
  localParticipant = {
    isMicrophoneEnabled: false,
    setMicrophoneEnabled: async (enabled: boolean) => {
      this.stream?.getTracks().forEach(track => track.stop());
      this.stream = enabled ? await navigator.mediaDevices.getUserMedia({ audio: true }) : undefined;
      this.localParticipant.isMicrophoneEnabled = enabled;
    },
    getTrackPublication: () => this.stream ? { track: { mediaStreamTrack: this.stream.getAudioTracks()[0] } } : undefined,
    performRpc: async ({ method, payload }: { method: string; payload: string }) => {
      if (method === 'jarvis.getSnapshot') this.send('session.snapshot', { state: 'listening', approval: this.approval, action: null, transcripts: [] });
      if (method === 'jarvis.resolveApproval') {
        if (JSON.parse(payload).actionId !== this.approval?.actionId) throw new Error('Stale approval');
        const decision = JSON.parse(payload).decision;
        this.approval = null; this.send('approval.cleared', {});
        this.send('action.finished', { id: 'approved', operation: decision === 'approve' ? 'execute' : 'cancel', status: 'completed' });
      }
      if (method === 'jarvis.stopTask') { this.approval = null; this.send('approval.cleared', {}); }
      return JSON.stringify({ status: 'completed' });
    },
    sendText: async (text: string) => {
      this.send('transcript.updated', { id: `user-${this.sequence}`, role: 'user', text, final: true });
      if (/review/i.test(text)) {
        this.approval = { actionId: 'fixture-review', delivered: true, description: 'Run the practice action', page: { url: 'http://practice/' }, operation: { action: 'click', target: { kind: 'role', value: 'button', name: 'Practice' } } };
        this.send('approval.pending', this.approval);
      } else {
        this.send('action.started', { id: 'search', operation: 'act', status: 'running' });
        this.send('action.finished', { id: 'search', operation: 'act', status: 'completed', page: { url: 'http://practice/search?q=hoodies' } });
        this.send('transcript.updated', { id: `assistant-${this.sequence}`, role: 'assistant', text: 'The practice search results are open.', final: true });
      }
    },
  };
  constructor(_options: unknown) { (window as unknown as Record<string, unknown>).fixtureRoom = this; }
  registerTextStreamHandler(_topic: string, callback: any) { this.handler = callback; }
  on(event: string, callback: (...args: any[]) => void) { this.callbacks.set(event, [...(this.callbacks.get(event) || []), callback]); return this; }
  emit(event: string, ...args: unknown[]) { this.callbacks.get(event)?.forEach(callback => callback(...args)); }
  async connect(_url: string, _token: string) {
    // The test session ID is monotonically allocated by the dedicated preload.
    const globals = window as unknown as Record<string, any>;
    globals.fixtureConnections = (globals.fixtureConnections || 0) + 1;
    this.sessionId = `fixture-${globals.fixtureConnections}`;
    this.state = 'connected';
  }
  private send(type: string, payload: unknown) {
    const text = JSON.stringify({ version: 1, sessionId: this.sessionId, sequence: ++this.sequence, type, payload, timestamp: Date.now() / 1000 });
    void this.handler?.({ readAll: async () => text }, { identity: 'fixture-agent' });
  }
  async switchActiveDevice(_kind: string, _id: string) {}
  async startAudio() {}
  async disconnect(_stop = true) {
    this.stream?.getTracks().forEach(track => track.stop()); this.stream = undefined;
    this.state = 'disconnected'; this.emit(RoomEvent.Disconnected);
  }
}
