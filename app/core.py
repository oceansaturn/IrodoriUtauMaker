"""Audio analysis for Irodori UTAU Maker.

This module splits generated speech into single sounds, measures the timing
of each sound, and writes the files that OpenUtau reads (WAV + oto.ini).
It needs only numpy and scipy.
"""
from __future__ import annotations

import os
import zipfile

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

OUT_SR = 44100

# ---------------------------------------------------------------- kana tables
# Each row is spoken in one generation. Entry: (kana, file name / romaji).
BASIC_ROWS = [
    [("あ", "a"), ("い", "i"), ("う", "u"), ("え", "e"), ("お", "o")],
    [("か", "ka"), ("き", "ki"), ("く", "ku"), ("け", "ke"), ("こ", "ko")],
    [("さ", "sa"), ("し", "shi"), ("す", "su"), ("せ", "se"), ("そ", "so")],
    [("た", "ta"), ("ち", "chi"), ("つ", "tsu"), ("て", "te"), ("と", "to")],
    [("な", "na"), ("に", "ni"), ("ぬ", "nu"), ("ね", "ne"), ("の", "no")],
    [("は", "ha"), ("ひ", "hi"), ("ふ", "fu"), ("へ", "he"), ("ほ", "ho")],
    [("ま", "ma"), ("み", "mi"), ("む", "mu"), ("め", "me"), ("も", "mo")],
    [("や", "ya"), ("ゆ", "yu"), ("よ", "yo"), ("わ", "wa"), ("ん", "n")],
    [("ら", "ra"), ("り", "ri"), ("る", "ru"), ("れ", "re"), ("ろ", "ro")],
    [("が", "ga"), ("ぎ", "gi"), ("ぐ", "gu"), ("げ", "ge"), ("ご", "go")],
    [("ざ", "za"), ("じ", "ji"), ("ず", "zu"), ("ぜ", "ze"), ("ぞ", "zo")],
    [("だ", "da"), ("で", "de"), ("ど", "do")],
    [("ば", "ba"), ("び", "bi"), ("ぶ", "bu"), ("べ", "be"), ("ぼ", "bo")],
    [("ぱ", "pa"), ("ぴ", "pi"), ("ぷ", "pu"), ("ぺ", "pe"), ("ぽ", "po")],
    [("きゃ", "kya"), ("きゅ", "kyu"), ("きょ", "kyo")],
    [("しゃ", "sha"), ("しゅ", "shu"), ("しょ", "sho")],
    [("ちゃ", "cha"), ("ちゅ", "chu"), ("ちょ", "cho")],
    [("にゃ", "nya"), ("にゅ", "nyu"), ("にょ", "nyo")],
    [("ひゃ", "hya"), ("ひゅ", "hyu"), ("ひょ", "hyo")],
    [("みゃ", "mya"), ("みゅ", "myu"), ("みょ", "myo")],
    [("りゃ", "rya"), ("りゅ", "ryu"), ("りょ", "ryo")],
    [("ぎゃ", "gya"), ("ぎゅ", "gyu"), ("ぎょ", "gyo")],
    [("じゃ", "ja"), ("じゅ", "ju"), ("じょ", "jo")],
    [("びゃ", "bya"), ("びゅ", "byu"), ("びょ", "byo")],
    [("ぴゃ", "pya"), ("ぴゅ", "pyu"), ("ぴょ", "pyo")],
]

EXTRA_ROWS = [
    [("ふぁ", "fa"), ("ふぃ", "fi"), ("ふぇ", "fe"), ("ふぉ", "fo")],
    [("てぃ", "ti"), ("とぅ", "tu"), ("でぃ", "di"), ("どぅ", "du")],
    [("うぃ", "wi"), ("うぇ", "we"), ("うぉ", "wo")],
    [("しぇ", "she"), ("じぇ", "je"), ("ちぇ", "che")],
    [("つぁ", "tsa"), ("つぃ", "tsi"), ("つぇ", "tse"), ("つぉ", "tso")],
]

TEST_ROWS = [BASIC_ROWS[0]]

# Extra kana that reuse an existing sound: (alias, romaji of the source file).
SHARED = [("を", "o"), ("ぢ", "ji"), ("づ", "zu")]

# ---- CVVC: vowel-to-consonant transitions (VC) ----
# (consonant name, katakana syllable that starts with this consonant)
VC_CONSONANTS = [
    ("k", "カ"), ("ky", "キャ"), ("g", "ガ"), ("gy", "ギャ"), ("s", "サ"), ("sh", "シャ"),
    ("z", "ザ"), ("j", "ジャ"), ("t", "タ"), ("ch", "チャ"), ("ts", "ツ"), ("d", "ダ"),
    ("n", "ナ"), ("ny", "ニャ"), ("h", "ハ"), ("hy", "ヒャ"), ("f", "フ"), ("b", "バ"),
    ("by", "ビャ"), ("p", "パ"), ("py", "ピャ"), ("m", "マ"), ("my", "ミャ"), ("y", "ヤ"),
    ("r", "ラ"), ("ry", "リャ"), ("w", "ワ"),
]
VC_VOWELS = [("a", "ア"), ("i", "イ"), ("u", "ウ"), ("e", "エ"), ("o", "オ"), ("n", "ン")]
# Entry: (alias, file name). Example: ("a k", "vc_a_k"). One row for each consonant.
VC_ROWS = [[(f"{v} {c}", f"vc_{v}_{c}") for v, _ in VC_VOWELS] for c, _ in VC_CONSONANTS]
VC_TEXT = {f"vc_{v}_{c}": vk + ck for c, ck in VC_CONSONANTS for v, vk in VC_VOWELS}

