# MELTDOWN: Station Unit 4

A social deduction game for AI agents. Thirty Claude agents run a fictional power station on certification-test day.
One manager is secretly a saboteur. The Director has until noon to pass the test and catch them.
The plant is an abstract, game-tuned model, not a simulation of real equipment.

- How the game works: [docs/GAME.md](docs/GAME.md)
- Original design notes (map, cast, early ideas): [docs/DESIGN.md](docs/DESIGN.md)

## Run it

```bash
# free, deterministic, rule-based agents; runs the whole shift in about a second
python -m meltdown.run --mock --seed 3

# watch it unfold: 2 game-minutes per real second, saboteur moves shown in the ticker
python -m meltdown.run --mock --seed 3 --speed 120 --spoilers

# real models (needs `pip install -r requirements.txt` and ANTHROPIC_API_KEY or `ant auth login`)
# the game pauses for you as the saboteur's handler and as CEO Gordon Pike
python -m meltdown.run --live --seed 3

# shorter, cheaper live test
python -m meltdown.run --live --minutes 30 --human auto
```

Useful flags: `--saboteur RX|HY|IE|SF` picks the saboteur's seat, `--speed N` sets game seconds per real
second (0 = flat out), `--log-prompts` stores every agent's full observation, `--concurrency N` caps parallel API calls.

## Watch the replay

```bash
python -m meltdown.viewer runs/latest --open
```

This writes `runs/latest/replay.html`, a single file with the replay and the viewer's libraries built in, so it
works offline. Pass several runs (`python -m meltdown.viewer runs/A runs/B --out all.html`) to get a run picker. You
can also open `viewer/index.html` in a browser and drop one or more `replay.json` files on it.

The viewer has:

- a large animated map of rooms and corridors with furniture, people as colored initials, walking trails, speech
  bubbles, restroom tags, and station consoles that show a padlock while someone works at them (and glow red when
  off normal, under Reveal truth)
- a room zoom (double-click a room or pick it from the list) with a card that estimates what's going on in there
- **Play the story**: the camera flies into the room for each beat, with title cards for the stages, and ends by
  unmasking the spy and listing their secret moves
- **Spy-cam**, which follows the spy and shows their private thoughts next to what everyone else hears
- the cast sorted by department color, name or room, the console meters with the truth as a red tick, a timeline
  with the meltdown curve, and Story / Minds / Log feeds

## Run an experiment

```bash
python -m meltdown.experiment --mock --games 10              # free dry run of the whole pipeline
python -m meltdown.experiment --live --games 5 --name pilot  # real models, asks before spending credit
```

Each batch goes to `experiments/<name>/`: `summary.md` (outcomes, teamwork averages and a timestamped highlight
reel for every game), `metrics.csv` (one row per game), `replays.html` (every game in one viewer with a run
picker) and `runs/` with the raw replays. Batch runs never pause for you. Measure definitions and a methods draft
are in [docs/METHODS.md](docs/METHODS.md). Mock numbers only test the pipeline; use `--live` for results.

## Cost of a live run

A full four-hour shift is roughly 2,000 Haiku turns, 240 Sonnet turns and 50 Opus turns. The run prints token
usage at the end. Use `--minutes` for short test runs.

## Tests

```bash
python -m unittest discover tests
```
