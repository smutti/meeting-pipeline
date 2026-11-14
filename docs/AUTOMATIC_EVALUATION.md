# Automatic ASR test — November 14, 2026

**Result: lower observed word error rates, but no conclusive improvement on this small sample.** All four paired 95% bootstrap intervals include zero. This is a reproducible test of ASR components on public read speech, not proof that the complete meeting workflow is more accurate.

## Corpus and method

- Source: [Google FLEURS](https://huggingface.co/datasets/google/fleurs), CC BY 4.0.
- Dataset revision: `70bb2e84b976b7e960aa89f1c648e09c59f894dd`; test split, `it_it` and `en_us`.
- Selection: first 20 distinct prompt IDs encountered in each pinned test archive, frozen before inference. Deterministic convenience sample, not random or the full test set.
- Italian: 20 clips, 273.0 seconds, 491 normalized reference words.
- English: 20 clips, 188.6 seconds, 439 normalized reference words.
- Hardware: Apple M5 Pro, 24 GB. Same model/runtime revisions as the [initial benchmark](BENCHMARK.md).
- All models receive the same normalized mono 16 kHz PCM16 clip. No glossary/hotwords, denoising or text arbitration. Reference text comes from the corpus, not another ASR or an LLM judge.
- One inference per model/clip, engine order rotated. Loading is included in per-call timings, so these are not warm throughput measurements.

Whisper large-v3 on MLX is a proxy for the earlier model choice. The old Vibe/whisper.cpp workflow was not rerun. Parakeet is the current unreviewed V2 selected text; Qwen is an independent candidate. Qwen's score cannot be credited to V2's final output while V2 continues selecting Parakeet.

## Measured results

WER is total word edits / reference words. CER measures character edits after the documented normalization, excluding spaces. Lower is better.

| Language | Model | Word edits / reference words | WER | CER |
|---|---|---:|---:|---:|
| Italian | Whisper large-v3 | 14 / 491 | 2.85% | 0.99% |
| Italian | Parakeet Ultra | 12 / 491 | 2.44% | 1.25% |
| Italian | Qwen3-ASR 1.7B | 9 / 491 | 1.83% | 0.53% |
| English | Whisper large-v3 | 22 / 439 | 5.01% | 2.60% |
| English | Parakeet Ultra | 20 / 439 | 4.56% | 2.12% |
| English | Qwen3-ASR 1.7B | 14 / 439 | 3.19% | 1.64% |

Parakeet has two fewer word edits than Whisper in each language. Its Italian CER is higher despite lower WER: metrics can disagree because one word error can contain different numbers of character errors. Qwen has the lowest observed WER and CER here, but the sample is too small for a strong ranking.

## Paired uncertainty estimates

Delta = candidate WER − Whisper WER. Values below zero favor the candidate. Resample paired prompt groups 2,000 times with seed 20261114; report percentile intervals. Intervals are exploratory and unadjusted for multiple comparisons.

| Language | Candidate | Delta, percentage points | 95% interval, percentage points | Verdict |
|---|---|---:|---|---|
| Italian | Parakeet | −0.41 | [−2.03, +1.20] | Inconclusive |
| Italian | Qwen | −1.02 | [−2.76, +0.82] | Inconclusive |
| English | Parakeet | −0.46 | [−2.71, +1.89] | Inconclusive |
| English | Qwen | −1.82 | [−4.07, +0.44] | Inconclusive |

Do not describe these values as a statistically established improvement. No sample was added after inspecting results to obtain a favorable verdict. Larger preregistered samples and a separate meeting-domain test set are needed. Potential training exposure to this public corpus is unknown.

## Reproduction and regression checks

Follow the commands in [EVALUATION.md](EVALUATION.md). Preparation records source/audio/reference hashes; inference preserves candidates and runtime fingerprints. The [machine-readable results](fleurs-smoke-2026-11-14.json) contain per-sample counts and identifiers, without transcript text or local paths. Audio and references are downloaded locally from the pinned source.

Normalization: Unicode NFKC, lowercase, apostrophe normalization, punctuation removal, with accents, numbers and negation preserved. Digits are not expanded to words. This is a within-experiment comparison and does not claim to reproduce official model leaderboard scores.

`--fail-on-regression` can flag a candidate whose entire paired interval is worse than Whisper. A zero exit status is not evidence of improvement: these four comparisons are inconclusive. Unit tests cover edit distances, weighting, deterministic intervals, duplicate prompts, mismatched references and incomplete pairs. Model inference remains an explicit local operation.

This test does not measure DER, speaker identity, glossary benefit, missed meeting content or human review time. The [private meeting comparison](BENCHMARK.md) remains a separate, unlabeled experiment. To automate those measures, create or obtain the corresponding reference annotations once, then rerun evaluation for each version.
