from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
from .common import data_home, load_config, read, save, file_hash, digest, locked
from .knowledge import load, add_term, enroll
from .state import State


def init(home, runtime_root):
    root = Path(runtime_root).expanduser().resolve()
    config_path = home / "config.json"
    if config_path.exists():
        raise ValueError(
            "Configuration already exists; edit its local config.json instead of resetting it"
        )
    runtime = {
        "fluid_binary": str(root / "vendor/FluidAudio/.build/release/fluidaudiocli"),
        "nemo_binary": str(
            root
            / "vendor/nemo-binary/nemo-speech-0.3.0-macos-aarch64-metal/bin/nemo-speech"
        ),
        "mlx_python": str(root / ".venv/bin/python"),
        "qwen_model": str(root / "models/qwen3-asr"),
        "whisper_model": str(root / "models/whisper-large-v3"),
        "nemotron_model": str(root / "models/nemotron3-f32.gguf"),
        "aligner_model": None,
        "embedding_model_id": "FluidAudio-16780f04/Community1-7eab74f3/centroid-v1",
    }
    for key, value in runtime.items():
        if (
            key not in {"aligner_model", "embedding_model_id"}
            and not Path(value).exists()
        ):
            raise ValueError(f"Runtime component missing: {key}: {value}")
    if (root / "models/qwen-aligner").is_dir():
        runtime["aligner_model"] = str(root / "models/qwen-aligner")
    home.mkdir(parents=True, exist_ok=True)
    os.chmod(home, 0o700)
    # Include actual local embedding/fbank model bytes in the profile compatibility ID.
    model_root = Path.home() / "Library/Application Support/FluidAudio/Models"
    model_files = [
        p
        for p in model_root.rglob("*")
        if p.is_file()
        and any(
            part in {"Embedding.mlmodelc", "FBank.mlmodelc", "PldaRho.mlmodelc"}
            for part in p.parts
        )
    ]
    if model_files:
        runtime["embedding_model_id"] += (
            "/"
            + digest(
                sorted(
                    (str(p.relative_to(model_root)), file_hash(p)) for p in model_files
                )
            )[:16]
        )
    save(
        config_path,
        {
            "schema": 1,
            "runtime": runtime,
            "inbox": str(home / "inbox"),
            "auto_export_directory": str(home / "outbox"),
        },
    )
    (home / "inbox").mkdir(exist_ok=True)
    State(home)
    return {
        "config": str(config_path),
        "inbox": str(home / "inbox"),
        "runtime_reused": str(root),
    }


def doctor(home):
    config = load_config(home)
    checks = {
        k: Path(v).exists() if v else False
        for k, v in config["runtime"].items()
        if k != "embedding_model_id"
    }
    checks.update({p: bool(shutil.which(p)) for p in ["ffmpeg", "ffprobe"]})
    return {
        "checks": checks,
        "processing_ready": all(v for k, v in checks.items() if k != "aligner_model"),
        "review_replacement_ready": checks.get("aligner_model", False),
        "data_home": str(home),
    }


def voice_enroll(home, args):
    from .adapters import Engines, prepare, crop

    if not args.confirmed:
        raise ValueError(
            "Use --confirmed only after identifying the person and checking clean single-speaker speech"
        )
    source = Path(args.audio).expanduser().resolve()
    if not source.is_file():
        raise ValueError("Audio file not found")
    if args.end - args.start < 6 or args.start < 0:
        raise ValueError("Select at least 6 seconds")
    config = load_config(home)
    with locked(home / "worker.lock"), tempfile.TemporaryDirectory(dir=home) as tmp:
        work = Path(tmp)
        full = prepare(source, work / "full.wav")
        if args.end > full["duration"]:
            raise ValueError("Sample exceeds recording duration")
        audio = crop(work / "full.wav", work / "sample.wav", args.start, args.end)
        vector = Engines(config["runtime"]).embed(audio, work / "embedding")
        result = enroll(
            home,
            args.name,
            vector["embedding"],
            vector["model_id"],
            file_hash(source),
            args.start,
            args.end,
            True,
        )
        return {k: v for k, v in result.items() if k != "embedding"}


