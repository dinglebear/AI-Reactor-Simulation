"""Digest of one finished run for writing notes: python overnight/digest.py RUN_DIR > digest.md"""
import json, re, sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from meltdown.analysis import metrics
d = sys.argv[1]
r = json.load(open(os.path.join(d, "replay.json")))
cast = {c["id"]: c for c in r["cast"]}
nm = lambda i: cast.get(i, {}).get("name", i or "-")
meta = r["meta"]
spies = meta.get("spies") or ([meta["saboteur"]] if meta.get("saboteur") else [])
m = metrics(r)
print(f"# {os.path.basename(d)}  scenario={meta.get('scenario')} seed={meta['seed']}")
print("spies:", [nm(s) + f" ({cast[s]['role']}, {cast[s]['model']})" for s in spies])
print("outcome:", meta["outcome"]); print("test:", meta["test_status"], "wall_s", meta.get("wall_s"))
print("usage:", meta.get("usage"))
print("\n## metrics"); print({k: v for k, v in m.items() if not k.startswith("_")})
ev = r["events"]
print("\n## kinds", collections.Counter(e["kind"] for e in ev).most_common())
KEY = {"arrest", "frisk", "search", "lockdown", "scram", "interact", "badge_lent", "badge_ask", "badge_request", "hide",
       "retrieve", "wipe_cctv", "report_director", "plant_alarm", "clue_found", "listen_in", "noticed", "lure", "end",
       "stage", "director_to_corporate", "spy_plan", "handler_msg", "copier", "sweep", "rummage", "order", "blocked",
       "high_alert", "eavesdrop", "corporate", "set_output", "interview"}
print("\n## key events")
for e in ev:
    if e["kind"] in KEY or (e["kind"] not in ("speech", "investigate", "swipe", "task_done", "clue_created", "exit_interview", "move", "chore")):
        print(e["clock"], e["kind"], nm(e.get("actor")), "|", (e.get("text") or "")[:260])
print("\n## spy thoughts")
for t in r["thoughts"]:
    if t["agent"] in spies:
        acts = ",".join(a["type"] + (":" + str(a.get("target")) if a.get("target") else "") for a in t.get("actions", []))
        print(t["clock"], nm(t["agent"]), t.get("source"), "|", t["thought"][:400], "| say:", (t.get("speech") or "")[:160], "| do:", acts)
print("\n## director thoughts")
for t in r["thoughts"]:
    if t["agent"] == "U4-DIR" and t["agent"] not in spies:
        print(t["clock"], t.get("source"), "|", t["thought"][:350])
print("\n## exit interviews")
for e in ev:
    if e["kind"] == "exit_interview":
        print("-", e["text"][:400])
print("\n## leak / meta scan (non-spy speech)")
pat = re.compile(r"\b(spy|spies|saboteur|mole|rival company|planted|handler|language model|AI model|simulation|NPC|prompt)\b", re.I)
for e in ev:
    if e["kind"] == "speech" and e.get("actor") not in spies and e.get("actor") != "U4-DIR" and pat.search(e["text"]):
        print(e["clock"], nm(e["actor"]), e.get("channel"), "|", e["text"][:250])
print("\n## fallbacks/errors", sum(1 for t in r["thoughts"] if t.get("source") != "live"),
      collections.Counter((t.get("error") or "")[:60] for t in r["thoughts"] if t.get("error")).most_common(5))
