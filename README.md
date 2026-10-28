<p align="center"><img src="https://codegpt.it.com/static/brand/logo-1024.png" width="96" alt="Code GPT"></p>
<h1 align="center">Code GPT CLI</h1>
<p align="center">Code GPT in your terminal: chat, pipe in any output, and let the coding agent fix and build things in your project.<br>
<a href="https://codegpt.it.com/cli">Website</a> · <a href="https://codegpt.it.com/learn/cli-in-10-minutes">10-minute lesson</a> · <a href="https://chat.codegpt.it.com/forum">Forum</a></p>

## Install

**Windows** (PowerShell):

```powershell
irm https://codegpt.it.com/install.ps1 | iex
```

**macOS and Linux:**

```sh
curl -fsSL https://codegpt.it.com/install.sh | sh
```

It needs Python 3.8 or newer and nothing else. No Python yet? On Windows: `winget install Python.Python.3.12`.

Then sign in once (your browser opens; check the code and press **Allow**):

```sh
codegpt login
```

## Use it

| Command | What it does |
|---|---|
| `codegpt` | Chat in the terminal. `/web` searches the web, `/model` switches model, `/new` starts a new chat |
| `codegpt ask "question"` | One answer, then back to your prompt. Great in scripts |
| `git diff \| codegpt ask "review my changes"` | Pipe in anything: logs, errors, diffs, files |
| `codegpt agent "fix the failing test"` | The coding agent works in the current folder: reads files, shows every change as a diff and asks before applying it or running a command |
| `codegpt agent --read-only "how does login work?"` | Explains code without changing anything |
| `codegpt models` | The models your plan can use (`--model` picks one) |
| `codegpt status` | Your plan and today's agent steps |
| `codegpt update` | Updates to the newest version (it also tells you once a day when an update is out) |
| `codegpt logout` | Removes the key from this computer |

## Safe by design

- Secret files (`.env`, private keys, certificates, credential files) are never read or sent.
- Every file change is shown as a diff and applied only when you say yes (`--yes` to trust a task).
- Commands run only after you confirm them.
- Your key is saved in `~/.codegpt/config.json`, readable only by you.
- Every conversation is saved in your Code GPT chats, so you can open it later on the web or your phone.

## Files

- `codegpt.py`: the whole CLI, one file, Python standard library only
- `install.sh`, `install.ps1`: the installers served at codegpt.it.com

Made by [AMAR Developers](https://codegpt.it.com/about). See [LICENSE.txt](LICENSE.txt).
