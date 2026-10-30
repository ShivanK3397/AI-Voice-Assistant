import { defaultPreferences, type Preferences } from './shared';

export function validatePreferences(input: unknown): Partial<Preferences> {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('Invalid preferences.');
  const values = input as Record<string, unknown>;
  const output: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(values)) {
    if (!(key in defaultPreferences)) throw new Error('Unknown preference.');
    if (key === 'inputDevice' || key === 'outputDevice') {
      if (typeof value !== 'string' || value.length > 512) throw new Error('Invalid audio device.');
    } else if (key === 'microphoneConsent') {
      // Consent is owned by the main-process permission dialog.
      throw new Error('Microphone consent cannot be changed through renderer IPC.');
    } else {
      if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error('Invalid numeric preference.');
      if (key === 'volume' && (value < 0 || value > 1)) throw new Error('Invalid volume.');
      if (key !== 'volume' && (value < 400 || value > 5000)) throw new Error('Invalid window size.');
    }
    output[key] = value;
  }
  return output;
}
