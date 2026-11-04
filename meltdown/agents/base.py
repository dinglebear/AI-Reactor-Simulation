"""What every agent sees (prompts) and what it may answer (the decision schema)."""
from __future__ import annotations

from .. import cast as C
from .. import facility as F
from ..cards import hand_text
from ..config import hhmm, SCRATCHPAD_CHARS, DIRECTOR_INVESTIGATIONS_PER_TURN
from ..plant import STAGES

CHANNELS = ["none", "say", "whisper", "radio", "exec", "security"]

STAFF_ACTIONS = {
    "go": "walk to a station. target = station name. Set pace to sprint only if it's urgent: people notice running.",
    "work": "stay at your current station and keep its system healthy",
    "restroom": "go to the nearest restroom (no cameras, no radio, whispers only)",
    "wait": "do nothing this turn",
    "lend_badge": "answer a badge request. arg = yes or no",
    "answer": "answer the Director in an interview (you must be at the Director's desk). arg = tell or withhold; "
              "text = what you say",
}
MANAGER_ACTIONS = dict(STAFF_ACTIONS, order="send one of your staff somewhere. target = person id, arg = station name")
SECURITY_MANAGER_EXTRA = {
    "audit_badges": "review the badge ledger for contradictions",
    "pull_cctv": "review camera footage. target = zone id (Z1..Z8)",
}
SABOTEUR_EXTRA = {
    "card": "play a saboteur card. target = card name, arg = person id when the card needs one, text = what you "
            "whisper or write",
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
    "inspect": "INVESTIGATION. Send someone to inspect a station for tampering. target = station, arg = person id",
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
            "pace": {"type": "string", "enum": ["walk", "sprint"]},
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
coolant system), stability, and the INCIDENT meter. If INCIDENT reaches 100 the game ends badly for everyone except
the saboteur. Four systems (core, coolant, instruments, security) wear down unless staff work at their stations.

HIDDEN ROLE: one of the four department managers is secretly a saboteur working for a rival. Their moves leave
clues (badge ledger, cameras, tamper marks, logbooks, testimony, radio). The Director wins by arresting the
saboteur with two different types of clue. Everyone else wins if the plant stays safe and the saboteur is caught.

THE MAP:
""" + "\n".join(f"- {z}: {d['name']} (reader {d['reader'] or 'none'}, cameras {'yes' if d['cctv'] else 'NO'}, "
                f"radio {'yes' if d['radio'] else 'NO'})" for z, d in F.ZONES.items()) + """
Doors: """ + ", ".join(f"{a}-{b}" for a, b in F.DOORS) + """
Stations: """ + ", ".join(f"{k} ({v['zone']}, {v['system'] or 'no system'})" for k, v in F.STATIONS.items()) + """

MOVING: walking is normal. Sprinting is fast but anyone nearby and any camera notices, and it looks suspicious.
Badges: every door with a reader logs a swipe. Restrooms have no reader, no cameras and no radio: only whispers work.
You get restroom urges over time; ignore them too long and you will have to go anyway.

TALKING: channel 'say' = everyone in your zone hears; 'whisper' = one person in your zone (set `to`);
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
        goal = ("GOAL: pass the certification test, keep INCIDENT below 100, and arrest the saboteur with evidence. "
                f"You have {DIRECTOR_INVESTIGATIONS_PER_TURN} investigations per turn. Corporate (CEO Gordon Pike) "
                "wants the pass; you want a plant that's still standing.")
    elif p.saboteur:
        goal = ("SECRET ROLE: you are the SABOTEUR. Nobody knows. Your handler wants INCIDENT at 100 before 12:00, "
                "or the Director discredited by two wrong arrests. Look like a good manager. Every card leaves clues; "
                "pick your moments (the Stage 2 heat makes a great cover) and spread your moves across clue types "
                "the Director hasn't checked. Your hand:\n" + hand_text())
    elif p.tier == "manager":
        goal = ("GOAL: keep your department's system healthy, help pass the test, and send the Director honest "
                "SitReps on the exec channel. One of your fellow managers may be the saboteur.")
    else:
        mgr = world.people[f"U4-MGR-{p.dept}"]
        goal = (f"GOAL: do your job ({p.role}), follow your manager {mgr.name} ({mgr.id}) and stay true to your "
                "personality. Report anything odd on the radio, or don't, depending on who you are.")
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
                     f"stability {sh['stability']:.0f}, INCIDENT {sh['incident']:.0f}. Systems: core {sh['h_core']:.0f}, "
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
    if p.saboteur:
        cds = ", ".join(f"{k} ready at {hhmm(v)}" for k, v in world.cooldowns.items() if v > t) or "all cards ready"
        heat = world.sab_heat
        mood = "nobody is looking at you" if heat < 6 else "people are starting to ask questions" if heat < 14 \
            else "you are under real suspicion"
        lines.append(f"[secret] True INCIDENT {world.plant.incident:.0f}. Cooldowns: {cds}. Heat: {mood}."
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
    if p.bladder > 70:
        lines.append("You really need the restroom soon." if p.bladder < 90 else "You need the restroom NOW.")
    if p.inbox:
        lines.append("SINCE YOUR LAST TURN:")
        for m in p.inbox:
            lines.append(f"  {hhmm(m['t'])} {m['frm']}: {m['text']}")
    if p.scratchpad:
        lines.append(f"YOUR NOTES: {p.scratchpad}")
    return "\n".join(lines)
