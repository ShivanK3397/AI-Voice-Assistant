import { Room, RoomEvent, Track, type RemoteParticipant, type RemoteTrack } from 'livekit-client';
import type { DesktopEvent, Preferences, SessionConnection } from '../shared';

export class VoiceController {
  readonly room = new Room({ adaptiveStream: true, dynacast: true });
  private connection?: SessionConnection;
  private agentIdentity?: string;
  private intentionalDisconnect = false;
  private audioElements = new Set<HTMLMediaElement>();
  private audioContext?: AudioContext;
  private animation?: number;
  private stopped = false;
  private preferences?: Preferences;
  constructor(
    private event: (event: DesktopEvent) => void,
    private status: (state: string, message?: string) => void,
    private level: (level: number) => void,
    private microphone: (enabled: boolean) => void,
  ) {
    this.room.registerTextStreamHandler('jarvis.desktop.events', async (reader, sender) => {
      if (!this.isAgent(sender.identity)) return;
      try {
        const envelope = JSON.parse(await reader.readAll()) as DesktopEvent;
        if (!envelope || typeof envelope.type !== 'string' || !envelope.payload || !this.connection || envelope.sessionId !== this.connection.sessionId) return;
        this.event(envelope);
      } catch { this.status('recovering', 'A session update was interrupted. Requesting current state.'); void this.snapshot(); }
    });
    this.room.on(RoomEvent.ParticipantConnected, participant => this.agentJoined(participant));
    this.room.on(RoomEvent.TrackSubscribed, (track, _publication, participant) => {
      if (track.kind !== Track.Kind.Audio || !this.isAgent(participant.identity)) return;
      void this.attachAudio(track);
    });
    this.room.on(RoomEvent.TrackUnsubscribed, track => { for (const element of track.detach()) { this.audioElements.delete(element); element.remove(); } });
    this.room.on(RoomEvent.Reconnecting, () => this.status('recovering', 'The room connection was interrupted. Reconnecting…'));
    this.room.on(RoomEvent.Reconnected, () => { this.status('connecting'); void this.snapshot(); });
    this.room.on(RoomEvent.Disconnected, () => { this.stopMeter(); this.microphone(false); if (!this.intentionalDisconnect) this.status('disconnected', 'The voice connection ended. Use Reconnect.'); });
    this.room.on(RoomEvent.MediaDevicesError, error => { this.microphone(false); this.status('', `Microphone unavailable: ${error.message}. Text input still works.`); });
    this.room.on(RoomEvent.LocalTrackUnpublished, () => { this.stopMeter(); this.microphone(false); });
    this.room.on(RoomEvent.ParticipantDisconnected, participant => { if (participant.identity === this.agentIdentity) this.status('disconnected', 'The agent left the room. Use Reconnect.'); });
  }

  private isAgent(identity: string): boolean {
    const participant = this.room.remoteParticipants.get(identity);
    return !!participant && participant.isAgent && (!this.agentIdentity || identity === this.agentIdentity);
  }
  private agentJoined(participant: RemoteParticipant) {
    if (!participant.isAgent || this.agentIdentity) return;
    this.agentIdentity = participant.identity;
    void this.snapshot();
  }
  async connect(connection: SessionConnection, preferences: Preferences) {
    this.connection = connection; this.preferences = preferences;
    await this.room.connect(connection.serverUrl, connection.participantToken);
    if (this.stopped) { await this.room.disconnect(); return; }
    for (const participant of this.room.remoteParticipants.values()) this.agentJoined(participant);
    await this.setMuted(false);
  }
  async snapshot() {
    if (!this.agentIdentity) return;
    try { await this.rpc('jarvis.getSnapshot', {}); }
    catch { this.status('recovering', 'Waiting for the voice agent to initialize…'); }
  }
  private async rpc(method: string, payload: unknown) {
    if (!this.agentIdentity) throw new Error('The agent is still connecting.');
    return JSON.parse(await this.room.localParticipant.performRpc({ destinationIdentity: this.agentIdentity, method, payload: JSON.stringify(payload), responseTimeout: 10 }));
  }
  resolveApproval(actionId: string, decision: 'approve' | 'cancel') { return this.rpc('jarvis.resolveApproval', { actionId, decision }); }
  stopTask() { return this.rpc('jarvis.stopTask', {}); }
  async sendText(text: string) {
    if (!text.trim()) return;
    if (!this.agentIdentity) throw new Error('Wait for the agent to connect before sending a command.');
    await this.room.localParticipant.sendText(text.trim(), { topic: 'lk.chat', destinationIdentities: [this.agentIdentity] });
  }
  async setMuted(muted: boolean) {
    try {
      await this.room.localParticipant.setMicrophoneEnabled(!muted, { deviceId: this.preferences?.inputDevice || undefined, echoCancellation: true, noiseSuppression: true, autoGainControl: true });
      this.microphone(!muted);
      if (muted) this.stopMeter(); else await this.startMeter();
    } catch (error) {
      this.microphone(false);
      throw new Error(`Microphone could not start. Check Windows microphone permissions or select another device. ${(error as Error).message}`);
    }
  }
  async changeDevices(preferences: Preferences) {
    this.preferences = preferences;
    await this.room.switchActiveDevice('audioinput', preferences.inputDevice || 'default');
    await this.room.switchActiveDevice('audiooutput', preferences.outputDevice || 'default');
    for (const element of this.audioElements) element.volume = preferences.volume;
    if (this.room.localParticipant.isMicrophoneEnabled) await this.startMeter();
  }
  private async attachAudio(track: RemoteTrack) {
    const element = track.attach();
    element.volume = this.preferences?.volume ?? 0.8;
    document.getElementById('audio-output')?.appendChild(element);
    this.audioElements.add(element);
    try {
      if (this.preferences?.outputDevice && 'setSinkId' in element) await (element as HTMLAudioElement & { setSinkId(id: string): Promise<void> }).setSinkId(this.preferences.outputDevice);
      await element.play();
    } catch { this.status('', 'Audio playback needs your interaction. Click Enable audio.'); }
  }
  async enableAudio() { await this.room.startAudio(); for (const element of this.audioElements) await element.play(); }
  private async startMeter() {
    this.stopMeter();
    const track = this.room.localParticipant.getTrackPublication(Track.Source.Microphone)?.track;
    if (!track) return;
    this.audioContext = new AudioContext();
    const analyser = this.audioContext.createAnalyser(); analyser.fftSize = 256;
    this.audioContext.createMediaStreamSource(new MediaStream([track.mediaStreamTrack])).connect(analyser);
    await this.audioContext.resume();
    const values = new Uint8Array(analyser.frequencyBinCount);
    const tick = () => { analyser.getByteTimeDomainData(values); this.level(Math.min(1, Math.sqrt(values.reduce((sum, value) => sum + ((value - 128) / 128) ** 2, 0) / values.length) * 5)); this.animation = requestAnimationFrame(tick); };
    tick();
  }
  private stopMeter() { if (this.animation) cancelAnimationFrame(this.animation); this.animation = undefined; void this.audioContext?.close(); this.audioContext = undefined; this.level(0); }
  async disconnect() {
    this.stopped = true; this.intentionalDisconnect = true;
    this.stopMeter();
    for (const element of this.audioElements) element.remove(); this.audioElements.clear();
    await this.room.disconnect(true);
    this.microphone(false);
  }
}
