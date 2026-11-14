"""Reference-based ASR metrics and paired, prompt-level uncertainty estimates."""

from __future__ import annotations

import random
import re
import unicodedata
from collections import defaultdict


def normalize(text):
    return re.findall(
        r"\w+(?:'\w+)*",
        unicodedata.normalize("NFKC", text).casefold().replace("’", "'"),
    )


def edit_distance(reference, hypothesis):
    previous = list(range(len(hypothesis) + 1))
    for i, item in enumerate(reference, 1):
        current = [i]
        for j, other in enumerate(hypothesis, 1):
            current.append(
                min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (item != other))
            )
        previous = current
    return previous[-1]


def metrics(reference, hypothesis):
    ref, hyp = normalize(reference), normalize(hypothesis)
    if not ref:
        raise ValueError("A reference must contain words")
    rc, hc = "".join(ref), "".join(hyp)
    we, ce = edit_distance(ref, hyp), edit_distance(rc, hc)
    return {
        "word_edits": we,
        "reference_words": len(ref),
        "wer": we / len(ref),
        "character_edits": ce,
        "reference_characters": len(rc),
        "cer": ce / len(rc),
    }


def paired_comparison(
    rows,
    baseline="whisper",
    candidate="parakeet",
    seed=20261114,
    repeats=2000,
    minimum_units=20,
    margin=0.0,
):
    """Delta is candidate minus baseline WER; resample complete prompt groups.

    Missing/duplicate model outputs are errors, not silent exclusions. The confidence
    interval describes this sampled corpus, not a guarantee about meeting audio.
    """
    if repeats < 100 or minimum_units < 2 or margin < 0 or candidate == baseline:
        raise ValueError("Invalid comparison configuration")
    samples = defaultdict(dict)
    for row in rows:
        if row["engine"] not in {baseline, candidate}:
            continue
        key = (row["language"], row["sample_id"])
        if row["engine"] in samples[key]:
            raise ValueError("Duplicate sample/engine output")
        samples[key][row["engine"]] = row
    groups = defaultdict(lambda: [0, 0, 0])
    for (language, _), pair in samples.items():
        if set(pair) != {baseline, candidate}:
            raise ValueError("Incomplete paired outputs")
        old, new = pair[baseline], pair[candidate]
        if (
            old["reference_hash"] != new["reference_hash"]
            or old["audio_hash"] != new["audio_hash"]
            or old["unit_id"] != new["unit_id"]
            or old["reference_words"] != new["reference_words"]
        ):
            raise ValueError("Paired outputs must use identical audio and reference")
        if old["reference_words"] <= 0:
            raise ValueError("Empty reference")
        unit = groups[(language, old["unit_id"])]
        unit[0] += old["word_edits"]
        unit[1] += new["word_edits"]
        unit[2] += old["reference_words"]
    if not groups:
        raise ValueError("No paired outputs")
    units = list(groups.values())
    total = sum(u[2] for u in units)
    old_wer, new_wer = (sum(u[i] for u in units) / total for i in (0, 1))
    rng = random.Random(seed)
    deltas = []
    for _ in range(repeats):
        sample = rng.choices(units, k=len(units))
        deltas.append(sum(u[1] - u[0] for u in sample) / sum(u[2] for u in sample))
    deltas.sort()
    low, high = deltas[int(0.025 * (repeats - 1))], deltas[int(0.975 * (repeats - 1))]
    verdict = "inconclusive"
    if len(units) < minimum_units:
        verdict = "insufficient_sample"
    elif high < -margin:
        verdict = "lower_wer_on_this_sample"
    elif low > margin:
        verdict = "higher_wer_on_this_sample"
    return {
        "baseline": baseline,
        "candidate": candidate,
        "samples": len(samples),
        "independent_prompt_groups": len(units),
        "reference_words": total,
        "baseline_wer": old_wer,
        "candidate_wer": new_wer,
        "delta_wer": new_wer - old_wer,
        "paired_bootstrap_95_percent_interval": [low, high],
        "bootstrap_repeats": repeats,
        "seed": seed,
        "minimum_prompt_groups": minimum_units,
        "margin": margin,
        "verdict": verdict,
    }


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row["language"], row["engine"])].append(row)
    totals = []
    for (language, engine), group in sorted(groups.items()):
        words = sum(r["reference_words"] for r in group)
        chars = sum(r["reference_characters"] for r in group)
        totals.append(
            {
                "language": language,
                "engine": engine,
                "samples": len(group),
                "reference_words": words,
                "word_edits": sum(r["word_edits"] for r in group),
                "wer": sum(r["word_edits"] for r in group) / words,
                "cer": sum(r["character_edits"] for r in group) / chars,
                "inference_wall_seconds": sum(r["wall_seconds"] for r in group),
            }
        )
    comparisons = []
    for language in sorted({r["language"] for r in rows}):
        subset = [r for r in rows if r["language"] == language]
        for candidate in ["parakeet", "qwen"]:
            comparisons.append(
                {"language": language, **paired_comparison(subset, candidate=candidate)}
            )
    return {
        "totals": totals,
        "comparisons": comparisons,
        "scope": "ASR components on public read speech. Whisper/MLX is a legacy-model proxy, not a rerun of V1/Vibe. Parakeet equals the unreviewed V2 selected text; Qwen is a separate candidate. No meeting WER, DER, identity or human-time claim.",
    }
