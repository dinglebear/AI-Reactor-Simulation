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

This writes `runs/latest/replay.html`, a single file with the replay inside. You can also open `viewer/index.html`
in a browser and drop any `replay.json` on it.

The viewer has an animated map, layer toggles (names, cameras and blind spots, badge swipes, sprints, talk, clues,
reveal truth), console meters with the true values as a red tick, a timeline with the incident curve, a feed of story
beats, agent thoughts and the raw log, and **Play the story**, which travels from beat to beat with narration captions.

## Cost of a live run

A full four-hour shift is roughly 2,000 Haiku turns, 240 Sonnet turns and 50 Opus turns. The run prints token
usage at the end. Use `--minutes` for short test runs.

## Tests

```bash
python -m unittest discover tests
```
