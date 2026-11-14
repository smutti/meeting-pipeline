---
name: meeting-process
description: "Process meeting audio attached or explicitly referenced in chat with the local meet pipeline: transcription, diarization, optional Outlook titles and transcript export. Use for a supplied recording or resuming its job."
---

# Meeting Process

Use the installed `meet` CLI (`command -v meet`, otherwise `~/.local/bin/meet`). Run `meet doctor` when setup is uncertain. The engines and state machine live in the package; do not recreate them in a chat or use Vibe as an implicit fallback.

The default input is an audio file attached or explicitly referenced in the current chat. Resolve the supplied attachment/path and process only that recording. Do not scan Downloads or an inbox, invoke `meet watch`, create a folder automation, or enable the LaunchAgent unless the user explicitly requests that input mode. See [chat input](../../docs/CHAT_INPUT.md). Folder intake remains an optional integration in the repository.

For a recording, run `meet process AUDIO --project PROJECT --language auto --recipe quality`. Use `it` or `en` when known. `--speakers N` means a known number of people who spoke, not merely attendees. Default quality runs independent Parakeet/Qwen reads and selective Whisper checks. `fast` is an explicit speed tradeoff.

When an Outlook title is wanted, read the calendar for the supplied recording's original time and duration and use the conservative matcher described in [the calendar contract](../../docs/IPHONE_OUTLOOK.md). File arrival time is not recording time. Pass verified title metadata using `--meeting-metadata PATH`; no folder watcher is needed. Ask about ambiguous matches rather than assigning a title from context.

`meet jobs` and `meet jobs JOB` show state. Re-running the same content/configuration resumes or returns the existing job. A queued job is not authorization to scan folders for additional recordings.

Report the actual job status and link its `review.html` and `transcript.md`. `needs_review` is a completed automatic pass with unresolved questions, not a final validated transcript. Keep transcripts in their spoken language. Do not silently replace text, assign names from context, or infer an accuracy percentage from decoder confidence.

For user-requested Obsidian delivery, use `meet export JOB --directory DESTINATION`; add `--draft` only when a draft is intended. Reuse a destination already authorized in the conversation; ask only if it is missing or ambiguous. Existing different notes are never overwritten. Route transcript/speaker corrections through `meeting-review` and reusable glossaries/voice profiles through `meeting-knowledge`. Historical Vibe/Sortformer results remain available as comparison artifacts only.
