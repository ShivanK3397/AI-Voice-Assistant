import { test, expect, _electron as electron } from '@playwright/test';
import path from 'node:path';

test('desktop captures synthetic audio, executes a fixture command and supports approvals', async () => {
  const application = await electron.launch({ args: [path.resolve('tests/electron-harness.cjs')] });
  try {
    const window = await application.firstWindow();
    await expect(window.getByRole('heading', { name: 'Listening', exact: true })).toBeVisible();
    await expect(window.getByRole('button', { name: 'Mute microphone' })).toBeEnabled();
    await window.getByRole('button', { name: 'Mute microphone' }).click();
    await expect(window.getByRole('heading', { name: 'Muted', exact: true })).toBeVisible();
    await window.getByRole('button', { name: 'Enable microphone' }).click();
    await window.getByRole('textbox', { name: 'Type a command' }).fill('Find hoodies');
    await window.getByRole('button', { name: 'Send', exact: true }).click();
    await expect(window.getByText('The practice search results are open.')).toBeVisible();
    await expect(window.getByText('http://practice/search?q=hoodies')).toBeVisible();
    await window.getByRole('textbox', { name: 'Type a command' }).fill('Review the practice action');
    await window.getByRole('button', { name: 'Send', exact: true }).click();
    await expect(window.getByRole('button', { name: 'Approve', exact: true })).toBeEnabled();
    await window.getByRole('button', { name: 'Approve', exact: true }).click();
    await expect(window.getByRole('button', { name: 'Approve', exact: true })).toHaveCount(0);
    await window.getByRole('button', { name: 'Settings', exact: true }).click();
    await expect(window.getByRole('combobox', { name: 'Microphone', exact: true })).toBeVisible();
    await window.getByRole('button', { name: 'Show redacted diagnostics' }).click();
    await expect(window.getByText('Fixture diagnostics: no external services were called.')).toBeVisible();
  } finally { await application.close(); }
});

test('reconnection starts a fresh session without replaying previous commands', async () => {
  const application = await electron.launch({ args: [path.resolve('tests/electron-harness.cjs')] });
  try {
    const window = await application.firstWindow();
    await expect(window.getByRole('heading', { name: 'Listening', exact: true })).toBeVisible();
    await window.getByRole('textbox', { name: 'Type a command' }).fill('Find hoodies');
    await window.getByRole('button', { name: 'Send', exact: true }).click();
    await expect(window.getByText('The practice search results are open.')).toBeVisible();
    await window.getByRole('button', { name: 'Reconnect', exact: true }).click();
    await expect(window.getByRole('heading', { name: 'Listening', exact: true })).toBeVisible();
    await expect(window.getByText('The practice search results are open.')).toHaveCount(0);
    await expect(window.getByText('Start with a simple request')).toBeVisible();
  } finally { await application.close(); }
});