def parser():
    p = argparse.ArgumentParser(
        prog="meet",
        description="Local meeting workflows, review, voice profiles and project glossaries",
    )
    p.add_argument(
        "--home",
        help="Private data directory (default MEETING_PIPELINE_HOME or ~/.local/share/meeting-pipeline)",
    )
    sub = p.add_subparsers(dest="command", required=True)
    cmd = sub.add_parser("init")
    cmd.add_argument("--runtime-root", required=True)
    sub.add_parser("doctor")
    intake = sub.add_parser("intake").add_subparsers(dest="action", required=True)
    cmd = intake.add_parser(
        "discover", help="Stage marked AirDrop ZIPs without running models"
    )
    cmd.add_argument("directory")
    cmd.add_argument("--timezone", default="Europe/Rome")
    cmd.add_argument("--stable-seconds", type=float, default=30)
    cmd = intake.add_parser("set-time")
    cmd.add_argument("intake_id")
    cmd.add_argument(
        "recorded_at", help="Original recording time with an explicit UTC offset"
    )
    cmd = intake.add_parser("apply-calendar")
    cmd.add_argument("intake_id")
    cmd.add_argument("snapshot")
    cmd.add_argument(
        "--event-id", help="Explicit user-confirmed selection for an ambiguous match"
    )
    cmd.add_argument(
        "--without-title",
        action="store_true",
        help="Explicitly queue with the original name",
    )
    cmd = sub.add_parser("process")
    cmd.add_argument("audio")
    cmd.add_argument("--project", default="general")
    cmd.add_argument("--language", choices=["it", "en", "auto"], default="auto")
    cmd.add_argument("--recipe", default="quality")
    cmd.add_argument("--speakers", type=int)
    cmd.add_argument(
        "--meeting-metadata",
        help="JSON title/provenance metadata for this explicitly supplied recording",
    )
    cmd = sub.add_parser("jobs")
    cmd.add_argument("job", nargs="?")
    cmd = sub.add_parser("watch")
    cmd.add_argument("--once", action="store_true")
    cmd.add_argument("--interval", type=float, default=15)
    cmd.add_argument("--stable-seconds", type=float, default=30)
    cmd = sub.add_parser("export")
    cmd.add_argument("job")
    cmd.add_argument("--directory", required=True)
    cmd.add_argument("--draft", action="store_true")
    rev = sub.add_parser("review").add_subparsers(dest="action", required=True)
    cmd = rev.add_parser("list")
    cmd.add_argument("job")
    cmd.add_argument("--limit", type=int, default=20)
    cmd = rev.add_parser("resolve")
    cmd.add_argument("job")
    cmd.add_argument("issue")
    cmd.add_argument(
        "--action",
        dest="resolution",
        choices=["keep", "name", "replace"],
        required=True,
    )
    cmd.add_argument("--text")
    cmd.add_argument("--name")
    cmd.add_argument("--language", choices=["it", "en"])
    cmd = rev.add_parser("render")
    cmd.add_argument("job")
    gloss = sub.add_parser("glossary").add_subparsers(dest="action", required=True)
    gloss.add_parser("list")
    cmd = gloss.add_parser("add")
    cmd.add_argument("term")
    cmd.add_argument("--alias", action="append", default=[])
    cmd.add_argument("--project", default="*")
    cmd.add_argument("--language", choices=["it", "en", "*"], default="*")
    cmd.add_argument("--meaning", default="")
    voices = sub.add_parser("voice").add_subparsers(dest="action", required=True)
    voices.add_parser("list")
    cmd = voices.add_parser("enroll")
    cmd.add_argument("name")
    cmd.add_argument("audio")
    cmd.add_argument("--start", type=float, required=True)
    cmd.add_argument("--end", type=float, required=True)
    cmd.add_argument("--confirmed", action="store_true")
    cmd = voices.add_parser("policy")
    cmd.add_argument("--threshold", type=float, required=True)
    cmd.add_argument("--margin", type=float, required=True)
    cmd.add_argument(
        "--evidence",
        required=True,
        help="Path to a report documenting validation on labeled held-out recordings",
    )
    cmd.add_argument("--enable", action="store_true")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    home = data_home(args.home)
    os.umask(0o077)
    try:
        if args.command == "init":
            result = init(home, args.runtime_root)
        elif args.command == "doctor":
            result = doctor(home)
        elif args.command == "intake":
            from .intake import discover, set_time, apply_calendar

            if args.action == "discover":
                result = discover(
                    home, args.directory, args.timezone, args.stable_seconds
                )
            elif args.action == "set-time":
                result = set_time(home, args.intake_id, args.recorded_at)
            else:
                result = apply_calendar(
                    home,
                    args.intake_id,
                    args.snapshot,
                    args.event_id,
                    args.without_title,
                )
        elif args.command == "process":
            from .workflow import process

            result = process(
                home,
                args.audio,
                args.project,
                args.language,
                args.recipe,
                args.speakers,
                meeting=read(args.meeting_metadata) if args.meeting_metadata else None,
            )
        elif args.command == "jobs":
            state = State(home)
            result = state.job(args.job) if args.job else state.jobs()
        elif args.command == "watch":
            from .service import scan_once

            if args.interval < 1 or args.stable_seconds < 0:
                raise ValueError("Invalid watcher interval")
            while True:
                result = scan_once(home, args.stable_seconds)
                if args.once:
                    break
                if result:
                    print(json.dumps(result, ensure_ascii=False), flush=True)
                time.sleep(args.interval)
        elif args.command == "export":
            from .service import export

            result = export(home, args.job, args.directory, args.draft)
        elif args.command == "review":
            from .report import render, resolve

            State(home).job(args.job)
            if args.action == "list":
                result = [
                    i
                    for i in read(home / "jobs" / args.job / "issues.json")
                    if i["status"] == "open"
                ][: args.limit]
            elif args.action == "render":
                result = render(home, args.job)
            else:
                result = resolve(
                    home,
                    args.job,
                    args.issue,
                    args.resolution,
                    args.text,
                    args.name,
                    args.language,
                )
        elif args.command == "glossary":
            result = (
                load(home)["terms"]
                if args.action == "list"
                else add_term(
                    home,
                    args.term,
                    args.alias,
                    args.project,
                    args.language,
                    args.meaning,
                )
            )
        elif args.command == "voice":
            if args.action == "list":
                result = {
                    "policy": load(home)["voice_policy"],
                    "samples": [
                        {k: v for k, v in x.items() if k != "embedding"}
                        for x in load(home)["voices"]
                    ],
                }
            elif args.action == "enroll":
                result = voice_enroll(home, args)
            else:
                if not -1 <= args.threshold <= 1 or not 0 <= args.margin <= 2:
                    raise ValueError("Invalid cosine threshold/margin")
                evidence = Path(args.evidence).expanduser().resolve()
                if not evidence.is_file() or not evidence.stat().st_size:
                    raise ValueError(
                        "Supply a nonempty validation report; a threshold alone is not calibration"
                    )
                with locked(home / "knowledge.lock"):
                    data = load(home)
                    data["voice_policy"].update(
                        threshold=args.threshold,
                        margin=args.margin,
                        auto_accept=args.enable,
                        evidence={"path": str(evidence), "sha256": file_hash(evidence)},
                    )
                    data["version"] += 1
                    save(home / "knowledge.json", data)
                    result = data["voice_policy"]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        print(f"meet: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
