# Evaluating transcripts and workflows

Separate three questions:

1. **Outputs:** compare archived notes, independent ASR, workflow-selected text and human revisions. Keep source, version, parameters, timing and edit provenance for every variant.
2. **Accuracy:** measure WER against a verified reference; inspect names, numbers, negations and terminology; measure diarization against annotated turns and identities against confirmed labels.
3. **Operations:** measure end-to-end time, flagged audio duration, actual human review minutes and missed errors. Issue count alone measures neither quality nor saved work.

Archived notes may already contain corrections: do not treat them as ground truth without listening. MLX Whisper and the previous whisper.cpp inference are different configurations. The new benchmark does not reconstruct old application timing or errors.

## Automatic evaluation with existing reference data

A public labeled corpus allows automatic scoring without asking a user to transcribe every new sample. The included runner downloads a pinned [Google FLEURS](https://huggingface.co/datasets/google/fleurs) test subset for Italian and US English. FLEURS provides audio and reference text under CC BY 4.0. It contains read speech, which is a different domain from noisy, overlapping meetings.

```sh
.venv/bin/python scripts/evaluate_asr.py prepare-fleurs \
  --output /path/to/private-evaluations/fleurs --samples-per-language 20
.venv/bin/python scripts/evaluate_asr.py run \
  /path/to/private-evaluations/fleurs/corpus.json \
  --output /path/to/private-evaluations/fleurs/run
```

Before evaluation, initialize the local runtime and run a normal transcription once so that Parakeet Core ML models are cached. The evaluator requires that cache to fingerprint the actual weights.

The preparation step selects the first distinct prompt IDs encountered in each pinned test archive before inference. This is deterministic, not random sampling or a full test-set benchmark. Audio, metadata, reference hashes and sample IDs are saved in `corpus.json`. The runner verifies hashes, normalizes identical audio, rotates engine order, preserves raw candidates, and caches inference against model-file, inference-package-version and inference-code fingerprints. It acquires the same worker lock as meeting processing.

Whisper large-v3/MLX is the baseline **model proxy**. It does not run Vibe or recreate every V1 setting. Parakeet represents unreviewed V2 selected text because V2 currently keeps that primary text. Qwen is scored separately; its score is not assigned to the whole workflow. No glossary terms are supplied in this generic benchmark.

Results include WER, CER and a paired bootstrap interval for candidate WER minus baseline WER, separately for each language. Whole prompt groups are resampled together; repeated recordings of one sentence are not counted as independent prompts. Aggregated WER is total word edits divided by total reference words. Negative delta means fewer edits. There are 2,000 bootstrap resamples with a fixed seed and a minimum of 20 independent prompts for a directional verdict. These are exploratory, unadjusted intervals, not a statistical guarantee or a domain-general ranking.

Possible verdicts:

- `lower_wer_on_this_sample`: the entire interval is below zero.
- `higher_wer_on_this_sample`: the entire interval is above zero.
- `inconclusive`: the interval includes zero.
- `insufficient_sample`: fewer than 20 independent prompt groups.

Missing pairs, duplicate outputs or mismatched audio/reference hashes fail evaluation instead of silently reducing coverage. `--fail-on-regression` exits with status 2 if Parakeet has `higher_wer_on_this_sample` in either language. It is a regression signal, not an improvement requirement: a successful exit can still be inconclusive. The default run reports all outcomes without making model quality a software-test failure.

The current [automatic results](AUTOMATIC_EVALUATION.md) report the exact sample and limitations. Possible model training exposure to public data is unknown. For deployment decisions, add a separate held-out meeting set, annotate it once, and rerun scoring automatically on each candidate version. Preserve model configuration and do not tune on that held-out set.

The runner also accepts a corpus using `reference_kind: human_verified` with the same sample fields as the downloaded manifest. Reference text must be verified outside the tool; the flag records provenance, not proof of listening. Keep evaluation inputs and outputs outside Git. GitHub Actions tests metric logic with synthetic fixtures; it does not download audio or run GPU inference.

## Reproducible local transcript comparison

`scripts/compare_transcripts.py` uses only the standard library and does not run inference. It reads a private JSON manifest and produces offline HTML, Markdown and JSON summaries. Store input/output outside the checkout or under Git-ignored `evaluations/`.

Minimal synthetic schema:

```json
{
  "recordings": [{
    "id": "IT-A", "label": "Test recording", "duration": 90,
    "audio": "file:///path/to/audio.wav",
    "variants": [
      {"id": "archive", "label": "Archive", "text": "Previous text",
       "notes": "Human editing not verified",
       "segments": [{"start": 0, "end": 10, "text": "Previous text"}]},
      {"id": "candidate", "label": "Candidate", "text": "New text",
       "segments": [{"start": 0, "end": 10, "text": "New text"}]}
    ]
  }],
  "clips": [{
    "id": "IT-A-1", "recording": "IT-A", "start": 0, "duration": 90,
    "audio": "file:///path/to/clip.wav",
    "candidates": [{"variant": "candidate", "scope": "exact_clip", "text": "New text"}]
  }]
}
```

The first variant is the **archived text baseline**, not the accuracy reference. `1 − SequenceMatcher.ratio`, with `autojunk=False`, describes normalized textual disagreement. It is not WER: greater difference can reflect corrections or new errors. Coarse segments intersecting a chosen interval are displayed in full; the interface does not invent word timestamps.

```sh
python scripts/compare_transcripts.py /path/to/manifest.json --output /path/to/comparison
# Open comparison.html, listen and download references.json.
python scripts/compare_transcripts.py /path/to/manifest.json \
  --output /path/to/comparison --references /path/to/references.json
```

Reference format:

```json
[{"clip_id":"IT-A-1","text":"Text verified by listening","human_reviewed":true}]
```

Candidates are initially collapsed. Saving a reference before opening them reduces, but does not eliminate, bias. Reload the JSON to continue editing. Text is not saved automatically when closing the page. Generated reports contain private material and must not be published.

## Metric definitions and boundaries

WER is word-level Levenshtein distance divided by reference word count. Normalization uses Unicode NFKC, lowercase, normalized apostrophes and removed punctuation. Accents, negations and numbers remain distinct; digits are not expanded into words. Report these choices because they affect scores. CER uses the same normalized tokens with spaces removed. These choices are not a claim to reproduce a vendor's official FLEURS leaderboard score. WER can exceed 100% when insertions are numerous.

The interactive comparison scores only `human_reviewed: true` references and `scope: exact_clip` candidates. Excerpts taken from coarse segments are `approximate` and excluded. To score a full workflow on selected intervals, verify exact boundary words rather than assuming timestamp cropping creates an exact hypothesis.

Separately decoded clips evaluate that inference mode, not necessarily the same model on a full recording. Include a representative set chosen before reading outputs and a separate difficult-case set. The initial private collection has six 90-second clips, nine minutes total; it still needs verified references.

## Further measurements

- **Diarization:** annotate who speaks when, including overlap. Compute DER with label mapping and declared collar/overlap policy, for example using [pyannote.metrics](https://pyannote.github.io/pyannote-metrics/reference.html). The current evaluator does not implement DER.
- **Identity:** separate enrollment, calibration and test meetings. Include unknown voices and measure false attribution and abstention. Speaker count does not measure name recognition.
- **Glossary:** hold audio, model and parameters constant; compare with/without terms, including correct terms and spurious substitutions. Human-corrected notes versus raw output do not isolate glossary effects.
- **Timing:** repeat runs and separate cold/warm startup, loading, normalization, inference, review and total duration. The initial benchmark uses one run per configuration.
- **Review:** time human work and listen to unflagged passages too. Lowering thresholds without this check may hide errors rather than reduce effort.
