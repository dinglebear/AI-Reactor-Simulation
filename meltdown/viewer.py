"""Bundle replays into a single self-contained HTML file you can double-click. Works offline: React and htm are
built into the page from viewer/vendor/.

  python -m meltdown.viewer runs/latest                  # writes runs/latest/replay.html
  python -m meltdown.viewer runs/latest --open           # ...and opens it in your browser
  python -m meltdown.viewer runs/*-s3 runs/*-s7 --out all.html   # several runs, with a run picker
"""
from __future__ import annotations
import argparse
import json
import os
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "..", "viewer", "index.html")
HEAD = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">'
        '<style>*,*::before,*::after{box-sizing:border-box}body{margin:0}[hidden]{display:none!important}</style>')


VENDOR = os.path.join(HERE, "..", "viewer", "vendor")
LIBS = ("react.production.min.js", "react-dom.production.min.js", "htm.umd.js")


def _inline_libs(page: str) -> str:
    a, b = page.index("<!--LIBS-->"), page.index("<!--/LIBS-->") + len("<!--/LIBS-->")
    parts = []
    for name in LIBS:
        with open(os.path.join(VENDOR, name)) as fh:
            parts.append("<script>" + fh.read().replace("</script", "<\\/script") + "</script>")
    return page[:a] + "\n".join(parts) + page[b:]


def bundle(replay_path, out_path: str | None = None, standalone: bool = True, inline_libs: bool = True) -> str:
    paths = [replay_path] if isinstance(replay_path, str) else list(replay_path)
    data = []
    for p in paths:
        with open(p) as fh:
            data.append(json.load(fh))
    with open(TEMPLATE) as fh:
        page = fh.read()
    blob = json.dumps(data[0] if len(data) == 1 else data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = page.replace("/*REPLAY_JSON*/null", blob, 1)
    if inline_libs:
        page = _inline_libs(page)
    if standalone:
        head_end = page.index("<div id=\"root\">")
        page = HEAD + page[:head_end] + "</head><body>" + page[head_end:] + "</body></html>"
    out_path = out_path or os.path.join(os.path.dirname(paths[0]), "replay.html")
    with open(out_path, "w") as fh:
        fh.write(page)
    return out_path


def main(argv=None):
    ap = argparse.ArgumentParser(prog="meltdown.viewer")
    ap.add_argument("runs", nargs="+", help="run directories (or replay.json paths); several give a run picker")
    ap.add_argument("--out", default=None)
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args(argv)
    paths = [r if r.endswith(".json") else os.path.join(r, "replay.json") for r in a.runs]
    out = bundle(paths, a.out)
    print(out)
    if a.open:
        webbrowser.open("file://" + os.path.abspath(out))


if __name__ == "__main__":
    main()
