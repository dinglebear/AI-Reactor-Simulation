"""Claude Code mode with a fake `claude` executable: calls are well-formed, usage limits pause and resume."""
import json
import os
import sys
import tempfile
import unittest

from meltdown.agents import claude_code
from meltdown.engine import Engine

FAKE = os.path.join(os.path.dirname(__file__), "fake_claude.py")


class ClaudeCodeMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.log = os.path.join(self.tmp, "calls.jsonl")
        os.environ["MELTDOWN_CLAUDE"] = FAKE
        os.environ["FAKE_CLAUDE_LOG"] = self.log
        os.environ["ANTHROPIC_API_KEY"] = "should-not-leak"
        self.old_min = claude_code.LIMIT_MIN_WAIT_S
        claude_code.LIMIT_MIN_WAIT_S = 0

    def tearDown(self):
        for k in ("MELTDOWN_CLAUDE", "FAKE_CLAUDE_LOG", "FAKE_CLAUDE_LIMIT_FILE", "ANTHROPIC_API_KEY"):
            os.environ.pop(k, None)
        claude_code.LIMIT_MIN_WAIT_S = self.old_min

    def test_short_game_runs_waits_out_a_limit_and_never_falls_back(self):
        os.environ["FAKE_CLAUDE_LIMIT_FILE"] = os.path.join(self.tmp, "limit-hit")
        eng = Engine(seed=2, mode="claude-code", run_dir=os.path.join(self.tmp, "run"), human="auto", quiet=True,
                     minutes=6)
        self.assertNotIn("ANTHROPIC_API_KEY", eng.brain.env)
        eng.brain.say = lambda *_: None
        rep = eng.run()
        self.assertEqual({t["source"] for t in rep["thoughts"]}, {"live"})
        self.assertEqual(rep["meta"]["usage"]["limit_waits"], 1)
        calls = [json.loads(x) for x in open(self.log)]
        self.assertEqual({c[c.index("--model") + 1] for c in calls},
                         {"claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"})
        for c in calls:
            self.assertEqual(c[c.index("--tools") + 1], "")
            self.assertIn("THE BONUS", c[c.index("--system-prompt") + 1])
            self.assertEqual(c[c.index("--output-format") + 1], "json")


if __name__ == "__main__":
    unittest.main()
