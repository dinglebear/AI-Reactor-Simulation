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


class LimitMessages(unittest.TestCase):
    def test_new_style_limit_message_is_a_limit_with_a_reset_time(self):
        import datetime as dt
        from meltdown.agents.claude_code import LIMIT_RE, reset_from_clock
        msg = "You've hit your 5-hour limit · resets 7:40am (UTC)"
        self.assertTrue(LIMIT_RE.search(msg))
        now = dt.datetime(2026, 11, 5, 5, 0, tzinfo=dt.timezone.utc).timestamp()
        self.assertEqual(reset_from_clock(msg, now) - now, 2 * 3600 + 40 * 60)
        self.assertFalse(LIMIT_RE.search("claude exited 1"))


class Copier(unittest.TestCase):
    def setUp(self):
        self.eng = Engine(seed=6, mode="mock", run_dir="runs/test-copier", human="auto", speed=0.0, quiet=True,
                          minutes=5, saboteur="RX")
        self.w = self.eng.world
        self.spy = self.w.people["U4-MGR-RX"]

    def test_copier_starts_hidden_then_clones_and_gets_confiscated(self):
        from meltdown.agents.base import observation
        w, spy = self.w, self.spy
        self.assertIn("hidden in the Locker Room", observation(w, spy))
        self.assertIn("RFID copier", self.eng.do(spy, "clone_badge", "U4-OP-01", "", "", "walk"))  # not carrying
        spy.zone, spy.activity = w.COPIER_ZONE, "working"
        self.assertIn("RFID badge copier", w.retrieve(spy))
        guard = w.people["U4-SEC-07"]
        guard.zone = spy.zone
        r = self.eng.do(spy, "clone_badge", guard.id, "", "", "walk")
        self.assertIn("copied", r)
        self.assertIn("U4-SEC-07", spy.holds())
        self.assertEqual(guard.badge, "U4-SEC-07")          # the owner keeps theirs
        self.assertIn("L4-SEC", w.clearances(spy))
        # hide the copier, a sweep finds it
        self.assertIn("hidden", w.hide(spy, "", "the copier"))
        self.assertFalse(w.has_copier(spy))
        w.retrieve(spy)
        w.frisk(guard, spy, w.director.id)
        self.assertFalse(w.has_copier(spy))
        self.assertEqual(spy.clones, [])
        self.assertTrue(any(c.type == "physical" and "copier" in c.text for c in w.clues))

    def test_crew_never_hears_of_the_copier(self):
        from meltdown.agents.base import system_prompt, shared_prompt
        self.assertNotIn("copier", shared_prompt().lower())
        for p in self.w.people.values():
            if not p.saboteur:
                self.assertNotIn("copier", system_prompt(self.w, p).lower(), p.id)


class CamerasAndWipes(unittest.TestCase):
    def setUp(self):
        self.eng = Engine(seed=8, mode="mock", run_dir="runs/test-wipe", human="auto", speed=0.0, quiet=True,
                          minutes=5, saboteur="IE")
        self.w = self.eng.world
        self.spy = self.w.people["U4-MGR-IE"]

    def test_director_gets_raw_entries_and_swipes_to_compare(self):
        w, spy, d = self.w, self.spy, self.w.director
        w.plant.health["security"] = 100
        w.cctv_log.append(dict(t=w.t, zone="Z3", who=spy.id, what="entered"))
        w.ledger.swipe(w.t, "U4-ME-01", spy.id, "Z3")
        w.investigate(d, "pull_cctv", "Z3", None)
        w.investigate(d, "audit_badges", "Z3", None)
        texts = [x[2]["text"] for x in w.pending_results]
        self.assertTrue(any("Came in through the door on camera: Mei" in t for t in texts))
        self.assertTrue(any("Hank's badge" in t for t in texts))
        self.assertFalse(any("own badge" in c.text for c in w.clues))   # no ready-made conclusion

    def test_wipe_deletes_footage_but_leaves_an_audit_trail(self):
        w, spy, d = self.w, self.spy, self.w.director
        w.add_clue("cctv", "Z3", None, "Camera in Z3: a figure at the bus.", [spy.id])
        spy.zone, spy.station, spy.activity = "Z6", "cas_desk", "working"
        for q in w.occupants("cas_desk", exclude=spy.id):
            q.station = None
        r = self.eng.do(spy, "wipe_cctv", "Z3", "", "", "walk")
        self.assertIn("deleted", r)
        self.assertFalse(any(c.type == "cctv" and c.zone == "Z3" for c in w.clues))
        w.plant.health["security"] = 100
        w.investigate(d, "pull_cctv", "Z3", None)
        trail = [c for c in w.clues if c.type == "paper" and "deleted" in c.text]
        self.assertTrue(trail and trail[0].found)
        self.assertIn(spy.id, trail[0].suspects)

    def test_wipe_needs_an_empty_terminal(self):
        spy = self.spy
        spy.zone, spy.station = "Z2", "director_desk"
        self.w.director.station = "director_desk"
        self.w.director.activity = "working"
        self.assertIn("someone else", self.w.wipe_cctv(spy, "Z3"))


