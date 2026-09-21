#!/usr/bin/env python3
"""quota-watch — read the weekly Claude Code and Codex limits, project where each
week will close at the pace so far, and nudge on Telegram while there is still
time to spend what is on track to expire unused.

Sources. None of them touches a credential, and none spends quota:
  Claude  <config>/.claude.json `cachedUsageUtilization` — written by Claude Code
          itself on every usage fetch. Carries the all-models weekly limit, any
          model-scoped one (Fable), the 5-hour window, and the window start. Left alone it goes
          stale (2h and 5 points behind on 2026-09-21), so it is refreshed first
          by running Claude Code's own `/usage` in print mode — no model call:
          num_turns 0, zero tokens, $0. The flags are borrowed from codenotch
          (github.com/vinzdg/codenotch, ClaudeUsageCLI.swift).
  Codex   `codex app-server` → `account/rateLimits/read`, on Codex's own login.
          Falls back to the newest snapshot in $CODEX_HOME/sessions rollout
          logs, which only moves when Codex runs on this machine.

Usage:
  quota_watch.py [status] [--telegram] [-v]  one row per weekly limit (-v: the working)
  quota_watch.py tick [--dry-run]             record, then nudge if a checkpoint is due
  quota_watch.py backfill                     seed history from Codex rollout logs

Configuration, all optional, from the environment or from the env file
(QUOTA_WATCH_ENV_FILE, default ~/.config/quota-watch/env, `KEY=value` lines):
  QUOTA_WATCH_TELEGRAM_BOT_TOKEN, QUOTA_WATCH_TELEGRAM_CHAT_ID   where nudges go
  QUOTA_WATCH_GAP           points on track to expire before a nudge (15)
  QUOTA_WATCH_CHECKPOINTS   hours before reset, comma-separated (96,48,24,10)
  QUOTA_WATCH_QUIET         local hours when Telegram is silent (23-8)
  CLAUDE_BIN, CODEX_BIN     binaries, when they are not where they install
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import re
import select
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HOME = os.path.expanduser("~")


def load_env_file(path):
    """`KEY=value` lines, `export` and quotes allowed. Never logged."""
    out = {}
    try:
        with open(path) as f:
            for line in f:
                m = re.match(r"\s*(?:export\s+)?([A-Z][A-Z0-9_]*)=(.*)", line)
                if m:
                    out[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    except OSError:
        pass
    return out


# launchd starts jobs with a bare environment, so settings can live in a file.
# The process environment wins over the file.
CONFIG = dict(load_env_file(os.environ.get("QUOTA_WATCH_ENV_FILE",
                                           os.path.join(HOME, ".config/quota-watch/env"))),
              **os.environ)


def first_executable(*paths):
    for p in paths:
        if p and os.access(p, os.X_OK):
            return p
    return None


STATE = os.path.join(CONFIG.get("XDG_STATE_HOME") or os.path.join(HOME, ".local/state"), "quota-watch")
HISTORY = os.path.join(STATE, "history.jsonl")
FIRED = os.path.join(STATE, "fired.json")
CLAUDE_JSON = os.path.join(CONFIG.get("CLAUDE_CONFIG_DIR") or HOME, ".claude.json")
# launchd's PATH is /usr/bin:/bin:/usr/sbin:/sbin, so `which` alone finds nothing there.
CLAUDE_BIN = first_executable(CONFIG.get("CLAUDE_BIN"), os.path.join(HOME, ".local/bin/claude"),
                              "/opt/homebrew/bin/claude", "/usr/local/bin/claude", shutil.which("claude"))
# One fixed cwd: Claude Code keys its projects/ folder on the working directory.
CLAUDE_CWD = os.path.join(STATE, "claude-usage-cwd")
CLAUDE_MAX_AGE = int(CONFIG.get("QUOTA_WATCH_CLAUDE_MAX_AGE", 20 * 60))  # refresh when older
CODEX_SESSIONS = os.path.join(CONFIG.get("CODEX_HOME") or os.path.join(HOME, ".codex"), "sessions")
CODEX_BIN = first_executable(CONFIG.get("CODEX_BIN"), shutil.which("codex"), "/opt/homebrew/bin/codex",
                             "/usr/local/bin/codex", "/Applications/ChatGPT.app/Contents/Resources/codex",
                             "/Applications/Codex.app/Contents/Resources/codex")

WEEK = 7 * 86400
SESSION = 5 * 3600           # the short window both tools have had; see is_session()
MIN_ELAPSED = 12 * 3600      # before this, a pace is one session's noise, not a week's habit
GAP = float(CONFIG.get("QUOTA_WATCH_GAP", 15))  # points on track to expire before a nudge
# Hours before reset; each fires at most once per window.
CHECKPOINTS_H = tuple(int(h) for h in CONFIG.get("QUOTA_WATCH_CHECKPOINTS", "96,48,24,10").split(",") if h.strip())
MIN_LEFT = 3 * 3600          # inside this, nothing heavy can still be scheduled: stay quiet
# Local hours when Telegram still delivers, but silently.
QUIET = tuple(int(h) for h in CONFIG.get("QUOTA_WATCH_QUIET", "23-8").split("-"))

# Pools that get nudged. Model-scoped Claude pools (Fable) sit inside the
# all-models one, so their headroom is only spendable if that one has room too.
# Model-scoped Codex limits (seen: "GPT-5.3-Codex-Spark") are of unknown nesting.
# Both kinds are reported, never nudged on their own.
NUDGED = ("claude", "codex")


# ── Readings ────────────────────────────────────────────────────────────────

def reading(pool, label, used, resets_at, at, source, start=None, window=WEEK):
    return {"pool": pool, "label": label, "used": float(used), "resets_at": int(resets_at),
            "start": int(start if start else resets_at - window), "at": int(at), "source": source}


def iso(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() if s else None


def load_json(path, retries=1):
    # ~/.claude.json is rewritten constantly by every live session; a read can
    # land mid-write. One retry is enough in practice.
    for i in range(retries + 1):
        try:
            with open(path) as f:
                return json.load(f)
        except (OSError, ValueError):
            if i < retries:
                time.sleep(1)
    return None


def claude_cache():
    d = (load_json(CLAUDE_JSON) or {}).get("cachedUsageUtilization") or {}
    u = d.get("utilization") or {}
    at = (d.get("fetchedAtMs") or 0) / 1000
    if not at:
        return []
    start = iso((u.get("seven_day_breakdown") or {}).get("window_started_at"))
    out = []
    for lim in u.get("limits") or []:
        resets = iso(lim.get("resets_at"))
        if resets is None or lim.get("percent") is None:
            continue
        if lim.get("kind") == "session":
            out.append(reading("claude-5h", "Claude 5h", lim["percent"], resets, at, "cache", window=SESSION))
        elif lim.get("kind") == "weekly_all":
            out.append(reading("claude", "Claude (all models)", lim["percent"], resets, at, "cache", start))
        elif lim.get("kind") == "weekly_scoped":
            name = (((lim.get("scope") or {}).get("model") or {}).get("display_name")) or "scoped"
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            out.append(reading("claude-" + slug, "Claude " + name, lim["percent"], resets, at, "cache"))
    if not any(r["pool"] == "claude" for r in out):
        sd = u.get("seven_day") or {}
        if sd.get("utilization") is not None and sd.get("resets_at"):
            out.append(reading("claude", "Claude (all models)", sd["utilization"], iso(sd["resets_at"]), at, "cache", start))
    if not any(r["pool"] == "claude-5h" for r in out):
        fh = u.get("five_hour") or {}
        if fh.get("utilization") is not None and fh.get("resets_at"):
            out.append(reading("claude-5h", "Claude 5h", fh["utilization"], iso(fh["resets_at"]), at, "cache", window=SESSION))
    return out


def claude_refresh():
    """Run `/usage` so Claude Code rewrites its own cache. The output is not
    parsed: the cache it leaves behind is the same figures, already structured.

    --print skips the workspace-trust dialogue; --no-session-persistence writes
    no transcript; --strict-mcp-config with no --mcp-config starts no MCP
    server. --setting-sources project drops the user settings and the hooks in
    them: a Stop hook that plays a sound would otherwise play it on every poll.
    Not --bare: that reads no OAuth login, so /usage would have nothing to ask with."""
    if not CLAUDE_BIN:
        return "no claude binary"
    os.makedirs(CLAUDE_CWD, exist_ok=True)
    try:
        subprocess.run([CLAUDE_BIN, "--print", "--no-session-persistence", "--strict-mcp-config",
                        "--setting-sources", "project", "/usage"],
                       cwd=CLAUDE_CWD, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return type(e).__name__
    return None


def claude_readings():
    out = claude_cache()
    fresh = next((r for r in out if r["pool"] == "claude"), None)
    if fresh is None or time.time() - fresh["at"] > CLAUDE_MAX_AGE:
        err = claude_refresh()
        if err:
            log(f"claude refresh failed ({err}); using the cache as it stands")
        out = claude_cache()
    return out


def codex_windows(limit_id, limit_name, windows, at, source):
    out = []
    for w in windows:
        mins = w.get("windowDurationMins", w.get("window_minutes"))
        used = w.get("usedPercent", w.get("used_percent"))
        resets = w.get("resetsAt", w.get("resets_at"))
        if not mins or used is None or not resets:
            continue
        pool = "codex" if limit_id in (None, "codex") else "codex-" + str(limit_id)
        label = "Codex" if pool == "codex" else "Codex " + str(limit_name or limit_id)
        if mins < 1440:
            # A short window (300 min on some plans; none on prolite since
            # September 2026). Reported and used to size the week, never nudged.
            pool, label = f"{pool}-{mins // 60}h", f"{label} {mins // 60}h"
        out.append(reading(pool, label, used, resets, at, source, window=mins * 60))
    return out


def codex_live(timeout=25):
    """Ask Codex's app-server. Returns (readings, extras) or (None, None)."""
    if not CODEX_BIN:
        return None, None
    try:
        p = subprocess.Popen([CODEX_BIN, "app-server"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True)
    except OSError:
        return None, None
    try:
        for msg in ({"id": 1, "method": "initialize", "params": {"clientInfo": {"name": "quota-watch", "version": "1"}}},
                    {"method": "initialized"},
                    {"id": 2, "method": "account/rateLimits/read"}):
            p.stdin.write(json.dumps(msg) + "\n")
        p.stdin.flush()
        deadline = time.time() + timeout
        while time.time() < deadline:
            ready, _, _ = select.select([p.stdout], [], [], 1)
            if not ready:
                continue
            line = p.stdout.readline()
            if not line:
                break
            try:
                m = json.loads(line)
            except ValueError:
                continue
            if m.get("id") != 2:
                continue
            res = m.get("result") or {}
            at = time.time()
            limits = res.get("rateLimitsByLimitId") or {}
            if not limits and res.get("rateLimits"):
                limits = {res["rateLimits"].get("limitId") or "codex": res["rateLimits"]}
            out = []
            for lid, rl in limits.items():
                out += codex_windows(lid, rl.get("limitName"), [rl.get("primary") or {}, rl.get("secondary") or {}], at, "app-server")
            credits = [c for c in (res.get("rateLimitResetCredits") or {}).get("credits") or []
                       if c.get("status") == "available"]
            extras = {"reset_credits": [{"title": c.get("title"), "expires_at": c.get("expiresAt")} for c in credits]}
            return out, extras
    except (OSError, ValueError):
        pass
    finally:
        p.kill()
    return None, None


def codex_rollout_snapshots(since):
    """Last rate-limit snapshot of each rollout log modified after `since`."""
    out = []
    for f in glob.glob(os.path.join(CODEX_SESSIONS, "*/*/*/rollout-*.jsonl")):
        try:
            if os.path.getmtime(f) < since:
                continue
            last = None
            with open(f) as fh:
                for line in fh:
                    if '"rate_limits"' in line:
                        last = line
        except OSError:
            continue
        if not last:
            continue
        try:
            ev = json.loads(last)
            rl = ev["payload"]["rate_limits"]
            at = iso(ev["timestamp"])
        except (ValueError, KeyError, TypeError):
            continue
        if rl:
            out += codex_windows(rl.get("limit_id"), rl.get("limit_name"),
                                 [rl.get("primary") or {}, rl.get("secondary") or {}], at, "rollout-log")
    return out


def codex_readings():
    # Two tries: the first spawn after a quiet spell has come back empty once
    # (2026-09-21); an immediate second one answered in about a second.
    for _ in range(2):
        live, extras = codex_live()
        if live:
            return live, extras
    # An expired window in an old log says nothing about this week.
    snaps = [r for r in codex_rollout_snapshots(time.time() - 8 * 86400) if r["resets_at"] > time.time()]
    newest = {}
    for r in snaps:
        if r["pool"] not in newest or r["at"] > newest[r["pool"]]["at"]:
            newest[r["pool"]] = r
    return list(newest.values()), {}


# ── History ─────────────────────────────────────────────────────────────────

def history():
    rows = []
    try:
        with open(HISTORY) as f:
            for line in f:
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return rows


def record(readings):
    seen = {(r["pool"], r["at"]) for r in history()}
    fresh = [r for r in readings if (r["pool"], r["at"]) not in seen]
    if fresh:
        os.makedirs(STATE, exist_ok=True)
        with open(HISTORY, "a") as f:
            for r in sorted(fresh, key=lambda r: r["at"]):
                f.write(json.dumps(r) + "\n")
    return len(fresh)


def backfill():
    return record(codex_rollout_snapshots(time.time() - 21 * 86400))


def same_window(a, b):
    return abs(a["resets_at"] - b["resets_at"]) < 3600


def is_session(r):
    """A short (5h) window rather than a week. It caps how fast the week can be
    spent; it wastes nothing by itself, so it is never nudged on."""
    return r["resets_at"] - r["start"] < 86400


def window_ratio(rows, weekly, session):
    """Weekly points one full session window is worth, measured from consecutive
    readings that share a timestamp, a week and a session window. None until
    at least one full window's worth (100 points) of session movement is seen:
    the percentages are integers, and less than that is mostly rounding."""
    by_at = {}
    for h in rows:
        if h["pool"] in (weekly, session):
            by_at.setdefault(h["at"], {})[h["pool"]] = h
    pairs = [d for _, d in sorted(by_at.items()) if len(d) == 2]
    dw = ds = 0.0
    for a, b in zip(pairs, pairs[1:]):
        if (same_window(a[weekly], b[weekly]) and abs(a[session]["resets_at"] - b[session]["resets_at"]) < 600
                and b[session]["used"] >= a[session]["used"] and b[weekly]["used"] >= a[weekly]["used"]):
            dw += b[weekly]["used"] - a[weekly]["used"]
            ds += b[session]["used"] - a[session]["used"]
    return dw / ds * 100 if ds >= 100 and dw > 0 else None


def session_pool(p, ps):
    return next((s for s in ps if s["pool"].startswith(p["pool"] + "-") and is_session(s)), None)


def previous_close(r, rows):
    """Highest reading of this pool's previous window — a floor, since usage
    after the last snapshot before reset was never seen."""
    # Not "resets_at == this start": a Codex window opens at the first use after
    # a reset, so the weeks are not back to back (19 Sep: reset 13:23, next
    # window opened 16:20). The previous week is the latest one closed by then.
    earlier = [h for h in rows if h["pool"] == r["pool"] and h["resets_at"] < r["start"] + 3600]
    if not earlier:
        return None
    last_reset = max(h["resets_at"] for h in earlier)
    prev = [h for h in earlier if abs(h["resets_at"] - last_reset) < 3600]
    top = max(prev, key=lambda h: (h["used"], h["at"]))
    return {"used": top["used"], "hours_before_reset": (top["resets_at"] - top["at"]) / 3600}


def recent_pace(r, rows, span=24 * 3600):
    """%/s over roughly the last day, from history in the same window."""
    older = [h for h in rows if h["pool"] == r["pool"] and same_window(h, r) and h["at"] <= r["at"] - span * 0.8]
    if not older:
        return None
    base = max(older, key=lambda h: h["at"])
    return max(0.0, (r["used"] - base["used"]) / (r["at"] - base["at"]))


# ── Projection ──────────────────────────────────────────────────────────────

def project(r, rows, now):
    elapsed = r["at"] - r["start"]
    ahead = max(0, r["resets_at"] - r["at"])
    p = dict(r, left=r["resets_at"] - now, elapsed=elapsed, pace=None, pace24=None,
             projected=None, projected24=None, unused=None, full_at=None)
    if now >= r["resets_at"]:
        p["rolled"] = True
        return p
    # What landing the week at 100% would take from here, as a daily rate.
    p["need"] = max(0.0, 100 - r["used"]) / max(ahead, 3600)
    if elapsed >= MIN_ELAPSED:
        p["pace"] = r["used"] / elapsed
        p["projected"] = r["used"] + p["pace"] * ahead
    p["pace24"] = recent_pace(r, rows)
    if p["pace24"] is not None:
        p["projected24"] = r["used"] + p["pace24"] * ahead
    # Judge on the busier of the two paces: a nudge should mean that even the
    # heavier recent habit leaves quota on the table.
    candidates = [x for x in (p["projected"], p["projected24"]) if x is not None]
    if candidates:
        busiest = max(candidates)
        p["unused"] = max(0.0, 100 - busiest)
        rate = max(x for x in (p["pace"], p["pace24"]) if x is not None)
        if busiest > 100 and rate > 0:
            p["full_at"] = r["at"] + (100 - r["used"]) / rate
    p["prev"] = None if is_session(r) else previous_close(r, rows)
    return p


# ── Formatting ──────────────────────────────────────────────────────────────

def dur(s):
    s = max(0, int(s))
    d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
    return f"{d}d {h}h" if d else f"{h}h {m:02d}m"


def when(ts, now=None):
    t = dt.datetime.fromtimestamp(ts)
    today = dt.datetime.fromtimestamp(now or time.time()).date()
    return t.strftime("%H:%M") if t.date() == today else t.strftime("%a %d %b %H:%M")


def per_day(pace):
    return f"{pace * 86400:.1f}%/day"


def short_dur(s):
    s = max(0, int(s))
    d, h, m = s // 86400, s % 86400 // 3600, s % 3600 // 60
    return f"{d}d{h:02d}h" if d else f"{h}h{m:02d}m"


def short_name(p):
    if p["pool"] in NUDGED:
        return p["pool"].capitalize()
    # A model-scoped limit, indented under its tool: " Fable", " Spark".
    sub = p["label"].split(" ", 1)[-1]
    return " " + (sub if len(sub) <= 7 else sub.rsplit("-", 1)[-1][:7])


def windows_per_day(p, ps, rows):
    """need/day in full session windows, when the ratio has been measured."""
    s = session_pool(p, ps)
    ratio = s and window_ratio(rows, p["pool"], s["pool"])
    return (p["need"] * 86400 / ratio, ratio) if ratio else None


def table_lines(ps, extras, now, rows=()):
    """One row per limit: used now, projected close, time left, and the daily
    rate that would use the rest of the week. A 5h window sits under its tool
    with only used and left. Notes only for what is out of the ordinary.
    Narrow enough for a phone screen in Telegram."""
    lines = [f"{'':<8}{'used':>5}{'end':>6}{'left':>7}{'need/d':>8}"]
    notes = []
    ps = sorted(ps, key=lambda p: (p["pool"].split("-")[0], p["pool"] not in NUDGED, not is_session(p)))
    for p in ps:
        name = short_name(p)[:8]
        if p.get("rolled"):
            lines.append(f"{name:<8}{'':>5}{'reset':>6}")
            continue
        used = f"{p['used']:.0f}%"
        if is_session(p):
            lines.append(f"{name:<8}{used:>5}{'':>6}{short_dur(p['left']):>7}")
            continue
        if p["pool"] not in NUDGED:
            lines.append(f"{name:<8}{used:>5}")
        else:
            end = "new" if p["unused"] is None else f"~{100 - p['unused']:.0f}%"
            need = p["need"] * 86400
            need = "·" if p["left"] < MIN_LEFT or p["used"] >= 100 else f"{need:.1f}%" if need < 10 else f"{need:.0f}%"
            lines.append(f"{name:<8}{used:>5}{end:>6}{short_dur(p['left']):>7}{need:>8}")
            wpd = need != "·" and windows_per_day(p, ps, rows)
            if wpd:
                notes.append(f"{name} need ≈ {wpd[0]:.1f} full 5h windows/day (one ≈ {wpd[1]:.0f}% of the week)")
        if p["full_at"] and p["full_at"] < p["resets_at"]:
            notes.append(f"{name.strip()} hits 100% ~{when(p['full_at'], now)}")
        if now - p["at"] > 3 * 3600 and p["pool"] in NUDGED:
            notes.append(f"{name.strip()} reading is {dur(now - p['at'])} old")
    prev = [f"{short_name(p).strip()} {p['prev']['used']:.0f}%" for p in ps if p.get("prev")]
    if prev:
        notes.insert(0, "last week: " + " · ".join(prev))
    for c in (extras or {}).get("reset_credits", []):
        exp = f" until {dt.datetime.fromtimestamp(c['expires_at']):%d %b}" if c.get("expires_at") else ""
        notes.append(f"Codex {(c.get('title') or 'reset').lower()} credit{exp}")
    return lines + ([""] + notes if notes else [])


def detail_lines(ps, extras, now):
    lines = []
    for p in ps:
        head = f"{p['label']:<22} {p['used']:>4.0f}%   resets {when(p['resets_at'], now)} ({dur(p['left'])} left)"
        lines.append(head)
        if p.get("rolled"):
            lines.append("    window has rolled over since this reading; no reading from the new one yet")
            continue
        if is_session(p):
            continue
        if p["pace"] is None:
            lines.append(f"    too early for a pace ({dur(p['elapsed'])} into the window)")
        else:
            bits = [f"pace since reset {per_day(p['pace'])} → {min(p['projected'], 100):.0f}% at reset"]
            if p["pace24"] is not None:
                bits.append(f"last 24h {per_day(p['pace24'])} → {min(p['projected24'], 100):.0f}%")
            lines.append("    " + ";  ".join(bits))
        if p["full_at"] and p["full_at"] < p["resets_at"]:
            lines.append(f"    on track to hit 100% around {when(p['full_at'], now)}")
        elif p["unused"] is not None:
            lines.append(f"    ~{p['unused']:.0f}% on track to expire unused; "
                         f"reaching 100% takes {per_day(p['need'])} from here")
        if p.get("prev"):
            lines.append(f"    last week ended at {p['prev']['used']:.0f}% or more")
        age = now - p["at"]
        lines.append(f"    as of {when(p['at'], now)} via {p['source']}" + (f"  ({dur(age)} old)" if age > 3 * 3600 else ""))
    for c in (extras or {}).get("reset_credits", []):
        exp = f", expires {when(c['expires_at'], now)}" if c.get("expires_at") else ""
        lines.append(f"Codex reset credit available: {c.get('title') or 'reset'}{exp}")
    return lines


def nudge_text(due, all_ps, now, rows=()):
    blocks = []
    for p in due:
        wpd = windows_per_day(p, all_ps, rows)
        lines = [f"⏳ <b>{short_name(p)}: ~{p['unused']:.0f}% of this week will go unused</b>",
                 f"{p['used']:.0f}% used · ~{100 - p['unused']:.0f}% at reset · {dur(p['left'])} left",
                 f"Need <b>{per_day(p['need'])}</b> to use it all" + (f" (≈ {wpd[0]:.1f} full 5h windows)" if wpd else "")]
        extra = [f"Last week {p['prev']['used']:.0f}%"] if p.get("prev") else []
        if p["pool"] == "claude":
            extra += [f"{short_name(s).strip()} {s['used']:.0f}%" for s in all_ps
                      if s["pool"].startswith("claude-") and not is_session(s) and not s.get("rolled") and same_window(s, p)]
        if extra:
            lines.append(" · ".join(extra))
        if now - p["at"] > 3 * 3600:
            lines.append(f"<i>Reading is {dur(now - p['at'])} old</i>")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


# ── Nudging ─────────────────────────────────────────────────────────────────

def due_nudges(ps, fired, now):
    due = []
    for p in ps:
        if p["pool"] not in NUDGED:
            continue
        if p.get("rolled") or p["unused"] is None or p["unused"] < GAP or p["left"] < MIN_LEFT:
            continue
        crossed = [c for c in CHECKPOINTS_H if p["left"] <= c * 3600]
        key = f"{p['pool']}@{round(p['resets_at'] / 3600)}"
        if crossed and not set(crossed) <= set(fired.get(key, [])):
            due.append((p, key, crossed))
    return due


def telegram(text, silent):
    token = CONFIG.get("QUOTA_WATCH_TELEGRAM_BOT_TOKEN")
    chat = CONFIG.get("QUOTA_WATCH_TELEGRAM_CHAT_ID")
    if not token or not chat:
        return "not configured"
    data = urllib.parse.urlencode({"chat_id": chat, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true",
                                   "disable_notification": "true" if silent else "false"}).encode()
    try:
        # The URL carries the bot token: never log it, and never log an
        # exception's text, which can quote the URL. Only its class.
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data, timeout=20) as r:
            return None if r.status == 200 else f"http {r.status}"
    except urllib.error.HTTPError as e:
        return f"http {e.code}"
    except Exception as e:  # noqa: BLE001
        return type(e).__name__


