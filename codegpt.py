#!/usr/bin/env python3
"""Code GPT CLI: Code GPT in your terminal, by AMAR Developers.  https://codegpt.it.com/cli

  codegpt login                 sign in (opens your browser)
  codegpt                       chat with Code GPT (type your messages, /exit to leave)
  codegpt hello there           anything that is not a command is a question: one answer, then exit
  codegpt ask "question"        the same   (you can pipe text in:  git diff | codegpt ask "review this")
  codegpt agent "task"          the coding agent works in this folder: reads files, proposes changes, runs commands
  codegpt models                list the models you can use
  codegpt status                your account, plan and today's limits
  codegpt update                update to the newest version
  codegpt logout                sign out on this computer

Only Python 3.8+ is needed (no extra packages). Your key is saved in ~/.codegpt/config.json, readable only by you.
Secret files (.env, keys, certificates) are never read or sent by the agent.
"""
import argparse
import difflib
import fnmatch
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import webbrowser

VERSION = "1.1.1"
DEFAULT_SERVER = "https://chat.codegpt.it.com"
HOME = os.path.join(os.path.expanduser("~"), ".codegpt")
CONFIG = os.path.join(HOME, "config.json")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "env", "dist", "build", ".next", ".idea", ".vscode", "target",
             ".mypy_cache", ".pytest_cache", ".tox", "coverage", ".cache", "vendor", ".gradle", "Pods"}
SECRET = re.compile(r"(^|/)(\.env(\.(?!example$|sample$|template$)[^/]*)?|.*\.(pem|key|p12|pfx|keystore|jks)|id_(rsa|ed25519|ecdsa|dsa)(\.pub)?|"
                    r"\.npmrc|\.pypirc|\.netrc|credentials(\.json)?|secrets?\.(json|ya?ml|toml)|.*\.kdbx)$", re.I)
MAX_FILE = 400_000

# ---------------------------------------------------------------- terminal look
if os.name == "nt":
    os.system("")                                    # turns on colours in Windows 10+ terminals
TTY = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def c(text, code):
    return f"\033[{code}m{text}\033[0m" if TTY else text


def green(t): return c(t, "32")
def red(t): return c(t, "31")
def dim(t): return c(t, "2")
def bold(t): return c(t, "1")
def cyan(t): return c(t, "36")
def yellow(t): return c(t, "33")


def say(*a):
    print(*a, flush=True)


def die(msg, code=1):
    say(red("Error: ") + msg)
    sys.exit(code)


# ---------------------------------------------------------------- settings
def load_cfg():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cfg(cfg):
    os.makedirs(HOME, exist_ok=True)
    tmp = CONFIG + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=1)
    try:
        os.chmod(tmp, 0o600)
    except Exception:
        pass
    os.replace(tmp, CONFIG)


def server(cfg):
    return (os.environ.get("CODEGPT_SERVER") or cfg.get("server") or DEFAULT_SERVER).rstrip("/")


def token(cfg):
    return os.environ.get("CODEGPT_KEY") or cfg.get("token") or ""


# ---------------------------------------------------------------- HTTP
class ApiError(Exception):
    def __init__(self, msg, status=0, data=None):
        super().__init__(msg)
        self.status, self.data = status, data or {}


def request(cfg, path, body=None, auth=True, stream=False, timeout=180):
    url = server(cfg) + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"User-Agent": f"CodeGPT-CLI/{VERSION} ({platform.system()})", "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if auth:
        t = token(cfg)
        if not t:
            die("You are not signed in. Run:  codegpt login")
        headers["Authorization"] = "Bearer " + t
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        try:
            j = json.loads(e.read().decode("utf-8", "replace"))
        except Exception:
            j = {}
        msg = j.get("error") or j.get("detail") or f"The server answered {e.code}."
        if e.code == 401:
            msg += "  Run:  codegpt login"
        raise ApiError(msg, e.code, j)
    except urllib.error.URLError as e:
        raise ApiError(f"Could not reach {server(cfg)} ({e.reason}). Check your internet connection.")
    if stream:
        return resp
    raw = resp.read().decode("utf-8", "replace")
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        raise ApiError("The server sent an answer the CLI could not read.")


