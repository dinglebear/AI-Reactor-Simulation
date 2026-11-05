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
| audit_badges zone | the raw swipes at that room's door, last 30 min (no conclusions: compare them with the cameras yourself) | 1 min |
| pull_cctv zone | cctv clues in that zone, run sightings, and who came in through the door and when (someone on camera with no swipe of their own badge is for the Director to spot) | 1 min; footage may be corrupted if security health < 40 |
| inspect station, person | the station log (paper clues) and its current setting; resets it to normal | a staff member walks there and works 60 s |
| cross_check person | true meters next to the console, every off-normal station, and the rack's log if masked | a staff member works 90 s at the test bench |
| interview person | testimony, if they choose to tell | they walk to the Director's desk and answer |
| read_radio channel | radio clues against that department's manager, plus the handset log: whose radio was tuned to this channel (RX, HY, IE, SF, exec or security) without belonging there | 90 s |
| search person | CAS locates them within a minute (cameras, or their badge's last swipe if they're off camera), and the nearest guard who can get there goes to check their pockets: borrowed badges or things they took become a **physical** clue | the call goes out on the security channel, so anyone on it, or listening in, hears who is wanted |
| search zone | a guard sweeps the room for anything hidden (80% per stash); finds become physical clues against whoever was in the room when it was hidden | 90 s once there |

The Security manager can also call `search` (one investigation every 10 minutes).

`accuse` detains someone. It is **justified** with two different clue types pointing at them. Arresting the
saboteur wins. Two wrong arrests lose. `scram` ends the game: forgiven only if MELTDOWN was really ≥ 60.

## Sneaking: eavesdropping and hiding things (anyone)

| Action | What it does | How it gets you caught |
|---|---|---|
| listen_in channel | your radio also plays another channel (a department, exec or security) for 10 minutes | people next to you may hear the wrong chatter (testimony); radios log which channel each handset is on, so `read_radio` on that channel shows you (radio clue). Restrooms have no signal. |
| hide | stash borrowed badges (`arg = badges`) or anything else (described in `text`) where you stand | cameras in the room (cctv clue) and anyone nearby (testimony). Off-camera rooms are safer, but a sweep can still find it, and then everyone who was in the room then is a suspect |
| retrieve | take back what you hid in this room | |
| rummage | look around the room for anything someone hid | finds become physical clues you hold, and tell the Director if interviewed |

## The spy's contraband: an RFID badge copier

The spy owns a badge copier. It starts hidden in the Locker Room (no cameras), and the spy has to `retrieve` it
before using it. `clone_badge` copies the badge of someone in the same room. The owner keeps theirs and doesn't
know. Doors then open for the copy, and the ledger logs the owner's name (an IMPOSSIBLE_LOCATION ledger clue if the
owner is on camera somewhere else). The moment of copying may be seen by people nearby or caught on camera. If the
copier is found in a pocket check, it is confiscated along with every copy (a physical clue). A room sweep or a
rummage can also find it where it's hidden, so the spy decides when to carry it and when to stash it. Only the spy
is told the copier exists.

## Deleting footage

The spy can `wipe_cctv` a zone from the Director's desk or the alarm station desk, but only if nobody else is
at that terminal. It deletes the last 30 minutes of that zone's footage: camera clues and door-camera entries. The
camera system keeps an audit trail of the deletion, which names everyone in the room at the time as suspects, and
it shows up the next time someone pulls that zone's cameras. People in the room may also see the spy on the camera
menus.

## The spy's read on people

The spy was a manager for years and trained to read people, so their prompt has a private dossier: what each
person notices, wants and gives way on (by personality), the Director's and managers' pressure points, and a
handful of the grudges and soft spots between coworkers. It is information, not a plan.

## The Director's day

The Director organises the certification test: she runs the schedule, watches every stage from the control room
(the game counts the minutes she's there), and owes corporate a written `test_report` for each stage (at least
300 characters; it ties her up for about 5 minutes). Her observation shows each stage's watched minutes and whether
the report is filed.

She is NOT told a spy exists. All she has is the CEO's 08:02 message: HR flagged weird encrypted traffic from a
mid-level terminal; handle it quietly, don't spook anyone, don't stop the test.

