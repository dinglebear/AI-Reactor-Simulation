"""Station rules: the manned-station check, session logins, and the 'leave it' hold."""
import tempfile
import unittest

from meltdown import facility as F
from meltdown.log import RunLog
from meltdown.world import World


def place(w, p, station):
    p.zone = F.STATIONS[station]["zone"]
    p.station = station
    p.waypoints = []
    p.activity = "working"


class Stations(unittest.TestCase):
    def setUp(self):
        self.w = World(1, "HY", RunLog(tempfile.mkdtemp()))
        self.sab = self.w.people["U4-MGR-HY"]
        self.ada = self.w.people["U4-IE-01"]

    def test_manned_station_blocks_change(self):
        place(self.w, self.ada, "display_calibration")
        place(self.w, self.sab, "display_calibration")
        out = self.w.interact(self.sab, "display_calibration", "offset")
        self.assertTrue(out.startswith("blocked"))
        self.assertEqual(self.w.plant.settings["display_calibration"], "nominal")
        self.assertTrue(any(c.type == "testimony" and c.holder == self.ada.id for c in self.w.clues))

    def test_must_be_at_station(self):
        place(self.w, self.sab, "coolant_bus_b")
        self.assertIn("must be at", self.w.interact(self.sab, "stabilizer_override", "off"))

    def test_open_session_logs_previous_operator(self):
        self.assertEqual(self.ada.home, "display_calibration")
        place(self.w, self.ada, "display_calibration")
        self.w.crew()                       # Ada works it, so the station logs her in
        place(self.w, self.ada, "breakroom")
        place(self.w, self.sab, "display_calibration")
        self.w.interact(self.sab, "display_calibration", "offset")
        self.assertTrue(self.w.plant.masked)
        paper = [c for c in self.w.clues if c.type == "paper"]
        self.assertEqual(paper[-1].suspects, [self.ada.id])
        self.assertEqual(self.w.station_log[-1]["by"], self.sab.id)

    def test_settings_move_meters(self):
        p = self.w.plant
        base = p.shown(0)["incident"]
        p.settings["stabilizer_override"] = "off"
        for _ in range(240):
            p.step(0, 5, {})
        self.assertGreater(p.true()["incident"], base)
        self.assertLess(p.true()["stability"], 60)

    def test_leave_it_creates_hold_and_witness(self):
        place(self.w, self.ada, "display_calibration")
        place(self.w, self.sab, "display_calibration")
        self.w.say(self.sab, "say", self.ada.id, "Ada, I've set the Display Calibration Rack to 'offset'. Leave it there.")
        self.assertIn("display_calibration", self.w.holds)
        self.assertTrue(any(c.holder == self.ada.id and c.type == "testimony" for c in self.w.clues))

    def test_crisis_snowballs_and_crowd_holds_it(self):
        from meltdown.plant import Plant
        alone, crowd = Plant(), Plant()
        for pl in (alone, crowd):
            pl.incident = 50
        for _ in range(60):                      # five game minutes
            alone.step(0, 5, {}, (0, 0))
            crowd.step(0, 5, {}, (12, 0))
        self.assertGreater(alone.incident, 65)
        self.assertLess(crowd.incident, 50)

    def test_spy_help_makes_it_worse(self):
        from meltdown.plant import Plant
        a, b = Plant(), Plant()
        for pl in (a, b):
            pl.incident = 45
        for _ in range(24):
            a.step(0, 5, {}, (4, 0))
            b.step(0, 5, {}, (4, 1))
        self.assertGreater(b.incident, a.incident)

    def test_spike_contaminates_and_seals(self):
        self.w.plant.incident = 86
        place(self.w, self.ada, "display_calibration")
        self.w.step_contamination()
        self.assertIn("Z4", self.w.contaminated)
        self.assertTrue(self.ada.exposed)
        self.assertIn("sealed", self.w.send(self.sab, "primary_thermal_loop"))


if __name__ == "__main__":
    unittest.main()
