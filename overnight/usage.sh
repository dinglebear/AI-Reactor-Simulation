#!/bin/bash
# prints five_hour utilization + reset epoch via a tiny haiku call
cd /tmp && timeout 120 claude -p "Reply with just: ok" --model claude-haiku-5-5 --output-format stream-json --verbose 2>/dev/null \
 | grep '"rate_limit_event"' | tail -1 | python3 /home/user/AI-Reactor-Simulation/overnight/usage.py
