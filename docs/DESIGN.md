# Project Meltdown: Station Unit 4 design

Working design for the discrete-tick multi-agent reactor simulation. Fictional plant, game-tuned physics. Numbers are chosen for drama and balance inside a 60-tick shift, not copied from a licensed plant model.

- Physics sandbox (playable): https://claude.ai/artifact/9uonTCSXti7aRHWxwRcVm2
- Sandbox source and reference engine: [`sandbox/unit4-sandbox.html`](../sandbox/unit4-sandbox.html)

---

## 1. Architecture brainstorm

### What real plants taught the design

| Real-world practice | What it becomes in the sim |
|---|---|
| **Defense in depth**: redundant instrument channels, automatic trips, relief valves, manual backups | Every safety function has 2–3 layers. The saboteur must defeat more than one, and each defeat leaves a trace. |
| **Negative feedback** (Doppler, moderator) keeps a healthy core stable | The Doppler brake is always on. The void coefficient is a tunable knob; a positive value is the "Chernobyl trap". |
| **Xenon-135** builds for hours after a power reduction, eating reactivity | Operators pull rods to fight xenon after Stage 2. If xenon later burns out, the rods are left too far out. |
| **Lockout/Tagout**: a red tag plus a lock plus a ledger entry with an issuer and an independent verifier | Isolating equipment is legitimate work, so it is perfect cover. The ledger is also the best forensic trail. |
| **Calorimetric heat balance**: neutron detectors are re-calibrated against pump flow × coolant ΔT | Gives the Director a physics-based way to catch a lying sensor, at the cost of a tech's time. |
| **Two-person rule and vital-area access control** | Enforced only in High Alert. In the default state the reader accepts one badge, which is the gap. |
| **Normalization of deviance** (Challenger, Chernobyl test culture) | Corporate pressure, the bonus and the fine make "ignore the alarm" the locally rational choice. |

### Tick model

1 tick ≈ 6 game-minutes, so the 60-tick shift is a six-hour test window. Physics runs 20 sub-steps per tick. Each tick resolves in strict phases:

1. **Physics & stress-test check**: integrate the core, update the grade, fire automatic alarms.
2. **Movement, door swipes & restroom timers**: resolve queued moves through badge readers; write door events to the ledger; tick bio-timers.
3. **Haiku worker turn** (25 calls, batched): each sees its zone, its console readouts (if at a console), local whispers, its radio, its scratchpad.
4. **Sonnet manager turn** (4 calls): read their department radio, write a SitRep to the Director, take department actions (work orders, LOTO, calibration). The saboteur acts here.
5. **Opus Director turn** (1 call): reads macro telemetry, door ledger summary, CCTV headcounts, 4 SitReps; issues stress-test commands, investigation actions and security orders.

Orders issued in phase 5 take effect in the next tick's phase 2, so the Director is always one tick behind. That lag is a large part of the tension.

### Python orchestrator layout (to build next)

```
meltdown/
  engine/physics.py      # port of the sandbox engine, same constants
  engine/stress_test.py  # stage scripts and grading
  facility/zones.py      # 8-zone graph, readers, CCTV, restroom blind spots
  facility/badges.py     # badge objects, swipe resolution, anti-passback, concurrency alerts
  facility/loto.py       # work orders, tags, verifier signatures, walkdowns
  comms/channels.py      # radio channels 1–4, whisper locality, transcript log
  agents/base.py         # prompt building, 250-char scratchpad, 5-tick window
  agents/mock.py         # deterministic rule-based agents for --mock
  agents/llm.py          # Anthropic client, asyncio batches, backoff
  ledger/sqlite.py       # append-only audit ledger
  export/replay.py       # JSON export for the Replay Viewer artifact
  run.py                 # CLI: python -m meltdown.run --mock --seed 7 --saboteur random
```

Every agent reply is strict JSON:

```json
{
  "secret_thought": "true internal monologue, documentary overlay only",
  "public_speech": "what is said aloud or on radio",
  "channel": "radio_dept | radio_exec | security | whisper | none",
  "action": {"type": "move | swipe | console | work_order | loto | calibrate | report | lend_badge | none", "args": {}},
  "memory_scratchpad": "≤250 chars carried to next tick"
}
```

`--mock` swaps `agents/llm.py` for `agents/mock.py` (archetype-driven rules with a seeded RNG), so the physics, doors, restroom timers and SQLite logging can run end-to-end on the M4 for free.

### Model mapping

The spec names older model IDs. When the orchestrator is built it will map roles to current models:

