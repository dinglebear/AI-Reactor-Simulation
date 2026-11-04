"""The saboteur's hand. Each card is an abstract game move: a cost, an effect on the meters, and clues left behind.

Cards never model real plant procedures. They are board-game actions on 0-100 meters.

Clue types (two DIFFERENT types pointing at one person are needed for a justified arrest):
  ledger    - a badge swipe that doesn't fit (found by audit_badges)
  cctv      - a camera saw something (found by pull_cctv)
  physical  - a tamper mark on a station (found by inspect)
  paper     - a logbook entry that doesn't add up (found by cross_check)
  testimony - something a person saw or was asked to do (found by interview)
  radio     - a report that doesn't match the radio traffic (found by read_radio)
"""
from __future__ import annotations

CARDS = {
    "tamper": dict(
        title="Tamper",
        text="Spend 60s at a station that services a system: that system -25 health, incident +10.",
        work_s=60, cooldown_s=900, incident=10, system_hit=25,
        needs="a station with a system (core_panel, coolant_panel, test_bench, instrument_rack, vault_panel, backup_rack)",
        clues=["physical", "cctv"],
    ),
    "mask_readings": dict(
        title="Mask the readings",
        text="Spend 45s at instrument_rack or backup_rack: for 30 game-min the console shows heat -15, "
             "stability +15 and incident -20 from the truth. Incident +4.",
        work_s=45, cooldown_s=1800, incident=4, mask_s=1800,
        mask={"heat": -15, "stability": 15, "incident": -20},
        needs="instrument_rack or backup_rack",
        clues=["paper", "physical"],
    ),
    "vault_override": dict(
        title="Vault override",
        text="Spend 90s at vault_panel (Z5): stability -25, core -15 health, incident +22. "
             "In High Alert the vault door needs two badges, so you need a borrowed one.",
        work_s=90, cooldown_s=2100, incident=22, system_hit=15, stability_hit=25,
        needs="vault_panel",
        clues=["ledger", "cctv"],
    ),
    "borrow_badge": dict(
        title="Borrow a badge",
        text="In a restroom with a target from the Compliance group: whisper and ask for their badge. "
             "If they say yes you carry it; doors log it under their name. Return it later in a restroom.",
        work_s=20, cooldown_s=600, incident=0,
        needs="a restroom (Z7N/Z7S) with the target present",
        clues=["testimony", "ledger"],
    ),
    "false_report": dict(
        title="False report",
        text="Send your SitRep to the Director blaming someone else (put their id in target). "
             "Their suspicion rises. The radio log won't back you up.",
        work_s=0, cooldown_s=1200, incident=0,
        needs="anywhere",
        clues=["radio"],
    ),
    "lie_low": dict(
        title="Lie low",
        text="Do honest, visible work for a while. Your own heat (how suspicious you look) drops faster.",
        work_s=0, cooldown_s=0, incident=0, needs="anywhere", clues=[],
    ),
}

TAMPER_STATIONS = ("core_panel", "coolant_panel", "test_bench", "instrument_rack", "vault_panel", "backup_rack")
MASK_STATIONS = ("instrument_rack", "backup_rack")

FIND_BY = {"ledger": "audit_badges", "cctv": "pull_cctv", "physical": "inspect", "paper": "cross_check",
           "testimony": "interview", "radio": "read_radio"}


def hand_text():
    lines = []
    for k, c in CARDS.items():
        lines.append(f"- {k}: {c['text']} (where: {c['needs']}; leaves: {', '.join(c['clues']) or 'nothing'})")
    return "\n".join(lines)
