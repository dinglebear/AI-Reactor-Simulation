"""New agent abilities: eavesdropping, hiding things, searches, the spy's read on people, tempo presets."""
import unittest

from meltdown import config
from meltdown.agents.base import system_prompt
from meltdown.engine import Engine


class Abilities(unittest.TestCase):
    def setUp(self):
        self.eng = Engine(seed=5, mode="mock", run_dir="runs/test-abilities", human="auto", speed=0.0, quiet=True,
                          minutes=5, saboteur="IE")
        self.w = self.eng.world
        self.spy = self.w.people["U4-MGR-IE"]

    def _clear(self):
        for p in self.w.people.values():
            p.inbox.clear()

    def test_listen_in_hears_other_channel_and_is_logged(self):
        w, spy = self.w, self.spy
        self.assertIn("listening", self.eng.do(spy, "listen_in", "security", "", "", "walk"))
        self._clear()
        w.say(w.people["U4-SEC-01"], "security", None, "Gate is quiet.")
        self.assertTrue(any("overheard" in m["text"] for m in spy.inbox))
        # own channel refused, restroom refused
        self.assertIn("already", w.listen_in(spy, "IE"))
        r = w.investigate(w.director, "read_radio", "security", None)
        self.assertIn("transcript", r)
        self.assertTrue(any(c.type == "radio" and spy.id in c.suspects and c.found for c in w.clues))

    def test_hide_rummage_and_retrieve(self):
        w, spy = self.w, self.spy
        spy.activity = "working"
        spy.extra_badges.append("U4-IE-03")
        w.people["U4-IE-03"].badge, w.people["U4-IE-03"].lent_to = None, spy.id
        self.assertIn("hidden", w.hide(spy, "badges", ""))
        self.assertEqual(spy.extra_badges, [])
        self.assertIn("you have", w.retrieve(spy))
        self.assertEqual(spy.extra_badges, ["U4-IE-03"])
        w.hide(spy, "badges", "")
        finder = next(q for q in w.people.values() if q.id != spy.id and q.tier == "staff")
        finder.zone = spy.zone
        w.rng.random = lambda: 0.0
        self.assertIn("found", w.rummage(finder))
        c = [c for c in w.clues if c.type == "physical"][-1]
        self.assertIn(spy.id, c.suspects)
        self.assertEqual(w.people["U4-IE-03"].badge, "U4-IE-03")

    def test_search_person_frisks_and_finds_badges(self):
        w, spy, d = self.w, self.spy, self.w.director
        spy.extra_badges.append("U4-IE-04")
        self._clear()
        r = self.eng.do(d, "search", spy.id, "", "", "walk")
        self.assertIn("on it", r)
        # the call goes out on the security channel
        self.assertTrue(any("locate" in m["text"] for m in w.people["U4-SEC-05"].inbox))
        gid = next(k for k, t in w.tasks.items() if t["kind"] == "frisk")
        w.people[gid].zone = spy.zone
        w.step_tasks()
        self.assertTrue(any(c.type == "physical" and c.found and spy.id in c.suspects for c in w.clues))

    def test_search_zone_sweeps(self):
        w, spy = self.w, self.spy
        spy.activity = "working"
        w.hide(spy, "", "a printout of the calibration log")
        r = w.investigate(w.director, "search", spy.zone, None)
        self.assertIn("on it", r)

    def test_spy_alone_gets_the_dossier(self):
        self.assertIn("YOUR READ ON PEOPLE", system_prompt(self.w, self.spy))
        for p in self.w.people.values():
            if not p.saboteur:
                self.assertNotIn("YOUR READ ON PEOPLE", system_prompt(self.w, p))

    def test_tempo(self):
        try:
            config.set_tempo("max")
            self.assertEqual(config.THINK_EVERY_S["staff"], 60)
            self.assertEqual(config.MIN_GAP_S, 15)
        finally:
            config.set_tempo("normal")
        self.assertEqual(config.THINK_EVERY_S["staff"], 180)


if __name__ == "__main__":
    unittest.main()
