export function redact(value: string, secrets: string[] = []): string {
  let safe = value;
  for (const secret of secrets) if (secret.length > 3) safe = safe.split(secret).join('[redacted]');
  return safe.replace(/([?&](?:key|token|access_token|api_key)=)[^\s&]+/gi, '$1[redacted]')
    .replace(/(Bearer\s+)[^\s]+/gi, '$1[redacted]')
    .replace(/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g, '[redacted token]');
}

export function parseLifecycle(line: string): { type: string; message?: string } | null {
  if (line.length > 65536) throw new Error('Backend lifecycle message exceeded the size limit.');
  let data;
  try { data = JSON.parse(line); } catch { throw new Error('Malformed backend lifecycle message.'); }
  if (!data || typeof data !== 'object' || data.version !== 1 || !['worker.ready', 'worker.error', 'worker.stopped', 'protocol.error'].includes(data.type)) return null;
  return { type: data.type, message: typeof data.message === 'string' ? data.message.slice(0, 1000) : undefined };
}
