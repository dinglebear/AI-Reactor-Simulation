"""What every agent sees (prompts) and what it may answer (the decision schema)."""
from __future__ import annotations

from .. import cast as C
from .. import facility as F
from ..config import hhmm, SCRATCHPAD_CHARS, DIRECTOR_INVESTIGATIONS_PER_TURN
from ..plant import STAGES

CHANNELS = ["none", "say", "whisper", "radio", "exec", "security"]

RESPOND_TEXT = ("crisis response: work your station flat out. Counts only at a response station "
                "(control_console, primary_thermal_loop, stabilizer_override, backup_rack, coolant_bus_a, coolant_bus_b, "
                "test_bench, ventilation_shunt) and only during a crisis. Lasts about 5 minutes; repeat it.")

STAFF_ACTIONS = {
    "move": "walk to a station (or a zone id). target = station name. Doors log your badge. pace: 'stroll' (no hurry, "
            "e.g. a patrol or a break), 'walk' (getting somewhere), 'run' (urgent; people notice running).",
    "interact": "change a station's setting. target = station, arg = setting. You must be standing at that station. "
                "If someone else is working at it, they stop you and raise the alarm.",
    "work": "stay at your current station and keep its system healthy",
    "restroom": "go to the nearest restroom (no cameras, no radio, whispers only)",
    "wait": "do nothing this turn",
    "lend_badge": "answer a badge request. arg = yes or no",
    "answer": "answer the Director in an interview (you must be at the Director's desk). arg = tell or withhold; "
              "text = what you say",
}
STAFF_ACTIONS["respond"] = RESPOND_TEXT
MANAGER_ACTIONS = dict(STAFF_ACTIONS, order="send one of your staff somewhere. target = person id, arg = station name")
SECURITY_MANAGER_EXTRA = {
    "audit_badges": "review the badge ledger for contradictions",
    "pull_cctv": "review camera footage. target = zone id (Z1..Z8)",
}
SABOTEUR_EXTRA = {
    "respond": RESPOND_TEXT + " SECRET: when YOU respond, it quietly makes the crisis worse instead of better, while "
               "looking like help. People working next to you may notice the numbers drop whenever you touch it.",
    "ask_badge": "quietly ask someone in your zone to lend you their badge. target = person id, text = your excuse",
    "return_badge": "hand back borrowed badges to their owners in the same zone",
    "message_handler": "send a private message to your handler outside the plant. text = message. The game pauses "
                       "until they reply.",
}
DIRECTOR_ACTIONS = {
    "set_output": "set the control room's output target. arg = number 0-110, or 'auto' to follow the test schedule",
    "high_alert": "turn High Alert on or off. arg = on/off. Slows doors, vault needs two badges, every alarm comes "
                  "to you",
    "audit_badges": "INVESTIGATION. Review the badge ledger for contradictions (2 min)",
    "pull_cctv": "INVESTIGATION. Review a zone's cameras (1 min). target = zone id",
    "inspect": "INVESTIGATION. Send someone to a station: they read its change log and reset it to normal. "
               "target = station, arg = person id",
    "cross_check": "INVESTIGATION. Send someone to the test bench to compare true readings with the console. "
                   "arg = person id",
    "interview": "INVESTIGATION. Summon a person to your desk for questions. target = person id",
    "read_radio": "INVESTIGATION. Read a department's raw radio traffic. target = RX, HY, IE or SF",
    "accuse": "arrest someone as the saboteur. target = person id, text = your case. Justified only with two "
              "different clue types pointing at them. Two wrong arrests and you lose.",
    "scram": "shut the unit down. Ends the game; the test fails. Corporate only forgives it if the danger was real.",
    "message_corporate": "send a message to CEO Gordon Pike. text = message. The game pauses until he replies.",
    "order": "send anyone somewhere. target = person id, arg = station name",
    "wait": "do nothing this turn",
}
STATIONS_TEXT = "\n".join(f"- {k} ({F.STATIONS[k]['label']}, {F.STATIONS[k]['zone']}): {', '.join(v['options'])}; "
                          f"normal = {v['nominal']}. {v['effect']}" for k, v in F.SETTINGS.items())


def actions_for(p) -> dict:
    if p.tier == "director":
        return DIRECTOR_ACTIONS
    acts = dict(MANAGER_ACTIONS if p.tier == "manager" else STAFF_ACTIONS)
    if p.id == "U4-MGR-SF":
        acts.update(SECURITY_MANAGER_EXTRA)
    if p.saboteur:
        acts.update(SABOTEUR_EXTRA)
    return acts


