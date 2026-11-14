# Status and roadmap

## Operational foundation

- Python package and CLI with an ML-free core and isolated model runtimes.
- Three installable skills and `quality`/`fast` workflows.
- Stable inbox detection, deduplication, checkpoints, retries, locks and macOS service.
- Parakeet/Qwen, selective Whisper, Nemotron/Community, review reports and Markdown.
- Project/language glossaries with Qwen hotwords and flagged aliases.
- Voice enrollment from real audio, versioned embeddings, suggestions/unknown and an explicit acceptance policy.
- Name/text review with correction alignment when an aligner is configured.
- Software tests in GitHub Actions; recordings and model inference excluded.
- Local transcript comparison and automatic reference-based ASR evaluation, including a pinned public Italian/English test subset.

## Next increment: measured meeting quality

1. Label a small Italian/English meeting set with both flagged and unflagged passages. Separate calibration and evaluation. Public read-speech scores are a preliminary check, not a substitute.
2. Confirm clean samples of recurring speakers from multiple recordings. Include unknown voices and different acoustic conditions in evaluation.
3. Measure text errors, omissions, false names, unflagged errors and human review time. Decoder scores are insufficient.
4. Merge nearby issues and improve filtering: initial thresholds are conservative and produce many alerts.
5. Align both readings to localize disagreements to words; enable automatic replacement only for validated cases.
6. Add speaker-cluster comparison/reconciliation and boundary review beyond count checks and name confirmation.
7. Evaluate diarization against annotated turns using DER with explicit collar and overlap handling.

## Later integrations

- Verify the export actually available from Comu Starter on the Mac; add a source adapter once transfer is reproducible.
- Add independent VAD to check omissions and silence.
- Provide a local editing UI and notify only when action is needed.
- Export to project-specific Obsidian destinations, with summaries separate from transcripts and links to existing notes.
- Package the Mac runtime, validate clean installation and gate model updates with regression benchmarks.

The background service can run before these increments: it produces drafts and review requests. Reliable recognition of names depends on a voice gallery and real evaluation, not installation alone.
