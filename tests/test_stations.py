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


if __name__ == "__main__":
    unittest.main()
