# Process files supplied in chat

Attach an audio file or provide its existing local path, then invoke `meeting-process`. The agent resolves that particular file and runs the installed CLI. No folder scan, scheduled import or running inbox service is required.

```sh
meet process /path/to/supplied-recording.mp3 --language auto --recipe quality
meet jobs JOB
meet review list JOB
```

The default remains the full local quality pipeline. Speaker count, project and language can be supplied when known. The agent must not infer speaker names from attendance lists or transcript content. Uploading to a chat is separate from ASR execution: do not describe the attachment upload itself as an offline transfer. The `meet` model adapters run locally once the attachment is available on the Mac.

## Optional Outlook title

An on-demand lookup can match the supplied recording's original timestamp and duration against Outlook. Use the complete bounded snapshot and conservative matching rules in [the calendar contract](IPHONE_OUTLOOK.md). Calendar arrival/download time is not recording time. A missing original timestamp or ambiguous event needs a user choice.

Save the chosen title and provenance in a private JSON file and pass it directly:

```sh
meet process /path/to/supplied-recording.mp3 --meeting-metadata /private/meeting.json
```

```json
{
  "title": "Engineering sync",
  "recorded_at": "2026-11-12T09:35:31+01:00",
  "original_name": "2026-11-12 09_35_31.mp3",
  "calendar_provider": "outlook",
  "event_id": "example-event-id",
  "title_source": "outlook_time_match"
}
```

The CLI records supplied metadata; it does not authenticate Outlook or perform the match itself. Match first, then supply the result. The job manifest and exported filename preserve the title. Calendar events are read only.

## Voice profiles from previous recordings

Reuse original audio and existing diarization to prepare short single-speaker candidates, retaining the source hash and exact original start/end times. Prefer intervals supported by both diarizers, but treat that agreement as candidate selection rather than proof that the audio contains one person. Present playable clips and ask for the speaker's name and clean-speech confirmation. IDs are local to each recording; matching numeric speaker IDs across recordings does not establish identity.

After confirmation, use `meet voice enroll NAME ORIGINAL_AUDIO --start SECONDS --end SECONDS --confirmed`. The command extracts an acoustic representation and stores it privately. It does not synthesize speech or copy a voice. Keep unclear or too-short intervals out of enrollment; the command requires at least six seconds. The review workflow prefers eight to twelve seconds to leave some margin.

An initial sample can create a profile. Automatic name acceptance remains disabled until a recognition policy has been validated on separate labeled recordings, including unknown speakers. The current policy additionally requires independent reference recordings and multiple query samples. Clips from the same meeting are not independent recordings. Reuse the same confirmed name across recordings only after checking identity; keep samples for evaluation separate from enrollment.

## Operating without folder monitoring

Remove the recurring import through Codex's automation controls. Unload `local.meeting-pipeline.inbox` and move its plist outside `~/Library/LaunchAgents` so it cannot restart at login. Preserve recordings, jobs and the private runtime. Do not run `scripts/install_local.py --service` unless folder monitoring is explicitly requested again.

The installed runtime can be updated without enabling a service:

```sh
uv pip install --python ~/.local/share/meeting-pipeline/service-env/bin/python \
  --reinstall-package local-meeting-pipeline /path/to/meeting-pipeline
```