# ---- VCV: each kana after each vowel. Entry: ("a か", "vcv_a_ka"). ----
def _katakana(text):
    return "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in text)


def _vcv_rows(cv_rows):
    return [[(f"{v} {kana}", f"vcv_{v}_{romaji}") for v, _ in VC_VOWELS]
            for row in cv_rows for kana, romaji in row]


# Text for Irodori-TTS. Katakana stops the particle readings of は and へ.
# The long mark makes the second vowel long. Example: "アカー".
VCV_TEXT = {f"vcv_{v}_{romaji}": vk + _katakana(kana) + "ー"
            for row in BASIC_ROWS + EXTRA_ROWS for kana, romaji in row for v, vk in VC_VOWELS}
VCV_CV = {f"vcv_{v}_{romaji}": romaji
          for row in BASIC_ROWS + EXTRA_ROWS for _, romaji in row for v, _ in VC_VOWELS}

# ---- Breaths. Entry: (alias, file name). The text is what Irodori-TTS speaks. ----
BREATH_ROWS = [[("br1", "br1")], [("br2", "br2")], [("br3", "br3")], [("br4", "br4")]]
BREATH_TEXT = {"br1": "はぁ…", "br2": "すぅ…", "br3": "ふぅ…", "br4": "はっ…"}
BREATH_STYLE = "声を出さずに、息だけで、ささやくように静かに息をする。"

SETS = {
    "Quick test - CV (5 sounds: a i u e o)": TEST_ROWS,
    "CV - Basic Japanese (recommended for a first voicebank)": BASIC_ROWS,
    "CV - Extended (Basic + fa, ti, wi, she ...)": BASIC_ROWS + EXTRA_ROWS,
    "CVVC - Basic Japanese (CV sounds + 162 vowel-consonant transitions)": BASIC_ROWS + VC_ROWS,
    "CVVC - Extended (CV Extended + 162 vowel-consonant transitions)":
        BASIC_ROWS + EXTRA_ROWS + VC_ROWS,
    "VCV - Basic Japanese (CV sounds + 606 vowel-to-kana transitions, long build)":
        BASIC_ROWS + _vcv_rows(BASIC_ROWS),
    "VCV - Extended (CV Extended + 714 vowel-to-kana transitions, long build)":
        BASIC_ROWS + EXTRA_ROWS + _vcv_rows(BASIC_ROWS + EXTRA_ROWS),
}
# Names from older versions of the tool.
OLD_SET_NAMES = {
    "Quick test (5 sounds: a i u e o)": 0,
    "Basic Japanese (recommended)": 1,
    "Extended (Basic + fa, ti, wi, she ...)": 2,
}


def set_name_fix(set_name):
    """Return a valid sound set name. Old names change to the new names."""
    names = list(SETS.keys())
    if set_name in SETS:
        return set_name
    return names[OLD_SET_NAMES.get(set_name, 0)]


def bank_type(set_name):
    """Return "CV", "CVVC" or "VCV"."""
    name = set_name_fix(set_name)
    return "CVVC" if name.startswith("CVVC") else "VCV" if name.startswith("VCV") else "CV"


PHONEMIZER = {"CV": "default phonemizer", "CVVC": "JA CVVC phonemizer",
              "VCV": "JA VCV phonemizer"}


def rows_for(set_name, breaths=False):
    rows = list(SETS[set_name_fix(set_name)])
    return rows + BREATH_ROWS if breaths else rows


def kind(file_name):
    if file_name.startswith("vcv_"):
        return "vcv"
    if file_name.startswith("vc_"):
        return "vc"
    if file_name.startswith("br"):
        return "breath"
    return "cv"


def sound_class(romaji: str) -> str:
    """Return the consonant family. The family sets the timing limits."""
    if romaji in ("a", "i", "u", "e", "o", "n"):
        return "vowel"
    head = romaji[:-1]
    if head in ("s", "sh", "h", "f", "hy"):
        return "fricative"
    if head in ("k", "t", "p", "ch", "ts", "ky", "py"):
        return "plosive"
    if head in ("g", "d", "b", "gy", "by"):
        return "voiced_plosive"
    if head in ("z", "j"):
        return "voiced_fricative"
    if head in ("n", "m", "ny", "my"):
        return "nasal"
    if head in ("r", "ry"):
        return "liquid"
    return "glide"  # y, w


# (minimum, default, maximum) consonant length in ms, by family.
PRE_LIMITS = {
    "plosive": (25, 60, 150),
    "voiced_plosive": (20, 50, 130),
    "fricative": (50, 110, 260),
    "voiced_fricative": (40, 90, 220),
    "nasal": (30, 70, 170),
    "liquid": (20, 45, 120),
    "glide": (30, 70, 180),
}