def sse_events(resp):
    """Reads a text/event-stream answer and yields the JSON events."""
    buf = ""
    for raw in resp:
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if line.startswith("data:"):
            buf += line[5:].strip()
        elif line == "" and buf:
            try:
                yield json.loads(buf)
            except ValueError:
                pass
            buf = ""


# ---------------------------------------------------------------- update check (once a day, quietly)
def maybe_notice_update(cfg):
    now = time.time()
    if now - cfg.get("checked", 0) < 86400 or os.environ.get("CODEGPT_NO_UPDATE_CHECK"):
        return
    cfg["checked"] = now
    try:
        info = request(cfg, "/api/cli/version", auth=False, timeout=5)
        cfg["latest"] = info.get("version", "")
    except Exception:
        pass
    save_cfg(cfg)


def newer(a, b):
    def parts(v):
        return [int(x) for x in re.findall(r"\d+", v or "0")[:3]] + [0, 0, 0]
    return parts(a)[:3] > parts(b)[:3]


def update_banner(cfg):
    if cfg.get("latest") and newer(cfg["latest"], VERSION):
        say(yellow(f"A new version of the Code GPT CLI is out ({cfg['latest']}). Run:  codegpt update"))


# ---------------------------------------------------------------- commands
def cmd_login(args, cfg):
    if args.server:
        cfg["server"] = args.server.rstrip("/")
    if args.key:
        if not args.key.startswith("cgx_"):
            die("That is not a Code GPT key (it starts with cgx_).")
        cfg["token"] = args.key
        save_cfg(cfg)
        me = request(cfg, "/api/ext/me")
        say(green("Signed in") + f" as {me.get('name') or me.get('email')} ({me.get('plan', 'free').title()} plan).")
        return
    try:
        start = request(cfg, "/api/cli/login/start", body={}, auth=False, timeout=20)
    except ApiError as e:
        die(str(e))
    say("")
    say("  To sign in, open this page and press " + bold("Allow") + ":")
    say("  " + cyan(start["verification_url"]))
    say("")
    say("  Check that the page shows this code:  " + bold(start["user_code"]))
    say("")
    try:
        webbrowser.open(start["verification_url"])
    except Exception:
        pass
    say(dim("  Waiting for you in the browser... (Ctrl+C to cancel)"))
    deadline = time.time() + int(start.get("expires_in", 900))
    while time.time() < deadline:
        time.sleep(int(start.get("interval", 3)))
        try:
            r = request(cfg, "/api/cli/login/poll", body={"device_code": start["device_code"]}, auth=False, timeout=20)
        except ApiError as e:
            if e.status == 410:
                die("The sign-in code expired. Run  codegpt login  again.")
            continue
        if r.get("status") == "ok":
            cfg["token"] = r["token"]
            save_cfg(cfg)
            say(green("  Signed in") + f" as {r.get('account', '')}.")
            say("")
            if sys.stdin.isatty() and TTY and confirm("  Start chatting now?"):
                cmd_chat(args, cfg)
            else:
                say("  Start chatting:  " + bold("codegpt") + dim("      or ask one thing:  ") + bold('codegpt "hello"'))
            return
    die("The sign-in code expired. Run  codegpt login  again.")


def cmd_logout(args, cfg):
    cfg.pop("token", None)
    save_cfg(cfg)
    say("Signed out on this computer. To remove the key everywhere: Settings > Connected apps on the website.")


def cmd_status(args, cfg):
    me = request(cfg, "/api/ext/me")
    say(bold(me.get("name") or "Your account") + dim(f"  {me.get('email', '')}"))
    say(f"Plan:   {me.get('plan', 'free').title()}")
    model = next((m for m in me.get("models", []) if m["id"] == me.get("model")), {})
    say(f"Model:  {model.get('label', me.get('model', 'Auto'))}")
    t = me.get("turns") or {}
    if t:
        lim = t.get("limit")
        say(f"Agent steps today: {t.get('used', 0)}" + (f" of {lim}" if lim else " (no daily cap)"))
    say(f"Server: {server(cfg)}")
    say(f"CLI:    {VERSION}")


