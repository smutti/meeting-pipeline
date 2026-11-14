"""Versioned local glossaries and confirmed voice exemplars."""

from __future__ import annotations
import math
import statistics
import time
from .common import read, save, digest, locked


def knowledge_path(home):
    return home / "knowledge.json"


def load(home):
    path = knowledge_path(home)
    return (
        read(path)
        if path.exists()
        else {
            "version": 1,
            "terms": [],
            "voices": [],
            "voice_policy": {
                "auto_accept": False,
                "threshold": 0.8,
                "margin": 0.1,
                "min_samples": 2,
                "evidence": None,
            },
        }
    )


def add_term(home, canonical, aliases, project, language, meaning=""):
    if not canonical.strip() or language not in {"it", "en", "*"}:
        raise ValueError("A nonempty term and it/en/* language are required")
    with locked(home / "knowledge.lock"):
        data = load(home)
        key = digest([canonical.casefold().strip(), project, language])[:16]
        entry = {
            "id": key,
            "canonical": canonical.strip(),
            "aliases": sorted(set(a.strip() for a in aliases if a.strip())),
            "project": project,
            "language": language,
            "meaning": meaning,
            "confirmed": True,
        }
        data["terms"] = [x for x in data["terms"] if x["id"] != key] + [entry]
        data["version"] += 1
        save(knowledge_path(home), data)
    return entry


def terms_for(data, project, language):
    # Project terms override a global entry with the same canonical spelling.
    entries = {}
    for term in sorted(data["terms"], key=lambda t: t["project"] != "*"):
        if (
            term.get("confirmed")
            and term["project"] in {"*", project}
            and term["language"] in {"*", language}
        ):
            entries[term["canonical"].casefold()] = term
    return list(entries.values())


def normalized(vector):
    vector = [float(v) for v in vector]
    if not vector or any(not math.isfinite(v) for v in vector):
        raise ValueError("Invalid speaker embedding")
    norm = math.sqrt(sum(x * x for x in vector))
    if norm < 1e-9:
        raise ValueError("Empty speaker signal")
    return [x / norm for x in vector]


def cosine(a, b):
    if len(a) != len(b):
        raise ValueError("Embedding dimensions differ")
    return sum(x * y for x, y in zip(normalized(a), normalized(b)))


def enroll(home, name, vector, model_id, source_hash, start, end, confirmed):
    if not confirmed:
        raise ValueError(
            "Confirm the person's identity and a single clean voice before enrollment"
        )
    if not name.strip() or end - start < 6:
        raise ValueError("A name and at least 6 seconds of clean speech are required")
    sample_id = digest([source_hash, start, end, model_id])
    with locked(home / "knowledge.lock"):
        data = load(home)
        duplicate = next((v for v in data["voices"] if v["id"] == sample_id), None)
        if duplicate:
            if duplicate["name"] != name:
                raise ValueError("This sample is already assigned to another person")
            return duplicate
        entry = {
            "id": sample_id,
            "name": name.strip(),
            "embedding": normalized(vector),
            "model_id": model_id,
            "source_hash": source_hash,
            "start": start,
            "end": end,
            "confirmed": True,
            "created": time.time(),
        }
        data["voices"].append(entry)
        data["version"] += 1
        # New identities change the open-set decision boundary; recalibrate policy.
        data["voice_policy"]["auto_accept"] = False
        save(knowledge_path(home), data)
        return {k: v for k, v in entry.items() if k != "embedding"}


def match(samples, data, model_id, exclude_source=None):
    policy = data["voice_policy"]
    profiles = {}
    for entry in data["voices"]:
        if (
            entry.get("confirmed")
            and entry["model_id"] == model_id
            and entry["source_hash"] != exclude_source
        ):
            profiles.setdefault(entry["name"], []).append(entry)
    if not samples or not profiles:
        return {"status": "unknown", "name": None, "candidates": []}
    ranked = []
    for name, refs in profiles.items():
        scores = [
            statistics.median(cosine(q, r["embedding"]) for r in refs) for q in samples
        ]
        ranked.append(
            {
                "name": name,
                "score": statistics.median(scores),
                "min_query_score": min(scores),
                "references": len(refs),
                "source_recordings": len({r["source_hash"] for r in refs}),
            }
        )
    ranked.sort(key=lambda x: x["score"], reverse=True)
    best = ranked[0]
    margin = best["score"] - (ranked[1]["score"] if len(ranked) > 1 else -1)
    enough = (
        len(samples) >= policy["min_samples"]
        and best["references"] >= policy["min_samples"]
        and best["source_recordings"] >= 2
    )
    confident = (
        enough
        and best["min_query_score"] >= policy["threshold"]
        and margin >= policy["margin"]
    )
    accepted = confident and policy["auto_accept"] and bool(policy.get("evidence"))
    return {
        "status": "matched" if accepted else "suggested" if confident else "unknown",
        "name": best["name"] if accepted else None,
        "candidates": ranked[:3],
        "margin": margin,
        "calibrated": bool(policy.get("evidence")),
    }
