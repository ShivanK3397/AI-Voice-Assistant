<a href="https://livekit.io/">
  <img src="./.github/assets/livekit-mark.png" alt="LiveKit logo" width="100" height="100">
</a>

# LiveKit Agents starter for Python

A starter project for building voice AI apps with [LiveKit Agents for Python](https://github.com/livekit/agents) and [LiveKit Cloud](https://cloud.livekit.io/).

The starter includes:

- A simple [voice AI assistant](https://docs.livekit.io/agents/start/voice-ai/) to extend and customize.
- A voice pipeline built on [LiveKit Inference](https://docs.livekit.io/agents/models/inference/), which gives you access to [models](https://docs.livekit.io/agents/models/) from top labs with no extra configuration:
  - The default LLM is Gemma 4 31B, an open-weight model [hosted by LiveKit](https://docs.livekit.io/agents/models/llm/livekit/) and tuned for voice AI.
  - The default TTS is [Fish Audio S2.1 Pro](https://docs.livekit.io/agents/models/tts/fishaudio/), an expressive and cost-effective voice.
  - More than 50 other models are available from OpenAI, Cartesia, Deepgram, and other providers.
  - [Realtime models](https://docs.livekit.io/agents/models/realtime/) and many others are available through the [plugin ecosystem](https://docs.livekit.io/agents/models/#plugins).
- [Expressive mode](https://docs.livekit.io/agents/models/tts/expressive/), on by default, so your agent's voice carries emotion and pacing that fit the conversation.
- [Keyterms](https://docs.livekit.io/agents/models/stt/keyterms/), on by default, so speech recognition gets your names, brands, and jargon right, including names it picks up during the conversation, like a caller's.
- [LiveKit Turn Detector](https://docs.livekit.io/agents/logic/turns/turn-detector/), which knows when the user has finished speaking, in 14 languages.
- [Adaptive interruption handling](https://docs.livekit.io/agents/logic/turns/adaptive-interruption-handling/), which tells a real interruption from an "uh-huh" or background noise, so your agent doesn't stop talking when it shouldn't.
- [Background voice cancellation](https://docs.livekit.io/transport/media/noise-cancellation/).
- Session transcripts, traces, and recordings from LiveKit [Agent Observability](https://docs.livekit.io/testing/observability/).
- [Simulations](https://docs.livekit.io/testing/simulations/) that test full conversations with your agent, run in CI on every merge to `main`.
- A `Dockerfile` for [deploying to LiveKit Cloud](https://docs.livekit.io/deploy/agents/).

The starter works with any [custom web or mobile frontend](https://docs.livekit.io/frontends/) or with [telephony](https://docs.livekit.io/telephony/).

## Using coding agents

This project works with coding agents like [Claude Code](https://claude.com/product/claude-code), [Cursor](https://www.cursor.com/), and [Codex](https://openai.com/codex/).

LiveKit offers both a CLI and an [MCP server](https://docs.livekit.io/reference/developer-tools/docs-mcp/) for browsing and searching its documentation. Search returns short excerpts, so fetch the full page to read the details:

```console
lk docs search "testing my agent"
lk docs get-page /testing/unit-tests
```

The project also includes an [`AGENTS.md`](AGENTS.md) file and LiveKit's [agent skills](https://docs.livekit.io/intro/coding-agents/#agent-skills), so your coding agent follows LiveKit's best practices for workflows, handoffs, and testing, and tries its changes with the [agent debugger](https://docs.livekit.io/testing/debugger/). See the [coding agents guide](https://docs.livekit.io/intro/coding-agents/) for more details, including MCP server setup and how to update the skill.

## Dev setup

Install the [LiveKit CLI](https://docs.livekit.io/intro/basics/cli/), version 2.18.8 or later:

- **macOS:** `brew install livekit-cli`
- **Linux:** `curl -sSL https://get.livekit.io/cli | bash`
- **Windows:** `winget install LiveKit.LiveKitCLI`

Check your version with `lk --version`. To update an existing install, see [Update the CLI](https://docs.livekit.io/reference/developer-tools/livekit-cli/#updates).

Then create a project from this template. The CLI clones the template and configures your environment:

```console
lk cloud auth
lk agent init my-agent --template agent-starter-python
```

<details>
<summary>Set up the project manually</summary>

Clone the repository and install dependencies into a virtual environment with [uv](https://docs.astral.sh/uv/):

```console
git clone https://github.com/livekit-examples/agent-starter-python.git
cd agent-starter-python
uv sync
```

Sign up for [LiveKit Cloud](https://cloud.livekit.io/), then copy `.env.example` to `.env.local` and fill it in. To have the CLI write your project's URL and API keys into the file instead, run:

```console
lk cloud auth
lk app env --write --destination .env.local
```

</details>

## Run the agent

### Start the Windows desktop app

From PowerShell, install the Python and Electron dependencies once, then start
the app in development mode:

```powershell
cd my-agent
uv sync
uv run playwright install chromium
cd desktop
npm install
npm run dev
```

Run these commands from the cloned repository's parent directory. If you are
already in the repository, omit `cd my-agent`. Set `LIVEKIT_URL`,
`LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, and `GOOGLE_API_KEY` in `.env.local`
at the repository root before launching. The desktop app starts the Python
agent directly and does not require the LiveKit CLI. For a packaged Windows
build and more details, see [Jarvis desktop](desktop/README.md).

The `lk agent console`, `lk agent dev`, and `lk agent debugger` commands run your agent on your own machine. To talk to it in your terminal:

```console
lk agent console
```

To connect it to LiveKit Cloud so a frontend, a phone call, or the [Agent Console](https://docs.livekit.io/testing/agent-console/) can reach it:

```console
lk agent dev
```

To let a coding agent or a script test it one text turn at a time, use the [agent debugger](https://docs.livekit.io/testing/debugger/). Each turn prints the agent's reply along with the tool calls and handoffs behind it:

```console
lk agent debugger start
lk agent debugger say "Hi, what can you do?"
lk agent debugger stop
```

In production, run the agent directly:

```console
uv run src/agent.py start
```

## Voice-controlled browser

`my-agent` can operate a dedicated visible browser on the same PC as the agent.
It keeps logins in a separate persistent profile and exposes navigation, tabs,
page reading, screenshots, forms, keyboard/mouse actions, frames, uploads,
downloads, dialogs, waits, and diagnostics. Advanced approved Python scripts can
use the full installed Playwright Python API, including network interception,
API requests, emulation, cookies, tracing, and additional browser contexts.

Install dependencies and Chromium from this directory:

```powershell
uv sync
uv run playwright install chromium
uv run src/agent.py dev
```

Keep the generated `uv.lock` committed after dependency changes. `uv sync`
refreshes an older lock; container builds use `uv sync --locked` and require it
to be current. Browser binaries are a separate installation from Python packages.

Say, for example, “Open the browser and find a notebook,” “Fill in my name but
don't submit,” or “Show me the current page.” Browser tools stay registered so
opening a site does not restart the Gemini connection. Outcome speech waits for
the tool result, and page-load timeouts are reported as unconfirmed navigation.
You can watch
the browser, log in manually, complete MFA, and then tell the agent to continue.
Closing the voice session closes its browsers while preserving login data.

### Configuration

Copy the browser settings from `.env.example` into `.env.local` as needed.

| Setting | Default | Meaning |
| --- | --- | --- |
| `BROWSER_ENGINE` | `chromium` | `chromium`, `firefox`, or `webkit` |
| `BROWSER_HEADLESS` | `false` | Visible local window; `true` for CI |
| `BROWSER_PROFILE_DIR` | `.browser/profile` | Persistent dedicated profile; one session at a time |
| `BROWSER_ARTIFACT_DIR` | `.browser/artifacts` | Screenshots, downloads, and registered script artifacts |
| `BROWSER_UPLOAD_DIR` | `.browser/uploads` | Allowed root for structured upload tools |
| `BROWSER_ACTION_TIMEOUT` | `15` | Interaction timeout, seconds |
| `BROWSER_NAVIGATION_TIMEOUT` | `30` | Navigation timeout, seconds |
| `BROWSER_SCRIPT_TIMEOUT` | `60` | Advanced script timeout, seconds |

Paths resolve relative to the agent's working directory. Use separate profile
directories for different engines. To use another engine, install it explicitly
with `uv run playwright install firefox` or `uv run playwright install webkit`.
Engine-specific limitations still apply, such as Chromium-only PDF/CDP features.
Profiles, artifacts, and uploads are excluded from Git and Docker build context;
keep any custom directories outside tracked source as well.

The agent runs locally even when its voice connection uses LiveKit Cloud.
The supplied container is not a remote-control bridge to your Windows browser.
The local feature does not attach to your everyday Chrome profile.

### Confirmation and advanced execution

Sending, submitting, buying, deleting, and other consequential interactions are
prepared for review before execution. The agent explains the operation and waits
for a later spoken approval. Corrections or cancellation invalidate the pending
action. The runtime checks review delivery, user-message ordering, the exact
prepared payload, and page state; each approval is consumed once. A successful
click is followed by observation rather than assumed to mean a successful order.

The model classifies website actions and interprets natural-language agreement.
Generic browser tools cannot perfectly identify arbitrary website side effects;
this is not a guarantee that every consequential click will be recognized.
When a submission has an uncertain result, inspect before retrying it.

Every advanced script requires approval, including read-only scripts. Scripts
are **trusted local Python, not sandboxed code**. The worker separates execution
from voice processing and omits provider credentials from its environment, but
it runs with the local user's filesystem/network permissions.

`browser_run_playwright(code, description, tab_id="")` accepts an async function
body with `await` and `return`. Available objects are `playwright`, `context`,
`page`, `browser` (possibly `None` for a persistent context), `asyncio`,
`artifact_dir` (a `Path`), and a session-persistent `registry` dictionary.
Imports are allowed. Return JSON-compatible values and store handles/callbacks
in `registry`. `register_page(page)` makes additional pages available to normal
tools. `register_artifact(path, kind="file")` registers an existing file under
the artifact directory. Save PDFs/traces there, then register them.

For example, an approved script can collect headings:

```python
return await page.get_by_role("heading").all_text_contents()
```

Callbacks can outlive a script and must be included in its approval explanation.
Remove routes/listeners explicitly in a subsequent approved script, or ask to
close the browser to stop all callbacks. Interrupted preparation and worker
timeouts can close the browser; logins persist, but unsaved form edits may not.
Page changes between review and execution require a new review. The version
check is deliberately conservative and may also reject changing advertisements
or clocks on dynamic pages.

### Browser verification

```powershell
uv run pytest -q
uv run ruff check
uv run ruff format --check
lk agent debugger start
lk agent debugger say "Open the browser and show me the current page"
lk agent debugger stop
lk agent simulate text --scenarios scenarios-browser.yaml
```

Unit tests cover approval state, upload boundaries, and profile locks. Scripted
provider tests exercise real LiveKit tool/speech/message plumbing; they do not
prove language understanding. Browser integration tests launch Chromium against
an isolated local practice site, exercising real forms, frames, popups, dialogs,
files, cookies, scripts, and stale approvals. They skip if the Playwright Python
package is absent; CI explicitly installs the package and browser before testing.

Browser simulations use an ephemeral headless profile and a local practice site,
with final-state checks against actual submitted orders. They never use your
personal browser profile. The existing simulations and browser scenarios run on
merges to `main`. Verify microphone interruptions, natural approvals, and image
understanding with a real Gemini voice session before relying on those behaviors.

## Frontends and telephony

Pair the agent with a prebuilt frontend starter, or add telephony:

| Platform | Link | Description |
|----------|----------|-------------|
| **Web** | [`livekit-examples/agent-starter-react`](https://github.com/livekit-examples/agent-starter-react) | Web voice AI assistant with React & Next.js |
| **iOS/macOS** | [`livekit-examples/agent-starter-swift`](https://github.com/livekit-examples/agent-starter-swift) | Native iOS, macOS, and visionOS voice AI assistant |
| **Flutter** | [`livekit-examples/agent-starter-flutter`](https://github.com/livekit-examples/agent-starter-flutter) | Cross-platform voice AI assistant app |
| **React Native** | [`livekit-examples/voice-assistant-react-native`](https://github.com/livekit-examples/voice-assistant-react-native) | Native mobile app with React Native & Expo |
| **Android** | [`livekit-examples/agent-starter-android`](https://github.com/livekit-examples/agent-starter-android) | Native Android app with Kotlin & Jetpack Compose |
| **Web Embed** | [`livekit-examples/agent-starter-embed`](https://github.com/livekit-examples/agent-starter-embed) | Voice AI widget for any website |
| **Telephony** | [Documentation](https://docs.livekit.io/telephony/) | Add inbound or outbound calling to your agent |

For more options, see the [frontend guide](https://docs.livekit.io/frontends/).

## Testing and debugging

Simulations run full multi-turn conversations between a simulated user and your agent on LiveKit Cloud, then judge each transcript. The scenarios live in [`scenarios.yaml`](scenarios.yaml). Run them locally with the CLI:

```console
lk agent simulate text --scenarios scenarios.yaml
```

The `Simulations` workflow in [`.github/workflows/simulations.yml`](.github/workflows/simulations.yml) runs the same file on every merge to `main`, and on demand from the Actions tab. It doesn't run on every pull request push because each run uses real inference. See the [simulations guide](https://docs.livekit.io/testing/simulations/) for how to write scenarios and read results.

To check a change turn by turn without a live session, use the [agent debugger](https://docs.livekit.io/testing/debugger/) shown in [Run the agent](#run-the-agent).

To debug a running agent, open it in the [Agent Console](https://docs.livekit.io/testing/agent-console/). It shows events, tool calls, and model timing as you talk to the agent. To stream logs from a deployed agent, run `lk agent logs`.

## Using this template for your own project

After you create your own project from this template:

- **Commit `uv.lock`.** The template doesn't track it, but your project should, for reproducible builds. If you deploy to LiveKit Cloud, commit `livekit.toml` too.
- **Add repository secrets.** Add `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` as [repository secrets](https://docs.github.com/en/actions/how-tos/writing-workflows/choosing-what-your-workflow-does/using-secrets-in-github-actions) so the simulations can run in CI.

## Deploying to production

To deploy the agent to LiveKit Cloud or another environment with the included `Dockerfile`, see the [deployment guide](https://docs.livekit.io/deploy/agents/).

## Self-hosted LiveKit

You can self-host LiveKit instead of using LiveKit Cloud. See the [self-hosting guide](https://docs.livekit.io/transport/self-hosting/local/). If you self-host, use [model plugins](https://docs.livekit.io/agents/models/#plugins) instead of LiveKit Inference, and remove the [LiveKit Cloud noise cancellation](https://docs.livekit.io/transport/media/noise-cancellation/) plugin.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