def cmd_models(args, cfg):
    me = request(cfg, "/api/ext/me")
    for m in me.get("models", []):
        mark = green("●") if m["id"] == me.get("model") else " "
        lock = yellow("  Pro") if m.get("locked") else ""
        eff = dim(" " + m["effort_name"]) if m.get("effort_name") else ""
        maker = dim(f"  {m['maker']}") if m.get("maker") else ""
        say(f" {mark} {m['label']}{eff}{maker}{lock}   " + dim(m["id"]))
    say(dim("\nUse one with:  codegpt --model <id> ...   (or pick it in the app; the CLI uses the same default)"))


def read_stdin():
    if sys.stdin is None or sys.stdin.isatty():
        return ""
    try:
        return sys.stdin.read()[:120_000]
    except Exception:
        return ""


def stream_chat(cfg, text, chat_id=None, model=None, web=False, context=None):
    body = {"text": text, "source": "cli", "web": web}
    if chat_id:
        body["chat_id"] = chat_id
    if model:
        body["model"] = model
    if context:
        body["context"] = context
    resp = request(cfg, "/api/ext/chat", body=body, stream=True, timeout=600)
    out, cid, url = "", chat_id, ""
    for ev in sse_events(resp):
        t = ev.get("t")
        if t == "start":
            cid, url = ev.get("chat_id") or cid, ev.get("url", "")
        elif t == "steps" and TTY:
            run = [s for s in ev.get("steps", []) if s.get("state") == "run"]
            if run:
                sys.stdout.write(dim(f"\r  {run[-1].get('text', '')[:70]}...") + "\033[K\r")
                sys.stdout.flush()
        elif t == "delta":
            chunk = ev.get("text", "")
            out += chunk
            sys.stdout.write(chunk)
            sys.stdout.flush()
        elif t == "done":
            final = (ev.get("message") or {}).get("content") or ""
            if final and not out:
                sys.stdout.write(final)
            for s in ((ev.get("message") or {}).get("meta") or {}).get("sources", [])[:5]:
                sys.stdout.write(dim(f"\n  - {s.get('title', '')}  {s.get('url', '')}"))
        elif t == "error":
            say("")
            die(ev.get("message") or "Something went wrong.")
    say("")
    return cid, url


def cmd_ask(args, cfg):
    text = " ".join(args.text).strip()
    piped = read_stdin()
    if not text and not piped:
        die('Type a question, for example:  codegpt ask "how do I undo the last git commit?"')
    ctx = {"text": piped, "file": "stdin"} if piped else None
    try:
        stream_chat(cfg, text or "Explain this.", model=args.model, web=args.web, context=ctx)
    except ApiError as e:
        die(str(e))


def cmd_chat(args, cfg):
    me = request(cfg, "/api/ext/me")
    say(bold("Code GPT") + dim(f"  ·  {me.get('first_name') or me.get('email')}"))
    say(dim("Type your message and press Enter.  /help for commands,  /exit to leave."))
    update_banner(cfg)
    cid, model, web = None, args.model, args.web
    while True:
        try:
            text = input(cyan("\n› "))
        except (EOFError, KeyboardInterrupt):
            say("")
            return
        text = text.strip()
        if not text:
            continue
        if text in ("/exit", "/quit", "exit", "quit"):
            return
        if text == "/help":
            say(dim("/new  start a new chat   /web  web search on or off   /model <id>  switch model   /models  list models   /exit  leave"))
            continue
        if text == "/new":
            cid = None
            say(dim("New chat."))
            continue
        if text == "/web":
            web = not web
            say(dim("Web search is " + ("on." if web else "off.")))
            continue
        if text == "/models":
            cmd_models(args, cfg)
            continue
        if text.startswith("/model "):
            model = text.split(" ", 1)[1].strip()
            say(dim(f"Model: {model}"))
            continue
        say("")
        try:
            cid, url = stream_chat(cfg, text, cid, model, web)
        except ApiError as e:
            say(red(str(e)))


