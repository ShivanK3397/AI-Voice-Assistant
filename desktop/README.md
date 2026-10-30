# Jarvis desktop

Windows desktop voice interface for the Python agent in the parent directory. The app
starts the agent directly, joins a private LiveKit room, and automatically enables
the microphone after permission. Browser commands run in a separate visible
Playwright browser on this PC. No LiveKit CLI is needed.

## First launch

Use a normal PowerShell terminal:

```powershell
cd "C:\Users\shiva\Coding Projects\Jarvis\my-agent"
uv sync
uv run playwright install chromium
cd desktop
npm install
npm run dev
```

Set `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, and `GOOGLE_API_KEY` in
`my-agent/.env.local`. This file stays outside the desktop build. Do not put keys
in renderer environment variables. Voice processing requires network access to
LiveKit and Gemini.

On the first launch, choose **Allow microphone** or **Use text only**. The window
shows the real session state and browser-operation results. Typed commands use
the same agent. Purchases, consequential changes, and advanced scripts still need
a delivered review and either spoken approval or the Approve button.
Close any existing agent console before using the desktop app: both would own
the same persistent browser profile, and the profile lock correctly rejects that.

## Build and desktop shortcut

```powershell
npm run build
npm run shortcut
```

The build produces `out/Jarvis-win32-x64/Jarvis.exe`. The shortcut opens that
executable without a terminal. This is a local-PC build: Python, its virtual
environment, browser binaries, and credentials are intentionally not bundled.
Keep `my-agent` in place. The default absolute project directory is recorded at
build time; `JARVIS_AGENT_DIR` can override it before launching the app.

`npm run start` opens the locally built `.vite` entry. `npm run dev` runs Vite
and Electron together. Build again after changing the production app.

## Controls and lifecycle

- **Mute microphone** stops publishing microphone audio. It does not stop a task.
- **Stop task** interrupts cancellable work and clears pending approvals. It
  does not replay or abort an approved effect already being executed.
- **Reconnect** closes the old session before creating a new one. The previous
  command is never automatically resent. Browser windows close; logins persist.
- Closing the window ends audio capture and shuts down the owned agent/browser
  process tree. Jarvis does not run in the tray or listen after closing.
- Settings select input/output devices and volume. Defaults follow Windows.
- Transcript history is in memory; Export saves a text file on request.

Settings and redacted rotating diagnostics are under `%APPDATA%/Jarvis` (Electron's
user-data directory). Transcripts and raw audio are not written to diagnostics.
The browser retains the existing `my-agent/.browser` profile and artifacts unless
the existing browser environment variables specify different directories.

## Validation

```powershell
npm run typecheck
npm test
npm run test:e2e
cd ..
uv run ruff check
uv run pytest
```

The Electron E2E harness uses a deterministic fake LiveKit room and Chromium's
synthetic microphone. It never starts the production backend, calls Gemini, or
visits Amazon. Python tests cover the real approval state and authenticated
desktop bridge; existing browser runtime tests cover real Playwright behavior.

Manual voice acceptance: open YouTube; search Amazon for hoodies; select a
specific variant; approve/cancel by voice and button; mute; switch devices;
disconnect the network; reconnect; close and check that child processes exit;
reopen and check retained browser logins.

## Troubleshooting

- **npm EACCES / registry access denied:** install from your normal terminal or
  ask your environment administrator to permit npm registry access. The coding
  environment may have different network restrictions from your terminal.
- **PyAV DLL blocked by Application Control:** the Python agent cannot start
  while that native library is blocked. Use an environment where your policy
  permits the installed dependencies; consult the administrator managing that
  policy. Reinstalling packages alone does not establish that a policy block is fixed.
- **No microphone:** check Windows Settings → Privacy & security → Microphone,
  then select an available device in Jarvis and enable it. Text input remains available.
- **No sound:** select speakers, check volume, and click Enable audio if prompted.
- **Recovering:** allow automatic reconnection. After fifteen seconds, the UI
  offers a fresh session. Do not repeat an uncertain purchase or submission.

The initial implementation was validated with dependency-free desktop protocol
tests and Python approval/bridge tests. Full installation/build, Electron E2E, and
real voice acceptance require an environment permitting npm downloads and the
agent's native Python libraries.
