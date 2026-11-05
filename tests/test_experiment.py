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