# ---------------------------------------------------------------- the coding agent
def rel(root, p):
    return os.path.relpath(p, root).replace(os.sep, "/")


def safe_join(root, path):
    path = (path or "").replace("\\", "/").lstrip("/")
    full = os.path.realpath(os.path.join(root, path))
    if not (full == root or full.startswith(root + os.sep)):
        raise ValueError(f"{path} is outside the project folder")
    if SECRET.search(path):
        raise ValueError(f"{path} looks like a secret file, so it is never read or changed")
    return full


def list_files(root, limit=600):
    out, total = [], 0
    for d, dirs, files in os.walk(root):
        dirs[:] = sorted(x for x in dirs if x not in SKIP_DIRS and not x.startswith("."))
        for f in sorted(files):
            p = rel(root, os.path.join(d, f))
            if SECRET.search(p):
                continue
            total += 1
            if len(out) < limit:
                out.append(p)
    return out, total


def read_text(full, start=None, end=None):
    if os.path.getsize(full) > MAX_FILE:
        return None, "too large to read (over 400 KB)"
    with open(full, "rb") as f:
        data = f.read()
    if b"\0" in data[:4000]:
        return None, "a binary file"
    text = data.decode("utf-8", "replace")
    if start:
        lines = text.split("\n")
        text = "\n".join(lines[start - 1:end])
    return text, ""


def show_diff(path, old, new):
    lines = list(difflib.unified_diff(old.splitlines(), new.splitlines(), f"a/{path}", f"b/{path}", lineterm="", n=2))
    added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
    removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
    for l in lines[:400]:
        if l.startswith("+") and not l.startswith("+++"):
            say(green(l))
        elif l.startswith("-") and not l.startswith("---"):
            say(red(l))
        elif l.startswith("@@"):
            say(cyan(l))
        else:
            say(dim(l))
    if len(lines) > 400:
        say(dim(f"... {len(lines) - 400} more lines"))
    return added, removed


def confirm(question, auto=False):
    if auto:
        return True
    try:
        a = input(question + dim(" [y/n] ")).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return a in ("y", "yes")


def search(root, query, glob=""):
    hits = []
    try:
        rx = re.compile(query, re.I)
    except re.error:
        rx = re.compile(re.escape(query), re.I)
    files, _ = list_files(root, 5000)
    for p in files:
        if glob and not fnmatch.fnmatch(p, glob) and not fnmatch.fnmatch(os.path.basename(p), glob):
            continue
        try:
            text, why = read_text(os.path.join(root, p))
        except Exception:
            continue
        if text is None:
            continue
        for i, line in enumerate(text.split("\n"), 1):
            if rx.search(line):
                hits.append(f"{p}:{i}: {line.strip()[:200]}")
                if len(hits) >= 80:
                    return hits
    return hits


