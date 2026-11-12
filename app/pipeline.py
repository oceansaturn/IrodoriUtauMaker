"""Runs Irodori-TTS and turns the results into single sounds."""
from __future__ import annotations

import os
import random
import re
import shlex
import shutil
import subprocess
import sys

import numpy as np

import core

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.environ.get("IRODORI_REPO", os.path.join(BASE, "Irodori-TTS"))
WORK = os.path.join(BASE, "work")
BANKS = os.path.join(BASE, "voicebanks")
CHECKPOINT = "Aratako/Irodori-TTS-v4.1-Small"
VOICE_TEXT = "こんにちは。今日はとてもいい天気ですね。一緒に楽しく歌を歌いましょう。"

_flags = None
STOP = {"now": False}


def safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', "_", (name or "").strip())
    return name or "MyVoice"


def supported_flags() -> set:
    """Ask infer.py which options it has. The answer is kept for later calls."""
    global _flags
    if _flags is None:
        try:
            p = subprocess.run([sys.executable, "infer.py", "--help"], cwd=REPO,
                               capture_output=True, timeout=600, env=_env())
            text = p.stdout.decode("utf-8", "replace") + p.stderr.decode("utf-8", "replace")
            _flags = set(re.findall(r"--[a-z][a-z0-9-]+", text))
        except Exception:
            _flags = set()
    return _flags


def _env():
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def run_infer(text, out_wav, ref_wav=None, caption=None, extra=""):
    """Generate one WAV with infer.py. Return (success, message)."""
    if not os.path.exists(os.path.join(REPO, "infer.py")):
        return False, "Irodori-TTS is not installed. Run 1_Install.bat first."
    os.makedirs(os.path.dirname(out_wav), exist_ok=True)
    if os.path.exists(out_wav):
        os.remove(out_wav)
    cmd = [sys.executable, "infer.py", "--hf-checkpoint", CHECKPOINT,
           "--text", text, "--output-wav", out_wav]
    if ref_wav:
        cmd += ["--ref-wav", ref_wav]
    else:
        cmd += ["--no-ref"]
    if caption:
        cmd += ["--caption", caption]
    if "--seed" in supported_flags() and "--seed" not in (extra or ""):
        cmd += ["--seed", str(random.randint(1, 2_000_000_000))]
    if extra and extra.strip():
        cmd += shlex.split(extra)
    # Show the Irodori-TTS output (download bars included) in the black window.
    print(f"\n--- Irodori-TTS: {text}", flush=True)
    tail = b""
    try:
        p = subprocess.Popen(cmd, cwd=REPO, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, env=_env())
        while True:
            chunk = p.stdout.read1(4096)
            if not chunk:
                break
            tail = (tail + chunk)[-6000:]
            try:
                sys.stdout.buffer.write(chunk)
                sys.stdout.flush()
            except Exception:
                pass
        p.wait(timeout=3600)
    except subprocess.TimeoutExpired:
        p.kill()
        return False, "The generation took more than 60 minutes. The tool stopped it."
    log = tail.decode("utf-8", "replace").strip()
    if p.returncode != 0 or not os.path.exists(out_wav):
        return False, "Irodori-TTS reported an error:\n" + log[-1500:]
    return True, ""


def make_voice(caption, extra=""):
    """Generate a sample sentence in a new voice from a description."""
    out = os.path.join(WORK, "_voice", f"voice_{random.randint(1000, 9999)}.wav")
    ok, msg = run_infer(VOICE_TEXT, out, caption=caption or None, extra=extra)
    return (out if ok else None), msg


STYLES = {
    "Low, calm and flat (recommended)": "低めの落ち着いた声で、静かに、平坦に、一定の高さでゆっくり発音する。",
    "Calm and flat": "落ち着いた声で、静かに、平坦に、一定の高さでゆっくり発音する。",
    "Soft and gentle": "やさしく、やわらかい声で、静かにゆっくり発音する。",
    "Clear and neutral": "はっきりとした普通の声で、感情を込めずに淡々と発音する。",
    "Bright and energetic": "明るく元気な声で、はっきりと発音する。",
    "No style (only the voice sample)": "",
}
TEXT_MODES = ["Long mark (かー)", "Double vowel (かあ)", "Short (か)"]
_VOWELS = {"a": "あ", "i": "い", "u": "う", "e": "え", "o": "お"}


