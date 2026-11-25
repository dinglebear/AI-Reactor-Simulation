"""Collect per-game numbers for the demo paper page: python overnight/paper/extract.py > overnight/paper/data.json"""
import json, glob, os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
games = []
for d in sorted(glob.glob(os.path.join(ROOT, "g*/"))):
    if not os.path.exists(os.path.join(d, "DONE")):
        continue
    rp = glob.glob(os.path.join(d, "2*/replay.json"))
    if not rp:
        continue
    r = json.load(open(rp[0]))
    meta, ev = r["meta"], r["events"]
    cast = {c["id"]: c for c in r["cast"]}
    spies = meta.get("spies") or ([meta["saboteur"]] if meta.get("saboteur") else [])
    ivs = [e for e in ev if e["kind"] == "exit_interview" and e.get("actor") not in spies]
    named = {"nobody": 0, "spy": 0, "innocent": 0}
    votes = {}
    for e in ivs:
        m = re.search(r"suspected (\S+?)\.", e["text"])
        who = m.group(1) if m else "nobody"
        if who in ("nobody", "me", "-") or who not in cast:
            named["nobody"] += 1
        elif who in spies:
            named["spy"] += 1
        else:
            named["innocent"] += 1
        if who in cast:
            votes[cast[who]["first"]] = votes.get(cast[who]["first"], 0) + 1
    changes = [e for e in ev if e["kind"] == "interact"]
    spy_moves = [e for e in ev if e.get("actor") in spies and e["kind"] in
                 ("interact", "clone", "wipe_cctv", "lure", "badge_ask", "retrieve")]
    arrests = [e for e in ev if e["kind"] == "arrest"]
    games.append(dict(
        n=int(os.path.basename(d.rstrip("/"))[1:]), scenario=meta.get("scenario", "classic"), seed=meta["seed"],
        prompt=meta.get("prompt_version") or ("v1" if int(os.path.basename(d.rstrip("/"))[1:]) <= 5 else "v2" if int(os.path.basename(d.rstrip("/"))[1:]) <= 9 else "v2.1"),
        spies=[dict(name=cast[s]["name"], first=cast[s]["first"], role=cast[s]["role"], model=cast[s]["model"]) for s in spies],
        result=meta["outcome"]["result"], outcome=meta["outcome"]["text"], ended=ev[-1]["clock"],
        grade={k: v["minutes"] for k, v in meta["grade"].items()},
        turns=len(r["thoughts"]), usd=meta["usage"]["api_equivalent_usd"], wall_min=round(meta.get("wall_s", 0) / 60),
        named=named, votes=dict(sorted(votes.items(), key=lambda kv: -kv[1])[:5]),
        plans=sum(1 for e in ev if e["kind"] == "spy_plan"),
        station_changes=len(changes), spy_station_changes=sum(1 for e in changes if e.get("actor") in spies),
        spy_moves=[(e["clock"], e["kind"], e["text"][:120]) for e in spy_moves][:12],
        arrests=[(e["clock"], e["text"][:160]) for e in arrests],
        output=[round(f["sh"]["output"]) for f in r["frames"][::4]],
        meter=[round(f["tr"]["incident"]) for f in r["frames"][::4]],
        frame_s=meta["frame_s"] * 4,
        lines=sum(1 for e in ev if e["kind"] == "speech"),
    ))
print(json.dumps(games, indent=1))
