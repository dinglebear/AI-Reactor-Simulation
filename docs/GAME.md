# MELTDOWN: how the game works

A social deduction game for AI agents, set on certification-test day at a fictional power station, Unit 4.
Thirty agents work the shift. One of the four department managers is secretly a corporate spy: planted by a rival company years ago, they worked their way up and are trusted by their team. Today their handler wants the test to fail. The Director has
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
| **INCIDENT** | Rises while any station sits off its normal setting, and from danger zones (heat over 75, stability under 45). At 100 the saboteur wins |
| System health ×4 | Core, coolant, instruments, security. Each wears down; staff working at the matching station restore it |

The control room sees **shown** values. While the Display Calibration Rack is on `offset` the console reads
calmer than the truth, and weak instruments add uncertainty. Corporate grades the test on the shown values, so a masked console can fool it too.

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

## Stations and the three verbs

There are no cards. Every agent acts with three verbs: `speak(target, channel, message)`, `move(zone or station)`
and `interact(station, setting)`. The stations below are **fictional**. Their names sound industrial, but each
one is a game piece with two or three settings that nudge the abstract meters. Nothing here describes how a
real plant works.

| Station (zone) | Settings, normal first | Game effect when off normal |
|---|---|---|
| Primary Thermal Loop (Z4) | nominal, boost | extra heat load |
| Display Calibration Rack (Z4) | nominal, offset | console shows calmer heat, stability and INCIDENT |
| Stabilizer Override Console (Z5, vault) | auto, manual, off | stability target drops |
| Coolant Bus A / B (Z3) | nominal, reduced, standby | coolant removes less heat |
| Ventilation Shunt (Z8) | open, closed | extra heat load |

Every station except the Display Calibration Rack also adds to INCIDENT for each minute it sits off normal.
An operator who finds their station off normal will usually put it back and report it.

### The manned-station rule

You have to be standing at a station to change it. If someone else is working at it, an off-normal change is
**blocked**: the operator sees you, an alarm reaches the Director ("change attempted while manned by Ada"), and
the operator holds a witness account. So the saboteur has to get the operator away first:

- **Lie.** Tell them the Director wants them in the breakroom, or that a delivery is waiting at the gate. A request
  from someone who isn't their boss, or a false "the Director wants you", becomes a witness account they can repeat
  in an interview (plus a radio-log clue if it went over the radio).
- **Wait for a break.** Restroom need builds over the shift. The saboteur can hover until the operator has to go.
- **"Leave it, it's signed off."** After a change, a manager can tell the regular operator to leave the new setting
  alone. Compliant staff often do. That instruction is itself a witness account.

### Forensics

Each change off normal leaves traces:

| Trace | What it says | The catch |
|---|---|---|
| Station log (paper) | which badge's login made the change | a station stays logged in for 10 minutes after its operator walks away, so a quick change frames the operator |
| Camera (cctv) | a figure at the station | only narrows it to everyone in the room in the last 15 minutes; restrooms have no cameras |
| Witnesses (testimony) | "I saw Frank at the rack" | held by the witness until the Director interviews them, and some won't talk |
| Badge ledger | swipes, borrowed badges, impossible locations | a borrowed badge logs under its owner's name |
| Console vs truth | `cross_check` shows true meters next to the console | only if someone runs it |

The mock Director interviews the main suspect before an arrest, which is often when the lured operator says
"Frank sent me to the gate".

## The Director's investigations (two per turn)

| Action | Finds | Cost |
|---|---|---|
| audit_badges | ledger clues, door alerts | result in 2 min |
| pull_cctv zone | cctv clues in that zone, sprint sightings | 1 min; footage may be corrupted if security health < 40 |
| inspect station, person | the station log (paper clues) and its current setting; resets it to normal | a staff member walks there and works 60 s |
| cross_check person | true meters next to the console, every off-normal station, and the rack's log if masked | a staff member works 90 s at the test bench |
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
| `events.jsonl` | every event as it happens: speech, swipes, station changes, blocked attempts, lures, clues, alarms, pauses |
| `thoughts.jsonl` | one line per agent turn: private `thought`, `reasoning_summary` (live runs), speech, actions, results, model, latency, tokens |
| `replay.json` | everything above plus position frames every 15 game-seconds (with off-normal stations), the station log, and narrated story beats |

The narrated story opens with a note that the stations are fictional, and adds a one-time narrator's note the
first time the game takes a big shortcut (one person tipping the plant, the manned-station rule, the forensics).

`thought` is the agent's in-character private monologue, which it writes as part of its JSON answer.
`reasoning_summary` is the summarized extended thinking the API returns for that call; models don't expose
their raw chain of thought.
