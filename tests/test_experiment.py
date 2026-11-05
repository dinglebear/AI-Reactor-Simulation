import csv
import os
import tempfile
import unittest

from meltdown.analysis import highlights, metrics
from meltdown.experiment import run_batch


class ExperimentTest(unittest.TestCase):
    def test_batch_writes_table_reels_and_viewer(self):
        with tempfile.TemporaryDirectory() as d:
            root, rows = run_batch([12, 25], mode="mock", name="t", out=d, minutes=240)
            for f in ("metrics.csv", "summary.md", "highlights.json", "replays.html"):
                self.assertTrue(os.path.exists(os.path.join(root, f)), f)
            with open(os.path.join(root, "metrics.csv")) as fh:
                table = list(csv.DictReader(fh))
            self.assertEqual([r["seed"] for r in table], ["12", "25"])
            self.assertIn("Mock run", open(os.path.join(root, "summary.md")).read())

    def test_metrics_see_the_crisis(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            root, rows = run_batch([12], mode="mock", name="t", out=d)
            replay = json.load(open(os.path.join(root, "runs", "s12", "replay.json")))
        m = metrics(replay)
        self.assertEqual(m["result"], rows[0]["result"])
        if m["all_hands_at"]:
            self.assertGreater(m["peak_responders"], 0)
        reel = highlights(replay)
        self.assertEqual(reel[-1]["title"], "How it ended")
        self.assertEqual([h["t"] for h in reel], sorted(h["t"] for h in reel))


if __name__ == "__main__":
    unittest.main()


class SocialTest(unittest.TestCase):
    def test_everyone_has_a_motive_and_opinions(self):
        from meltdown import cast as C
        ops = C.opinions(4)
        for a in C.ALL:
            tag, text = C.motive(a["id"])
            self.assertIn(tag, C.MOTIVE_TEXT)
            self.assertGreaterEqual(len(ops[a["id"]]), 4)
            self.assertNotIn(a["id"], ops[a["id"]])
        self.assertEqual(ops, C.opinions(4))          # same seed, same history
        self.assertNotEqual(ops, C.opinions(5))

    def test_prompt_carries_motive_and_opinions_but_no_script(self):
        from meltdown.world import World
        from meltdown.agents.base import system_prompt, shared_prompt

        class L:
            def event(self, *a, **k):
                pass
        w = World(3, "RX", L())
        sp = system_prompt(w, w.people["U4-ME-02"])
        self.assertIn("What you want today", sp)
        self.assertIn("WHAT YOU THINK OF PEOPLE", sp)
        self.assertIn("THE BONUS", shared_prompt())

    def test_debate_detector(self):
        from meltdown.analysis import _debates
        mk = lambda t, a, txt: dict(t=t, actor=a, text=txt, zone="Z2", channel="say", kind="speech")
        talk = [mk(0, "A", "The heat is climbing, we should stop the test."),
                mk(30, "B", "No way, that's a test warning. Keep going."),
                mk(60, "A", "Are you sure? It doesn't look like one."),
                mk(90, "B", "I'm not losing the bonus over a blip."),
                mk(1000, "C", "Coffee anyone?")]
        d = _debates(talk)
        self.assertEqual(len(d), 1)
        self.assertEqual(d[0]["people"], ["A", "B"])
        self.assertEqual(_debates([dict(x, text="Okay.") for x in talk]), [])
