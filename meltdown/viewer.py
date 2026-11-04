"""Bundle a replay into a single self-contained HTML file you can double-click.

  python -m meltdown.viewer runs/latest            # writes runs/latest/replay.html
  python -m meltdown.viewer runs/latest --open     # ...and opens it in your browser
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


def bundle(replay_path: str, out_path: str | None = None, standalone: bool = True) -> str:
    with open(replay_path) as fh:
        data = json.load(fh)
    with open(TEMPLATE) as fh:
        page = fh.read()
    blob = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    page = page.replace("/*REPLAY_JSON*/null", blob, 1)
    if standalone:
        head_end = page.index("<div id=\"root\">")
        page = HEAD + page[:head_end] + "</head><body>" + page[head_end:] + "</body></html>"
    out_path = out_path or os.path.join(os.path.dirname(replay_path), "replay.html")
    with open(out_path, "w") as fh:
        fh.write(page)
    return out_path


def main(argv=None):
    ap = argparse.ArgumentParser(prog="meltdown.viewer")
    ap.add_argument("run", help="a run directory (or a replay.json path)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args(argv)
    path = a.run if a.run.endswith(".json") else os.path.join(a.run, "replay.json")
    out = bundle(path, a.out)
    print(out)
    if a.open:
        webbrowser.open("file://" + os.path.abspath(out))


if __name__ == "__main__":
    main()
