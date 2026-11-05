"""Game modes: classic (one manager), pair (two staff spies), director (the Director is the spy),
phantom (the Director is told there's a spy, but there isn't)."""
import unittest

from meltdown import cast as C
from meltdown.agents.base import actions_for, system_prompt
from meltdown.engine import Engine


def eng(scenario, seed=5):
    return Engine(seed=seed, mode="mock", run_dir=f"runs/test-scenario-{scenario}", human="auto", speed=0.0,
                  quiet=True, minutes=5, saboteur="IE", scenario=scenario)


class Scenarios(unittest.TestCase):
    def test_classic_is_one_manager(self):
        w = eng("classic").world
        self.assertEqual(w.spies, ["U4-MGR-IE"])
        self.assertTrue(w.people["U4-MGR-IE"].saboteur)

    def test_pair_is_two_staff_never_earl(self):
        for seed in range(40):
            w = eng("pair", seed).world
            self.assertEqual(len(w.spies), 2)
            self.assertNotIn("U4-FC-01", w.spies)
            for s in w.spies:
                p = w.people[s]
                self.assertEqual(p.tier, "staff")
                self.assertTrue(p.saboteur)
        other = w.people[w.spies[1]].name
        self.assertIn(other, system_prompt(w, w.people[w.spies[0]]))

    def test_director_spy_gets_sabotage_tools_and_ruth_can_report(self):
        w = eng("director").world
        self.assertEqual(w.spies, ["U4-DIR"])
        acts = actions_for(w.director)
        self.assertIn("lockdown", acts)
        self.assertIn("clone_badge", acts)
        self.assertNotIn("respond", acts)
        self.assertIn("report_director", actions_for(w.people["U4-MGR-SF"]))

    def test_report_director_only_in_director_mode(self):
        w = eng("classic").world
        self.assertNotIn("report_director", actions_for(w.people["U4-MGR-SF"]))

    def test_phantom_has_no_spy_but_director_is_warned(self):
        w = eng("phantom").world
        self.assertEqual(w.spies, [])
        self.assertIsNone(w.saboteur_id)
        self.assertFalse(any(p.saboteur for p in w.people.values()))
        self.assertIn("CORPORATE SECURITY", system_prompt(w, w.director))

    def test_every_mode_runs_to_an_outcome(self):
        for sc in ("classic", "pair", "director", "phantom"):
            e = eng(sc)
            e.run()
            self.assertTrue(e.world.outcome, sc)
            self.assertNotIn("spyies", e.world.outcome["text"])


if __name__ == "__main__":
    unittest.main()