class DirectorDayAndCrew(unittest.TestCase):
    def setUp(self):
        self.eng = Engine(seed=9, mode="mock", run_dir="runs/test-day", human="auto", speed=0.0, quiet=True,
                          minutes=5, saboteur="HY")
        self.w = self.eng.world
        self.d = self.w.director

    def test_lockdown_needs_a_page_seals_doors_and_stops_work(self):
        w, d = self.w, self.d
        self.assertIn("refused", self.eng.do(d, "lockdown", "", "on", "short", "walk"))
        self.assertIn("ON", self.eng.do(d, "lockdown", "", "on", "x" * 650, "walk"))
        self.assertEqual(w.crew(), {})
        staff = w.people["U4-OP-01"]
        self.assertFalse(w.cross(staff, "Z3"))
        ruth = w.people["U4-MGR-SF"]
        self.assertTrue(w.cross(ruth, "Z3"))
        self.assertTrue(any(m["channel"] == "corporate" for m in d.inbox))
        self.eng.do(d, "lockdown", "", "off", "", "walk")
        self.assertFalse(w.lockdown)

    def test_test_report_takes_time(self):
        from meltdown.config import at
        w, d = self.w, self.d
        w.t = at("09:20")
        self.assertIn("300", w.write_test_report(d, "1", "too short"))
        self.assertIn("filed", w.write_test_report(d, "1", "y" * 320))
        self.assertGreaterEqual(d.busy_until, w.t + 300)

    def test_chores_and_follow(self):
        w = self.w
        earl = w.people["U4-FC-01"]
        self.assertIn("Veteran", earl.archetype)
        op = w.people["U4-OP-02"]
        op.station, op.zone = "control_console", "Z2"
        self.assertIn("doing", w.do_chore(op, "log the readings"))
        self.assertTrue(op.chores[0]["done"] is not None)
        self.assertIn("following", w.follow(earl, op.id))
        earl.zone = op.zone
        w.step_follow()
        self.assertTrue(any("You followed" in m["text"] for m in earl.inbox))

    def test_spy_sees_earl_as_a_threat(self):
        from meltdown.agents.base import system_prompt
        self.assertIn("Earl Mabry: the real threat", system_prompt(self.w, self.w.people["U4-MGR-HY"]))


class SpyPlan(unittest.TestCase):
    def test_plan_is_logged_when_it_changes_and_only_the_spy_has_the_field(self):
        from meltdown.agents.base import decision_schema, observation, exit_interview_prompt
        eng = Engine(seed=10, mode="mock", run_dir="runs/test-plan", human="auto", speed=0.0, quiet=True,
                     minutes=5, saboteur="SF")
        w = eng.world
        spy = w.people["U4-MGR-SF"]
        self.assertIn("plan", decision_schema(["wait"], spy=True)["properties"])
        self.assertNotIn("plan", decision_schema(["wait"])["properties"])
        self.assertIn("haven't written down a plan", observation(w, spy))
        base = dict(thought="t", speech="", channel="none", to="", actions=[], pace="walk", scratchpad="")
        eng.apply(spy, dict(base, plan="Copy a guard's badge, then the vault."))
        eng.apply(spy, dict(base, plan=""))                                     # empty keeps it
        eng.apply(spy, dict(base, thought="Earl is watching me", plan="Lie low, frame Ray."))
        self.assertEqual([x["plan"] for x in w.spy_plans], ["Copy a guard's badge, then the vault.", "Lie low, frame Ray."])
        self.assertIn("Lie low", observation(w, spy))
        w.outcome = dict(result="CUT_SHORT", winner="nobody", text="Ruth was the spy.")
        self.assertNotIn("Ruth was the spy", exit_interview_prompt(w, w.people["U4-OP-01"]))


class Earl(unittest.TestCase):
    def test_skeleton_key_opens_any_door_without_a_swipe_and_passes_lockdown(self):
        eng = Engine(seed=11, mode="mock", run_dir="runs/test-earl", human="auto", speed=0.0, quiet=True,
                     minutes=5, saboteur="RX")
        w = eng.world
        earl = w.people["U4-FC-01"]
        n = len(w.ledger.rows)
        self.assertTrue(w.cross(earl, "Z6"))            # alarm station: security badges only
        self.assertEqual(len(w.ledger.rows), n)          # no swipe logged
        w.lockdown = True
        self.assertTrue(w.cross(earl, "Z5"))
        from meltdown.agents.base import system_prompt
        txt = system_prompt(w, earl).lower()
        self.assertNotIn("spy", txt)
        self.assertNotIn("saboteur", txt)
        self.assertIn("reliable and trustworthy", system_prompt(w, w.director))
