"""The after-show: Claude reads a finished game's logs and writes a narrated movie script for the viewer.

    python -m meltdown.movie runs/latest                  # writer picked from how the game was run
    python -m meltdown.movie runs/latest --claude-code    # on your Pro/Max plan
    python -m meltdown.movie runs/latest --live           # on the API
    python -m meltdown.movie runs/latest --mock           # free, rule-based, for testing

The script is a list of scenes. Each scene has a game time and a room (the viewer flies the camera there) and a
list of lines: the narrator, people saying things, people's private thoughts, and 'secret' lines (the spy's
thoughts; the audience knows who the spy is, but not how it ends). The viewer reads it aloud with a different voice per person.

The writer may only use what is in the logs: every quoted line must come from what someone said or thought.
The script is saved as `movie` in replay.json (and as movie.json), a readable script.md is written for reading it
aloud yourself, and the replay.html is rebuilt.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import re
import sys

from .analysis import highlights
from .config import MODELS

KINDS = ("narration", "say", "thought", "secret")
SKIP_EVENTS = {"speech", "door_denied", "security_alert", "swipe", "restroom", "task_done", "handler", "spy",
               "badge_returned", "director_to_corporate"}
DIGEST_CHARS = 60000

MOVIE_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["title", "logline", "scenes"],
    "properties": {
        "title": {"type": "string"}, "logline": {"type": "string"},
        "scenes": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["t", "zone", "title", "lines"],
            "properties": {
                "t": {"type": "number", "description": "game seconds since 08:00 where this scene happens"},
                "zone": {"type": "string", "description": "room id (Z2, Z4, H1...) or empty"},
                "title": {"type": "string"},
                "lines": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False, "required": ["who", "kind", "text", "pause"],
                    "properties": {
                        "who": {"type": "string", "description": "'narrator' or a person id"},
                        "kind": {"type": "string", "enum": list(KINDS)},
                        "text": {"type": "string"},
                        "pause": {"type": "number", "description": "seconds of silence after the line, 0-3"},
                    }}},
            }}},
    },
}

WRITER_BRIEF = """You are the narrator and editor of a short movie made from one game of MELTDOWN, a social deduction
game with AI characters at a fictional power station called Unit 4. Everything about the plant is invented: the
stations and the meltdown meter are game pieces, so never add technical or engineering detail beyond the log.
The movie is about the people: who noticed, who argued, who pulled together, who lied.

Write a script of 12 to 20 scenes that takes about four to six minutes to read aloud. Rules:
- Use only what is in the log. Every 'say' line must be something that person actually said, and every 'thought'
  or 'secret' line something they actually thought (you may trim, never invent or reword the meaning).
- Narration carries the story between quotes: present tense, short sentences, a documentary voice with
  suspense. Hint, hold back, build towards the turns. Use pauses (0-3 s) for weight.
- The audience is in on the secret: say early on who the spy is, follow them, and use their private thoughts
  (kind 'thought') next to their helpful-sounding 'say' lines. The suspense is whether they get away with it.
- NEVER give away how the day ends before the final scene: not in the title, the logline, the scene titles or the
  narration. No "the person who was only waiting", no "until it was too late", no hints at an arrest or a
  meltdown. The audience should have to watch to the end to find out.
- When someone's personality matters to a moment (the one who can't say no, the joker nobody believes), the
  narrator can say so in a few words the first time it matters.
- Say when a line went out over the radio, the exec channel or the PA if it matters who could hear it.
- Give the crew credit for teamwork, quick thinking and courage when it happened. Arguments make great scenes.
- Each scene's t is the game time (seconds since 08:00) of its moment, scenes in time order, and zone is where it
  happens (a room id from the log, or empty for the whole site).
- The spy's plans (events 'spy_plan': the opening plan and every change, each with the thought behind it) are the
  spy's own private working ideas. Use them in the final scenes, after the outcome: what they first had in mind, and
  where and why they changed course. Don't reveal a plan earlier than the moment it was made.