def mac_notify(text):
    if sys.platform != "darwin":
        return
    plain = re.sub(r"<[^>]+>", "", text).split("\n")
    title, body = plain[0].lstrip("⏳ "), " · ".join(x for x in plain[1:3] if x)
    script = f'display notification {json.dumps(body)} with title {json.dumps(title)}'
    subprocess.run(["osascript", "-e", script], capture_output=True)


def log(msg):
    print(f"[{dt.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


# ── Commands ────────────────────────────────────────────────────────────────

def gather():
    if not os.path.exists(HISTORY):
        log(f"seeded history with {backfill()} codex snapshots from rollout logs")
    codex, extras = codex_readings()
    return claude_readings() + codex, extras


def cmd_status(send, verbose):
    readings, extras = gather()
    record(readings)
    now = time.time()
    rows = history()
    ps = [project(r, rows, now) for r in readings]
    if not ps:
        print("no readings")
        return
    title = f"Weekly limits · {dt.datetime.fromtimestamp(now):%a %H:%M}"
    table = "\n".join(table_lines(ps, extras, now, rows))
    print(title + "\n\n" + table)
    if verbose:
        print("\n" + "\n".join(detail_lines(ps, extras, now)))
    if send:
        esc = table.replace("&", "&amp;").replace("<", "&lt;")
        err = telegram(f"<b>{title}</b>\n<pre>{esc}</pre>", silent=False)
        print(f"telegram: {err or 'sent'}")


def cmd_tick(dry_run):
    readings, extras = gather()
    n = record(readings)
    now = time.time()
    rows = history()
    ps = [project(r, rows, now) for r in readings]
    summary = ", ".join(f"{p['pool']} {p['used']:.0f}%" + (f"→{100 - p['unused']:.0f}%" if p["unused"] is not None else "")
                        for p in ps)
    log(f"tick: {summary or 'no readings'} ({n} new)")
    fired = load_json(FIRED, retries=0) or {}
    due = due_nudges(ps, fired, now)
    if not due:
        return
    text = nudge_text([p for p, _, _ in due], ps, now, rows)
    if dry_run:
        print(text)
        return
    hour = dt.datetime.now().hour
    silent = hour >= QUIET[0] or hour < QUIET[1]
    err = telegram(text, silent)
    if err:
        log(f"telegram failed ({err}); macOS notification instead")
        mac_notify(text)
    for p, key, crossed in due:
        fired[key] = sorted(set(fired.get(key, [])) | set(crossed), reverse=True)
        log(f"nudged {p['pool']}: ~{p['unused']:.0f}% on track to expire, {dur(p['left'])} left")
    # Forget windows that have closed.
    fired = {k: v for k, v in fired.items() if int(k.split("@")[1]) * 3600 > now - 86400}
    os.makedirs(STATE, exist_ok=True)
    with open(FIRED, "w") as f:
        json.dump(fired, f, indent=1)


def main(argv):
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "status":
        cmd_status("--telegram" in argv, "-v" in argv or "--verbose" in argv)
    elif cmd == "tick":
        cmd_tick("--dry-run" in argv)
    elif cmd == "backfill":
        print(f"{backfill()} new codex snapshots")
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
