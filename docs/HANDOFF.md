# Handoff: overnight work (2026-11-05)

Short note so a fresh session can pick up without the old thread.

## Where things are
- Repo dinglebear/AI-Reactor-Simulation. Work on `claude/project-thread-urapcb`; PRs go into `claude/project-thread-63g43k` (no main). PRs #1-#3 merged; later commits on the work branch are not in a PR yet.
- Rules for agents: `meltdown/agents/base.py` (GAME_RULES, system_prompt, observation). Cast/personalities/opinions: `meltdown/cast.py`. Engine/clock: `meltdown/engine.py`, `meltdown/config.py` (THINK_EVERY_S, MIN_GAP_S). World mechanics: `meltdown/world.py`. Claude Code brain (runs on Travis's plan): `meltdown/agents/claude_code.py`. Movie: `meltdown/movie.py`. Viewer: `viewer/index.html`. Rules doc: `docs/GAME.md`. Tests: `python -m unittest discover tests` (26 pass).
- The `claude` CLI in the cloud container is logged in to Travis's plan, so `python -m meltdown.run --claude-code --minutes N --human auto --speed 0 --seed S --movie` works there. Usage reference: a 10-minute game = 155 turns, about $1.26 API-equivalent, roughly 2-4% of his 5-hour window.

## Fixed limits (do not change)
- Controls are fictional stations; the MELTDOWN meter is an abstract 0-100 score. No real reactor physics, procedures or hardware.
- Don't script agent behaviour. The engine only informs; agents decide. Mock brains are test stand-ins, never results.

## Done today
- Only the Director and the spy are told a spy may exist (tests/test_secrets.py checks this). The crew thinks it's a noisy test day.
- Test-rig alarms reach staff as ordinary alarms; the Director has the schedule and a Director-only `pa` channel.
- Rumours rule; Chaos Prankster invents rumours; reputations (fibber, cries wolf) shape belief.
- Badge doors: the rules explain the levels, a refused swipe tells the person why, and orders to rooms someone can't open are refused with the reason.
- Short test runs end as CUT_SHORT instead of "Noon, test failed".

## First live test (10 min, seed 7)
Copied to /mnt/project-files/meltdown/test-runs/live-10min-s7/ (replay.html, script.md, thoughts.jsonl).
- 0 fallbacks; no crew member mentioned a spy; nobody broke character; the movie camera followed speakers correctly.
- Bug found and fixed: Simone sent two mechanics to the Janitor Closet, which only custodians and L4 can open. Security read the refusals as suspicious, which made a fun accidental subplot.
- Noise: people compare system-health numbers taken minutes apart and chase "gaps" that are just health recovering.
- The spy (Mei, IE) played it very safe: "stay in cover, sabotage later". Not much happened in 10 minutes.
- A 90-minute run (seed 11) was started and then stopped so the new features go in first.

## Travis's new asks (2026-11-05, his words in the thread)
1. Wrap up this thread, then run games overnight and look for bugs: cameras, agents knowing what they shouldn't, breaking character.
2. Spice up the thriller. Agents should come up with their own strategies. "Don't nerf the AIs too hard." He may make the spy Opus if it plays too timidly.
3. New agent abilities:
   - The Director can call a search for a person (locate someone).
   - Anyone can listen in on a radio channel they shouldn't be on. It turns heads if done in public.
   - People can hide things.
4. The spy gets extra insight into each person's personality and weak spots: a manager for years, trained to read people.
5. After he upgrades his plan, add a setting for more turns per game minute (shorter THINK_EVERY_S / MIN_GAP_S, higher concurrency) so agents react faster.
6. Deliverable at the end: a document of everything done, plus advice on how to approach his first "research" documentary and whether it's worth documenting.

Usage: he's fine with heavy use overnight (the 5-hour cap limits it to about 25% of his weekly). His 5-hour window resets around 1:40 AM his time; the weekly limit resets Saturday at noon.