def decision_schema(action_types: list[str]) -> dict:
    act = {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": action_types},
            "target": {"type": "string"},
            "arg": {"type": "string"},
            "text": {"type": "string"},
        },
        "required": ["type", "target", "arg", "text"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "thought": {"type": "string", "description": "your private in-character reasoning, 1-4 sentences"},
            "speech": {"type": "string", "description": "what you say out loud or on the radio; empty for silence"},
            "channel": {"type": "string", "enum": CHANNELS},
            "to": {"type": "string", "description": "person id you are addressing, or empty"},
            "actions": {"type": "array", "items": act},
            "pace": {"type": "string", "enum": ["stroll", "walk", "run"]},
            "scratchpad": {"type": "string", "description": f"notes to your future self, max {SCRATCHPAD_CHARS} chars"},
        },
        "required": ["thought", "speech", "channel", "to", "actions", "pace", "scratchpad"],
        "additionalProperties": False,
    }


GAME_RULES = f"""You are a character in MELTDOWN, a social deduction game set in a fictional power station, Unit 4.
Everything here is a game abstraction: the plant is a handful of 0-100 meters, not real equipment.

THE DAY: Corporate's certification test runs 08:00-12:00 in three stages:
""" + "\n".join(f"- Stage {s['n']} {s['name']}: {hhmm(s['start'])}-{hhmm(s['end'])}, target output {s['target']}. "
                f"Pass: {s['rule']}." for s in STAGES) + """

THE PLANT: output (follows the control room's target), heat (rises with output and test load, cooled by the
coolant system), stability, and the MELTDOWN meter. If MELTDOWN reaches 100 the game ends badly for everyone except
the saboteur. Four systems (core, coolant, instruments, security) wear down unless staff work at their stations.

HIDDEN ROLE: one of the four department managers is secretly a saboteur working for a rival. Their moves leave
clues (badge ledger, cameras, station logs, witness testimony, radio). The Director wins by arresting the
saboteur with two different types of clue. Everyone else wins if the plant stays safe and the saboteur is caught.

THE MAP:
""" + "\n".join(f"- {z}: {d['name']} (reader {d['reader'] or 'none'}, cameras {'yes' if d['cctv'] else 'NO'}, "
                f"radio {'yes' if d['radio'] else 'NO'})" for z, d in F.ZONES.items()) + """
Doors: """ + ", ".join(f"{a}-{b}" for a, b in F.DOORS) + """
Stations: """ + ", ".join(f"{k} ({v['zone']}, {v['system'] or 'no system'})" for k, v in F.STATIONS.items()) + """
Station controls (fictional; each only moves the game meters). Use `interact` while standing at the station:
""" + STATIONS_TEXT + """
A station that someone is working at can't be changed without them stopping you and raising the alarm.
Every change is written to the station's log. A station stays logged in to its regular operator for about 10
minutes after they step away, so a change made in that window is logged under their badge; otherwise it is logged
under the badge you last used at a door. If a manager tells an operator to "leave it" at a new setting, the
operator may go along with it, and will remember who said so.

CRISIS: once the true meltdown meter passes 40 it snowballs: it climbs faster the higher it gets, and goes from
alarm to meltdown in minutes. Only a crowd fixes it: every person using `respond` at a response station pulls it
back (up to 3 per station count), and resetting off-normal stations matters too. If the meter spikes past 85, the
room(s) behind it become contaminated and sealed off for the rest of the day, even if the meltdown is stopped;
anyone inside is exposed. Past 95, the Reactor Hall and Override Vault go too.

BREAK ROTA: staff get a 15-minute coffee break and a 30-minute early lunch, staggered by department and split in
two halves. The canteen fills up and some stations go quiet for a while.
ALARMS: the building alarm follows the control room CONSOLE's meltdown meter: advisory at 28, ALL HANDS at 40
(breaks cancelled, everyone to a response station), site emergency at 70 (sirens; staff without a response post
muster in the courtyard). During the test stages the test rig also raises EXPECTED warnings, labelled [test warning]; they are
part of the test and not by themselves a sign of trouble. Telling the two apart is part of the job.

MOVING: three paces. Stroll is slow and unhurried (patrols, breaks). Walk is normal. Running is fast but anyone
nearby and any camera notices, and it looks suspicious. Rooms connect through corridors (Main Corridor, Service
Corridor, Center Stairwell, East Link), which have cameras except the stairwell and no badge readers.
Badges: every door with a reader logs a swipe. The three restrooms have no reader, no cameras and no radio: only
whispers work. The Locker Room has no cameras either.
You get restroom urges over time; ignore them too long and you will have to go anyway.

TALKING (the speak verb): fill `speech`, `channel` and `to`. Channel 'say' = everyone in your zone hears; 'whisper' = one person in your zone (set `to`);
'radio' = your department; 'exec' = Director and managers; 'security' = security team and Director.

Each turn, answer with one JSON object. Keep `thought` honest and in character: it is private and only appears in
the replay after the game. Keep speech short and natural. Use person ids (like U4-OP-01) in `to` and `target`.
Usually take one action; the Director may take up to """ + str(DIRECTOR_INVESTIGATIONS_PER_TURN + 1) + """."""