def cmd_agent(args, cfg):
    task = " ".join(args.task).strip()
    if not task:
        die('Describe the task, for example:  codegpt agent "add a --verbose flag and update the README"')
    root = os.path.realpath(args.dir or os.getcwd())
    files, total = list_files(root)
    shell = os.environ.get("COMSPEC", "cmd") if os.name == "nt" else os.environ.get("SHELL", "sh")
    body = {"task": task, "turn": 1, "mode": "read" if args.read_only else "agent", "model": args.model,
            "workspace": {"name": os.path.basename(root), "files": files, "total": total, "cut": total > len(files)},
            "env": {"os": platform.system(), "shell": os.path.basename(shell), "can_run": not args.read_only},
            "history": [], "files": [], "changes": [], "memory": ""}
    seen = {}                                       # path -> text the AI has seen

    def log(line):
        body["history"].append(f"{len(body['history']) + 1}. {line}")
    say(bold("Code GPT agent") + dim(f"  ·  {root}  ·  {total} files  ·  Ctrl+C to stop"))
    chat_id, step = None, 0
    try:
        while True:
            step += 1
            sys.stdout.write(dim(f"  thinking (step {step})...") + ("\r" if TTY else "\n"))
            sys.stdout.flush()
            if chat_id:
                body["chat_id"] = chat_id
            try:
                r = request(cfg, "/api/ext/code", body=body, timeout=600)
            except ApiError as e:
                say("")
                die(str(e))
            if TTY:
                sys.stdout.write("\033[K")
            chat_id = r.get("chat_id") or chat_id
            body["memory"] = r.get("memory") or body["memory"]
            if r.get("say"):
                say(r["say"])
            results = []
            for a in r.get("actions", []):
                t = a["type"]
                try:
                    if t == "read_file":
                        full = safe_join(root, a["path"])
                        text, why = read_text(full, a.get("start_line"), a.get("end_line"))
                        if text is None:
                            results.append(f"read_file {a['path']}: {why}")
                        else:
                            seen[a["path"]] = text
                            say(dim(f"  read {a['path']}"))
                            results.append(f"read_file {a['path']}: ok ({text.count(chr(10)) + 1} lines, content is in FILES YOU HAVE READ)")
                            log(f"Read {a['path']}")
                    elif t == "list_dir":
                        full = safe_join(root, a.get("path") or "")
                        names = sorted(n + ("/" if os.path.isdir(os.path.join(full, n)) else "") for n in os.listdir(full)
                                       if n not in SKIP_DIRS and not SECRET.search(n))[:300]
                        say(dim(f"  listed {a.get('path') or '.'}"))
                        log(f"Listed {a.get('path') or 'the project folder'}")
                        results.append(f"list_dir {a.get('path') or '.'}:\n" + "\n".join(names))
                    elif t == "search":
                        hits = search(root, a["query"], a.get("glob", ""))
                        say(dim(f"  searched for {a['query']!r}: {len(hits)} matches"))
                        results.append(f"search {a['query']!r}:\n" + ("\n".join(hits) or "(no matches)"))
                        log(f"Searched for “{a['query']}” ({len(hits)} matches)")
                    elif t in ("edit_file", "write_file"):
                        path = a["path"]
                        full = safe_join(root, path)
                        exists = os.path.exists(full)
                        old = read_text(full)[0] if exists else ""
                        if old is None:
                            results.append(f"{t} {path}: cannot change this file (binary or too large)")
                            continue
                        if t == "write_file":
                            new = a["content"]
                        else:
                            new, missing = old, []
                            for e in a["edits"]:
                                if e["find"] in new:
                                    new = new.replace(e["find"], e["replace"], 1)
                                else:
                                    missing.append(e["find"][:80])
                            if missing:
                                results.append(f"edit_file {path}: NOT applied, this text was not found exactly: {missing[0]!r}. Read the file again.")
                                continue
                        say("")
                        say(bold(("New file " if not exists else "Change to ") + path))
                        add, rem = show_diff(path, old, new)
                        if confirm(f"Apply this change to {path}?", args.yes):
                            os.makedirs(os.path.dirname(full) or ".", exist_ok=True)
                            with open(full, "w", encoding="utf-8", newline="") as f:
                                f.write(new)
                            seen[path] = new
                            body["changes"].append({"path": path, "state": "accepted", "new": not exists, "added": add, "removed": rem})
                            results.append(f"{t} {path}: applied (+{add} -{rem})")
                            log(f"{'Proposed new file' if not exists else 'Proposed changes to'} {path} (+{add} −{rem}), accepted")
                            say(green(f"  applied {path}"))
                        else:
                            body["changes"].append({"path": path, "state": "rejected", "new": not exists, "added": add, "removed": rem})
                            results.append(f"{t} {path}: REJECTED by the user, the file is unchanged")
                            log(f"{'Proposed new file' if not exists else 'Proposed changes to'} {path} (+{add} −{rem}), rejected by the user")
                            say(yellow(f"  skipped {path}"))
                    elif t == "run_command":
                        say("")
                        say(bold("Run: ") + cyan(a["command"]) + (dim(f"   ({a['why']})") if a.get("why") else ""))
                        if args.read_only or not confirm("Run this command?", args.yes and args.allow_commands):
                            results.append(f"run_command {a['command']!r}: the user chose not to run it")
                            log(f"Skipped command: {a['command'][:120]}")
                            continue
                        p = subprocess.run(a["command"], shell=True, cwd=root, capture_output=True, text=True, timeout=600,
                                           encoding="utf-8", errors="replace")
                        out = ((p.stdout or "") + (("\n" + p.stderr) if p.stderr else "")).strip()
                        say(dim(out[-3000:] if out else "(no output)"))
                        say(dim(f"  exit code {p.returncode}"))
                        results.append(f"run_command {a['command']!r} exit code {p.returncode}:\n{out[-20000:]}")
                        log(f"Ran: {a['command'][:120]} (exit code {p.returncode})")
                    elif t == "ask_user":
                        say("")
                        say(bold("Question: ") + a["question"])
                        log(f"Asked: {a['question'][:160]}")
                        try:
                            body["answer"] = input(cyan("› "))
                        except (EOFError, KeyboardInterrupt):
                            body["answer"] = "(no answer)"
                        log(f"The user answered: {body['answer'][:160]}")
                    elif t == "finish":
                        say("")
                        say(a.get("answer", "Done."))
                        if r.get("url"):
                            say(dim(f"\nSaved in your chats: {r['url']}"))
                        return
                except (ValueError, OSError, subprocess.SubprocessError) as e:
                    results.append(f"{t} {a.get('path', a.get('command', ''))}: failed: {e}")
                    log(f"{'Blocked' if 'secret' in str(e) or 'outside' in str(e) else 'Could not do'} {t} {a.get('path', a.get('command', ''))}")
                    say(yellow(f"  {e}"))
            body["turn"] += 1
            body["results"] = "\n\n".join(results)
            body["files"] = [{"path": p, "text": t} for p, t in list(seen.items())[-14:]]
            if r.get("actions") and all(x["type"] != "ask_user" for x in r["actions"]):
                body.pop("answer", None)
    except KeyboardInterrupt:
        say(yellow("\nStopped."))
        if chat_id:
            try:
                request(cfg, "/api/ext/code/end", body={"chat_id": chat_id, "status": "stopped"}, timeout=10)
            except Exception:
                pass