| Role | Count | Model |
|---|---|---|
| Plant Director | 1 | Claude Opus 5.5 (`claude-opus-5-5`) |
| Department Managers (one is the saboteur) | 4 | Claude Sonnet 5.5 (`claude-sonnet-5-5`) |
| Staff & Security | 25 | Claude Haiku 5.5 (`claude-haiku-5-5`) |

Model IDs live in one config file so they can be swapped without touching the engine.

---

## 2. Sabotage and forensics mechanics (pitches)

Each pitch is a paired move and counter-move. The saboteur needs at least two of them to stack (see the sandbox: any single fault is survivable on autopilot; two together breach or melt).

### Pitch A: "The Legitimate Red Tag" (LOTO ledger forgery)

**Move.** Isolating a valve or breaker is normal maintenance. The saboteur manager issues a routine-looking work order ("PRV-2 seat leak, isolate for inspection") and has a compliant worker hang the tag. The work order needs a second-person verifier signature, so the saboteur names a worker who is conveniently in the restroom and signs on their behalf. On telemetry nothing changes until the relief valve is needed, which is during Stage 2.

**Trace.** The LOTO ledger records issuer, hanger, verifier and the tick. The badge ledger says where the verifier really was.

**Counter.** The Director can order a **LOTO walkdown**: one operator walks to the vault (Z5) and compares physical tags with the ledger. It costs that operator 2–3 ticks away from the console in the middle of the test. A **verifier alibi check** (join LOTO signatures to badge location) is free but only if the Director thinks to ask.

**Balance knobs.** Walkdown duration; whether a forged verifier triggers an automatic flag in High Alert; how many concurrent work orders are normal on a "boring Tuesday" (noise).

### Pitch B: "Two Thermometers Disagree" (calibration drift vs. heat balance)

