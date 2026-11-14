from __future__ import annotations
from collections import Counter, defaultdict
from difflib import SequenceMatcher
import re
from .common import digest


def tokens(text):
    return re.findall(r"\w+", text.casefold())


def text_between(words, start, end):
    return " ".join(
        w["text"].strip() for w in words if start <= (w["start"] + w["end"]) / 2 < end
    )


def issue(kind, start, end, reason, **extra):
    identity = [kind, round(start, 3), round(end, 3)]
    return {
        "id": digest(identity)[:12],
        "kind": kind,
        "start": start,
        "end": end,
        "reason": reason,
        "status": "open",
        **extra,
    }


def inspect_primary(primary, diar, duration, recipe, terms=(), expected=None):
    issues = []
    width = recipe["window_seconds"]
    words = primary["words"]
    for i in range(int(duration // width) + 1):
        start, end = i * width, min(duration, (i + 1) * width)
        if end <= start:
            continue
        ws = [w for w in words if start <= w["start"] < end]
        low = [
            w
            for w in ws
            if w.get("confidence") is not None
            and w["confidence"] < recipe["low_confidence"]
        ]
        text = " ".join(w["text"] for w in ws)
        ts = tokens(text)
        counts = Counter(tuple(ts[j : j + 8]) for j in range(max(0, len(ts) - 7)))
        reasons = []
        if low:
            reasons.append(
                f"{len(low)} low decoder scores (not calibrated error probabilities)"
            )
        if any(n >= 3 for n in counts.values()):
            reasons.append("Repeated word sequence")
        speech = sum(
            max(0, min(end, s["end"]) - max(start, s["start"]))
            for s in diar["segments"]
        )
        if speech > 5 and not ws:
            reasons.append("Diarizer detects speech without transcript words")
        if any(w["end"] <= w["start"] for w in ws):
            reasons.append("Zero/negative word duration")
        aliases = [
            t["canonical"]
            for t in terms
            if any(
                re.search(r"(?<!\w)" + re.escape(a) + r"(?!\w)", text, re.I)
                for a in t["aliases"]
            )
        ]
        if aliases:
            reasons.append("Possible glossary spelling: " + ", ".join(aliases))
        if reasons:
            issues.append(issue("text", start, end, "; ".join(reasons), primary=text))
        uncertain = [w for w in ws if len(speaker_for(w, diar["segments"])) != 1]
        if sum(max(0, w["end"] - w["start"]) for w in uncertain) >= 2:
            issues.append(
                issue(
                    "speaker_alignment",
                    start,
                    end,
                    "At least 2 seconds of words have missing or ambiguous speaker attribution",
                )
            )
    totals = defaultdict(float)
    for s in diar["segments"]:
        totals[s["speaker"]] += s["end"] - s["start"]
    for speaker, total in totals.items():
        if total < recipe["rare_speaker_seconds"]:
            sample = max(
                (s for s in diar["segments"] if s["speaker"] == speaker),
                key=lambda s: s["end"] - s["start"],
            )
            issues.append(
                issue(
                    "speaker",
                    sample["start"],
                    sample["end"],
                    f"Speaker {speaker}: only {total:.1f}s total; may be a short real intervention",
                    speaker=speaker,
                )
            )
    if expected and expected != len(totals):
        issues.append(
            issue(
                "speaker_count",
                0,
                min(duration, 60),
                f"Expected {expected}, detected {len(totals)}; expectation is not ground truth",
            )
        )
    if diar["engine"] == "nemotron3" and len(totals) == 8:
        issues.append(
            issue(
                "speaker_count",
                0,
                min(duration, 60),
                "Nemotron reached its 8-speaker capacity",
            )
        )
    return issues


def compare(primary, secondary, threshold, offset=0):
    issues = []
    for s in secondary["segments"]:
        start, end = s["start"] + offset, s["end"] + offset
        base = text_between(primary["words"], start, end)
        a, b = tokens(base), tokens(s["text"])
        distance = 1 - SequenceMatcher(None, a, b, autojunk=False).ratio()
        # This score is disagreement, never WER.
        if distance >= threshold and (a or b):
            issues.append(
                issue(
                    "disagreement",
                    start,
                    end,
                    f"Independent ASR disagreement {distance:.2f} (not WER)",
                    primary=base,
                    secondary=s["text"],
                    disagreement=distance,
                )
            )
    return issues


def speaker_for(word, segments):
    start, end = word["start"], word["end"]
    if end <= start:
        return []
    coverage = defaultdict(list)
    for s in segments:
        lo, hi = max(start, s["start"]), min(end, s["end"])
        if hi > lo:
            coverage[s["speaker"]].append((lo, hi))
    scores = {}
    for speaker, spans in coverage.items():
        merged = []
        for lo, hi in sorted(spans):
            if merged and lo <= merged[-1][1]:
                merged[-1][1] = max(hi, merged[-1][1])
            else:
                merged.append([lo, hi])
        scores[speaker] = sum(hi - lo for lo, hi in merged) / (end - start)
    overlapping = sorted(s for s, v in scores.items() if v >= 0.2)
    return (
        overlapping
        if len(overlapping) > 1
        else sorted(s for s, v in scores.items() if v >= 0.5)
    )


def clean_spans(segments, speaker, minimum=6, maximum=15, count=2):
    candidates = []
    others = [s for s in segments if s["speaker"] != speaker]
    for segment in [s for s in segments if s["speaker"] == speaker]:
        spans = [(segment["start"], segment["end"])]
        for other in others:
            divided = []
            for lo, hi in spans:
                if other["end"] <= lo or other["start"] >= hi:
                    divided.append((lo, hi))
                else:
                    if lo < other["start"]:
                        divided.append((lo, other["start"]))
                    if other["end"] < hi:
                        divided.append((other["end"], hi))
            spans = divided
        candidates += [
            (lo + 0.15, hi - 0.15) for lo, hi in spans if hi - lo >= minimum + 0.3
        ]
    candidates.sort(key=lambda x: x[1] - x[0], reverse=True)
    chosen = []
    for lo, hi in candidates:
        end = min(hi, lo + maximum)
        if all(end <= a or lo >= b for a, b in chosen):
            chosen.append((lo, end))
        if len(chosen) == count:
            break
    return chosen
