# Meeting Pipeline

A local pipeline for Italian and English meetings, with independent transcriptions, diarization, targeted review, project glossaries and voice profiles. Available through a CLI, a macOS background service and three Codex skills.

Open-source code under the [Apache License 2.0](LICENSE). An operational Apple Silicon prototype: recognition quality and installation on other Macs still need further validation. Model weights have [separate licenses](docs/THIRD_PARTY.md). All project documentation is maintained in English; transcripts stay in the language spoken.

## Organization

| Component | Responsibility |
|---|---|
| `src/meeting_pipeline/` | Engine, SQLite state, adapters, quality checks, knowledge and export |
| `src/meeting_pipeline/recipes/` | Versioned `quality` and `fast` workflows |
| `skills/meeting-process/` | Start and inspect processing jobs |
| `skills/meeting-review/` | Review words and speaker assignments |
| `skills/meeting-knowledge/` | Manage glossaries and voice profiles |
| `scripts/compare_transcripts.py` | Offline comparison of archived and candidate transcripts |
| `scripts/evaluate_asr.py` | Repeatable ASR evaluation against public or verified references |
| `tests/`, `.github/workflows/ci.yml` | Software checks without private recordings or model downloads |
| `docs/` | Architecture, evaluation, measured results and roadmap |

Skills are interfaces to the engine. The queue runs without an open Codex chat. Adding a model requires an adapter; changing behavior requires a recipe and appropriate checks, rather than another copy of the skills.

## Install on macOS

Requirements: Apple Silicon, Python 3.12, `uv`, `ffmpeg`, git and Swift/Xcode command-line tools for the native runtime.

```sh
git clone https://github.com/smutti/meeting-pipeline.git
cd meeting-pipeline
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e .
```

Reuse an existing benchmark runtime when available:

```sh
.venv/bin/meet init --runtime-root /path/to/local-meeting-pipeline
.venv/bin/meet doctor
```

For a new installation, `scripts/setup_runtime.py --path /path/to/runtime` downloads several GB, builds FluidAudio and prepares pinned versions. Then run `meet init --runtime-root /path/to/runtime`. A complete clean-Mac rebuild remains unverified; reuse of the existing benchmark runtime has been tested. Core ML models download on first use. Voice representations include hashes of the model files actually used.

```sh
.venv/bin/python scripts/install_local.py
# Also enable the inbox check every minute:
.venv/bin/python scripts/install_local.py --service
```

Skill links are installed in `~/.codex/skills` or `$CODEX_HOME/skills`; the command is installed in `~/.local/bin/meet`. A new chat may be needed to discover the skills. The installer does not replace unrelated installations.

When retiring a previous Vibe workflow, archive its `vibe` and Vibe-based `obsidian-knowledge-capture` skill folders outside the active skills directory. Use `meeting-process`, `meeting-review` and `meeting-knowledge` for ongoing work. Keep historical recordings, transcripts and benchmark artifacts for comparison; retiring the old entry points does not require deleting those results.

With `--service`, a non-editable package is installed in `~/.local/share/meeting-pipeline/service-env`. Runtimes under Documents/Desktop/Downloads are copied into application data because macOS may deny background services access to protected folders. The development checkout stays in place. After updating the code, rerun the installer with `--service` to update the operational copy. Installation stops if a worker is busy.

## Daily use

```sh
meet process "/path/to/meeting.mp3" --project ProjectAlpha --language auto --recipe quality
meet jobs
meet review list JOB
```

The `quality` recipe runs Parakeet and Qwen on the full recording, Nemotron-3 for speaker turns and Whisper on a bounded set of disagreements. Community-1 checks suspicious diarization. `--speakers N` specifies the known number of people who spoke; above eight, Community-1 is selected directly.

The `fast` recipe runs Qwen only on flagged intervals and can miss errors the first engine considers confident. Confidence scores are not accuracy percentages. Initial thresholds are heuristics that need calibration.

Results live in `~/.local/share/meeting-pipeline/jobs/JOB/`: Markdown transcript, local HTML review with audio, original candidates, issue reasons, manifest and audit trail. Open `review.html` in your Mac's browser. Private results stay outside the repository.

### Automatic inbox

Place audio in `~/.local/share/meeting-pipeline/inbox/`. The service waits for a stable file and optionally reads a sidecar named `meeting.mp3.json`:

