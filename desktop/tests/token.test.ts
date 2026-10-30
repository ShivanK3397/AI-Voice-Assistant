import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createConnection } from '../src/backend';

test('desktop token grants only its room and dispatches only its owned worker', async () => {
  const connection = await createConnection({ LIVEKIT_API_KEY: 'test-key', LIVEKIT_API_SECRET: 'test-secret', LIVEKIT_URL: 'wss://example.livekit.cloud' }, 'owned-session');
  const claims = JSON.parse(Buffer.from(connection.participantToken.split('.')[1], 'base64url').toString());
  assert.equal(claims.video.room, 'jarvis-desktop-owned-session');
  assert.equal(claims.sub, 'desktop-user-owned-session');
  assert.equal(claims.video.roomAdmin, undefined);
  assert.equal(claims.roomConfig.agents[0].agentName, 'jarvis-desktop-owned-session');
  assert.equal(claims.exp - claims.nbf, 600);
  assert.equal((connection as unknown as Record<string, unknown>).LIVEKIT_API_SECRET, undefined);
});
