"""Live-mode plumbing with a fake Claude client: requests are well-formed, replies parse, failures fall back."""
import json
import tempfile
import unittest
from types import SimpleNamespace as NS

try:
    import anthropic  # noqa: F401
    HAVE_SDK = True
except ImportError:
    HAVE_SDK = False

from meltdown.engine import Engine


class FakeMessages:
    def __init__(self, calls, fail_every=0):
        self.calls, self.fail_every = calls, fail_every

    async def create(self, **kw):
        self.calls.append(kw)
        if self.fail_every and len(self.calls) % self.fail_every == 0:
            raise RuntimeError("simulated outage")
        schema = kw["output_config"]["format"]["schema"]
        acts = schema["properties"]["actions"]["items"]["properties"]["type"]["enum"]
        typ = "work" if "work" in acts else "wait"
        d = dict(thought="Fake thought.", speech="", channel="none", to="", pace="walk", scratchpad="note",
                 actions=[dict(type=typ, target="", arg="", text="")])
        return NS(stop_reason="end_turn", model=kw["model"],
                  usage=NS(input_tokens=100, output_tokens=20, cache_read_input_tokens=0),
                  content=[NS(type="thinking", thinking="summary of reasoning"), NS(type="text", text=json.dumps(d))])


@unittest.skipUnless(HAVE_SDK, "anthropic SDK not installed")
class LivePlumbing(unittest.TestCase):
    def test_short_live_game_with_fake_client(self):
        eng = Engine(seed=2, mode="live", run_dir=tempfile.mkdtemp(), human="auto", quiet=True, minutes=20)
        calls = []
        fake = FakeMessages(calls, fail_every=7)
        eng.brain.client = NS(messages=fake, beta=NS(messages=fake))
        rep = eng.run()
        models = {c["model"] for c in calls}
        self.assertEqual(models, {"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"})
        for c in calls:
            self.assertEqual(c["thinking"], {"type": "adaptive", "display": "summarized"})
            self.assertEqual(c["output_config"]["format"]["type"], "json_schema")
            self.assertIn("cache_control", c["system"][0])
        sources = {t["source"] for t in rep["thoughts"]}
        self.assertEqual(sources, {"live", "mock-fallback"})
        self.assertTrue(any(t["reasoning_summary"] for t in rep["thoughts"]))


if __name__ == "__main__":
    unittest.main()
