"""Live agents on the Claude API. One stateless call per turn; memory is the scratchpad plus the inbox.

Director = Opus, managers = Sonnet, staff = Haiku (config.MODELS). Output is constrained to the decision
schema with structured outputs. Reasoning summaries (thinking display "summarized") are kept for the replay's
chain-of-thought layer. Any failure or refusal falls back to the mock brain for that one turn and is logged.
"""
from __future__ import annotations
import asyncio
import json
import time

from ..config import model_for, effort_for, MODELS, EFFORT, MAX_TOKENS
from .base import system_prompt, shared_prompt, decision_schema, actions_for, observation
from .mock import MockBrain

try:
    import anthropic
except ImportError:  # mock runs don't need the SDK
    anthropic = None


class LLMBrain:
    name = "live"

    def __init__(self, world, concurrency=8, use_fallbacks=True):
        if anthropic is None:
            raise SystemExit("pip install anthropic   (needed for live runs; use --mock otherwise)")
        self.w = world
        self.client = anthropic.AsyncAnthropic()
        self.sem = asyncio.Semaphore(concurrency)
        self.mock = MockBrain(world)
        self.use_fallbacks = use_fallbacks
        self.shared = shared_prompt()
        self.loop = asyncio.new_event_loop()
        self.usage = {"input": 0, "output": 0, "cache_read": 0, "calls": 0, "fallback_to_mock": 0}

    async def _call(self, p, obs):
        model = model_for(p)
        schema = decision_schema(list(actions_for(p).keys()))
        kw = dict(
            model=model,
            max_tokens=MAX_TOKENS[p.tier],
            system=[{"type": "text", "text": self.shared, "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": system_prompt(self.w, p)}],
            messages=[{"role": "user", "content": obs}],
            thinking={"type": "adaptive", "display": "summarized"},
            output_config={"effort": effort_for(p), "format": {"type": "json_schema", "schema": schema}},
        )
        async with self.sem:
            t0 = time.time()
            if self.use_fallbacks and p.tier in ("director", "manager"):
                try:
                    resp = await self.client.beta.messages.create(
                        betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kw)
                except (TypeError, anthropic.BadRequestError):
                    self.use_fallbacks = False
                    resp = await self.client.messages.create(**kw)
            else:
                resp = await self.client.messages.create(**kw)
            ms = int((time.time() - t0) * 1000)
        u = resp.usage
        self.usage["calls"] += 1
        self.usage["input"] += u.input_tokens or 0
        self.usage["output"] += u.output_tokens or 0
        self.usage["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
        if resp.stop_reason == "refusal":
            raise RuntimeError(f"refusal ({getattr(getattr(resp, 'stop_details', None), 'category', None)})")
        summary = " ".join(b.thinking for b in resp.content if b.type == "thinking" and b.thinking).strip()
        text = next(b.text for b in resp.content if b.type == "text")
        decision = json.loads(text)
        return decision, dict(source="live", latency_ms=ms, reasoning_summary=summary, model=resp.model,
                              tokens=dict(i=u.input_tokens, o=u.output_tokens))

    async def _one(self, p, obs):
        try:
            return await self._call(p, obs)
        except Exception as e:  # network, refusal, bad JSON: the game must go on
            self.usage["fallback_to_mock"] += 1
            d = self.mock.decide(p)
            return d, dict(source="mock-fallback", error=f"{type(e).__name__}: {str(e)[:200]}")

    def decide_batch(self, people):
        obs = [observation(self.w, p) for p in people]
        for p in people:
            p.inbox.clear()

        async def run():
            return await asyncio.gather(*(self._one(p, o) for p, o in zip(people, obs)))
        res = self.loop.run_until_complete(run()) if people else []
        return [(d, m, o) for (d, m), o in zip(res, obs)]
