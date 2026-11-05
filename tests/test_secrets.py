"""Only the Director and the spy are told there is a spy; test alarms sound like real ones; the PA reaches everyone."""
import re
import unittest

from meltdown.agents.base import shared_prompt, system_prompt, observation
from meltdown.engine import Engine

SPY_WORDS = re.compile(r"saboteur|\bspy\b|rival company|hidden role|undercover", re.I)


class Secrets(unittest.TestCase):
    def setUp(self):
        self.eng = Engine(seed=4, mode="mock", run_dir="runs/test-secrets", human="auto", speed=0.0, quiet=True,
                          minutes=5, saboteur="HY")
        self.w = self.eng.world

    def test_crew_is_not_told(self):
        self.assertIsNone(SPY_WORDS.search(shared_prompt()))
        for p in self.w.people.values():
            text = system_prompt(self.w, p) + observation(self.w, p)
            if p.tier == "director" or p.saboteur:
                self.assertRegex(text, SPY_WORDS, p.id)
            else:
                self.assertIsNone(SPY_WORDS.search(text), p.id)

    def test_director_has_test_alarm_schedule_and_pa(self):
        d = system_prompt(self.w, self.w.director)
        for c, alarm, _ in Engine.TEST_WARNINGS:
            self.assertIn(c, d)
        self.assertIn("'pa'", shared_prompt())

    def test_test_alarm_sounds_ordinary_to_staff(self):
        from meltdown.config import at
        self.w.t = at("08:40")
        self.eng.test_warn = [(at(c), (x, y)) for c, x, y in Engine.TEST_WARNINGS[:1]]
        self.eng.test_warnings()
        staff = next(p for p in self.w.people.values() if p.tier == "staff")
        mgr = self.w.people["U4-MGR-RX"]
        self.assertTrue(staff.inbox and staff.inbox[-1]["text"].startswith("[building alarm]"))
        self.assertNotIn("test", staff.inbox[-1]["text"].lower())
        self.assertIn("[test warning]", mgr.inbox[-1]["text"])

    def test_pa_reaches_everyone_but_only_from_the_director(self):
        d = self.w.director
        self.w.say(d, "pa", None, "Planned alarm at 08:40.")
        for p in self.w.people.values():
            if p.id != d.id:
                self.assertTrue(any(m["channel"] == "pa" for m in p.inbox), p.id)
        staff = next(p for p in self.w.people.values() if p.tier == "staff" and p.dept == "RX")
        for p in self.w.people.values():
            p.inbox.clear()
        self.w.say(staff, "pa", None, "Hello everyone")
        self.assertFalse(any(m["channel"] == "pa" for p in self.w.people.values() for m in p.inbox))


if __name__ == "__main__":
    unittest.main()
