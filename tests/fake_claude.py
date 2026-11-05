#!/usr/bin/env python3
"""Stand-in for the `claude` CLI in tests: answers `claude -p --json-schema ... --output-format json` like Claude
Code does. FAKE_CLAUDE_LIMIT_FILE: if that file doesn't exist yet, create it and answer with a usage-limit error."""
import json
import os
import sys
import time

args = sys.argv[1:]
log = os.environ.get("FAKE_CLAUDE_LOG")
if log:
    with open(log, "a") as fh:
        fh.write(json.dumps(args) + "\n")
lim = os.environ.get("FAKE_CLAUDE_LIMIT_FILE")
if lim and not os.path.exists(lim):
    open(lim, "w").close()
    print(json.dumps({"type": "result", "subtype": "success", "is_error": True,
                      "result": f"Claude AI usage limit reached|{int(time.time()) + 1}"}))
    sys.exit(1)
sys.stdin.read()
schema = json.loads(args[args.index("--json-schema") + 1])
acts = schema["properties"]["actions"]["items"]["properties"]["type"]["enum"]
typ = "work" if "work" in acts else "wait"
d = dict(thought="Fake thought.", speech="", channel="none", to="", pace="walk", scratchpad="note",
         actions=[dict(type=typ, target="", arg="", text="")])
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "", "structured_output": d,
                  "total_cost_usd": 0.001, "usage": {"input_tokens": 50, "output_tokens": 20,
                                                     "cache_read_input_tokens": 900}}))
