import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import { defaultPreferences, type Preferences, type Transcript } from '../shared';
import { VoiceController } from './controller';
import { applyEvent, initialState, visibleState } from './state';

const operationNames: Record<string, string> = { navigate: 'Opening page', act: 'Interacting with page', observe: 'Inspecting page', tabs: 'Managing browser tabs', wait: 'Waiting for page', prepare: 'Preparing review', execute: 'Executing approved action', cancel: 'Cancelling pending action', diagnostics: 'Reading browser diagnostics' };

export function App() {
  const [dashboard, setDashboard] = useState(initialState());
  const [preferences, setPreferences] = useState<Preferences>(defaultPreferences);
  const [muted, setMuted] = useState(true);
  const [level, setLevel] = useState(0);
  const [settings, setSettings] = useState(false);
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [text, setText] = useState('');
  const [notice, setNotice] = useState('');
  const [approvalBusy, setApprovalBusy] = useState(false);
  const [diagnostics, setDiagnostics] = useState('');
  const [recoveryExpired, setRecoveryExpired] = useState(false);
  const [busy, setBusy] = useState(false);
  const voice = useRef<VoiceController | null>(null);
  const connectionId = useRef('');
  const connecting = useRef(false);
  const mounted = useRef(true);
  const transcriptEnd = useRef<HTMLDivElement>(null);
  const showError = (error: unknown) => setNotice(error instanceof Error ? error.message : String(error));
  const refreshDevices = useCallback(async () => {
    try { setDevices(await navigator.mediaDevices.enumerateDevices()); } catch (error) { showError(error); }
  }, []);

  const connect = useCallback(async () => {
    if (connecting.current) return;
    connecting.current = true; setBusy(true); setNotice(''); setDashboard(initialState());
    try {
      await voice.current?.disconnect(); voice.current = null;
      if (connectionId.current) await window.jarvis.endSession(connectionId.current);
      connectionId.current = '';
      const config = await window.jarvis.getConfiguration(); setPreferences(config.preferences);
      const connection = await window.jarvis.startSession();
      if (!mounted.current) { await window.jarvis.endSession(connection.sessionId); return; }
      connectionId.current = connection.sessionId;
      setDashboard({ ...initialState(connection.sessionId), state: 'connecting' });
      const controller = new VoiceController(
        event => setDashboard(current => applyEvent(current, event)),
        (state, message) => { if (state) setDashboard(current => ({ ...current, state })); if (message) setNotice(message); },
        setLevel, enabled => setMuted(!enabled),
      );
      voice.current = controller;
      try { await controller.connect(connection, config.preferences); }
      catch (error) {
        // A denied microphone must not prevent text commands on a connected room.
        if (controller.room.state === 'connected') { showError(error); await controller.snapshot(); } else throw error;
      }
      await refreshDevices();
    } catch (error) {
      showError(error); setDashboard(current => ({ ...current, state: 'disconnected' }));
      await voice.current?.disconnect(); voice.current = null;
      if (connectionId.current) await window.jarvis.endSession(connectionId.current).catch(() => {});
      connectionId.current = '';
    } finally { connecting.current = false; setBusy(false); }
  }, [refreshDevices]);

  useEffect(() => {
    mounted.current = true;
    const unsubscribe = window.jarvis.onBackendEvent(event => {
      if (event.sessionId && connectionId.current && event.sessionId !== connectionId.current) return;
      if (event.type === 'worker.error') { setNotice(event.message || 'The agent failed.'); setDashboard(current => ({ ...current, state: 'disconnected' })); }
      if (event.type === 'worker.stopped' && !connecting.current) setDashboard(current => ({ ...current, state: 'disconnected' }));
      if (event.type === 'app.closing') void voice.current?.disconnect();
    });
    void connect();
    navigator.mediaDevices.addEventListener('devicechange', refreshDevices);
    return () => { mounted.current = false; unsubscribe(); navigator.mediaDevices.removeEventListener('devicechange', refreshDevices); void voice.current?.disconnect(); };
  }, [connect, refreshDevices]);
  useEffect(() => { transcriptEnd.current?.scrollIntoView({ behavior: 'smooth' }); }, [dashboard.transcripts.length, dashboard.interim]);
  useEffect(() => { setApprovalBusy(false); }, [dashboard.approval?.actionId]);
  useEffect(() => {
    setRecoveryExpired(false);
    if (!['recovering', 'connecting', 'initializing'].includes(dashboard.state)) return;
    const timer = setTimeout(() => setRecoveryExpired(true), 15000);
    return () => clearTimeout(timer);
  }, [dashboard.state]);
  const updatePreferences = async (values: Partial<Preferences>) => {
    try { const saved = await window.jarvis.savePreferences(values); setPreferences(saved); await voice.current?.changeDevices(saved); }
    catch (error) { showError(error); }
  };
  const resolveApproval = async (decision: 'approve' | 'cancel') => {
    if (!dashboard.approval || approvalBusy) return;
    setApprovalBusy(true);
    try { await voice.current!.resolveApproval(dashboard.approval.actionId, decision); }
    catch (error) { showError(error); await voice.current?.snapshot(); setApprovalBusy(false); }
  };
  const send = async () => {
    if (!text.trim() || busy) return;
    setBusy(true);
    try { await voice.current!.sendText(text); setText(''); } catch (error) { showError(error); }
    finally { setBusy(false); }
  };
  const exportTranscript = () => {
    const blob = new Blob([dashboard.transcripts.map(item => `${item.role === 'user' ? 'You' : 'Jarvis'}: ${item.text}`).join('\n\n')], { type: 'text/plain' });
    const url = URL.createObjectURL(blob); const link = document.createElement('a'); link.href = url; link.download = 'jarvis-conversation.txt'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const state = visibleState(dashboard, muted);
  const disconnected = dashboard.state === 'disconnected' || !connectionId.current;
  return <div className="app-shell">
    <header><div className="brand"><span className="brand-mark">J</span><div><strong>Jarvis</strong><small>Your voice, in command.</small></div></div><div className="header-actions"><span className="local-badge"><i />Runs on your PC</span><button className="icon-button" onClick={() => setSettings(!settings)} aria-expanded={settings}>Settings</button></div></header>
    <main>
      <section className="voice-panel">
        <div className="eyebrow">VOICE ASSISTANT</div>
        <div className={`orb ${muted ? 'muted' : ''} ${state === 'speaking' ? 'speaking' : ''}`} style={{ '--level': level } as CSSProperties}><div className="orb-core"><svg viewBox="0 0 40 40" aria-hidden="true"><rect x="15" y="6" width="10" height="20" rx="5"/><path d="M10 19v3a10 10 0 0 0 20 0v-3M20 32v5M14 37h12"/></svg></div></div>
        <h1>{state.charAt(0).toUpperCase() + state.slice(1)}</h1>
        <p className="voice-subtitle">{muted ? 'Microphone is off. You can still type a command.' : 'Speak naturally. Jarvis will respond and carry out your commands.'}</p>
        <div className="level-meter" aria-label={`Microphone level ${Math.round(level * 100)} percent`}><span style={{ width: `${level * 100}%` }}/></div>
        <div className="voice-controls">
          <button className={muted ? 'primary' : ''} disabled={disconnected || busy} onClick={async () => { try { await voice.current?.setMuted(!muted); await refreshDevices(); } catch (error) { showError(error); } }}>{muted ? 'Enable microphone' : 'Mute microphone'}</button>
          <button disabled={disconnected} onClick={async () => { try { const result = await voice.current?.stopTask(); if (result?.status === 'execution_in_progress') setNotice('An approved action is already executing. Its result will appear here.'); } catch (error) { showError(error); } }}>Stop task</button>
        </div>
        <button className="text-button" disabled={busy} onClick={() => void connect()}>Reconnect</button>
        {recoveryExpired && <p className="recovery-hint">The connection is taking longer than expected. Reconnect to start a fresh session.</p>}
        <div className="privacy-note"><span>●</span> Listening only while this app is open.<br/>Voice processing uses LiveKit and Gemini.</div>
      </section>
      <section className="conversation-panel">
        <div className="panel-heading"><div><div className="eyebrow">CONVERSATION</div><h2>What can I do for you?</h2></div><button className="text-button" disabled={!dashboard.transcripts.length} onClick={exportTranscript}>Export</button></div>
        {(notice || dashboard.error) && <div role="alert" className="notice"><span>{notice || dashboard.error}</span><button className="text-button" onClick={() => { setNotice(''); setDashboard(current => ({ ...current, error: '' })); }}>Dismiss</button>{/playback|audio/i.test(notice) && <button onClick={() => voice.current?.enableAudio().catch(showError)}>Enable audio</button>}</div>}
        <div className="transcript" aria-live="polite">
          {!dashboard.transcripts.length && <div className="empty-state"><div className="empty-icon">✦</div><h3>Start with a simple request</h3><p>“Open YouTube”<br/>“Find hoodies on Amazon”<br/>“Show me the black version”</p><small>Your conversation stays here until you reconnect or close the app.</small></div>}
          {dashboard.transcripts.map((item: Transcript) => <div className={`message ${item.role}`} key={item.id}><div className="message-label">{item.role === 'user' ? 'YOU' : 'JARVIS'}</div><p>{item.text}</p></div>)}
          {dashboard.interim && <div className="message user interim"><div className="message-label">YOU · SPEAKING</div><p>{dashboard.interim}</p></div>}
          <div ref={transcriptEnd}/>
        </div>
        {dashboard.action && <div className={`action-card ${dashboard.action.status}`}><div className="action-dot"/><div><strong>{operationNames[dashboard.action.operation] || dashboard.action.operation}</strong><p>{dashboard.action.message || dashboard.action.page?.url || 'Local browser'}</p>{dashboard.action.verify && <small>Page verification required</small>}</div><span>{dashboard.action.status}</span></div>}
        {dashboard.approval && <div className="approval-card"><div className="eyebrow">YOUR APPROVAL IS NEEDED</div><h3>{dashboard.approval.description}</h3><p>{dashboard.approval.page?.url}</p><details><summary>Review action details</summary><pre>{JSON.stringify(dashboard.approval.operation, null, 2)}</pre></details><div className="approval-actions"><button className="primary" disabled={!dashboard.approval.delivered || approvalBusy} onClick={() => void resolveApproval('approve')}>{approvalBusy ? 'Submitting…' : 'Approve'}</button><button disabled={approvalBusy} onClick={() => void resolveApproval('cancel')}>Cancel</button><small>{dashboard.approval.delivered ? 'You can also reply by voice.' : 'Wait for the spoken review to finish.'}</small></div></div>}
        <form className="command-input" onSubmit={event => { event.preventDefault(); void send(); }}><input aria-label="Type a command" placeholder="Or type a command…" value={text} onChange={event => setText(event.target.value)} disabled={disconnected}/><button className="primary" disabled={disconnected || busy || !text.trim()} type="submit">Send</button></form>
      </section>
    </main>
    {settings && <section className="settings-panel" aria-label="Settings"><div className="panel-heading"><h2>Audio & diagnostics</h2><button onClick={() => setSettings(false)}>Close</button></div><div className="settings-grid"><label>Microphone<select value={preferences.inputDevice} onChange={event => void updatePreferences({ inputDevice: event.target.value })}><option value="">System default</option>{devices.filter(device => device.kind === 'audioinput').map((device, index) => <option key={device.deviceId || index} value={device.deviceId}>{device.label || `Microphone ${index + 1}`}</option>)}</select></label><label>Speakers<select value={preferences.outputDevice} onChange={event => void updatePreferences({ outputDevice: event.target.value })}><option value="">System default</option>{devices.filter(device => device.kind === 'audiooutput').map((device, index) => <option key={device.deviceId || index} value={device.deviceId}>{device.label || `Speaker ${index + 1}`}</option>)}</select></label><label>Volume<input type="range" min="0" max="1" step="0.05" value={preferences.volume} onChange={event => void updatePreferences({ volume: Number(event.target.value) })}/></label></div><button onClick={async () => { try { setDiagnostics(await window.jarvis.getDiagnostics()); } catch (error) { showError(error); } }}>Show redacted diagnostics</button>{diagnostics && <pre className="diagnostics">{diagnostics}</pre>}</section>}
    <div id="audio-output" hidden/>
  </div>;
}
