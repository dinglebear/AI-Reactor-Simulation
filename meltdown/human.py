"""The human desk. Travis plays the saboteur's handler and CEO Gordon Pike; the game pauses while he types.

mode "ask":  print a banner and wait for input (Enter accepts the suggested line).
mode "auto": use the suggested line immediately (mock runs, unattended runs).
"""
from __future__ import annotations
import sys
import time

BANNER = "\n" + "=" * 72


class HumanDesk:
    def __init__(self, mode: str, log, timeout_note: str = ""):
        self.mode = mode
        self.log = log

    def _ask(self, t, who, reason, context, prompt, suggestion):
        start = time.time()
        if self.mode == "ask" and sys.stdin.isatty():
            print(f"{BANNER}\n  GAME PAUSED  -  {reason}\n{'-' * 72}")
            print(context)
            print(f"\n  {prompt}")
            print(f"  (Enter = use suggestion: \"{suggestion}\")")
            try:
                reply = input("  > ").strip()
            except EOFError:
                reply = ""
            reply = reply or suggestion
            print("  Resuming..." + BANNER[1:] + "\n")
        else:
            reply = suggestion
        self.log.pause(t, who, reason, prompt, reply, time.time() - start)
        return reply

    def handler(self, t, saboteur_name, message, context):
        return self._ask(t, "handler", f"{saboteur_name} is messaging you (you are the handler)",
                         context, f"{saboteur_name} wrote: \"{message}\"\n  Your reply as the handler:",
                         "Stay patient. Hit them when the heat is up, and don't get seen twice in one place.")

    def handler_checkin(self, t, saboteur_name, default_text, context):
        return self._ask(t, "handler", f"Handler check-in to {saboteur_name} (you are the handler)", context,
                         f"Message to {saboteur_name} as the handler:", default_text)

    def corporate_checkin(self, t, default_text, context):
        return self._ask(t, "corporate", "Corporate check-in (you are CEO Gordon Pike)", context,
                         "Message to the Director as Gordon Pike:", default_text)

    def corporate_reply(self, t, director_text, context):
        return self._ask(t, "corporate", "The Director is waiting on corporate (you are CEO Gordon Pike)",
                         context, f"Director Hart wrote: \"{director_text}\"\n  Your reply as Gordon Pike:",
                         "Do what you have to, Simone, but I want that certificate on my desk by noon.")
