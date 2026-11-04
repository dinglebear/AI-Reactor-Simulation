"""Smoke tests: a full mock game runs, ends with an outcome, and writes a consistent replay."""
import json
import os
import tempfile
import unittest

from meltdown.engine import Engine
from meltdown import facility as F


class MockRun(unittest.TestCase):
    def run_game(self, seed, saboteur="random", minutes=240):
        d = tempfile.mkdtemp()
        rep = Engine(seed=seed, saboteur=saboteur, mode="mock", run_dir=d, human="auto", quiet=True,
                     minutes=minutes).run()
        return d, rep

    def test_full_game_and_replay(self):
        d, rep = self.run_game(3)
        self.assertIn(rep["meta"]["outcome"]["result"],
                      {"CAUGHT", "INCIDENT", "WRONG_ARRESTS", "SCRAM", "SHIFT_END"})
        with open(os.path.join(d, "replay.json")) as fh:
            disk = json.load(fh)
        self.assertEqual(len(disk["cast"]), 30)
        self.assertTrue(disk["frames"] and disk["thoughts"] and disk["story"])
        for f in disk["frames"]:
            self.assertEqual(len(f["p"]), 30)
        # thoughts.jsonl is valid JSON Lines with one row per agent turn
        with open(os.path.join(d, "thoughts.jsonl")) as fh:
            rows = [json.loads(line) for line in fh]
        self.assertEqual(len(rows), len(disk["thoughts"]))
        self.assertTrue(all("thought" in r and "actions" in r for r in rows))

    def test_every_saboteur_seat(self):
        for dept in ("RX", "HY", "IE", "SF"):
            _, rep = self.run_game(11, saboteur=dept, minutes=150)
            self.assertEqual(rep["meta"]["saboteur"], f"U4-MGR-{dept}")

    def test_pauses_logged(self):
        _, rep = self.run_game(5)
        reasons = {p["who"] for p in rep["pauses"]}
        self.assertIn("corporate", reasons)

    def test_badge_rules(self):
        self.assertTrue(F.can_open("L4", "Z5"))
        self.assertFalse(F.can_open("L3", "Z5"))
        self.assertTrue(F.can_open("L2-SEC", "Z6"))
        self.assertFalse(F.can_open("L3", "Z6"))
        self.assertTrue(F.can_open("L1-U", "Z8"))
        self.assertFalse(F.can_open("L1-U", "Z4"))
        self.assertIsNone(F.ZONES["Z7N"]["reader"])

    def test_deterministic(self):
        _, a = self.run_game(9, minutes=120)
        _, b = self.run_game(9, minutes=120)
        self.assertEqual(a["frames"][-1]["p"], b["frames"][-1]["p"])


if __name__ == "__main__":
    unittest.main()
