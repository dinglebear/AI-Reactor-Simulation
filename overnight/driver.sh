#!/bin/bash
# runs the schedule; skips games that already have done markers; pauses if 5-hour usage > 0.85 until reset
cd /home/user/AI-Reactor-Simulation
MIN=${MIN:-150}
while read n scen seed; do
  d=overnight/g$(printf %02d $n)
  [ -f $d/DONE ] && continue
  [ -f overnight/STOP ] && exit 0
  mkdir -p $d
  u=$(overnight/usage.sh); echo "$(date -u +%T) before game $n: $u" >> overnight/usage.log
  python -m meltdown.run --claude-code --minutes $MIN --human auto --speed 0 --seed $seed --scenario $scen \
     --exit-interviews --movie --quiet --out $d > $d/stdout.log 2>&1
  echo "exit=$?" >> $d/stdout.log
  u=$(overnight/usage.sh); echo "$(date -u +%T) after game $n: $u" >> overnight/usage.log
  date -u +%FT%TZ > $d/DONE
  [ -f overnight/PAUSE_AFTER ] && { rm overnight/PAUSE_AFTER; exit 0; }
done < overnight/$LANE.txt
touch overnight/$LANE.DONE