def roster_text():
    rows = []
    for a in C.ALL:
        rows.append(f"{a['id']} {a['name']} - {a['role']}"
                    + (f", {C.DEPT_NAME[a['dept']]} dept" if a["dept"] else ""))
    return "\n".join(rows)


def system_prompt(world, p) -> str:
    me = (f"YOU ARE {p.name} ({p.id}), {p.role}"
          + (f" in the {C.DEPT_NAME[p.dept]} department" if p.dept else "")
          + f". Badge clearance {p.clearance}. Home station: {p.home or 'none'}.\n"
          + f"Personality ({p.archetype}): {C.PERSONALITY[p.archetype]}\n")
    if p.tier == "director":
        goal = ("GOAL: pass the certification test, keep MELTDOWN below 100, and arrest the saboteur with evidence. "
                f"You have {DIRECTOR_INVESTIGATIONS_PER_TURN} investigations per turn. Corporate (CEO Gordon Pike) "
                "wants the pass; you want a plant that's still standing.")
    elif p.saboteur:
        goal = ("SECRET ROLE: you are an undercover corporate spy. A rival company placed you at Unit 4 years ago, "
                "and you worked your way up to department manager. Your team trusts you, the Director relies on you, "
                "and nobody knows. Today your handler at the rival company wants Unit 4's certification test to "
                "fail: MELTDOWN at 100 before 12:00, or the Director discredited by two wrong arrests. Your cover is "
                "everything: keep acting like the manager everyone knows.\n"
                "Stations left off their normal setting push MELTDOWN up; the Display Calibration Rack on 'offset' "
                "makes the control room console look calm. But a station can't be touched while someone works at it. "
                "Get them away: give a convincing reason to be elsewhere, wait for their restroom break, or catch "
                "them alone. Everything leaves traces: station logs record the badge that was used (a borrowed one "
                "logs its owner), cameras see who was in the room, witnesses remember, and the Director can check "
                "the console against the truth. Staff who find a station off-normal will reset it.")
    elif p.tier == "manager":
        goal = ("GOAL: keep your department's system healthy, help pass the test, and send the Director honest "
                "SitReps on the exec channel. One of your fellow managers may be the saboteur.")
    else:
        mgr = world.people[f"U4-MGR-{p.dept}"]
        goal = (f"GOAL: do your job ({p.role}), follow your manager {mgr.name} ({mgr.id}) and stay true to your "
                "personality. Report anything odd on the radio, or don't, depending on who you are. If a station you "
                "work at is off its normal setting, you can reset it with interact.")
    acts = "\n".join(f"- {k}: {v}" for k, v in actions_for(p).items())
    return f"{me}\n{goal}\n\nYOUR ACTIONS:\n{acts}"


def shared_prompt() -> str:
    """Identical for every agent, so it is sent first and cached."""
    return f"{GAME_RULES}\n\nCAST:\n{roster_text()}"