def _spell(kana, romaji, long_vowel, mode):
    """Return the text that Irodori-TTS speaks for one sound."""
    if romaji in core.VCV_TEXT:
        return core.VCV_TEXT[romaji]
    if romaji in core.VC_TEXT:
        return core.VC_TEXT[romaji]
    if romaji in core.BREATH_TEXT:
        return core.BREATH_TEXT[romaji]
    if not long_vowel or mode == TEXT_MODES[2]:
        return kana
    if mode == TEXT_MODES[1] and romaji[-1] in _VOWELS:
        return kana + _VOWELS[romaji[-1]]
    return kana + "ー"


def _row_text(group, long_vowel, sep, mode):
    return sep.join(_spell(k, r, long_vowel, mode) for k, r in group) + "。"


# Pitch matching for the current job. target = wanted pitch in Hz (0 = off).
PITCH = {"target": 0.0, "tries": 1, "log": []}
PITCH_OK = 0.32            # log2(1.25): a take within 25 % of the target is good
PITCH_MODES = ["Off", "Normal (up to 3 takes for each row)", "Strong (up to 6 takes for each row)"]
PITCH_TRIES = dict(zip(PITCH_MODES, (0, 3, 6)))


def _score(res, target):
    """Smaller is better. 0 = perfect."""
    s = 0.0
    if target > 0:
        p = res.get("pitch", 0.0)
        s += abs(float(np.log2(p / target))) if p > 0 else 1.0
    reason = res.get("reason", "")
    if "very short" in reason:
        s += 0.5
    if "estimated" in reason or "not stable" in reason:
        s += 0.2
    return s


def _try_group(group, ref_wav, seg_dir, raw_dir, extra, attempts, style="", mode=TEXT_MODES[0]):
    """Generate a group of sounds and cut it.

    Return (success, error message, sounds that have no usable take).
    With pitch matching, the tool makes more takes and keeps the best take of each sound.
    """
    what = core.kind(group[0][1])
    breath = what == "breath"
    if breath:
        style = core.BREATH_STYLE
    target = 0.0 if breath else PITCH["target"]
    tries = max(1, PITCH["tries"]) if target > 0 else 1
    plan = [(lv, sep, mode) for lv, sep in attempts]
    # More takes for pitch matching. Other spellings give other results.
    variants = [(True, "。", TEXT_MODES[1]), (True, "、", mode), (True, "。", TEXT_MODES[0])]
    while len(plan) < tries + 1:
        plan.append(variants[len(plan) % 3])
    tag = "_".join(r for _, r in group)
    best = {}
    splits = 0
    for n, (long_vowel, sep, how) in enumerate(plan):
        if STOP["now"]:
            return False, "stopped", group
        raw = os.path.join(raw_dir, f"{tag}_{n}.wav")
        ok, msg = run_infer(_row_text(group, long_vowel, sep, how), raw, ref_wav=ref_wav,
                            caption=style or None, extra=extra)
        if not ok:
            return False, msg, group
        x = core.load_wav(raw)
        segs = core.find_segments(x, len(group), loose=breath)
        if segs is None:
            continue
        splits += 1
        for (s, e), (_, r) in zip(segs, group):
            cut = core.cut_with_padding(x, s, e)
            res = core.analyze(cut, r)
            if not res.get("ok"):
                continue
            score = _score(res, target)
            if r not in best or score < best[r][0]:
                best[r] = (score, cut, res.get("pitch", 0.0))
        complete = all(r in best for _, r in group)
        if complete and (target <= 0 or splits >= tries
                         or all(best[r][0] <= PITCH_OK for _, r in group)):
            break
    for kana, r in group:
        if r not in best:
            continue
        path = os.path.join(seg_dir, r + ".wav")
        if os.path.exists(path + ".old"):
            # A replacement must be better than the old sound.
            old = core.analyze(core.load_wav(path + ".old"), r)
            if old.get("ok") and _score(old, target) <= best[r][0]:
                continue
        core.save_wav(path, best[r][1])
    if target > 0 and best:
        PITCH["log"].append("   Pitch in Hz: " + ", ".join(
            f"{k} {best[r][2]:.0f}" for k, r in group if r in best) + f". Target {target:.0f}.")
    missing = [(k, r) for k, r in group if r not in best]
    return not missing, "", missing


