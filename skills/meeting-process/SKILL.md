---
name: meeting-process
description: "Import and process meeting recordings with the local meet pipeline: AirDrop/Outlook intake, transcription, diarization and transcript export. Use for new audio, queued processing or resuming a job."
---

# Meeting Process

Use the installed `meet` CLI (`command -v meet`, otherwise `~/.local/bin/meet`). Run `meet doctor` when setup is uncertain. The engines and state machine live in the package; do not recreate them in a chat or use Vibe as an implicit fallback.

For iPhone/AirDrop input, follow [the intake contract](../../docs/IPHONE_OUTLOOK.md). The `Send to Meeting Pipeline` shortcut produces marked ZIPs; `meet intake discover DIRECTORY` stages them, and `meet intake apply-calendar INTAKE_ID SNAPSHOT` queues uniquely matched recordings. Reuse the existing Outlook automation when installed. Read Outlook to obtain the meeting title; use the original recording timestamp and preserve unresolved calendar matches for user review. Do not bypass this metadata step by processing the archive's extracted audio directly.

For a recording, run `meet process AUDIO --project PROJECT --language auto --recipe quality`. Use `it` or `en` when known. `--speakers N` means a known number of people who spoke, not merely attendees. Default quality runs independent Parakeet/Qwen reads and selective Whisper checks. `fast` is an explicit speed tradeoff.

For queued input, `meet watch --once` processes stable files in the configured local inbox. The installed background service may already do this; do not launch a second persistent watcher. `meet jobs` and `meet jobs JOB` show state. Re-running the same content/configuration resumes or returns the existing job.

Report the actual job status and link its `review.html` and `transcript.md`. `needs_review` is a completed automatic pass with unresolved questions, not a final validated transcript. Keep transcripts in their spoken language. Do not silently replace text, assign names from context, or infer an accuracy percentage from decoder confidence.

For user-requested Obsidian delivery, use `meet export JOB --directory DESTINATION`; add `--draft` only when a draft is intended. Reuse a destination already authorized in the conversation; ask only if it is missing or ambiguous. Existing different notes are never overwritten. Route transcript/speaker corrections through `meeting-review` and reusable glossaries/voice profiles through `meeting-knowledge`. Historical Vibe/Sortformer results remain available as comparison artifacts only. Comu transfer follows the separate intake contract above; a folder watcher does not establish device sync or cloud backup.