def observation(world, p) -> str:
    t = world.t
    z = F.ZONES[p.zone]
    lines = [f"TIME {hhmm(t)}. {world.stage_text()}",
             f"You are in {p.zone} {z['name']}" + (f" at {p.station}" if p.station else " (on the move)")
             + f". Activity: {p.activity}."]
    others = world.in_zone(p.zone, exclude=p.id)
    if others:
        lines.append("With you: " + ", ".join(f"{q.first} ({q.id}, {q.role}{', ' + q.activity if q.activity != 'working' else ''})"
                                              for q in others[:12]))
    else:
        lines.append("Nobody else is here.")
    if p.zone == "Z2" or p.tier == "director":
        sh = world.plant.shown(t)
        lines.append(f"CONSOLE: output {sh['output']:.0f} (target {world.plant.target:.0f}), heat {sh['heat']:.0f}, "
                     f"stability {sh['stability']:.0f}, MELTDOWN {sh['incident']:.0f}. Systems: core {sh['h_core']:.0f}, "
                     f"coolant {sh['h_coolant']:.0f}, instruments {sh['h_instruments']:.0f}, security "
                     f"{sh['h_security']:.0f}." + (f" (instrument uncertainty +/-{sh['uncertainty']})" if sh['uncertainty'] else ""))
    elif p.station and F.STATIONS[p.station]["system"] not in (None, "output"):
        s = F.STATIONS[p.station]["system"]
        lines.append(f"The {p.station} gauge shows {s} system health {world.plant.health[s]:.0f}%.")
    if p.tier == "manager" and p.dept:
        s = C.DEPT_SYSTEM[p.dept]
        team = [q for q in world.people.values() if q.dept == p.dept and q.tier == "staff"]
        lines.append(f"Your department system ({s}) health: {world.plant.health[s]:.0f}%. Team: "
                     + ", ".join(f"{q.first} {q.id} @{q.station or q.zone}{' (' + q.activity + ')' if q.activity != 'working' else ''}"
                                 for q in team))
    if p.tier == "director":
        lines.append(f"High Alert: {'ON' if world.high_alert else 'off'}. Wrong arrests so far: {world.wrong_arrests}/2.")
        hc = world.headcounts()
        lines.append("CCTV headcounts: " + ", ".join(f"{k}:{v}" for k, v in sorted(hc.items())))
        board = world.case_board()
        if board:
            lines.append("CASE BOARD (clues found):")
            for c in board:
                lines.append(f"  {c['id']} [{c['type']}] {c['at']} {c['where']}: {c['text']} -> consistent with "
                             + ", ".join(f"{world.people[s].first} ({s})" for s in c["suspects"]))
            tally = {}
            for c in board:
                for s in c["suspects"]:
                    tally.setdefault(s, set()).add(c["type"])
            lines.append("Clue types per person: " + "; ".join(
                f"{world.people[k].first} ({k}): {', '.join(sorted(v))}" for k, v in sorted(tally.items(), key=lambda kv: -len(kv[1]))))
        else:
            lines.append("CASE BOARD: empty. You have found no clues yet.")
    if p.station in F.SETTINGS:
        cur, nom = world.plant.settings[p.station], F.SETTINGS[p.station]["nominal"]
        lines.append(f"The {F.STATIONS[p.station]['label']} is set to '{cur}'"
                     + ("." if cur == nom else f". That is NOT its normal setting ('{nom}')."))
        occ = world.occupants(p.station, exclude=p.id)
        if occ:
            lines.append("Also working at this station: " + ", ".join(f"{q.first} ({q.id})" for q in occ))
    if p.saboteur:
        off = world.plant.off_nominal()
        manned = {k: [q.first for q in world.occupants(k, exclude=p.id)] for k in F.SETTINGS}
        cds = "; ".join(f"{k}={world.plant.settings[k]} ({'manned by ' + ', '.join(v) if v else 'unmanned'})"
                        for k, v in manned.items())
        heat = world.sab_heat
        mood = "nobody is looking at you" if heat < 6 else "people are starting to ask questions" if heat < 14 \
            else "you are under real suspicion"
        lines.append(f"[secret] True MELTDOWN {world.plant.incident:.0f}. Stations: {cds}. Heat: {mood}."
                     + (f" You carry borrowed badges: {', '.join(p.extra_badges)}." if p.extra_badges else ""))
    if p.lent_to:
        lines.append(f"You lent your badge to {world.people[p.lent_to].first}. Doors with readers won't open for you.")
    if p.pending:
        if p.pending["kind"] == "badge_request":
            lines.append("PENDING: someone asked to borrow your badge. Use lend_badge with yes or no.")
        elif p.pending["kind"] == "interview":
            lines.append("PENDING: the Director summoned you for an interview. Go to director_desk (Z2) and use answer.")
    if p.order:
        lines.append(f"Your latest order: go to {p.order}.")
    if p.break_kind:
        lines.append(f"You are on your {p.break_kind} break until {hhmm(p.break_until)}.")
    elif p.breaks:
        k, st, mins = p.breaks[0]
        lines.append(f"Your next scheduled break: {k} at {hhmm(st)} ({mins} min).")
    if world.contaminated:
        lines.append("SEALED OFF (contaminated): " + ", ".join(F.ZONES[z]["name"] for z in world.contaminated) + ".")
    if p.exposed:
        lines.append("You were exposed in a contaminated room.")
    if world.alarm_level:
        lines.append(f"BUILDING ALARM LEVEL {world.alarm_level} is sounding "
                     f"({['', 'advisory', 'plant alert', 'site emergency'][world.alarm_level]}).")
    if p.bladder > 70:
        lines.append("You really need the restroom soon." if p.bladder < 90 else "You need the restroom NOW.")
    if p.inbox:
        lines.append("SINCE YOUR LAST TURN:")
        for m in p.inbox:
            lines.append(f"  {hhmm(m['t'])} {m['frm']}: {m['text']}")
    if p.scratchpad:
        lines.append(f"YOUR NOTES: {p.scratchpad}")
    return "\n".join(lines)