ROW_ATTEMPTS = [(True, "。"), (True, "、"), (True, "。")]
SINGLE_ATTEMPTS = [(True, "。"), (True, "。"), (False, "。")]


def _restore_old(seg_dir, rows):
    """Put back each old sound that has no replacement. Return their kana."""
    kept = []
    for row in rows:
        for kana, romaji in row:
            path = os.path.join(seg_dir, romaji + ".wav")
            old = path + ".old"
            if os.path.exists(old):
                if os.path.exists(path):
                    os.remove(old)
                else:
                    os.replace(old, path)
                    kept.append(kana)
    return kept


def generate(name, ref_wav, set_name, skip_done=True, extra="", style="", mode=TEXT_MODES[0],
             breaths=False, tries=0, target_hz=0.0, short=True):
    """Generate every sound of the set. Yields progress messages."""
    seg_dir = os.path.join(WORK, safe_name(name), "sounds")
    set_name = core.set_name_fix(set_name)
    try:
        yield from _generate(name, ref_wav, set_name, skip_done, extra, style, mode, breaths,
                             tries, target_hz, short)
    finally:
        _restore_old(seg_dir, core.rows_for(set_name, breaths))


def _drain_pitch_log():
    lines, PITCH["log"] = PITCH["log"], []
    return lines


def _generate(name, ref_wav, set_name, skip_done, extra, style, mode, breaths, tries, target_hz,
              short=True):
    STOP["now"] = False
    name = safe_name(name)
    rows = core.rows_for(set_name, breaths)
    seg_dir = os.path.join(WORK, name, "sounds")
    raw_dir = os.path.join(WORK, name, "raw")
    os.makedirs(seg_dir, exist_ok=True)
    os.makedirs(raw_dir, exist_ok=True)
    # Keep a private copy of the voice. The upload folder can be temporary.
    ref_copy = os.path.join(WORK, name, "reference.wav")
    if ref_wav and os.path.abspath(ref_wav) != os.path.abspath(ref_copy):
        shutil.copyfile(ref_wav, ref_copy + ".tmp")
        os.replace(ref_copy + ".tmp", ref_copy)
    if not os.path.exists(ref_copy):
        yield "ERROR. This voicebank has no saved voice. Do step 1 first."
        return
    target = 0.0
    if tries:
        target = float(target_hz or 0) or core.voice_pitch(ref_copy)
        if target > 0:
            yield (f"Pitch matching is on. Target pitch: {target:.0f} Hz. "
                   "The tool keeps the take of each sound that is nearest to this pitch.")
        else:
            yield "The tool found no pitch in the voice sample. Pitch matching is off."
    PITCH.update(target=target, tries=int(tries or 1), log=[])
    save_project(name, set_name, extra, style, mode, breaths, tries, target_hz, target, short)

    total = sum(len(r) for r in rows)
    done = 0
    for row in rows:
        todo = [(k, r) for k, r in row
                if not (skip_done and os.path.exists(os.path.join(seg_dir, r + ".wav")))]
        done += len(row) - len(todo)
        if not todo:
            continue
        label = " ".join(k for k, _ in todo)
        yield f"[{done}/{total}] Generating: {label}"
        ok, msg, missing = _try_group(todo, ref_copy, seg_dir, raw_dir, extra, ROW_ATTEMPTS,
                                      style, mode)
        yield from _drain_pitch_log()
        if msg and msg != "stopped":
            yield "ERROR. " + msg
            return
        if not ok and not STOP["now"] and len(todo) > 1:
            yield ("   No usable take for: " + " ".join(k for k, _ in missing)
                   + ". The tool now makes each of these sounds alone.")
            for item in missing:
                ok1, msg, _ = _try_group([item], ref_copy, seg_dir, raw_dir, extra,
                                         SINGLE_ATTEMPTS, style, mode)
                yield from _drain_pitch_log()
                if msg and msg != "stopped":
                    yield "ERROR. " + msg
                    return
                if not ok1 and not STOP["now"]:
                    yield f"   {item[0]} failed. Regenerate it later in step 3."
        if STOP["now"]:
            yield "Stopped. Click Build again to continue from this point."
            return
        done += len(todo)
    kept = _restore_old(seg_dir, rows)
    if kept:
        yield "   No good replacement for: " + " ".join(kept) + ". The old sounds stay."
    yield f"[{total}/{total}] Generation complete. Building the voicebank files."
    yield finalize(name, set_name)


