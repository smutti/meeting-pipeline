---
name: meeting-knowledge
description: "Manage local meet knowledge: project and language glossaries, confirmed voice samples and recognition policies. Use to teach technical terms or recurring speakers to the pipeline."
---

# Meeting Knowledge

Use `meet` from PATH or `~/.local/bin/meet`. Knowledge is stored under `MEETING_PIPELINE_HOME` or `~/.local/share/meeting-pipeline`, separately from GitHub. Never add recordings, actual voice embeddings, personal glossaries or meeting transcripts to the code repository.

Inspect `meet glossary list` before updating. Add only terms/spellings supported by the user or a supplied authoritative glossary:

```sh
meet glossary add "Canonical term" --alias "observed spelling" --project PROJECT --language it --meaning "Short disambiguating context"
```

Use language `*` for names shared across Italian/English and project `*` only for global terminology. An alias flags a possible spelling and the canonical form is offered to Qwen as a hotword; it is not an unconditional search-and-replace. These are transcriptions in the spoken language, not automatic translations. The stored meaning is descriptive metadata; the current adapter passes canonical terms, not the full definitions, to ASR.

Inspect `meet voice list` before enrollment. For a person whose identity the user has confirmed, choose a clean single-speaker interval of at least six seconds and run:

```sh
meet voice enroll "Confirmed person" AUDIO --start SECONDS --end SECONDS --confirmed
```

Existing processed meetings can supply enrollment candidates without running ASR again. Use the original audio and stored diarization, prefer isolated 8–12 second intervals, and present playable clips with stable review IDs. Confirmation must bind the name to the exact source hash and interval; speaker IDs are local to a job. Keep candidates private and unregistered until the user confirms identity and clean speech. For detailed candidate handling, see [voice profiles from existing recordings](../../docs/CHAT_INPUT.md#voice-profiles-from-previous-recordings).

Prefer several samples from different recordings/acoustic conditions. Never use a name merely guessed from the transcript. Duplicate intervals are not extra evidence. Enrollment stores a versioned acoustic representation; it does not clone a voice. Names confirmed in a job are not automatically enrollment samples.

Matching returns unknown/suggested until a policy has been validated. `meet voice policy --threshold VALUE --margin VALUE --evidence REPORT --enable` is for a user-requested, evaluated policy change. The evidence report must document labeled held-out tests including unknown speakers; the software records it but cannot attest its quality. Do not create a dummy report to activate recognition. New enrollment disables automatic acceptance until the expanded gallery is re-evaluated.