```json
{"project":"ProjectAlpha","language":"it","recipe":"quality","speakers":7}
```

Without metadata, the defaults are project `general`, automatic language and quality mode. A completed automatic pass ends in `needs_review` or `ready`. Only jobs without unresolved issues are exported automatically to the local `outbox`. An Obsidian destination can be configured in `config.json` once its location has been chosen. Reviewed jobs can also be exported explicitly.

For iPhone input, **Send to Meeting Pipeline** packages exported Comu audio and opens AirDrop. A separate Codex automation can read Outlook and queue recordings using the event subject for audio/transcript titles. Only unambiguous time matches proceed automatically. See [iPhone intake and Outlook setup](docs/IPHONE_OUTLOOK.md), including the hourly calendar bridge, device setup and verification limits. Comu Starter still requires the initial export/share action.

### Review

```sh
meet review resolve JOB ISSUE --action keep
meet review resolve JOB ISSUE --action name --name "Confirmed person"
meet review resolve JOB ISSUE --action replace --text "Text confirmed by listening" --language en
meet export JOB --directory "/path/to/vault/Meetings"
```

Replacement requires a configured Qwen ForcedAligner: new words receive new timestamps. `keep` retains the current selection. A name applies to this meeting; enrolling a persistent voice profile is a separate operation. Use `--draft` to export an intentionally unreviewed draft. Different existing notes are not overwritten.

### Glossary

```sh
meet glossary add "Product X" --alias "product ex" --project ProjectAlpha --language '*' --meaning "Product name"
meet glossary list
```

Canonical spellings become Qwen hotwords; aliases identify possible review cases. There is no unconditional replacement, and text remains in its spoken language. Definitions are descriptive metadata; the current adapter passes canonical terms, not full definitions, to ASR.

### Voice profiles

```sh
meet voice enroll "Confirmed person" "/path/to/audio.mp3" --start 120 --end 135 --confirmed
meet voice list
```

Choose clean, single-speaker intervals of at least six seconds, preferably from multiple recordings. The engine proposes candidates and can abstain. Automatic acceptance starts disabled. Enabling it requires a threshold, a margin and a validation report on separate labeled recordings, including unknown speakers. The CLI records that report but cannot verify its validity. New enrollment disables automatic acceptance until recalibration. Automatically assigned samples never enroll themselves.

## Automatic quality evaluation

A small public test can run without manually transcribing new audio:

```sh
.venv/bin/python scripts/evaluate_asr.py prepare-fleurs \
  --output /path/to/private-evaluations/fleurs --samples-per-language 20
.venv/bin/python scripts/evaluate_asr.py run \
  /path/to/private-evaluations/fleurs/corpus.json \
  --output /path/to/private-evaluations/fleurs/run
```

This downloads a pinned FLEURS test subset, runs Whisper, Parakeet and Qwen locally, and reports WER/CER plus paired bootstrap intervals. Whisper/MLX is a proxy for the previous ASR model, not a rerun of the previous Vibe workflow. Parakeet is the unreviewed V2 selected text. Public read speech cannot establish quality on noisy meetings or speaker identities. See the [evaluation protocol](docs/EVALUATION.md) and [automatic test results](docs/AUTOMATIC_EVALUATION.md).

## Operations and development

```sh
meet doctor
meet watch --once
python -m unittest discover -s tests -v
launchctl print gui/$(id -u)/local.meeting-pipeline.inbox
# Stop the installed service:
launchctl bootout gui/$(id -u) "$HOME/Library/LaunchAgents/local.meeting-pipeline.inbox.plist"
```

Configuration and SQLite live under `MEETING_PIPELINE_HOME`, defaulting to `~/.local/share/meeting-pipeline`. The worker uses a lock, saves checkpoints and retries failed files with increasing delays. Completed files are not processed on every scan. Changing metadata, profiles or recipes and invoking `process` creates a new tracked execution.

See [architecture](docs/ARCHITECTURE.md), [roadmap](docs/ROADMAP.md) and [contribution guidelines](CONTRIBUTING.md). GitHub Actions validates software behavior; model inference runs on the Mac. The [initial comparison](docs/BENCHMARK.md) reports observed timings and limitations without treating disagreement as measured error.

Do not attach meeting recordings, private transcripts, voice profiles or personal glossaries to public issues or pull requests.
