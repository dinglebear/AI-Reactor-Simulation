"""Live agents through the Claude Code CLI, so a game can run on a Claude Pro or Max subscription.

Each agent turn is one `claude -p` call: the game rules and the character go in as the system prompt (replacing
Claude Code's own), the observation goes in on stdin, no tools are allowed, and the answer is held to the same
decision schema as API mode. When the plan's usage limit is reached, the game simply waits until it resets and
carries on; the game clock is frozen while it waits, so nothing in the game changes.

    python -m meltdown.run --claude-code --minutes 10      # needs `claude` installed and logged in

If ANTHROPIC_API_KEY is set in your shell, Claude Code bills that key instead of your plan, so this mode removes
it from the environment of each call.
"""
from __future__ import annotations
import asyncio
import json
import os
import re
import shutil
import tempfile
import time

from ..config import model_for, effort_for, MODELS, EFFORT
from .base import system_prompt, shared_prompt, decision_schema, actions_for, observation
from .mock import MockBrain

LIMIT_RE = re.compile(r"(usage limit|rate limit|limit reached|hit your (\S+ )?limit|limit will reset|resets? (at|in) |"
                      r"\d-hour limit|weekly limit|resets \d)", re.I)
RESET_CLOCK_RE = re.compile(r"resets\s+(?:at\s+)?(\d{1,2})(?::(\d\d))?\s*(am|pm)?\s*(?:\(([^)]+)\))?", re.I)
RESET_EPOCH_RE = re.compile(r"\|(\d{10})\b")         # "Claude AI usage limit reached|1762318800"
LIMIT_WAIT_S = 600                                    # when the reset time isn't given, look again in 10 minutes
LIMIT_MIN_WAIT_S = 60
LIMIT_MAX_WAIT_S = 6 * 3600


def reset_from_clock(msg, now=None):
    """'resets 7:40am (UTC)' -> epoch seconds of the next such time, or None."""
    import datetime as dt
    m = RESET_CLOCK_RE.search(msg)
    if not m:
        return None
    h, mi, ap, tzname = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower(), (m.group(4) or "").strip()
    if ap == "pm" and h < 12:
        h += 12
    if ap == "am" and h == 12:
        h = 0
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(tzname) if tzname else None
    except Exception:
        tz = None
    cur = dt.datetime.fromtimestamp(now or time.time(), tz)
    at = cur.replace(hour=h % 24, minute=mi, second=0, microsecond=0)
    if at <= cur:
        at += dt.timedelta(days=1)
    return int(at.timestamp())


class UsageLimit(Exception):
    def __init__(self, text, reset_at=None):
        super().__init__(text)
        self.reset_at = reset_at