def _rows(name, set_name):
    """Rows of a saved voicebank. The breath option comes from its saved settings."""
    info = project_info(name)
    return core.rows_for(set_name, bool(info and info.get("breaths")))


def finalize(name, set_name):
    name = safe_name(name)
    btype = core.bank_type(set_name)
    rep = core.build_bank(os.path.join(WORK, name, "sounds"),
                          os.path.join(BANKS, name), name, _rows(name, set_name), btype,
                          float((project_info(name) or {}).get("target") or 0),
                          bool((project_info(name) or {}).get("short", True)))
    msg = [f"DONE. The {btype} voicebank has {rep['count']} sounds.",
           f"Zip file: {rep['zip']}",
           f"In OpenUtau, select the {core.PHONEMIZER[btype]}."]
    with open(os.path.join(WORK, name, "flagged.json"), "w", encoding="utf-8") as f:
        json.dump(rep["flagged"], f, ensure_ascii=False)
    if rep["flagged"]:
        msg.append(f"PITCH: {rep.get('in_range')} of {rep.get('with_pitch')} sounds are within "
                   f"25 % of {rep.get('typical_pitch')} Hz. Typical pitch of this voicebank: "
                   f"{rep.get('median_pitch')} Hz.")
        shown = rep["flagged"][:60]
        more = len(rep["flagged"]) - len(shown)
        msg.append(f"Sounds with a different pitch (possibly shouted), {len(rep['flagged'])} in all: "
                   + ", ".join(shown) + (f", and {more} more." if more else "."))
        msg.append('Click "Make the flagged sounds again" in step 3 to replace them.')
    if rep["check"]:
        shown = rep["check"][:40]
        more = len(rep["check"]) - len(shown)
        msg.append("Listen to these sounds in step 3: " + ", ".join(shown)
                   + (f", and {more} more." if more else "."))
    if rep["missing"]:
        msg.append("Missing sounds: " + " ".join(rep["missing"]))
    return "\n".join(msg)


def regenerate_one(name, set_name, kana, extra="", style="", mode=TEXT_MODES[0]):
    """Make one sound again and rebuild the voicebank."""
    STOP["now"] = False
    name = safe_name(name)
    item = next(((k, r) for row in _rows(name, set_name) for k, r in row if k == kana), None)
    ref = os.path.join(WORK, name, "reference.wav")
    if item is None or not os.path.exists(ref):
        return None, "Build the voicebank first (step 2)."
    seg_dir = os.path.join(WORK, name, "sounds")
    info = project_info(name) or {}
    PITCH.update(target=float(info.get("target") or 0), tries=int(info.get("tries") or 1), log=[])
    ok, msg, _ = _try_group([item], ref, seg_dir, os.path.join(WORK, name, "raw"), extra,
                            SINGLE_ATTEMPTS, style, mode)
    if not ok:
        return None, msg or f"{kana} failed again. Click the button again."
    return sound_path(name, kana, set_name), finalize(name, set_name)


def sound_path(name, kana, set_name):
    name = safe_name(name)
    for row in _rows(name, set_name):
        for k, r in row:
            if k == kana:
                p = os.path.join(BANKS, name, r + ".wav")
                return p if os.path.exists(p) else None
    return None


# ------------------------------------------------------- background build job
# The build runs in its own thread. The browser page only reads JOB, so a lost
# browser connection cannot hide the result.
import threading  # noqa: E402

JOB = {"running": False, "status": "Idle. No build is running.", "lines": [], "zip": None}


def open_folder(path):
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception:
        pass


def flagged_sounds(name):
    try:
        with open(os.path.join(WORK, safe_name(name), "flagged.json"), encoding="utf-8") as f:
            return list(json.load(f))
    except Exception:
        return []


