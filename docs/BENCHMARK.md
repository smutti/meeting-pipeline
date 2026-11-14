# Initial workflow comparison — November 14, 2026

**Finding:** the architectural limit of four speakers has been exceeded, and a local workflow with independent readings and an audit trail is operational. This private-meeting experiment does not yet measure an improvement in WER, DER or human review time. Its selected text still matches Parakeet; no replacements have been approved automatically. The subsequent [public-corpus ASR test](AUTOMATIC_EVALUATION.md) is a separate experiment.

Here **V1** means the previous Vibe/Whisper workflow with four-channel Sortformer; **V2** means this repository's local engine. These are architectures, not Git tags: the repository starts with V2. The old adapter required a matrix with four columns and iterated over four channels. Names in archived notes were assigned manually and could exceed the model's channel count.

## Corpus and configuration

Two private recordings: IT-A, Italian, 1,419.987 s (~23:40), seven participants reportedly likely to have spoken; EN-B, predominantly English, 3,411.828 s (~56:52), four reported speakers, recorded in a large reverberant room. User estimates do not replace turn annotations. Archived notes contain some human edits and are not ground truth. The archived English transcript ends at 3,407.05 s, before the normalized WAV ends.

All new engines receive the same mono 16 kHz PCM16 WAV, without denoising or gain adjustment. The decoder reported invalid MP3 packets in the English file; decoded duration is about 0.32 s shorter than the container duration. Originals remain unchanged. Three 90-second excerpts per recording were selected by temporal position before reading outputs: nine minutes total, without completed human references.

Hardware: Apple M5 Pro, 24 GB. MLX 0.32.4, mlx-audio 0.6.5, mlx-whisper 0.4.3. Revisions:

| Component | Revision |
|---|---|
| Whisper large-v3 MLX | `49e6aa286ad60c14352c404340ded53710378a11` |
| Qwen3-ASR 1.7B BF16 MLX | `e1f6c266914abc5a46e8756e02580f834a6cf8a7` |
| Parakeet Ultra Core ML | `95eaa59a39d4394f047a4dc5cce480388a60d1b6` |
| FluidAudio | `16780f04d2ece24f67d0fc00efccd0296491c1a8` |
| Nemotron-3 Diarization | `52a432672732425e4c19765b9fec9b5810e6f4ba` |
| NeMo-Speech.cpp | binary 0.3.0, converter `e790e463b2913cff9f989a3df224c587f14b4c5c` |
| Community-1 Core ML | `7eab74f3463c736418d0eb10296261ae581146c9` |

Parakeet uses a per-channel INT8 encoder; Whisper uses FP16 and Qwen BF16. The Nemotron GGUF contains 358 F32 tensors and one F16 convolution. These are specific implementations and precisions, not a comparison of theoretical architectures alone. Qwen uses 90-second chunks and temperature 0; Whisper uses normal decoding fallback. An earlier greedy diagnostic run is preserved separately and excluded from the main table.

## Full-recording ASR inference

| Engine | IT-A, seconds | EN-B, seconds |
|---|---:|---:|
| Whisper large-v3 / MLX | 104.49 | 306.35 |
| Qwen3-ASR 1.7B / MLX | 73.94 | 121.27 |
| Parakeet Ultra / Core ML | 8.29 | 18.70 |

One execution per configuration, with models already downloaded. Initial MLX loading is excluded; Core ML command startup is included. These are indicative measurements, not repeated averages or timing comparisons with the old Vibe app. Timing does not establish transcript accuracy.

In the English recording, Whisper repeats one short phrase 18 times around 38:30–38:54; the other two outputs contain different text. This is an observed textual anomaly requiring audio verification, not a certified error count without a verified reference.

## Diarization

| Configuration | IT-A | EN-B | Interpretation |
|---|---:|---:|---|
| V1 four-channel Sortformer | maximum capacity 4 | maximum capacity 4 | Old adapter limit, not a measurement on these files |
| Automatic Nemotron-3 | 7 | 4 | Detected count |
| Automatic Community-1 Core ML | 6 | 3 | Detected count |
| Community-1 Core ML with known count | 7 | 4 | Count supplied as a constraint |

Nemotron supports at most [eight speakers](https://huggingface.co/nvidia/Nemotron-3-Diarization). The workflow selects Community-1 when more than eight speakers are explicitly supplied. This does not promise unlimited or correct diarization.

Nemotron's seventh Italian cluster contains only 3.868 s; its shortest English cluster contains 1.696 s. Counts match expectations but may include fragmentation of one voice. DER requires annotated turns and label mapping. Community-1 with a supplied count is not independent confirmation of the real count.

## Complete V2 workflow

These runs use the `quality` recipe at commit `cd1ded5`, with the operational runtime outside protected macOS folders. The ASR benchmark above is separate. Package version was 0.1.0; the commit is recorded here because the initial manifest stored only the package version.

| Measurement | IT-A | EN-B |
|---|---:|---:|
| Observed end-to-end time | 138.97 s | 179.70 s |
| Open issues | 67 | 151 |
| Targeted Whisper readings | 6 | 2 |
| Audio covered by the union of flagged intervals | 97.2% | 97.3% |
| Approved text replacements | 0 | 0 |
| Final state | `needs_review` | `needs_review` |

End-to-end time is job creation to last update, excluding human review. Checks include low decoder scores, speaker alignment, disagreements, very short clusters and unknown identities. Check windows are broad: 97% coverage **does not mean 97% incorrect words**, nor does it measure actual review time. It does show that a substantial reduction in manual listening is not yet established.

Selected text matches benchmark Parakeet on both recordings when compared as whitespace-separated words. Qwen and Whisper add alternatives and flags; this version does not automatically select the most accurate text. No voice profiles are enrolled. The glossary contains only one project name per recording. Neither name recognition nor glossary benefits have been measured in this experiment.

An earlier Italian run had 46 issues because the later speaker-alignment check was absent. It remains in the local comparison but is not used to infer improvement or regression from the current 67 issues.

[Aggregate data](benchmark-2026-11-14.json) is public; recordings, transcripts, names, paths and profiles remain private. These are author-reported observations on a private corpus, not independently reproducible results without the audio. The [protocol](EVALUATION.md) and code support repetition on another corpus. Establishing meeting accuracy gains requires verified references on identical intervals, annotated speaker turns and review-time measurements.
