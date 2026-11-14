#!/usr/bin/env python3
"""Download a fixed public test subset, run local ASR, and score against its references."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import tarfile
import urllib.request
from pathlib import Path

from meeting_pipeline import adapters
from meeting_pipeline.adapters import Engines, prepare
from meeting_pipeline.common import (
    data_home,
    digest,
    file_hash,
    load_config,
    locked,
    read,
    save,
)
from meeting_pipeline.evaluation import metrics, summarize

REVISION = "70bb2e84b976b7e960aa89f1c648e09c59f894dd"
BASE = f"https://huggingface.co/datasets/google/fleurs/resolve/{REVISION}/data"


def prepare_fleurs(root, count):
    if count < 1:
        raise ValueError("Sample count must be positive")
    manifest_path = root / "corpus.json"
    if manifest_path.exists():
        manifest = read(manifest_path)
        if (
            manifest.get("samples_per_language") != count
            or manifest.get("revision") != REVISION
        ):
            raise ValueError("Existing corpus differs; choose a new output directory")
        return manifest_path
    root.mkdir(parents=True, exist_ok=True)
    samples = []
    for language, config in [("it", "it_it"), ("en", "en_us")]:
        with urllib.request.urlopen(
            f"{BASE}/{config}/test.tsv", timeout=60
        ) as response:
            metadata = response.read()
        (root / (config + "-test.tsv")).write_bytes(metadata)
        lookup = {}
        for line in metadata.decode().splitlines():
            fields = line.split("\t")
            lookup[fields[1]] = fields
        chosen = set()
        print(
            f"Downloading {config}: first {count} distinct prompts in the pinned test archive",
            flush=True,
        )
        with (
            urllib.request.urlopen(
                f"{BASE}/{config}/audio/test.tar.gz", timeout=60
            ) as response,
            tarfile.open(fileobj=response, mode="r|gz") as archive,
        ):
            for member in archive:
                name = Path(member.name).name
                fields = lookup.get(name)
                if not member.isfile() or not fields or fields[0] in chosen:
                    continue
                if member.size > 20_000_000:
                    raise ValueError("Unexpectedly large sample")
                target = root / "audio" / config / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as stream:
                    target.write_bytes(stream.read())
                chosen.add(fields[0])
                samples.append(
                    {
                        "sample_id": config + "-" + name.removesuffix(".wav"),
                        "unit_id": fields[0],
                        "language": language,
                        "audio": str(target.relative_to(root)),
                        "audio_hash": file_hash(target),
                        "reference": fields[3],
                        "reference_hash": hashlib.sha256(
                            fields[3].encode()
                        ).hexdigest(),
                        "reference_source": f"{BASE}/{config}/test.tsv",
                        "metadata_sha256": hashlib.sha256(metadata).hexdigest(),
                    }
                )
                if len(chosen) == count:
                    break
        if len(chosen) != count:
            raise ValueError("Not enough distinct prompts in corpus")
    save(
        manifest_path,
        {
            "dataset": "google/fleurs",
            "revision": REVISION,
            "split": "test",
            "license": "CC-BY-4.0",
            "source": "https://huggingface.co/datasets/google/fleurs",
            "samples_per_language": count,
            "selection": "First distinct prompt IDs encountered in each pinned tar archive, before inference; not random, not a full test-set score.",
            "reference_kind": "dataset_reference",
            "samples": samples,
        },
    )
    return manifest_path


def runtime_identity(config):
    artifacts = []
    for key in ["fluid_binary", "mlx_python", "qwen_model", "whisper_model"]:
        path = Path(config[key])
        files = (
            [path]
            if path.is_file()
            else sorted(
                p for p in path.rglob("*") if p.is_file() and ".cache" not in p.parts
            )
        )
        artifacts.extend(
            {"component": key, "file": p.name, "sha256": file_hash(p)} for p in files
        )
    coreml = (
        Path.home() / "Library/Application Support/FluidAudio/Models/parakeet-ultra"
    )
    if not coreml.is_dir():
        raise ValueError(
            "Parakeet models are not cached. Run a normal transcription once before evaluation."
        )
    artifacts.extend(
        {
            "component": "parakeet_coreml",
            "file": str(p.relative_to(coreml)),
            "sha256": file_hash(p),
        }
        for p in sorted(coreml.rglob("*"))
        if p.is_file()
    )
    for name in ["adapters.py", "mlx_worker.py"]:
        p = Path(adapters.__file__).with_name(name)
        artifacts.append(
            {"component": "pipeline", "file": name, "sha256": file_hash(p)}
        )
    versions = json.loads(
        subprocess.check_output(
            [
                config["mlx_python"],
                "-c",
                "import importlib.metadata as m,json; print(json.dumps({n:m.version(n) for n in ['mlx','mlx-audio','mlx-whisper','numpy','transformers','tokenizers','huggingface-hub','soundfile','scipy','librosa']}))",
            ],
            text=True,
        )
    )
    return {
        "artifacts": artifacts,
        "inference_package_versions": versions,
        "python_platform": platform.platform(),
        "fingerprint": digest([artifacts, versions]),
    }


def run_corpus(corpus_path, root):
    corpus = read(corpus_path)
    if corpus.get("reference_kind") not in {"dataset_reference", "human_verified"}:
        raise ValueError("A documented dataset or verified human reference is required")
    samples = corpus["samples"]
    if not samples:
        raise ValueError("The evaluation corpus is empty")
    if len({s["sample_id"] for s in samples}) != len(samples):
        raise ValueError("Duplicate sample IDs")
    home = data_home()
    config = load_config(home)["runtime"]
    root.mkdir(parents=True, exist_ok=True)
    with locked(home / "worker.lock"):
        identity = runtime_identity(config)
        engines = Engines(config)
        rows = []
        for index, sample in enumerate(samples):
            source = (corpus_path.parent / sample["audio"]).resolve()
            if (
                file_hash(source) != sample["audio_hash"]
                or hashlib.sha256(sample["reference"].encode()).hexdigest()
                != sample["reference_hash"]
            ):
                raise ValueError("Corpus audio or reference changed")
            directory = (
                root
                / "samples"
                / digest([sample["sample_id"], sample["audio_hash"]])[:20]
            )
            directory.mkdir(parents=True, exist_ok=True)
            wav = directory / "audio.wav"
            audio = prepare(source, wav)
            # Rotate model order to avoid always favoring the first/last engine.
            order = ["whisper", "parakeet", "qwen"]
            order = order[index % 3 :] + order[: index % 3]
            for engine in order:
                signature = digest(
                    [
                        identity["fingerprint"],
                        sample["audio_hash"],
                        file_hash(wav),
                        engine,
                        sample["language"],
                        "no-hotwords",
                    ]
                )
                result_path = directory / f"{engine}-{signature[:16]}.json"
                if result_path.exists():
                    result = read(result_path)
                else:
                    print(
                        f"{index + 1}/{len(samples)} {sample['language']} {sample['sample_id']} {engine}",
                        flush=True,
                    )
                    result = engines.asr(
                        engine,
                        wav,
                        sample["language"],
                        directory / (engine + "-" + signature[:16]),
                    )
                    save(result_path, result)
                rows.append(
                    {
                        "sample_id": sample["sample_id"],
                        "unit_id": sample["unit_id"],
                        "language": sample["language"],
                        "audio_hash": sample["audio_hash"],
                        "reference_hash": sample["reference_hash"],
                        "engine": engine,
                        "duration_seconds": audio["duration"],
                        "wall_seconds": result["wall_seconds"],
                        "hypothesis": result["text"],
                        "reference": sample["reference"],
                        **metrics(sample["reference"], result["text"]),
                    }
                )
            save(root / "rows.json", rows)
        report = {
            "dataset": {k: v for k, v in corpus.items() if k != "samples"},
            "runtime": identity,
            "normalization": "Unicode NFKC, lowercase, punctuation removed, apostrophes preserved; no number expansion. CER excludes spaces.",
            "timing": "One run per clip/model, including per-call loading. Model order rotated. Cached inference timings retained on rerun. Not a warm throughput benchmark.",
            **summarize(rows),
        }
        save(root / "results.json", report)
        lines = [
            "# Automatic ASR evaluation",
            "",
            report["scope"],
            "",
            "| Language | Model | Samples | WER | CER |",
            "|---|---|---:|---:|---:|",
        ]
        for item in report["totals"]:
            lines.append(
                f"| {item['language']} | {item['engine']} | {item['samples']} | {100 * item['wer']:.2f}% | {100 * item['cer']:.2f}% |"
            )
        lines += [
            "",
            "## Paired comparison against Whisper",
            "",
            "| Language | Candidate | WER delta (pp) | 95% bootstrap interval (pp) | Result |",
            "|---|---|---:|---|---|",
        ]
        for item in report["comparisons"]:
            lo, hi = item["paired_bootstrap_95_percent_interval"]
            lines.append(
                f"| {item['language']} | {item['candidate']} | {100 * item['delta_wer']:+.2f} | [{100 * lo:+.2f}, {100 * hi:+.2f}] | {item['verdict']} |"
            )
        lines += [
            "",
            "Negative delta means fewer word edits. These exploratory intervals are not corrected for multiple comparisons. Read speech and a small deterministic subset do not establish meeting accuracy. Possible training exposure to public data is unknown.",
            "",
            report["normalization"],
            "",
            report["timing"],
        ]
        (root / "results.md").write_text("\n".join(lines) + "\n")
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare-fleurs")
    prepare_parser.add_argument("--output", type=Path, required=True)
    prepare_parser.add_argument("--samples-per-language", type=int, default=20)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("corpus", type=Path)
    run_parser.add_argument("--output", type=Path, required=True)
    run_parser.add_argument("--fail-on-regression", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare-fleurs":
        print(prepare_fleurs(args.output, args.samples_per_language))
    else:
        report = run_corpus(args.corpus, args.output)
        print(args.output / "results.md")
        if args.fail_on_regression and any(
            c["candidate"] == "parakeet" and c["verdict"] == "higher_wer_on_this_sample"
            for c in report["comparisons"]
        ):
            raise SystemExit(2)


if __name__ == "__main__":
    main()
