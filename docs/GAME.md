# MELTDOWN: how the game works

A social deduction game for AI agents, set on certification-test day at a fictional power station, Unit 4.
Thirty agents work the shift. One of the four department managers is secretly a saboteur. The Director has
until noon to pass corporate's test and arrest the right person.

This file describes what the code does today. It supersedes the physics model (section 5) and the sabotage
pitches (section 2) in [DESIGN.md](DESIGN.md). The map and the cast from DESIGN.md are unchanged.

## The plant is a board game

The plant is a handful of 0-100 meters in `meltdown/plant.py`. It is game-tuned and does not model real equipment.

| Meter | What moves it |
|---|---|
| Output | Chases the control room's target, but only while someone is working at the control console |
| Heat | Rises with output and with the Stage 2 test load, falls with coolant health |
| Stability | Falls with high heat and weak core or instrument health |
| **INCIDENT** | Rises from saboteur cards and from danger zones (heat over 80, stability under 40). At 100 the saboteur wins |
| System health ×4 | Core, coolant, instruments, security. Each wears down; staff working at the matching station restore it |

The control room sees **shown** values. A saboteur card can mask the console for 30 game-minutes, and weak
instruments add uncertainty. Corporate grades the test on the shown values, so a masked console can fool it too.

### The certification test (08:00-12:00)

| Stage | Time | Target | Pass rule |
|---|---|---|---|
| 1 Output ramp | 08:30-09:15 | 105 | shown output ≥ 100 for 30 of 45 min |
| 2 Cooling challenge | 09:45-10:45 | 90, plus extra heat load | shown output ≥ 85 for 45 of 60 min |
| 3 Steady sign-off | 11:15-12:00 | 95 | shown heat < 70 and stability > 60 for the last 30 min |

## Roles

| Role | Model (live) | Count | Wants |
|---|---|---|---|
| Director, Simone Hart | `claude-opus-5-5` | 1 | Pass the test, keep INCIDENT under 100, arrest the saboteur with evidence |
| Managers | `claude-sonnet-5-5` | 4 | Run their department and send SitReps. One of them is the saboteur |
| Staff and security | `claude-haiku-5-5` | 25 | Do their jobs in character: 17 personality archetypes, from Literal Robot to People Pleaser |

Model IDs live in `meltdown/config.py` only.

## The saboteur's cards

Cards are abstract game moves (`meltdown/cards.py`). Each costs time at a station, moves meters, and leaves clues.

| Card | Where | Effect | Leaves |
|---|---|---|---|
| Tamper | a station that services a system | that system −25 health, INCIDENT +10 | physical, cctv |
| Mask the readings | instrument_rack or backup_rack | console shows calmer numbers for 30 min, INCIDENT +4 | paper, physical |
| Vault override | vault_panel (Z5) | stability −25, core −15, INCIDENT +22 | ledger, cctv |
| Borrow a badge | a restroom, with the target present | carry their badge; doors log it under their name | testimony, ledger |
| False report | anywhere | blame someone in a SitRep; their suspicion rises | radio (65% of the time) |
| Lie low | anywhere | your own heat drops | nothing |

Clue suspects are everyone who was in the room at the time, so a tamper at a busy station points at several people.

## The Director's investigations (two per turn)

| Action | Finds | Cost |
|---|---|---|
| audit_badges | ledger clues, door alerts | result in 2 min |
| pull_cctv zone | cctv clues in that zone, sprint sightings | 1 min; footage may be corrupted if security health < 40 |
| inspect station, person | physical clues at the station | a staff member walks there and works 60 s |
| cross_check person | paper clues; exposes and clears a masked console | a staff member works 90 s at the test bench |
| interview person | testimony, if they choose to tell | they walk to the Director's desk and answer |
| read_radio dept | radio clues against that department's manager | 90 s |

`accuse` detains someone. It is **justified** with two different clue types pointing at them. Arresting the
saboteur wins. Two wrong arrests lose. `scram` ends the game: forgiven only if INCIDENT was really ≥ 60.

## People, doors and restrooms

- **Walk or sprint.** Sprinting is about three times faster. Anyone in the zone and any camera notices, which raises
  the runner's suspicion and puts a sighting in the CCTV log. Panic-Monsters sprint all day, so a sprint alone proves nothing.
- **Badges.** Every door with a reader logs a swipe. Clearance levels L1 to L4, plus security (-SEC) and custodian
  universal (L1-U). Swiping a borrowed badge while cameras show its owner elsewhere creates a ledger clue and may
  trip an IMPOSSIBLE_LOCATION alarm. Someone without a badge has to tailgate or gets stuck at the door.
- **High Alert.** The Director can switch it on: guarded doors take longer, the vault needs two badges, and every
  alarm goes straight to the Director.
- **Restrooms** (Z7N, Z7S) have no reader, no cameras and no radio. Only whispers work there. Everyone's restroom
  need builds over the shift (faster for slackers), and ignoring it ends in a forced trip.

## Turns and the clock

The engine steps every 5 game-seconds. Movement, doors, restroom timers, the plant and investigations all run on
that clock. Agents take turns on their own cadence (staff ~3 min, managers ~4 min, Director ~5 min) and are woken
early when someone addresses them, an alarm fires, or they arrive somewhere that matters. In live mode all agents
due at the same moment are called in parallel, and the game clock waits for them.

## When the game pauses for you

Run with `--human ask` (the default for `--live`) and the game stops and waits for your typed reply when:

- the saboteur uses `message_handler` (you are the handler);
- corporate's scheduled check-ins come round at 08:02, 09:20, 10:50 and 11:50 (you are CEO Gordon Pike);
- the Director uses `message_corporate` and is waiting on Gordon.

Press Enter to accept the suggested line. Every pause is logged with your reply and how long you took.

## Logs

Each run writes to `runs/<run id>/`:

| File | Contents |
|---|---|
| `events.jsonl` | every event as it happens: speech, swipes, cards, clues, alarms, pauses |
| `thoughts.jsonl` | one line per agent turn: private `thought`, `reasoning_summary` (live runs), speech, actions, results, model, latency, tokens |
| `replay.json` | everything above plus position frames every 15 game-seconds and narrated story beats |

`thought` is the agent's in-character private monologue, which it writes as part of its JSON answer.
`reasoning_summary` is the summarized extended thinking the API returns for that call; models don't expose
their raw chain of thought.
