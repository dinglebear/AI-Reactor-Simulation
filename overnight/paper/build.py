import json, os
here = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(os.path.join(here, "data.json")))
for g in data:
    g.pop("meter", None); g.pop("spy_moves", None)
planned = []
for lane in ("laneA", "laneB"):
    for line in open(os.path.join(here, "..", lane + ".txt")):
        n, scen, seed = line.split()[:3]
        planned.append(dict(n=int(n), scenario=scen, prompt="v1" if int(n) <= 5 else "v2"))
planned.append(dict(n=1, scenario="classic", prompt="v1"))
planned = sorted({p["n"]: p for p in planned}.values(), key=lambda p: p["n"])
html = open(os.path.join(here, "template.html")).read()
html = html.replace("/*DATA*/[]", json.dumps(data, separators=(",", ":"))).replace("/*PLANNED*/[]", json.dumps(planned)).replace("/*VO*/[]", json.dumps(json.load(open(os.path.join(here, "narration.json")))))
out = "/mnt/project-files/meltdown/test-runs/overnight-2026-11-25/paper/demo-paper.html"
os.makedirs(os.path.dirname(out), exist_ok=True)
open(out, "w").write(html)
print(out, len(html))