# ------------------------------------------------------------------ audio IO
def load_wav(path: str):
    """Read a WAV file. Return mono float32 audio at 44.1 kHz."""
    sr, data = wavfile.read(path)
    if data.dtype.kind == "i":
        data = data.astype(np.float32) / float(np.iinfo(data.dtype).max)
    elif data.dtype.kind == "u":
        data = (data.astype(np.float32) - 128.0) / 128.0
    else:
        data = data.astype(np.float32)
    if data.ndim > 1:
        data = data.mean(axis=1)
    if sr != OUT_SR:
        g = np.gcd(int(sr), OUT_SR)
        data = resample_poly(data, OUT_SR // g, int(sr) // g).astype(np.float32)
    return data


def save_wav(path: str, x: np.ndarray):
    x = np.clip(x, -1.0, 1.0)
    # Write to a temporary file first. A crash cannot leave a damaged WAV.
    tmp = path + ".tmp"
    wavfile.write(tmp, OUT_SR, (x * 32767.0).astype(np.int16))
    os.replace(tmp, path)


def frame_rms(x: np.ndarray, hop: int, win: int) -> np.ndarray:
    n = max(1, 1 + (len(x) - win) // hop) if len(x) >= win else 1
    out = np.zeros(n, dtype=np.float32)
    for i in range(n):
        seg = x[i * hop: i * hop + win]
        out[i] = np.sqrt(np.mean(seg * seg) + 1e-12)
    return out


# --------------------------------------------------------------- segmentation
def _regions(active: np.ndarray, min_gap: int, min_len: int):
    regs = []
    start = None
    for i, a in enumerate(active):
        if a and start is None:
            start = i
        elif not a and start is not None:
            regs.append([start, i])
            start = None
    if start is not None:
        regs.append([start, len(active)])
    merged = []
    for r in regs:
        if merged and r[0] - merged[-1][1] < min_gap:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [r for r in merged if r[1] - r[0] >= min_len]


def find_segments(x: np.ndarray, expected: int, loose: bool = False):
    """Split audio at the pauses. Return `expected` (start, end) sample pairs.

    Return None when the number of sounds is not the expected number.
    With loose=True, return one pair from the first sound to the last sound.
    """
    hop = OUT_SR // 200  # 5 ms
    win = hop * 4
    rms = frame_rms(x, hop, win)
    peak = float(rms.max())
    if peak < 1e-4:
        return None
    floor = float(np.percentile(rms, 10))
    thr = max(peak * 0.02, floor * 3.0)
    active = rms > thr
    if loose:
        on = np.where(active)[0]
        if len(on) < 20:
            return None
        return [(int(on[0]) * hop, min(len(x), int(on[-1]) * hop + win))]
    for gap_ms in (150, 220, 100, 320, 60, 450):
        regs = _regions(active, gap_ms // 5, 60 // 5)
        if len(regs) == expected:
            return [(r[0] * hop, min(len(x), r[1] * hop + win)) for r in regs]
    return None


def cut_with_padding(x: np.ndarray, start: int, end: int, pad_ms: int = 60):
    pad = OUT_SR * pad_ms // 1000
    a = max(0, start - pad)
    b = min(len(x), end + pad)
    seg = x[a:b].copy()
    # Short fades stop clicks at the cut points.
    f = min(len(seg) // 4, OUT_SR * 5 // 1000)
    if f > 1:
        ramp = np.linspace(0.0, 1.0, f, dtype=np.float32)
        seg[:f] *= ramp
        seg[-f:] *= ramp[::-1]
    return seg


# ------------------------------------------------------------------- auto oto
def _band_spectra(x: np.ndarray, hop: int, win: int, nbands: int = 24):
    n = max(1, 1 + (len(x) - win) // hop)
    window = np.hanning(win).astype(np.float32)
    freqs = np.fft.rfftfreq(win, 1.0 / OUT_SR)
    edges = np.geomspace(100.0, 8000.0, nbands + 1)
    idx = [np.where((freqs >= edges[i]) & (freqs < edges[i + 1]))[0] for i in range(nbands)]
    out = np.zeros((n, nbands), dtype=np.float32)
    for i in range(n):
        seg = x[i * hop: i * hop + win]
        if len(seg) < win:
            seg = np.pad(seg, (0, win - len(seg)))
        mag = np.abs(np.fft.rfft(seg * window)) ** 2
        for b, ii in enumerate(idx):
            out[i, b] = 10.0 * np.log10(mag[ii].mean() + 1e-10) if len(ii) else -100.0
    return out


def analyze_breath(x: np.ndarray) -> dict:
    """Measure a breath. Most of the breath is fixed, so OpenUtau does not loop it."""
    hop = OUT_SR // 200
    rms = frame_rms(x, hop, hop * 5)
    above = np.where(rms > max(float(rms.max()) * 0.05, 1e-4))[0]
    if len(above) < 30:
        return {"ok": False, "reason": "breath too short or silent"}
    onset, last = int(above[0]), int(above[-1])
    offset_ms = max(0.0, onset * 5.0 - 10.0)
    length = last * 5.0 - offset_ms
    return {"ok": True, "reason": "", "offset": round(offset_ms, 1),
            "consonant": round(length - 30.0, 1), "cutoff": round(-length, 1),
            "preutterance": 10.0, "overlap": 5.0,
            "steady_rms": float(np.median(rms[onset:last + 1])), "pitch": 0.0}


def analyze_vc(x: np.ndarray) -> dict:
    """Measure a vowel-consonant-vowel sound. Return oto numbers for the VC part.

    The VC part starts in the first vowel and stops in the consonant.
    """
    hop = OUT_SR // 200
    win = hop * 5
    ms = 5.0
    rms = frame_rms(x, hop, win)
    above = np.where(rms > max(float(rms.max()) * 0.03, 1e-4))[0]
    if len(above) < 24:
        return {"ok": False, "reason": "too short or silent"}
    onset, last = int(above[0]), int(above[-1])
    span = last - onset
    spec = _band_spectra(x, hop, win)
    spec = spec - spec.mean(axis=1, keepdims=True)
    n = min(len(rms), len(spec))
    rms, spec = rms[:n], spec[:n]
    last = min(last, n - 1)

    def edge(ref_a, ref_b, frames):
        """First frame in `frames` that stops being like the reference vowel."""
        ref = spec[ref_a:ref_b].mean(axis=0)
        level = float(np.median(rms[ref_a:ref_b]))
        dist = np.abs(spec - ref).mean(axis=1)
        limit = max(1.6 * float(np.percentile(dist[ref_a:ref_b], 90)), 4.0)
        run = 0
        for i in frames:
            run = run + 1 if (dist[i] > limit or rms[i] < 0.4 * level) else 0
            if run >= 3:
                return i, level
        return None, level

    a0 = onset + 3
    c_start, v1_level = edge(a0, a0 + 8, range(a0 + 8, last - 6))
    b1 = last - 4
    back, _ = edge(b1 - 8, b1, range(b1 - 9, onset + 8, -1))
    notes = []
    if c_start is not None:
        c_start -= 2                     # first frame of the run
    if back is not None:
        v2_start = back + 3              # first vowel frame after the consonant
    if (c_start is None or back is None or v2_start - c_start < 4
            or v2_start - c_start > 70 or c_start - onset < 8):
        notes.append("transition estimated")
        c_start = onset + int(span * 0.45)
        v2_start = onset + int(span * 0.62)
    cons_len = (v2_start - c_start) * ms
    end_ms = c_start * ms + min(max(cons_len * 0.7, 30.0), 150.0)
    offset_ms = max(onset * ms + 15.0, c_start * ms - 150.0)
    pre = c_start * ms - offset_ms
    length = end_ms - offset_ms
    return {"ok": True, "reason": ", ".join(notes), "offset": round(offset_ms, 1),
            "consonant": round(length - 10.0, 1), "cutoff": round(-length, 1),
            "preutterance": round(pre, 1), "overlap": round(min(pre * 0.5, 80.0), 1),
            "steady_rms": v1_level, "pitch": _region_pitch(x, hop, a0, max(a0 + 4, c_start))}


def analyze_vcv(x: np.ndarray, file_name: str) -> dict:
    """Measure a vowel + kana sound, for example "a か". Return oto numbers.

    The sound has three parts: first vowel, consonant, second vowel.
    The tool finds the end of the first vowel. It then measures the rest as a CV sound.
    """
    romaji = VCV_CV[file_name]
    cls = sound_class(romaji)
    hop = OUT_SR // 200
    win = hop * 5
    ms = 5.0
    rms = frame_rms(x, hop, win)
    above = np.where(rms > max(float(rms.max()) * 0.03, 1e-4))[0]
    if len(above) < 40:
        return {"ok": False, "reason": "too short or silent"}
    onset, last = int(above[0]), int(above[-1])
    span = last - onset
    notes = []
    c_start = None
    if cls in ("plosive", "fricative"):
        # Unvoiced consonant: the first vowel stops where the voice stops.
        f0 = pitch_track(x, hop)
        i = onset
        while i < min(onset + 14, len(f0)) and f0[i] <= 0:
            i += 1
        j = i
        while j < len(f0) and (f0[j] > 0 or (j + 1 < len(f0) and f0[j + 1] > 0)):
            j += 1
        if j - onset >= 8 and j < onset + span * 0.6:
            c_start = j
    if c_start is None:
        spec = _band_spectra(x, hop, win)
        spec = spec - spec.mean(axis=1, keepdims=True)
        n = min(len(rms), len(spec))
        a0 = onset + 3
        if c_start is None and a0 + 8 < n:
            ref = spec[a0:a0 + 8].mean(axis=0)
            level = float(np.median(rms[a0:a0 + 8]))
            dist = np.abs(spec[:n] - ref).mean(axis=1)
            limit = max(1.6 * float(np.percentile(dist[a0:a0 + 8], 90)), 4.0)
            run = 0
            for i in range(a0 + 8, min(n, onset + int(span * 0.6))):
                run = run + 1 if (dist[i] > limit or rms[i] < 0.4 * level) else 0
                if run >= 3:
                    c_start = i - 2
                    break
    if c_start is None or c_start - onset < 8:
        notes.append("transition estimated")
        c_start = onset + min(int(span * 0.3), 30)
    # Measure the consonant and the second vowel as a CV sound.
    cut = c_start * hop
    tail = analyze(x[cut:], romaji)
    if "offset" not in tail:
        return {"ok": False, "reason": tail.get("reason", "second vowel not found")}
    c_ms = c_start * ms
    v2_ms = c_ms + (30.0 if cls == "vowel" else tail["v_ms"])
    offset_ms = max(onset * ms + 10.0, c_ms - 100.0)
    pre = v2_ms - offset_ms
    end_ms = c_ms + tail["offset"] - tail["cutoff"]
    fixed = pre + max(tail["consonant"] - tail["preutterance"], 30.0)
    length = end_ms - offset_ms
    if tail["reason"]:
        notes.append(tail["reason"])
    return {"ok": tail["ok"] and length - fixed >= 80.0,
            "reason": ", ".join(notes) if length - fixed >= 80.0 else "vowel too short",
            "offset": round(offset_ms, 1), "consonant": round(fixed, 1),
            "cutoff": round(-length, 1), "preutterance": round(pre, 1),
            "overlap": round(max(min(c_ms - offset_ms, 100.0) * 0.8, 10.0), 1),
            "steady_rms": tail["steady_rms"], "pitch": tail["pitch"]}


def pitch_track(x: np.ndarray, hop: int) -> np.ndarray:
    """Return the pitch (Hz) of each 5 ms frame. 0 = no clear pitch."""
    step = 4                                  # work at 11025 Hz: faster
    y = x[::step].astype(np.float64)
    sr = OUT_SR // step
    size = sr * 40 // 1000
    lo, hi = sr // 600, sr // 60
    n = max(1, 1 + (len(x) - hop * 5) // hop) if len(x) >= hop * 5 else 1
    out = np.zeros(n, dtype=np.float32)
    for i in range(n):
        c = (i * hop + hop * 5 // 2) // step
        seg = y[max(0, c - size // 2): c + size // 2]
        if len(seg) < size - 2:
            continue
        seg = seg - seg.mean()
        ac = np.correlate(seg, seg, mode="full")[len(seg) - 1:]
        if ac[0] <= 1e-9:
            continue
        r = ac[: hi + 1] / ac[0]
        best = float(r[lo:hi].max())
        if best < 0.45:
            continue
        # Take the shortest period that is nearly as good as the best period.
        # This stops errors of one octave.
        for lag in range(lo, hi):
            if r[lag] >= 0.85 * best and r[lag] >= r[lag - 1] and r[lag] >= r[lag + 1]:
                out[i] = sr / lag
                break
    return out


def _region_pitch(x, hop, f_a, f_b) -> float:
    f0 = pitch_track(x, hop)[f_a:f_b]
    f0 = f0[f0 > 0]
    return float(np.median(f0)) if len(f0) else 0.0


def voice_pitch(path: str) -> float:
    """Return the typical pitch (Hz) of a recording, or 0."""
    try:
        f0 = pitch_track(load_wav(path), OUT_SR // 200)
    except Exception:
        return 0.0
    f0 = f0[f0 > 0]
    return float(np.median(f0)) if len(f0) >= 20 else 0.0


def _median3(v: np.ndarray) -> np.ndarray:
    p = np.pad(v, 1, mode="edge")
    return np.median(np.stack([p[:-2], p[1:-1], p[2:]]), axis=0)


# Consonant time (ms) that the "short" mode keeps before the vowel.
SHORT_KEEP = {"fricative": 70.0, "voiced_fricative": 60.0, "voiced_plosive": 45.0,
              "nasal": 50.0, "liquid": 40.0, "glide": 60.0}
SHORT_HEAD, SHORT_TAIL = 35.0, 20.0     # plosives: keep the burst and the end


def shorten_consonant(x: np.ndarray, romaji: str, res: dict) -> np.ndarray:
    """Make a slow spoken consonant short. Fast songs need short consonants."""
    cls = sound_class(romaji)
    if cls == "vowel" or "v_ms" not in res or "estimated" in res.get("reason", ""):
        return x
    to_s = lambda t: int(t * OUT_SR / 1000.0)
    on, v = res["onset_ms"], res["v_ms"]
    fade = to_s(8.0)
    if cls == "plosive":
        a, b = to_s(on + SHORT_HEAD), to_s(v - SHORT_TAIL)
        if b - a < to_s(15.0):
            return x
        # Remove the middle of the consonant. Cross-fade the two parts.
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        joint = x[a:a + fade] * (1.0 - ramp) + x[b:b + fade] * ramp
        return np.concatenate([x[:a], joint, x[b + fade:]])
    start = to_s(v - SHORT_KEEP[cls])
    if start - to_s(on) < to_s(15.0):
        return x
    y = x[start:].copy()
    y[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
    return np.concatenate([np.zeros(to_s(20.0), dtype=np.float32), y])


def analyze(x: np.ndarray, romaji: str, short: bool = False) -> dict:
    """Measure one sound. Return the oto.ini numbers in ms and a quality flag."""
    if kind(romaji) == "vcv":
        return analyze_vcv(x, romaji)
    if kind(romaji) == "vc":
        return analyze_vc(x)
    if kind(romaji) == "breath":
        return analyze_breath(x)
    cls = sound_class(romaji)
    hop = OUT_SR // 200  # 5 ms
    win = hop * 5        # 25 ms
    ms = 5.0
    rms = frame_rms(x, hop, win)
    peak = float(rms.max())
    above = np.where(rms > max(peak * 0.03, 1e-4))[0]
    if len(above) < 10:
        return {"ok": False, "reason": "almost silent"}
    spec = _band_spectra(x, hop, win)
    spec = spec - spec.mean(axis=1, keepdims=True)
    f0 = pitch_track(x, hop)
    n = min(len(rms), len(spec), len(f0))
    rms, spec, f0 = rms[:n], spec[:n], f0[:n]
    onset, last = int(above[0]), min(int(above[-1]), n - 1)
    span = last - onset
    a = onset + int(span * 0.40)
    b = max(a + 2, onset + int(span * 0.80))
    steady = float(np.median(rms[a:b]))
    ref = spec[a:b].mean(axis=0)
    dist = _median3(np.abs(spec - ref).mean(axis=1))
    d_v = float(np.median(dist[a:b]))
    voiced = f0[a:b][f0[a:b] > 0]
    pitch = float(np.median(voiced)) if len(voiced) else 0.0
    notes = []

    # ---- 1. Start of the vowel (the preutterance point) ----
    if cls == "vowel":
        v_start = onset
    else:
        lo, default, hi = PRE_LIMITS[cls]
        v_start = None
        if cls in ("plosive", "fricative"):
            # Unvoiced consonant: the vowel starts where the voice starts.
            run = 0
            for i in range(onset, b):
                run = run + 1 if (f0[i] > 0 and rms[i] >= 0.35 * steady) else 0
                if run >= 5:
                    v_start = i - 4
                    break
            if v_start is not None and v_start - onset < 3:
                notes.append("consonant very short")
                v_start = onset + 3
        elif a - onset >= 4:
            d_c = float(dist[onset:a].max())
            if d_c - d_v >= 2.5:
                limit = d_v + 0.55 * (d_c - d_v)
                # Go back from the stable vowel to the last consonant frame.
                for i in range(a, onset - 1, -1):
                    if dist[i] > limit or rms[i] < 0.25 * steady:
                        v_start = i + 1
                        break
        length_c = None if v_start is None else (v_start - onset) * ms
        if length_c is None or length_c < 10 or length_c > 420:
            notes.append("consonant length estimated")
            v_start = onset + int(default / ms)

    # ---- 2. Stable part of the vowel (the part that OpenUtau stretches) ----
    def stable_run(use_pitch):
        ok = (dist < max(2.0 * d_v, d_v + 2.5)) & (rms >= 0.6 * steady)
        if use_pitch and pitch > 0:
            ok &= (f0 > 0) & (np.abs(f0 / pitch - 1.0) < 0.15)
        mid = (a + b) // 2
        if not ok[mid]:
            return None
        s0 = s1 = mid
        gap = 0
        for i in range(mid, v_start - 1, -1):
            gap = 0 if ok[i] else gap + 1
            if gap > 2:
                break
            if ok[i]:
                s0 = i
        gap = 0
        for i in range(mid, last + 1):
            gap = 0 if ok[i] else gap + 1
            if gap > 2:
                break
            if ok[i]:
                s1 = i
        return s0, s1

    run = stable_run(True)
    if run is None or (run[1] - max(run[0], v_start + 6)) * ms < 120:
        run = stable_run(False)
    if run is None or (run[1] - max(run[0], v_start + 6)) * ms < 120:
        loud = np.where(rms >= 0.5 * steady)[0]
        run = (v_start + 10, max(int(loud[-1]) - 4, onset + 10) if len(loud) else last)
        notes.append("vowel not stable")
    s0, s1 = run

    # ---- 3. The oto numbers ----
    onset_ms = onset * ms
    v_ms = v_start * ms
    if cls == "vowel":
        offset_ms = onset_ms + 5.0
        pre, ovl = 50.0, 25.0
        cons = min(max(s0 * ms - offset_ms, 90.0), 150.0)
    else:
        # Long spoken consonants make the timing slow. Keep only the last part.
        keep = {"plosive": 220.0, "voiced_plosive": 70.0, "fricative": 130.0,
                "voiced_fricative": 110.0, "nasal": 80.0, "liquid": 60.0, "glide": 90.0}[cls]
        offset_ms = max(onset_ms - 10.0, v_ms - keep, 0.0)
        pre = v_ms - offset_ms
        if cls in ("plosive", "fricative"):
            ovl = min(pre / 3.0, 40.0)
        else:
            ovl = min(pre / 2.0, 50.0)
        cons = pre + min(max(s0 * ms - v_ms, 30.0), 60.0 if short else 120.0)
    length = s1 * ms - offset_ms
    ok = True
    if length - cons < 80.0:
        ok = False
        notes.append("vowel too short")
    if span * ms > 2500:
        notes.append("very long sound")
    return {
        "ok": ok,
        "reason": ", ".join(notes),
        "offset": round(offset_ms, 1),
        "consonant": round(cons, 1),
        "cutoff": round(-length, 1),
        "preutterance": round(pre, 1),
        "overlap": round(max(ovl, 5.0), 1),
        "steady_rms": steady,
        "pitch": pitch,
        "onset_ms": onset_ms,
        "v_ms": v_ms,
    }


def normalize(x: np.ndarray, steady_rms: float, target: float = 0.12):
    gain = target / max(steady_rms, 1e-5)
    peak = float(np.abs(x).max()) * gain
    if peak > 0.95:
        gain *= 0.95 / peak
    return x * gain


# -------------------------------------------------------------- bank assembly
def build_bank(seg_dir: str, out_dir: str, name: str, rows, btype: str = "CV",
               target: float = 0.0, short: bool = False) -> dict:
    """Make the OpenUtau voicebank folder and zip from the cut sounds."""
    os.makedirs(out_dir, exist_ok=True)
    lines = []
    report = {"good": [], "check": [], "missing": [], "flagged": []}
    info = {}
    for row in rows:
        for kana, romaji in row:
            src = os.path.join(seg_dir, romaji + ".wav")
            if not os.path.exists(src):
                report["missing"].append(kana)
                continue
            x = load_wav(src)
            res = analyze(x, romaji)
            if "offset" not in res:
                report["missing"].append(kana)
                continue
            what = kind(romaji)
            if short and what == "cv":
                x = shorten_consonant(x, romaji, res)
                again = analyze(x, romaji, short=True)
                if "offset" in again:
                    again["reason"], again["ok"] = res["reason"], res["ok"]
                    res = again
            level = 0.04 if what == "breath" else 0.12    # breaths are quiet
            save_wav(os.path.join(out_dir, romaji + ".wav"),
                     normalize(x, res["steady_rms"], level))
            info[romaji] = res
            (report["good"] if res["ok"] and not res["reason"] else report["check"]).append(
                kana if not res["reason"] else f"{kana} ({res['reason']})")
            if what in ("vc", "vcv"):
                aliases = [kana]                       # examples: "a k", "a か"
            elif what == "breath":
                aliases = [kana] + (["br", "息"] if romaji == "br1" else [])
            elif btype != "CV":
                aliases = [kana, romaji, "- " + kana]  # "- か" = start of a phrase
            else:
                aliases = [kana, romaji]
            for alias in aliases:
                lines.append(_oto_line(romaji, alias, res))
    # Find the sounds with an unusual pitch. These are often shouted or whispered.
    pitches = [r["pitch"] for r in info.values() if r["pitch"] > 0]
    if len(pitches) >= 5:
        mid = float(target) if target > 0 else float(np.median(pitches))
        report["median_pitch"] = round(float(np.median(pitches)))
        report["in_range"] = int(sum(mid / 1.25 <= v <= mid * 1.25 for v in pitches))
        report["with_pitch"] = len(pitches)
        report["typical_pitch"] = round(mid)
        for row in rows:
            for kana, romaji in row:
                pitch = info.get(romaji, {}).get("pitch", 0)
                if pitch > 0 and not (mid / 1.25 <= pitch <= mid * 1.25):
                    report["flagged"].append(kana)
    for alias, romaji in SHARED:
        if romaji in info:
            lines.append(_oto_line(romaji, alias, info[romaji]))
    with open(os.path.join(out_dir, "oto.ini"), "w", encoding="shift_jis", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(out_dir, "character.txt"), "w", encoding="shift_jis",
              errors="replace", newline="\r\n") as f:
        f.write(f"name={name}\n")
    with open(os.path.join(out_dir, "readme.txt"), "w", encoding="utf-8", newline="\r\n") as f:
        kind_text = (f"Japanese {btype} voicebank. In OpenUtau, use the {PHONEMIZER[btype]}.")
        f.write(f"{name}\n{kind_text}\n"
                "Breath sounds, if present, have the aliases br1, br2, br3, br4.\n"
                "The audio is synthetic speech from Irodori-TTS-v4.1-Small.\n"
                "Irodori UTAU Maker made the oto.ini automatically.\n")
    zip_path = out_dir.rstrip("/\\") + ".zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in sorted(os.listdir(out_dir)):
            z.write(os.path.join(out_dir, fn), f"{name}/{fn}")
    report["zip"] = zip_path
    report["count"] = len(info)
    return report


def _oto_line(romaji: str, alias: str, r: dict) -> str:
    return (f"{romaji}.wav={alias},{r['offset']},{r['consonant']},{r['cutoff']},"
            f"{r['preutterance']},{r['overlap']}")


# ----------------------------------------------- auto-oto for any CV folder
def reoto_folder(folder: str, short: bool = False) -> str:
    """Write a new oto.ini for a folder of CV WAV files. Return a report.

    File names must be romaji (ka.wav) or hiragana (か.wav).
    The old oto.ini stays as a backup file.
    """
    if not os.path.isdir(folder):
        return "ERROR. This folder does not exist: " + folder
    table = [(k, r) for row in rows_for(list(SETS.keys())[2]) for k, r in row]
    by_romaji = {r: k for k, r in table}
    by_kana = {k: r for k, r in table}
    lines, info, skipped, check = [], {}, [], []
    for fn in sorted(os.listdir(folder)):
        if not fn.lower().endswith(".wav"):
            continue
        stem = fn[:-4]
        romaji = stem if stem in by_romaji else by_kana.get(stem)
        if romaji is None:
            skipped.append(fn)
            continue
        try:
            x = load_wav(os.path.join(folder, fn))
            res = analyze(x, romaji)
            if short and "offset" in res:
                y = shorten_consonant(x, romaji, res)
                again = analyze(y, romaji, short=True) if len(y) != len(x) else {}
                if "offset" in again:
                    # Keep the original WAV in a backup folder. Write the short WAV.
                    keep = os.path.join(folder, "original_wavs")
                    os.makedirs(keep, exist_ok=True)
                    if not os.path.exists(os.path.join(keep, fn)):
                        os.replace(os.path.join(folder, fn), os.path.join(keep, fn))
                    save_wav(os.path.join(folder, fn), y)
                    again["reason"], again["ok"] = res["reason"], res["ok"]
                    res = again
        except Exception:
            res = {}
        if "offset" not in res:
            skipped.append(fn)
            continue
        info[romaji] = (stem, res)
        if res["reason"] or not res["ok"]:
            check.append(f"{by_romaji[romaji]} ({res['reason'] or 'vowel too short'})")
        for alias in (by_romaji[romaji], romaji):
            lines.append(_oto_line(stem, alias, res))
    for alias, romaji in SHARED:
        if romaji in info:
            lines.append(_oto_line(info[romaji][0], alias, info[romaji][1]))
    if not lines:
        return "ERROR. No usable WAV files. Names must be romaji (ka.wav) or hiragana."
    oto = os.path.join(folder, "oto.ini")
    if os.path.exists(oto):
        n = 1
        while os.path.exists(os.path.join(folder, f"oto_backup_{n}.ini")):
            n += 1
        os.replace(oto, os.path.join(folder, f"oto_backup_{n}.ini"))
    with open(oto, "w", encoding="shift_jis", errors="replace", newline="\r\n") as f:
        f.write("\n".join(lines) + "\n")
    pitches = [r["pitch"] for _, r in info.values() if r["pitch"] > 0]
    msg = [f"DONE. New oto.ini for {len(info)} sounds. The old oto.ini is a backup file."]
    if pitches:
        msg.append(f"Pitch of the sounds: lowest {min(pitches):.0f} Hz, typical "
                   f"{np.median(pitches):.0f} Hz, highest {max(pitches):.0f} Hz.")
        if max(pitches) / min(pitches) > 1.6:
            msg.append("WARNING. The pitch range is wide. The voice can sound uneven. "
                       "A new oto.ini cannot correct this.")
    if check:
        msg.append("Check these sounds: " + ", ".join(check))
    if skipped:
        msg.append("Skipped files: " + ", ".join(skipped))
    return "\n".join(msg)


# ------------------------------------------------ file names to hiragana
def hiragana_name(stem: str):
    """Return the hiragana name for a file name of this tool, or None."""
    table = {r: k for row in BASIC_ROWS + EXTRA_ROWS for k, r in row}
    if stem in table:
        return table[stem]
    if stem.startswith("vcv_"):                       # vcv_a_ka -> "a か"
        v, _, romaji = stem[4:].partition("_")
        return f"{v} {table[romaji]}" if romaji in table else None
    if stem.startswith("vc_"):                        # vc_a_k -> "a k"
        v, _, c = stem[3:].partition("_")
        return f"{v} {c}" if c else None
    return None


def rename_to_hiragana(folder: str) -> str:
    """Rename romaji WAV files to hiragana names and update oto.ini. Return a report."""
    if not os.path.isdir(folder):
        return "ERROR. This folder does not exist: " + folder
    changes, skipped = {}, []
    for fn in sorted(os.listdir(folder)):
        if not fn.lower().endswith(".wav"):
            continue
        new = hiragana_name(fn[:-4])
        if new is None:
            skipped.append(fn)
        elif os.path.exists(os.path.join(folder, new + ".wav")):
            skipped.append(fn + " (the hiragana name exists)")
        else:
            changes[fn] = new + ".wav"
    if not changes:
        return ("No file names changed. The names must be romaji names of this tool "
                "(ka.wav, shi.wav, vcv_a_ka.wav).")
    oto = os.path.join(folder, "oto.ini")
    oto_note = "No oto.ini in this folder."
    if os.path.exists(oto):
        raw = open(oto, "rb").read()
        try:
            text, enc = raw.decode("shift_jis"), "shift_jis"
        except UnicodeDecodeError:
            text, enc = raw.decode("utf-8", "replace"), "utf-8"
        lines = []
        for line in text.splitlines():
            fn, eq, rest = line.partition("=")
            lines.append(changes.get(fn, fn) + eq + rest)
        n = 1
        while os.path.exists(os.path.join(folder, f"oto_backup_{n}.ini")):
            n += 1
        os.replace(oto, os.path.join(folder, f"oto_backup_{n}.ini"))
        with open(oto, "w", encoding=enc, errors="replace", newline="\r\n") as f:
            f.write("\n".join(lines) + "\n")
        oto_note = f"oto.ini uses the new names. The old file is oto_backup_{n}.ini."
    for old, new in changes.items():
        os.replace(os.path.join(folder, old), os.path.join(folder, new))
    msg = [f"DONE. {len(changes)} WAV files have hiragana names now.", oto_note]
    if skipped:
        msg.append("Not changed: " + ", ".join(skipped[:40]))
    return "\n".join(msg)
