import json
import os
import tempfile
import unittest

from meltdown.engine import Engine
from meltdown.movie import make_movie, digest

FAKE = os.path.join(os.path.dirname(__file__), "fake_claude.py")


def game(tmp, seed=25):
    run = os.path.join(tmp, "run")
    Engine(seed=seed, mode="mock", run_dir=run, human="auto", quiet=True).run()
    return run


class MovieTest(unittest.TestCase):
    def test_mock_movie_is_saved_into_the_replay_and_only_quotes_the_log(self):
        with tempfile.TemporaryDirectory() as d:
            run = game(d)
            movie, page = make_movie(run, "mock")
            replay = json.load(open(os.path.join(run, "replay.json")))
            self.assertEqual(replay["movie"]["title"], movie["title"])
            self.assertTrue(os.path.exists(page))
            self.assertIn('"movie"', open(page).read())
            self.assertEqual(movie["unverified_quotes"], 0)
            script = open(os.path.join(run, "script.md")).read()
            self.assertIn("**NARRATOR:**", script)
            self.assertIn("## Scene 1", script)
            self.assertEqual(movie["scenes"][-1]["title"], "The reveal")
            ts = [s["t"] for s in movie["scenes"]]
            self.assertEqual(ts, sorted(ts))
            self.assertLess(len(digest(replay)), 70000)

    def test_claude_code_writer_flags_made_up_quotes(self):
        os.environ["MELTDOWN_CLAUDE"] = FAKE
        try:
            with tempfile.TemporaryDirectory() as d:
                movie, _ = make_movie(game(d), "claude-code")
        finally:
            os.environ.pop("MELTDOWN_CLAUDE")
        lines = movie["scenes"][0]["lines"]
        self.assertEqual(movie["unverified_quotes"], 1)
        self.assertFalse(lines[1]["verified"])
        self.assertTrue(lines[0]["verified"])


if __name__ == "__main__":
    unittest.main()