- End with how the day ended: caught or not, the plant's fate, and the spy's last thought if there is one.
Answer with the JSON object only."""


# ------------------------------------------------------------------ the log, condensed for the writer
def spies_of(replay: dict) -> list:
    m = replay["meta"]
    return list(m.get("spies") or ([m["saboteur"]] if m.get("saboteur") else []))


def spy_line(replay: dict, cast: dict) -> str:
    spies, sc = spies_of(replay), replay["meta"].get("scenario", "classic")
    if not spies:
        return ("THE SPY: there is none. Corporate told the Director a manager was a spy, but nobody is. "
                "The audience knows this from the start; the Director and crew don't.")
    names = " and ".join(f"{s} {cast[s]['name']}" for s in spies)
    if sc == "director":
        return (f"THE SPY (the audience knows from the start; the crew doesn't): the Director herself, {names}, "
                "trying to turn the crew against each other")
    return f"THE SPY{'S' if len(spies) > 1 else ''} (the audience knows from the start; the crew doesn't): {names}"


def digest(replay: dict) -> str:
    cast = {c["id"]: c for c in replay["cast"]}
    spies = spies_of(replay)
    spy = spies[0] if spies else None
    zones = replay["zones"]
    o = replay["meta"]["outcome"]
    L = ["CAST (id | name | role | personality | wants)"]
    for c in replay["cast"]:
        L.append(f"{c['id']} | {c['name']} | {c['role']} | {c['personality'].split('. ')[0]} | {c.get('motive', '')}")
    L += ["", spy_line(replay, cast),
          f"OUTCOME (for the final scene ONLY; never hint at it earlier): {o['result']}, winner {o['winner']}. {o['text']}", "",
          "ROOMS: " + ", ".join(f"{z} {d['name']}" for z, d in zones.items()), "", "WHAT HAPPENED"]
    for e in replay["events"]:
        if e["kind"] in SKIP_EVENTS or (e["kind"] == "run" and not e.get("witnesses")):
            continue
        L.append(f"[{e['clock']}] {e['kind']}{' @' + e['zone'] if e.get('zone') else ''}: {e['text'][:260]}")
    head = "\n".join(L)

    talk = [f"[{e['clock']} t={int(e['t'])}] {e['actor']} ({e.get('channel')}{'->' + e['to'] if e.get('to') else ''}"
            f"{' @' + e['zone'] if e.get('zone') else ''}): \"{e['text'][:240]}\""
            for e in replay["events"] if e["kind"] == "speech" and e.get("actor") in cast]
    keytimes = [h["t"] for h in highlights(replay)]
    picked, per = [], {}
    for th in replay["thoughts"]:
        txt = (th.get("thought") or "").strip()
        if len(txt) < 15:
            continue
        a = th["agent"]
        near = any(abs(th["t"] - k) <= 240 for k in keytimes)
        cap = 45 if a in spies else 30 if cast.get(a, {}).get("tier") == "director" else 6 if near else 0
        if cap and per.get(a, 0) < cap or (near and per.get(a, 0) < 3):
            per[a] = per.get(a, 0) + 1
            picked.append(f"[{_clock(th['t'])} t={int(th['t'])}] {a} thinks: \"{txt[:220]}\"")
    budget = DIGEST_CHARS - len(head)
    talk, picked = _fit(talk, budget * 0.55), _fit(picked, budget * 0.45)
    return head + "\n\nWHAT PEOPLE SAID\n" + "\n".join(talk) + "\n\nWHAT PEOPLE THOUGHT (private)\n" + "\n".join(picked)


def _fit(lines, chars):
    """Keep lines under a character budget, thinning evenly so the whole day stays represented."""
    total = sum(len(x) + 1 for x in lines)
    if total <= chars:
        return lines
    step = total / chars
    return [x for i, x in enumerate(lines) if int(i / step) != int((i - 1) / step) or i == 0]


def _clock(t):
    total = 8 * 3600 + int(t)
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}"


# ------------------------------------------------------------------ writers
def write_with_claude_code(replay, model=None):
    import shutil
    import tempfile
    exe = os.environ.get("MELTDOWN_CLAUDE") or shutil.which("claude")
    if not exe:
        raise SystemExit("Claude Code isn't installed; use --live or --mock.")
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")}
    cmd = [exe, "-p", "--model", model or MODELS["director"], "--effort", "medium", "--system-prompt", WRITER_BRIEF,
           "--json-schema", json.dumps(MOVIE_SCHEMA), "--output-format", "json", "--tools", "",
           "--strict-mcp-config", "--setting-sources", "project", "--disable-slash-commands",
           "--no-session-persistence"]

    async def go():
        proc = await asyncio.create_subprocess_exec(*cmd, cwd=tempfile.mkdtemp(prefix="meltdown-movie-"), env=env,
                                                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(digest(replay).encode()), timeout=900)
        return proc.returncode, out.decode(errors="replace"), err.decode(errors="replace")
    code, out, err = asyncio.run(go())
    res = json.loads(out.strip().splitlines()[-1]) if out.strip() else {}
    if code != 0 or res.get("is_error"):
        raise RuntimeError(f"Claude Code couldn't write the script: {(res.get('result') or err)[:300]}")
    return res.get("structured_output") or _json_in(res.get("result", ""))


def write_with_api(replay, model=None):
    import anthropic
    client = anthropic.Anthropic()
    with client.messages.stream(
            model=model or MODELS["director"], max_tokens=32000, system=WRITER_BRIEF,
            messages=[{"role": "user", "content": digest(replay)}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": MOVIE_SCHEMA}}) as s:
        msg = s.get_final_message()
    if msg.stop_reason == "refusal":
        raise RuntimeError("the model declined to write the script")
    return json.loads(next(b.text for b in msg.content if b.type == "text"))


def _json_in(text):
    return json.loads(text[text.find("{"): text.rfind("}") + 1])


def _mock_spy_intro(replay, cast):
    spies = spies_of(replay)
    if not spies:
        return "Except, this time, there isn't one. Only the Director was told otherwise."
    if replay["meta"].get("scenario") == "director":
        return f"Nobody here knows it's the Director, {cast[spies[0]]['name']}. You do."
    return f"Nobody here knows it's {' and '.join(cast[s]['name'] for s in spies)}. You do."


def write_mock(replay):
    """Rule-based stand-in: one scene per highlight, with real lines from around that moment."""
    cast = {c["id"]: c for c in replay["cast"]}
    spies = spies_of(replay)
    spy = spies[0] if spies else None
    o = replay["meta"]["outcome"]
    speech = [e for e in replay["events"] if e["kind"] == "speech" and e.get("actor") in cast]
    scenes = [dict(t=0, zone="", title="Certification day", lines=[
        dict(who="narrator", kind="narration", pause=1.5, text="Unit 4. Certification day. Thirty people on shift, "
             "a bonus on the line, and one manager who has been working for someone else for years."),
        dict(who="narrator", kind="narration", pause=1, text=_mock_spy_intro(replay, cast))])]
    for h in highlights(replay):
        if h["title"] == "How it ended":
            continue
        lines = [dict(who="narrator", kind="narration", pause=0.8, text=h["text"])]
        near = [e for e in speech if h["t"] - 60 <= e["t"] <= h["t"] + 120 and e["actor"] not in spies
                and "Team reports" not in e["text"]][:2]
        lines += [dict(who=e["actor"], kind="say", pause=0.5, text=e["text"]) for e in near]
        st = next((th for th in replay["thoughts"] if th["agent"] == spy and abs(th["t"] - h["t"]) <= 300
                   and len(th.get("thought") or "") > 12), None)
        if st:
            lines.append(dict(who=spy, kind="thought", pause=1.5, text=st["thought"]))
        ev = next((e for e in replay["events"] if abs(e["t"] - h["t"]) < 30 and e.get("zone")), None)
        scenes.append(dict(t=h["t"], zone=(ev or {}).get("zone") or "", title=h["title"], lines=lines))
    last = next((th for th in reversed(replay["thoughts"]) if th["agent"] == spy and len(th.get("thought") or "") > 12), None)
    end = [dict(who="narrator", kind="narration", pause=2, text=o["text"])]
    if last:
        end.insert(1, dict(who=spy, kind="thought", pause=1.5, text=last["thought"]))
    scenes.append(dict(t=replay["meta"]["duration_s"], zone="", title="The reveal", lines=end))
    return dict(title="Unit 4", logline="One shift, one hidden spy.", scenes=scenes)


# ------------------------------------------------------------------ checking the script against the log
def _norm(s):
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower())


def clean(script: dict, replay: dict, writer: str) -> dict:
    cast = {c["id"] for c in replay["cast"]}
    zones = set(replay["zones"])
    said, thought = {}, {}
    for e in replay["events"]:
        if e["kind"] == "speech" and e.get("actor"):
            said.setdefault(e["actor"], []).append((_norm(e["text"]), e.get("channel") or "say"))
    for th in replay["thoughts"]:
        thought.setdefault(th["agent"], []).append(_norm(th.get("thought")))
    out, unverified = [], 0
    for sc in sorted(script.get("scenes", []), key=lambda s: s.get("t", 0)):
        lines = []
        for ln in sc.get("lines", []):
            who, kind, text = ln.get("who", "narrator"), ln.get("kind", "narration"), (ln.get("text") or "").strip()
            if not text or kind not in KINDS:
                continue
            if kind != "narration" and who not in cast:
                kind, who = "narration", "narrator"
            ok, channel = True, None
            if kind == "secret":        # the audience follows the spy openly now: a private thought is a thought
                kind = "thought"
            if kind != "narration":
                probe = _norm(text)[:40]
                if kind == "say":
                    hit = next((ch for s_, ch in said.get(who, []) if probe in s_), None)
                    ok, channel = hit is not None, hit
                else:
                    ok = any(probe in s_ for s_ in thought.get(who, []))
                unverified += not ok
            row = dict(who=who if kind != "narration" else "narrator", kind=kind, text=text,
                       pause=max(0.0, min(3.0, float(ln.get("pause") or 0))), verified=ok)
            if channel:
                row["channel"] = channel     # say, whisper, radio, exec, security, pa
            lines.append(row)
        if lines:
            out.append(dict(t=max(0.0, min(float(sc.get("t") or 0), replay["meta"]["duration_s"])),
                            zone=sc.get("zone") if sc.get("zone") in zones else "", title=sc.get("title", ""),
                            lines=lines))
    return dict(title=script.get("title") or "Unit 4", logline=script.get("logline", ""), writer=writer,
                unverified_quotes=unverified, scenes=out)


def script_markdown(movie: dict, replay: dict) -> str:
    """The movie as a readable script, for reading it aloud yourself as the narrator."""
    cast = {c["id"]: c for c in replay["cast"]}
    zones = replay["zones"]
    spies = spies_of(replay)
    spy = spies[0] if spies else None
    o = replay["meta"]["outcome"]
    who_in = []
    for sc in movie["scenes"]:
        for ln in sc["lines"]:
            if ln["who"] in cast and ln["who"] not in who_in:
                who_in.append(ln["who"])
    L = [f"# {movie['title']}", "", f"*{movie['logline']}*" if movie.get("logline") else "", "",
         f"MELTDOWN, seed {replay['meta']['seed']} ({replay['meta']['mode']} game). Ending: {o['result']}. "
         f"Script by {movie.get('writer', '?')}. Read the **NARRATOR** lines yourself; the others are the "
         "characters' own words from the game.", "",
         "Marks: *(beat)* a short silence, *(long beat)* a longer one. *(thinking)* means a private thought. "
         "*(paraphrased)* means the writer reworded a line it couldn't match word for word in the log.", "",
         "## Cast", ""]
    for pid in who_in:
        c = cast[pid]
        L.append(f"- **{c['name']}**, {c['role']}. {c['personality'].split('. ')[0]}."
                 + (" *(the spy)*" if pid in spies else ""))
    L += ["", "---", ""]
    for i, sc in enumerate(movie["scenes"], 1):
        place = zones.get(sc.get("zone") or "", {}).get("name", "Unit 4")
        L += [f"## Scene {i} · {_clock(sc['t'])} · {place}", f"### {sc['title']}", ""]
        for ln in sc["lines"]:
            mark = " *(paraphrased)*" if ln.get("verified") is False else ""
            if ln["kind"] == "narration":
                L.append(f"**NARRATOR:** {ln['text']}{mark}")
            elif ln["kind"] == "secret":
                L.append(f"**SOMEONE** *(thinking; this is {cast[ln['who']]['name']}, don't say so)*: "
                         f"{ln['text']}{mark}")
            else:
                name = cast.get(ln["who"], {}).get("name", ln["who"]).upper()
                L.append(f"**{name}**" + (" *(thinking)*" if ln["kind"] == "thought" else "")
                         + (f": \"{ln['text']}\"" if ln["kind"] == "say" else f": {ln['text']}") + mark)
            if ln.get("pause", 0) >= 2:
                L.append("*(long beat)*")
            elif ln.get("pause", 0) >= 1:
                L.append("*(beat)*")
            L.append("")
        L += ["---", ""]
    return "\n".join(L)


def make_movie(run, writer=None, model=None):
    path = run if run.endswith(".json") else os.path.join(run, "replay.json")
    with open(path) as fh:
        replay = json.load(fh)
    writer = writer or {"mock": "mock", "claude-code": "claude-code"}.get(replay["meta"]["mode"], "live")
    raw = (write_mock(replay) if writer == "mock" else write_with_claude_code(replay, model)
           if writer == "claude-code" else write_with_api(replay, model))
    movie = clean(raw, replay, writer)
    replay["movie"] = movie
    with open(path, "w") as fh:
        json.dump(replay, fh, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(os.path.dirname(path), "movie.json"), "w") as fh:
        json.dump(movie, fh, indent=1, ensure_ascii=False)
    with open(os.path.join(os.path.dirname(path), "script.md"), "w") as fh:
        fh.write(script_markdown(movie, replay))
    from .viewer import bundle
    html = bundle(path)
    return movie, html


def main(argv=None):
    ap = argparse.ArgumentParser(prog="meltdown.movie", description="Write the narrated movie for a finished game")
    ap.add_argument("run", nargs="?", default="runs/latest")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--mock", action="store_const", dest="writer", const="mock")
    g.add_argument("--live", action="store_const", dest="writer", const="live")
    g.add_argument("--claude-code", action="store_const", dest="writer", const="claude-code")
    ap.add_argument("--model", default=None, help=f"writer model (default {MODELS['director']})")
    a = ap.parse_args(argv)
    print("Writing the movie script (Claude is reading the whole game; this can take a few minutes) ...", flush=True)
    movie, html = make_movie(a.run, a.writer, a.model)
    n = sum(len(s["lines"]) for s in movie["scenes"])
    print(f"'{movie['title']}': {len(movie['scenes'])} scenes, {n} lines"
          + (f", {movie['unverified_quotes']} quotes not found word-for-word in the log" if movie["unverified_quotes"] else "")
          + f".\nOpen {html} and press 'Play the movie'. The script to read aloud yourself is "
          f"{os.path.join(os.path.dirname(html), 'script.md')}.")


if __name__ == "__main__":
    sys.exit(main())