def _job(name, ref_wav, set_name, skip_done, extra, style, mode, redo, breaths, tries, target_hz,
         short=True):
    try:
        # Set the old sounds aside. The build then makes only these sounds.
        for row in (core.rows_for(set_name, breaths) if redo else []):
            for kana, romaji in row:
                path = os.path.join(WORK, safe_name(name), "sounds", romaji + ".wav")
                if kana in redo and os.path.exists(path):
                    os.replace(path, path + ".old")  # kept as a backup
        for line in generate(name, ref_wav, set_name, skip_done, extra, style, mode, breaths,
                             tries, target_hz, short):
            JOB["lines"].append(line)
            print(line, flush=True)
            if line.startswith("["):
                JOB["status"] = "WORKING. " + line
        last = JOB["lines"][-1] if JOB["lines"] else ""
        if last.startswith("DONE"):
            zip_path = os.path.join(BANKS, safe_name(name) + ".zip")
            JOB["zip"] = zip_path if os.path.exists(zip_path) else None
            JOB["status"] = "FINISHED. The voicebank is ready. The folder is open in File Explorer."
            open_folder(BANKS)
        elif last.startswith("Stopped"):
            JOB["status"] = "STOPPED. Click Build voicebank to continue."
        else:
            JOB["status"] = "FAILED. Read the Progress box."
    except Exception as exc:  # show every failure in the page
        JOB["lines"].append(f"ERROR. {type(exc).__name__}: {exc}")
        JOB["status"] = "FAILED. Read the Progress box."
    finally:
        JOB["running"] = False
        print("=== " + JOB["status"] + " ===", flush=True)


def start_job(name, ref_wav, set_name, skip_done=True, extra="", style="",
              mode=TEXT_MODES[0], redo=(), breaths=False, tries=0, target_hz=0.0, short=True):
    """Start a build in the background. Return False if a build is running."""
    if JOB["running"]:
        return False
    JOB.update(running=True, status="WORKING. Starting ...", lines=[], zip=None)
    threading.Thread(target=_job,
                     args=(name, ref_wav, set_name, skip_done, extra, style, mode, list(redo),
                           bool(breaths), int(tries or 0), float(target_hz or 0), bool(short)),
                     daemon=True).start()
    return True


def job_view():
    return "### Status: " + JOB["status"], "\n".join(JOB["lines"][-40:])


# ------------------------------------------------------------ saved projects
# Each voicebank keeps its settings, its voice and its finished sounds in the
# "work" folder. After a crash, the tool reads them and continues.
import json  # noqa: E402


def save_project(name, set_name, extra="", style="", mode=TEXT_MODES[0], breaths=False,
                 tries=0, target_hz=0.0, target=0.0, short=True):
    name = safe_name(name)
    data = {"name": name, "set_name": set_name, "extra": extra or "",
            "style": style or "", "mode": mode, "breaths": bool(breaths),
            "tries": int(tries or 0), "target_hz": float(target_hz or 0), "target": float(target),
            "short": bool(short)}
    for path in (os.path.join(WORK, name, "project.json"), os.path.join(WORK, "last.json")):
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(path + ".tmp", path)


def project_info(name):
    """Return the saved settings and the progress of one voicebank, or None."""
    name = safe_name(name)
    folder = os.path.join(WORK, name)
    ref = os.path.join(folder, "reference.wav")
    if not os.path.exists(ref):
        return None
    data = {"name": name, "set_name": list(core.SETS.keys())[0], "extra": "",
            "style": list(STYLES.values())[0], "mode": TEXT_MODES[0], "breaths": False,
            "tries": 3, "target_hz": 0.0, "target": 0.0, "short": True}
    try:
        with open(os.path.join(folder, "project.json"), encoding="utf-8") as f:
            data.update(json.load(f))
    except Exception:
        pass
    if data["mode"] not in TEXT_MODES:
        data["mode"] = TEXT_MODES[0]
    data["set_name"] = core.set_name_fix(data["set_name"])
    items = [r for row in core.rows_for(data["set_name"], data.get("breaths")) for _, r in row]
    data["done"] = sum(os.path.exists(os.path.join(folder, "sounds", r + ".wav")) for r in items)
    data["total"] = len(items)
    data["ref"] = ref
    return data


def last_project():
    try:
        with open(os.path.join(WORK, "last.json"), encoding="utf-8") as f:
            return project_info(json.load(f)["name"])
    except Exception:
        return None


def list_projects():
    if not os.path.isdir(WORK):
        return []
    return sorted(n for n in os.listdir(WORK)
                  if os.path.exists(os.path.join(WORK, n, "reference.wav")))