class ClaudeCodeBrain:
    name = "claude-code"

    def __init__(self, world, concurrency=3, exe=None, say=print):
        self.exe = exe or os.environ.get("MELTDOWN_CLAUDE") or shutil.which("claude")
        if not self.exe:
            raise SystemExit("Claude Code isn't installed. Install it (https://claude.com/claude-code), run `claude` "
                             "once to log in with your Pro or Max account, then try again.")
        self.w = world
        self.sem = asyncio.Semaphore(concurrency)
        self.mock = MockBrain(world)
        self.shared = shared_prompt()
        self.loop = asyncio.new_event_loop()
        self.say = say
        self.workdir = tempfile.mkdtemp(prefix="meltdown-cc-")   # empty folder: no CLAUDE.md or project settings
        self.env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
        self.usage = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "calls": 0,
                      "fallback_to_mock": 0, "api_equivalent_usd": 0.0, "limit_waits": 0, "limit_wait_s": 0}
        self.limit_gate = asyncio.Event()
        self.limit_gate.set()

    # one turn ---------------------------------------------------------------------------------------------
    def command(self, p):
        schema = decision_schema(list(actions_for(p).keys()))
        return [self.exe, "-p", "--model", model_for(p), "--effort", effort_for(p),
                "--system-prompt", f"{self.shared}\n\n{system_prompt(self.w, p)}",
                "--json-schema", json.dumps(schema), "--output-format", "json",
                "--tools", "", "--strict-mcp-config", "--setting-sources", "project",
                "--disable-slash-commands", "--no-session-persistence"]

    async def _run(self, p, obs):
        proc = await asyncio.create_subprocess_exec(
            *self.command(p), cwd=self.workdir, env=self.env, stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(obs.encode()), timeout=600)
        text = out.decode(errors="replace").strip()
        try:
            res = json.loads(text.splitlines()[-1]) if text else {}
        except json.JSONDecodeError:
            res = {"is_error": True, "result": text[-400:]}
        msg = str(res.get("result") or "") + " " + err.decode(errors="replace")[-400:]
        if proc.returncode != 0 or res.get("is_error"):
            if LIMIT_RE.search(msg):
                m = RESET_EPOCH_RE.search(msg)
                raise UsageLimit(msg.strip()[:200], int(m.group(1)) if m else reset_from_clock(msg))
            raise RuntimeError(msg.strip()[:300] or f"claude exited {proc.returncode}")
        return res

    def _decision(self, res):
        d = res.get("structured_output")
        if d is None:
            body = str(res.get("result") or "").strip()
            body = body[body.find("{"): body.rfind("}") + 1] if "{" in body else body
            d = json.loads(body)
        return d

    async def _call(self, p, obs):
        while True:
            await self.limit_gate.wait()
            async with self.sem:
                t0 = time.time()
                try:
                    res = await self._run(p, obs)
                except UsageLimit as e:
                    await self._wait_for_reset(e)
                    continue
            ms = int((time.time() - t0) * 1000)
            break
        u = res.get("usage") or {}
        self.usage["calls"] += 1
        self.usage["input"] += u.get("input_tokens") or 0
        self.usage["output"] += u.get("output_tokens") or 0
        self.usage["cache_read"] += u.get("cache_read_input_tokens") or 0
        self.usage["cache_write"] += u.get("cache_creation_input_tokens") or 0
        self.usage["api_equivalent_usd"] = round(self.usage["api_equivalent_usd"] + (res.get("total_cost_usd") or 0), 4)
        return self._decision(res), dict(source="live", latency_ms=ms, reasoning_summary="", model=model_for(p),
                                         tokens=dict(i=u.get("input_tokens") or 0, o=u.get("output_tokens") or 0))

    async def _wait_for_reset(self, e):
        if not self.limit_gate.is_set():            # another turn is already waiting it out
            return
        self.limit_gate.clear()
        now = time.time()
        wait = min(LIMIT_MAX_WAIT_S, max(LIMIT_MIN_WAIT_S, (e.reset_at - now + 30) if e.reset_at else LIMIT_WAIT_S))
        until = time.strftime("%H:%M", time.localtime(now + wait))
        self.say(f"\n[plan usage limit reached] Game paused, nothing in it changes. Trying again at {until}. "
                 f"({e})")
        self.usage["limit_waits"] += 1
        self.usage["limit_wait_s"] += int(wait)
        await asyncio.sleep(wait)
        self.limit_gate.set()

    async def _one(self, p, obs):
        try:
            try:
                return await self._call(p, obs)
            except (RuntimeError, json.JSONDecodeError):    # a one-off CLI hiccup: try once more
                await asyncio.sleep(3)
                return await self._call(p, obs)
        except Exception as e:  # still failing: the game must go on
            self.usage["fallback_to_mock"] += 1
            return self.mock.decide(p), dict(source="mock-fallback", error=f"{type(e).__name__}: {str(e)[:200]}")

    def decide_batch(self, people):
        obs = [observation(self.w, p) for p in people]
        for p in people:
            p.inbox.clear()

        async def run():
            return await asyncio.gather(*(self._one(p, o) for p, o in zip(people, obs)))
        res = self.loop.run_until_complete(run()) if people else []
        return [(d, m, o) for (d, m), o in zip(res, obs)]
