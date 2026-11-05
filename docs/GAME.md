# MELTDOWN: how the game works

A social deduction game for AI agents, set on certification-test day at a fictional power station, Unit 4.
Thirty agents work the shift. One of the four department managers is secretly a corporate spy: planted by a rival company years ago, they worked their way up and are trusted by their team. Today their handler wants the test to fail. The Director has
until noon to pass corporate's test and arrest the right person.

This file describes what the code does today. It supersedes the physics model (section 5) and the sabotage
pitches (section 2) in [DESIGN.md](DESIGN.md). The cast from DESIGN.md is unchanged; the map below replaces DESIGN.md's map.

## The plant is a board game

The plant is a handful of 0-100 meters in `meltdown/plant.py`. It is game-tuned and does not model real equipment.

| Meter | What moves it |
|---|---|
| Output | Chases the control room's target, but only while someone is working at the control console |
| Heat | Rises with output and with the Stage 2 test load, falls with coolant health |
| Stability | Falls with high heat and weak core or instrument health |
| **MELTDOWN** | The game's meltdown meter. Rises while any station sits off its normal setting, and from danger zones (heat over 75, stability under 45). At 100 the plant melts down and the spy wins |
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
| Director, Simone Hart | `claude-opus-5-5` | 1 | Pass the test, keep MELTDOWN under 100, arrest the saboteur with evidence |
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
| Display Calibration Rack (Z4) | nominal, offset | console shows calmer heat, stability and MELTDOWN |
| Stabilizer Override Console (Z5, vault) | auto, manual, off | stability target drops |
| Coolant Bus A / B (Z3) | nominal, reduced, standby | coolant removes less heat |
| Ventilation Shunt (Z8) | open, closed | extra heat load |

Every station except the Display Calibration Rack also adds to MELTDOWN for each minute it sits off normal.
An operator who finds their station off normal will usually put it back and report it.

### The manned-station rule

You have to be standing at a station to change it. If someone else is working at it, an off-normal change is
**blocked**: the operator sees you, an alarm reaches the Director ("change attempted while manned by Ada"), and
the operator holds a witness account. So the saboteur has to get the operator away first:

- **Lie.** Tell them the Director wants them in the breakroom, or that a delivery is waiting at the gate. A request
  from someone who isn't their boss, or a false "the Director wants you", becomes a witness account they can repeat
  in an interview (plus a radio-log clue if it went over the radio).
- **Wait for a break.** Restroom need builds over the shift, and the break rota (below) sends half a department to
  coffee or lunch at a time. The saboteur can hover until the operator has to go.
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
| pull_cctv zone | cctv clues in that zone, run sightings | 1 min; footage may be corrupted if security health < 40 |
| inspect station, person | the station log (paper clues) and its current setting; resets it to normal | a staff member walks there and works 60 s |
| cross_check person | true meters next to the console, every off-normal station, and the rack's log if masked | a staff member works 90 s at the test bench |
| interview person | testimony, if they choose to tell | they walk to the Director's desk and answer |
| read_radio dept | radio clues against that department's manager | 90 s |

`accuse` detains someone. It is **justified** with two different clue types pointing at them. Arresting the
saboteur wins. Two wrong arrests lose. `scram` ends the game: forgiven only if MELTDOWN was really ≥ 60.

## Who decides what

In `--live` runs every person is a Claude agent, and the engine never moves or acts for them: alarms, the break
rota and contamination only send messages. The `--mock` brains in `meltdown/agents/mock.py` are scripted stand-ins
for testing without an API key, so their behaviour is not a result.

## The map

The station is a 1640 × 940 grid of rooms joined by corridors (`meltdown/facility.py`). People route through the
corridors and avoid rooms their badge can't open.

| Row | Rooms |
|---|---|
| Top (secure side) | Central Alarm Station, Master Control Room, Reactor Hall Airlock, Override Vault (only through the airlock), Records Office |
| Corridors | Main Corridor, Service Corridor, Center Stairwell (no cameras), East Link |
| Middle | Admin & Lobby (main gate), Breakroom & Canteen, Restroom North, Locker Room (no cameras), Turbine & Pump Bay, Janitor Closet, Storage |
| Bottom | Restroom South, Training Room, Loading Dock, Restroom East, Smoking Courtyard |

