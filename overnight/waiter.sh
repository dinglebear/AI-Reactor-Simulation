#!/bin/bash
# exits when a new game finishes, or the driver stops; keeps the container alive
cd /home/user/AI-Reactor-Simulation/overnight
start=$(ls g*/DONE 2>/dev/null | wc -l)
while true; do
  now=$(ls g*/DONE 2>/dev/null | wc -l)
  [ "$now" -gt "$start" ] && { echo "game finished: $now done"; tail -2 usage.log; exit 0; }
  pgrep -f "driver2?\.sh" >/dev/null || { echo "driver not running; $now done"; exit 0; }
  sleep 60
done