`lockdown on` stops all work (no system upkeep) and seals every door with a reader except for the Director and the
Security manager. Turning it on needs a full page (600+ characters) of reasons, which goes straight to the CEO, who
is furious. `lockdown off` lifts it.

## Chores, following, and the janitor

Everyone except the Director has ordinary chores for the day (log readings, walk down the buses, calibration
checks, patrol rounds, cleaning). They're listed with a station and a due time, and `chore` does one while
standing at its station (about 3 minutes). Nobody is made to do them; overdue ones just show as OVERDUE.

Anyone can `follow` someone for up to 10 minutes: they keep going where that person goes and are told what the
person is doing in each room. The person being followed may get the feeling someone is behind them.

Earl Mabry, the custodian, is a 68-year-old Navy veteran with thirty years on site: hard-working, sharp, observant
and willing to follow someone himself. The spy's dossier marks him as the real threat.

Restrooms have radio now (still no cameras and no badge reader).

## Who knows about the spy

Only the Director and the spy are told a spy may exist. The shared rules every agent reads describe a long, noisy
test day and nothing more; managers and staff only learn of a spy if someone tells them (the Director, a rumour, an
arrest). The CEO's HR tip goes to the Director alone.

## Game modes (`--scenario`)

| Mode | Who is the spy | What changes |
|---|---|---|
| `classic` (default) | one department manager | the original game |
| `pair` | two random staff members (Haiku), never Earl | each knows the other; they share stashed contraband; the Director must arrest both to win |
| `director` | the Director | her goal is to turn the crew against each other and sink the test (a failed test, MELTDOWN, or two wrong arrests all count); she keeps her lockdown and search powers and gets the spy's tools. Ruth (security chief) can take a case to corporate with `report_director`, which works only with two kinds of evidence against her (20-minute cooldown) |
| `phantom` | nobody | corporate security privately tells the Director one of the four managers is a spy. Any arrest is a wrongful one; reaching noon with no arrests is the clean result |

Earl (the janitor) can never be the spy in any mode. Run one with, for example,
`python -m meltdown.run --claude-code --scenario pair`.

## Rumours and reputations

The rules tell everyone that people gossip, and that a rumour is worth what its source is worth. The Chaos
Prankster is encouraged to make up rumours of their own. Reputations ("funny, but you can't believe half of what
they say", "cries wolf") are in other people's opinion lists, so a report from a known fibber or a panicker may be
taken with a grain of salt, even on the day it's true. Nothing in the engine forces anyone to believe, spread or
dismiss a rumour.

## People: motives, opinions and the bonus

Corporate has promised everyone a cash bonus if Unit 4 passes all three stages, and a SCRAM or failed stage means
no bonus. Each person has a motive (`MOTIVE` in `meltdown/cast.py`): some want the bonus badly, some put safety
first, some want a promotion, some protect their team, some just want to go home. The four managers each have their
own persona; the spy's motive is only their cover.

Everyone starts with opinions of about a dozen coworkers: their department, the managers, the Director and a few
others. Most opinions follow the other person's reputation ("a yes-man", "rude and loud, but honest", "very kind"),
and about a third are personal history ("they took credit for your work once", "you have lunch together"), drawn
fresh from the game seed. Yes-men, people pleasers and brown-nosers exist, and nobody is told who to ask.

None of this scripts anything. The prompt only tells each agent what they want and what they think of people, and
that they can agree, argue, push back on a boss or go along. Whether a scare turns into an argument between the
bonus crowd and the safety crowd is up to the models. The viewer shows each person's motive and opinions on their
profile.

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
- **Test alarms.** At set times the test rig sets off alarms on purpose (high output, heat pulses, a stability
  sweep). Staff hear them as ordinary building alarms. Managers know the test plan, and the Director has the exact
  schedule and a site PA (`pa` channel, Director only, heard everywhere including restrooms). Whether the floor is
  warned is the Director's call, and real trouble can hide behind a test alarm.

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
early when someone addresses them, an alarm fires, or they arrive somewhere that matters. `--tempo fast` halves
those gaps and `--tempo max` cuts them to about a third (staff every ~60 s), for when there's plan or API budget
to spare: everyone reacts faster, at 2-3x the calls per game minute. In live mode all agents
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
