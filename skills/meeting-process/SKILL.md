---
name: meeting-process
description: "Process meeting recordings with the local meet pipeline: transcription, diarization, glossary, voice matching and review reports. Use for new audio, queued processing or resuming a job."
---

# Meeting Process

Use the installed `meet` CLI (`command -v meet`, otherwise `~/.local/bin/meet`). Run `meet doctor` when setup is uncertain. The engines and state machine live in the package; do not recreate them in a chat or use Vibe as an implicit fallback.

For a recording, run `meet process AUDIO --project PROJECT --language auto --recipe quality`. Use `it` or `en` when known. `--speakers N` means a known number of people who spoke, not merely attendees. Default quality runs independent Parakeet/Qwen reads and selective Whisper checks. `fast` is an explicit speed tradeoff.

For queued input, `meet watch --once` processes stable files in the configured local inbox. The installed background service may already do this; do not launch a second persistent watcher. `meet jobs` and `meet jobs JOB` show state. Re-running the same content/configuration resumes or returns the existing job.

Report the actual job status and link its `review.html` and `transcript.md`. `needs_review` is a completed automatic pass with unresolved questions, not a final validated transcript. Keep transcripts in their spoken language. Do not silently replace text, assign names from context, or infer an accuracy percentage from decoder confidence.

For user-requested Obsidian delivery, use `meet export JOB --directory DESTINATION`; add `--draft` only when a draft is intended. Existing different notes are never overwritten. Comu transfer is a separate input integration: a folder watcher does not establish device sync or cloud backup.