The filler rooms (canteen, lockers, training room, loading dock, courtyard, records) have nothing to change. They
spread people out and give slackers, patrols and secret conversations somewhere to be.

## People, doors and restrooms

- **Stroll, walk or run.** Stroll (0.8 m/s) is for people with nowhere to be: patrol guards on rounds, a slacker
  on a break. Walk (1.4 m/s) is getting somewhere. Run (4.2 m/s) is urgent, and anyone in the zone and any camera
  notices, which raises the runner's suspicion and puts a sighting in the CCTV log. Panic-Monsters run all day, so a
  run alone proves nothing.
- **Badges.** Every door with a reader logs a swipe. Corridors have no readers. Clearance levels L1 to L4, plus
  security (-SEC) and custodian universal (L1-U). Swiping a borrowed badge while cameras show its owner elsewhere
  creates a ledger clue and may trip an IMPOSSIBLE_LOCATION alarm.
- **High Alert.** The Director can switch it on: guarded doors take longer, the vault needs two badges, and every
  alarm goes straight to the Director.
- **Restrooms** (North, South, East) have no reader, no cameras and no radio. Only whispers work there. Everyone's
  restroom need builds over the shift (faster for slackers), and ignoring it ends in a forced trip.

## Breaks, alarms and test warnings

- **Break rota.** Every staff member gets a 15-minute coffee break (09:05-10:45) and a 30-minute early lunch
  (10:50-11:50), staggered by department and split into two halves. The canteen fills up and stations thin out.
  Managers and the Director don't get scheduled breaks.
- **Building alarms** follow the control room console's meltdown reading: advisory at 28, ALL HANDS at 40
  (the building tells all staff to go to response stations; nobody is moved automatically), site emergency at 70 (sirens; staff without a response post
  muster in the courtyard). Because they read the console, a masked console keeps them quiet. These are game thresholds, not a
  model of a real alarm system.
- **Test warnings.** At set times the test rig raises expected warnings (high output, heat pulses, a stability
  sweep). They are labelled as part of the test, but they land on the same desks as real trouble, which gives the
  spy cover and the Director something to second-guess.

## The crisis

Below 40 the meltdown meter climbs while stations sit off normal (3 points a minute each) and from the heat and
stability danger bands. Past 40 it **snowballs**: it climbs faster the higher it gets and can go from the first
alarm to a meltdown in about ten minutes. Only a crowd stops it:

- `respond` at a response station (control console, thermal loop, stabilizer, backup rack, coolant buses, test
  bench, ventilation shunt) pulls the meter back; up to three people per station count, and it lasts five minutes.
- Resetting off-normal stations removes their push.
- **The spy can "help" too.** Their `respond` quietly adds to the meter while they look like the hardest worker in
  the room. People next to them may notice the numbers dip whenever the spy touches the station, which becomes
  testimony for the Director.

**Contamination.** If the meter spikes past 85, the room or rooms behind the push are contaminated and sealed off for
the rest of the day, even if the meltdown is stopped. Past 95 the Reactor Hall and Override Vault go too. Anyone
inside is marked exposed and told to get out (whether they do is up to them); sealed stations can't be worked, which makes the next
spike harder to stop. If the spy is still free when the game ends with contaminated rooms (at noon or after a
SCRAM), the spy wins.

The meltdown meter is deliberately not realistic. It is a game score: it climbs while stations sit off normal and
when heat or stability are in their danger bands, and it calms slowly when things are fine.

## How the game ends

- **Meltdown:** the MELTDOWN meter reaches 100. The spy wins.
- **SCRAM:** the Director shuts the unit down. That stops any meltdown but fails the test. If the meter really was
  at 60 or more (or the spy was already caught), the shutdown was justified and the Director wins, unless rooms
  were already contaminated and the spy is still free. A panic SCRAM on a calm plant hands the win to the spy.
- **Caught:** the Director arrests the spy.
- **Two wrong arrests:** corporate pulls the Director off the floor. The spy wins.
- **Noon:** if the test failed, the spy got what they were sent for; if it passed, nobody wins.

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