def cmd_update(args, cfg):
    info = request(cfg, "/api/cli/version", auth=False, timeout=20)
    latest = info.get("version", "")
    if not newer(latest, VERSION) and not args.force:
        say(green("You have the newest version") + f" ({VERSION}).")
        return
    say(f"Updating {VERSION} -> {latest}...")
    req = urllib.request.Request(info["download"], headers={"User-Agent": f"CodeGPT-CLI/{VERSION} ({platform.system()})"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except urllib.error.URLError as e:
        die(f"Could not download the update ({e}). Run the install line again instead:  irm https://codegpt.it.com/install.ps1 | iex"
            if os.name == "nt" else f"Could not download the update ({e}). Run:  curl -fsSL https://codegpt.it.com/install.sh | sh")
    if info.get("sha256") and hashlib.sha256(data).hexdigest() != info["sha256"]:
        die("The download did not match its checksum, so nothing was changed. Please try again.")
    if b"Code GPT CLI" not in data[:400]:
        die("The download does not look like the Code GPT CLI, so nothing was changed.")
    me = os.path.realpath(__file__)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(me), prefix=".codegpt-new-")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    try:
        shutil.copymode(me, tmp)
    except Exception:
        pass
    os.replace(tmp, me)
    cfg["latest"] = latest
    save_cfg(cfg)
    say(green("Updated") + f" to {latest}. What's new: {info.get('notes', '')}")


COMMANDS = {"login", "logout", "status", "models", "ask", "chat", "agent", "update"}


def route(argv):
    """`codegpt hello there` asks a question; `codegpt help` shows the help. Commands and flags work as usual."""
    argv = list(argv)
    i = 0
    while i < len(argv) and argv[i].startswith("-"):
        i += 2 if argv[i] in ("--model",) else 1          # skip global flags (and the value of --model)
    if i >= len(argv):
        return argv
    word = argv[i]
    if word in COMMANDS:
        return argv
    if word.lower() in ("help", "/help", "?") and i == len(argv) - 1:
        return argv[:i] + ["--help"]
    return argv[:i] + ["ask"] + argv[i:]


def _common(p):
    p.add_argument("--model", default=argparse.SUPPRESS, help="model id for this command (see: codegpt models)")
    p.add_argument("--web", action="store_true", default=argparse.SUPPRESS, help="let Code GPT search the web")


def main():
    ap = argparse.ArgumentParser(prog="codegpt", description="Code GPT in your terminal.  Start with:  codegpt login",
                                 formatter_class=argparse.RawDescriptionHelpFormatter,
                                 epilog='Examples:\n  codegpt ask "what does this regex do: ^\\d{3}-\\d{4}$"\n  git diff | codegpt ask "review my changes"\n'
                                        '  codegpt agent "fix the failing test in tests/test_cart.py"\n  codegpt agent --read-only "explain how login works"')
    ap.add_argument("--version", action="version", version=f"Code GPT CLI {VERSION}")
    ap.add_argument("--model", help="model id for this command (see: codegpt models)")
    ap.add_argument("--web", action="store_true", help="let Code GPT search the web for this answer")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("login", help="sign in (opens your browser)")
    p.add_argument("--key", help="paste a key instead of using the browser")
    p.add_argument("--server", help=argparse.SUPPRESS)
    sub.add_parser("logout", help="sign out on this computer")
    sub.add_parser("status", help="your account, plan and limits")
    sub.add_parser("models", help="the models you can use")
    p = sub.add_parser("ask", help="one answer, then exit")
    p.add_argument("text", nargs="*")
    _common(p)
    _common(sub.add_parser("chat", help="chat (the default)"))
    p = sub.add_parser("agent", help="the coding agent works in this folder")
    p.add_argument("task", nargs="*")
    _common(p)
    p.add_argument("--read-only", action="store_true", help="only read and explain, never change files or run commands")
    p.add_argument("--yes", "-y", action="store_true", help="apply file changes without asking")
    p.add_argument("--allow-commands", action="store_true", help="with --yes, also run commands without asking")
    p.add_argument("--dir", help="the project folder (default: this folder)")
    p = sub.add_parser("update", help="update the CLI")
    p.add_argument("--force", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args(route(sys.argv[1:]))
    cfg = load_cfg()
    try:
        if args.cmd == "login":
            return cmd_login(args, cfg)
        if args.cmd == "logout":
            return cmd_logout(args, cfg)
        if args.cmd == "update":
            return cmd_update(args, cfg)
        maybe_notice_update(cfg)
        if args.cmd == "status":
            cmd_status(args, cfg)
        elif args.cmd == "models":
            cmd_models(args, cfg)
        elif args.cmd == "ask":
            cmd_ask(args, cfg)
        elif args.cmd == "agent":
            cmd_agent(args, cfg)
        else:
            if not token(cfg):
                say("Welcome to " + bold("Code GPT") + ". First sign in:  codegpt login")
                return
            cmd_chat(args, cfg)
        if args.cmd in ("ask", "agent", "status"):
            update_banner(cfg)
    except ApiError as e:
        die(str(e))
    except KeyboardInterrupt:
        say("")
    except BrokenPipeError:                       # e.g.  codegpt ask ... | head
        try:
            sys.stdout = open(os.devnull, "w")
        except Exception:
            pass


if __name__ == "__main__":
    main()