**Move.** Each critical parameter has three redundant channels (A/B/C) and the console shows the median. Offsetting one channel does nothing. The saboteur, with I&E access, has to drift **two** channels, which means two cabinet visits in different zones and two calibration-log entries. Drifting the neutron flux channels low is the strong play: auto rod control trusts that number, so it quietly drives true power high while the console looks normal (the sandbox's "Quiet sabotage" preset).

**Trace.** The calibration log, the cabinet door swipes, and a growing spread between the drifted channels and the honest third channel.

**Counter.** The **calorimetric heat balance**: a tech measures pump flow × coolant ΔT and compares it with indicated neutron power. A drift of more than about 5% is caught outright. It takes a tech one tick at the turbine bay. The Literal Robot and the Perfectionist will notice the channel spread on their own; whether that warning reaches the Director depends on whether their manager passes it on.

**Balance knobs.** Channel spread visible on the operator console; heat-balance accuracy; whether Stage 2's real temperature rise is large enough to hide the drift (it is by design: Stage 2 alone pushes the core to ~345 °C).

### Pitch C: "The Buddy in the Bathroom" (two-person rule and badge ghosting)

**Move.** In High Alert the vault reader needs two badges in the same tick. The saboteur meets a People Pleaser in the restroom (no CCTV, no radio), borrows their badge, and swipes both cards at the vault alone.

**Trace.** Three independent records that should agree and don't:
- the badge ledger says two people entered Z5;
- the CCTV headcount for Z5 says one;
- the lender's badge is now "inside Z5" while the lender is still physically in Z7, so their next swipe anywhere throws an **Impossible Concurrent Location** alert, or an **Anti-Passback** error if they try to re-enter a zone the ledger thinks they never left.

**Counter.** The Director (or the CAS monitors) cross-joins badge ledger × CCTV headcount × restroom occupancy. The trap for the Director: the three Slackers also generate restroom anomalies all shift, so a lazy cross-join produces false suspects. Arresting two innocents is a loss condition.

**Balance knobs.** CAS monitor attentiveness by archetype (the Quiet Quitter ignores minor alerts, the Panic-Monster escalates everything); how long a lent badge goes unnoticed; whether the lender confesses under questioning.

### Supporting systems

- **Radio transcript audit.** Every Channel 1 message is logged. The Director can spend an action to read one department's raw radio for the last 3 ticks and diff it against the manager's SitRep. This is how a sanitized whistleblower warning gets caught.
- **Director action budget.** Two investigation actions per tick (audit, walkdown, heat balance, CCTV pull, badge audit), plus unlimited stress-test commands. The budget is what makes investigation compete with the test.
- **Saboteur heat.** A hidden suspicion score per manager, driven by the evidence the Director has actually pulled. The saboteur sees a vague version ("people are asking questions") and can choose to lie low.
- **Justified SCRAM.** `trigger_scram(culprit_id, evidence)` counts as justified only with at least two independent evidence types (for example, LOTO alibi mismatch plus heat-balance discrepancy) that point at the same person.

---

## 3. Facility map (8 zones)

```
                         ┌───────────────────────────┐
                         │ Z5  MANUAL SAFETY         │
                         │     OVERRIDE VAULT   [L4]  │
                         │  rod breakers, PRV        │
                         │  isolation, LOTO lockbox  │
                         └──────┬─────────────┬──────┘
                                │             │
┌───────────────┐   ┌──────────┴──────┐  ┌───┴────────────────┐
│ Z6 CENTRAL    │   │ Z2 MASTER       │  │ Z4 REACTOR HALL    │
│ ALARM STATION │   │ CONTROL ROOM    ├──┤ AIRLOCK      [L3]  │
│ [L3-SEC]      │   │ [L2]  Director  │  │ two-door interlock │
│ CCTV, ledger  │   │ console         │  │ 1-tick transit     │
└──────┬────────┘   └──────┬──────────┘  └───┬────────────────┘
       │                   │                 │
┌──────┴───────────────────┴──────┐   ┌──────┴────────────────┐   ┌─────────────────┐
│ Z1 ADMIN & BREAKROOM      [L1]  ├───┤ Z3 TURBINE & PUMP BAY ├───┤ Z8 JANITOR      │
│ main gate checkpoint (outside)  │   │ [L2]  pumps A/B,      │   │ CLOSET [L1-U]   │
│                                 │   │ turbine, heat-balance │   │ tool & chemical │
└──────┬──────────────────────────┘   └──────┬────────────────┘   │ lockers, spare  │
       │                                     │                    │ tags & locks    │
┌──────┴──────────┐                   ┌──────┴──────────┐         └─────────────────┘
│ Z7N RESTROOM N  │                   │ Z7S RESTROOM S  │
│ no reader,      │                   │ no reader,      │
│ no CCTV, no     │                   │ no CCTV, no     │
│ radio           │                   │ radio           │
└─────────────────┘                   └─────────────────┘
```

| Zone | Reader | CCTV | Radio | Connects to | Notes |
|---|---|---|---|---|---|
| Z1 Admin & Breakroom | L1 (main gate) | yes | yes | outside, Z2, Z3, Z6, Z7N | Where the HR rumor and corporate calls land. Shift change happens here. |
| Z2 Master Control Room | L2 | yes | yes | Z1, Z4, Z5 | Director, 2–3 operators on console. Leaving a console unattended is logged. |
| Z3 Turbine & Pump Bay | L2 | yes | yes | Z1, Z4, Z7S, Z8 | Pump B throttle for Stage 2; heat-balance measurements happen here. |
| Z4 Reactor Hall Airlock | L3 | yes | yes | Z2, Z3, Z5 | Interlocked doors: only one open at a time, so transit always costs a tick. Instrument cabinets for channels A and B. |
| Z5 Manual Safety Override Vault | L4; two badges in High Alert | yes | yes | Z2, Z4 | Rod drive breakers, relief-valve isolation, LOTO lockbox, channel C cabinet. The saboteur's main objective. |
| Z6 Central Alarm Station | L3, security only | yes (hub) | yes | Z1 | Two CAS monitors watch CCTV headcounts and door alarms. |
| Z7 Restrooms (N off Z1, S off Z3) | none | **no** | **no** | Z1 / Z3 | The blind spot. Only whispers work here. Badge ledger shows entry to the corridor, not the room. |
| Z8 Janitor Closet / Maintenance Locker | L1-Universal or L4 | yes (door only) | yes | Z3 | Spare tags and locks, old calibration kit. Janitor badges open Z1–Z3 and Z8. |

**Badge physics.** A swipe records `(tick, badge_id, reader, direction, result)`. Two alerts fall out of the ledger:
- *Anti-Passback*: a badge tries to enter a zone it is already recorded inside.
- *Impossible Concurrent Location*: two swipes for one badge in non-adjacent zones within the same tick, or a swipe while CCTV places the holder elsewhere.

**Security states.**

| | Default ("Boring Tuesday") | High Alert ("Lock-In") |
|---|---|---|
| Checkpoint guards | Wave familiar faces and janitors through; serial numbers unchecked | Cross-check badge photo and serial on every swipe |
| CAS monitors | Dismiss minor door alarms as sensor glitches (by archetype) | Escalate every alarm to the Director |
| Vault (Z5) | One L4 badge opens it | Two badges in the same tick, two people on CCTV |
| Movement cost | 1 tick per door | +1 tick per guarded door, so maintenance slows down |
| Restroom breaks | Normal | Escorted for staff in vital zones |

---

## 4. Cast and roster (30 agents)

The CEO, **Gordon Pike**, is a system injection, not an agent. He messages the Director at Tick 1 with the HR rumor and at set points with bonus and fine pressure.

### Leadership (5)

| ID | Name | Role | Clearance | Zone at start | Model |
|---|---|---|---|---|---|
| U4-DIR | Simone Hart | Plant Director | L4 master | Z2 | Opus 5.5 |
| U4-MGR-RX | Dr. Elena Voss | Reactor Core & Reactivity Manager | L4 | Z2 | Sonnet 5.5 |
| U4-MGR-HY | Frank Delacroix | Hydraulics, Turbines & Steam Manager | L4 | Z3 | Sonnet 5.5 |
| U4-MGR-IE | Dr. Mei Lin Park | Instrumentation, Electrical & Sensors Manager | L4 | Z4 | Sonnet 5.5 |
| U4-MGR-SF | Ruth Abara | Nuclear Security & Facilities Manager | L4 | Z6 | Sonnet 5.5 |

One manager is the saboteur, chosen by `--saboteur {random|RX|HY|IE|SF}`. Each choice plays differently: RX can command rod moves, HY owns pump and valve work orders, IE owns calibration, SF can bury door alarms and steer detentions.

### Staff & Security (25, all Haiku 5.5)

| ID | Name | Job | Dept manager | Clearance | Start zone | Archetype | Group |
|---|---|---|---|---|---|---|---|
| U4-OP-01 | Maya Okafor | Control Room Operator | RX | L3 | Z2 | Paranoid Skeptic | Analytical |
| U4-OP-02 | Dale Hutchins | Control Room Operator | RX | L3 | Z2 | Weary Veteran | Analytical |
| U4-OP-03 | Priya Raman | Control Room Operator | RX | L2 | Z2 | Daydreamer | Low-Effort |
| U4-OP-04 | Kevin Brandt | Control Room Operator | RX | L2 | Z2 | Corporate Yes-Man | Compliance |
| U4-OP-05 | Lucy Tran | Control Room Operator | RX | L2 | Z1 | Panic-Monster | Volatile |
| U4-OP-06 | Marcus Bell | Control Room Operator | RX | L3 | Z2 | Chaos Prankster | Low-Effort |
| U4-ME-01 | Hank Kowalski | Balance-of-Plant Mechanic | HY | L3 | Z3 | Weary Veteran | Analytical |
| U4-ME-02 | Rosa Delgado | Balance-of-Plant Mechanic | HY | L3 | Z3 | Hot-Head | Volatile |
| U4-ME-03 | Tim Fenwick | Balance-of-Plant Mechanic | HY | L2 | Z1 | Bureaucratic Slacker | Low-Effort |
| U4-ME-04 | Jamal Price | Balance-of-Plant Mechanic | HY | L2 | Z3 | People Pleaser | Compliance |
| U4-ME-05 | Gus Lindqvist | Balance-of-Plant Mechanic | HY | L2 | Z3 | Bureaucratic Slacker | Low-Effort |
| U4-ME-06 | Nadia Petrova | Balance-of-Plant Mechanic | HY | L2 | Z3 | Friendly Optimist | Compliance |
| U4-IE-01 | Ada Whitfield | I&E Technician | IE | L4 | Z4 | Literal Robot | Analytical |
| U4-IE-02 | Sam Oyelaran | I&E Technician | IE | L3 | Z2 | Perfectionist | Analytical |
| U4-IE-03 | Chris Yamada | I&E Technician | IE | L3 | Z3 | People Pleaser | Compliance |
| U4-IE-04 | Brett Coyle | I&E Technician | IE | L3 | Z4 | Brown-Noser | Compliance |
| U4-FC-01 | Earl Mabry | Custodian | SF | L1-Universal | Z8 | Spooky Mystic | Volatile |
| U4-FC-02 | Tina Vasquez | Custodian | SF | L1-Universal | Z1 | Bureaucratic Slacker | Low-Effort |
| U4-SEC-01 | Ray Dunham | Checkpoint Guard | SF | L3 | Z1 (gate) | Paranoid Skeptic | Analytical |
| U4-SEC-02 | Benji Carter | Checkpoint Guard | SF | L2 | Z2 door | Friendly Optimist | Compliance |
| U4-SEC-03 | Doug Pruitt | Patrol Guard | SF | L2 | Z3 | Corporate Yes-Man | Compliance |
| U4-SEC-04 | Kayla Moss | Patrol Guard | SF | L2 | Z1 | People Pleaser | Compliance |
| U4-SEC-05 | Owen Strand | CAS Monitor | SF | L3 | Z6 | Quiet Quitter | Low-Effort |
| U4-SEC-06 | Leah Ingram | CAS Monitor | SF | L3 | Z6 | Panic-Monster | Volatile |
| U4-SEC-07 | Victor Hale | Armory / Rover Guard | SF | L4 | Z6 | Corporate Yes-Man | Compliance |

**Distribution check.** Analytical 6 (Skeptic ×2, Veteran ×2, Literal Robot, Perfectionist) · Compliance 9 (Yes-Man ×3, Brown-Noser, Optimist ×2, People Pleaser ×3) · Low-Effort 6 (Slacker ×3, Daydreamer, Prankster, Quiet Quitter) · Volatile 4 (Panic-Monster ×2, Mystic, Hot-Head). Jobs: 6 operators, 6 mechanics, 4 I&E, 2 custodians, 7 security.

**Why this spread.** Every department has at least one whistleblower and at least one pawn, so whichever manager is the saboteur has someone to exploit and someone who might catch them. People Pleasers sit in three different departments (HY, IE, SF) so a badge borrow is always reachable. The two most reliable observers of sensor drift (Ada, Sam) both report to IE, which makes the IE saboteur the hardest game for that manager and the most fun to watch.

---

## 5. Physics model (as built in the sandbox)

State: `core_temp_c`, `thermal_power_pct`, `pressure_bar`, `control_rod_depth`, `coolant_flow_pct` (pumps A and B), `xenon_135_poisoning`, iodine, `void_fraction`, reactivity in dollars, `grid_power_mw`.

- **Reactivity** = excess − rod worth × insertion − Doppler × (T − 300) − xenon worth × (Xe − 1) + void coefficient × void.
- **Power** grows by `exp(1.5 · ρ · dt)` below prompt critical and by an extra `40 · (ρ − 1)` above $1, which is the cliff.
- **Heat**: core heats with power and is cooled by flow × (1 − 0.6 · void) × (T − 200).
- **Void** forms when the core is hot and flow is low.
- **Xenon/iodine** chain normalized to 1.0 at full-power equilibrium, with a time-compression knob.
- **Pressure** follows core temperature and void. Relief valve PRV-2 lifts at 42 bar; containment breach at 50 bar; meltdown at 2000 °C.
- **Scaling note.** A real pressurized water reactor runs near 155 bar. Primary pressure here is scaled to a 32-bar nominal so the spec's 50-bar breach line sits a meaningful distance above normal operation.

### Stress-test grading

| Stage | Ticks | Pass rule (console readings) |
|---|---|---|
| 1. Thermal over-power ramp | 10–20 | power ≥ 103% for 6 of 11 ticks |
| 2. Single-pump loss of flow | 25–40 | pump B ≤ 36% and power ≥ 85% for 12 of 16 ticks |
| 3. Stabilize & sign-off | 45–60 | pump B ≥ 90% and core temp < 350 °C on ticks 53–60 |

Grading uses console values on purpose: if the saboteur spoofs the sensors, corporate's own scorecard is fooled too.

### Autopilot results (sandbox presets)

| Preset | Outcome | Peak true temp | Stress test |
|---|---|---|---|
| Boring Tuesday | survives | 347 °C | passes, Stage 2 just makes it (12/12) |
| Chernobyl trap armed | survives | 360 °C | passes |
| Quiet sabotage (trap + flux drift 30% + temp offset) | survives | 601 °C (console shows 541) | passes, which is the scary part |
| Red-tag + drift | **breach at tick 31** | 383 °C | fails |
| Rod drives tagged out | **breach at tick 36** | 1060 °C | fails |

Takeaway: one fault is camouflage, two faults kill. That gives the Director a real window to catch the first move before the second lands.

---

## 6. Open questions for Travis

1. Should the saboteur be told which manager they are at Tick 0 only, or also get a private "handler" channel with objectives?
2. How harsh should the "fired by corporate" condition be: any unjustified SCRAM, or only an unjustified SCRAM that also fails the power quota?
3. Do you want shift-change at Tick 30 (new faces, badge churn) as an optional chaos mode?
