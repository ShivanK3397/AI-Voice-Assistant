import type { Action, Approval, DesktopEvent, Transcript } from '../shared';

export interface DashboardState {
  sessionId: string; sequence: number; state: string; action: Action | null;
  approval: Approval | null; transcripts: Transcript[]; interim: string; error: string;
}
export function initialState(sessionId = ''): DashboardState {
  return { sessionId, sequence: 0, state: 'starting', action: null, approval: null, transcripts: [], interim: '', error: '' };
}
export function applyEvent(state: DashboardState, event: DesktopEvent): DashboardState {
  if (event.version !== 1 || event.sessionId !== state.sessionId || !Number.isSafeInteger(event.sequence) || event.sequence <= state.sequence) return state;
  const next = { ...state, sequence: event.sequence };
  const payload = event.payload;
  if (event.type === 'session.snapshot') {
    next.state = String(payload.state);
    next.action = payload.action as Action | null;
    next.approval = payload.approval as Approval | null;
    next.transcripts = (payload.transcripts as Transcript[]).slice(-300);
    next.interim = '';
  } else if (event.type === 'session.ready' || event.type === 'session.state') {
    next.state = String(payload.state);
    if (next.state !== 'recovering' && next.state !== 'disconnected') next.error = '';
  } else if (event.type === 'session.error') {
    next.state = payload.recoverable ? 'recovering' : 'disconnected';
    next.error = String(payload.message);
  } else if (event.type.startsWith('action.')) next.action = payload as unknown as Action;
  else if (event.type === 'approval.pending') next.approval = payload as unknown as Approval;
  else if (event.type === 'approval.cleared') next.approval = null;
  else if (event.type === 'transcript.updated') {
    const transcript = payload as unknown as Transcript;
    if (!transcript.final) next.interim = transcript.text;
    else {
      next.interim = '';
      const existing = state.transcripts.findIndex(item => item.id === transcript.id);
      next.transcripts = existing < 0 ? [...state.transcripts, transcript].slice(-300) : state.transcripts.map(item => item.id === transcript.id ? transcript : item);
    }
  }
  return next;
}
export function visibleState(state: DashboardState, muted: boolean): string {
  if (['starting', 'connecting', 'initializing', 'recovering', 'disconnected'].includes(state.state)) return state.state;
  if (state.approval) return 'awaiting approval';
  if (state.action?.status === 'running') return 'working';
  if (muted && ['listening', 'idle'].includes(state.state)) return 'muted';
  return state.state;
}
