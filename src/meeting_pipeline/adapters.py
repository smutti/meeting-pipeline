"""Adapters expose plain word/turn records; model SDKs stay outside the core."""

from __future__ import annotations
from pathlib import Path
import time
import wave
from .common import read, save, run, digest, file_hash
from .knowledge import normalized


def prepare(source, target):
    run(
        [
            "ffmpeg",
            "-v",
            "warning",
            "-y",
            "-i",
            source,
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            target,
        ],
        target.with_suffix(".decode.log"),
    )
    with wave.open(str(target), "rb") as wav:
        duration = wav.getnframes() / wav.getframerate()
    if duration <= 0:
        raise ValueError("Recording contains no decodable audio")
    return {"wav": str(target), "duration": duration, "sample_rate": 16000}


def crop(wav, target, start, end):
    if not 0 <= start < end:
        raise ValueError("Invalid crop interval")
    run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-ss",
            start,
            "-i",
            wav,
            "-t",
            end - start,
            "-c:a",
            "pcm_s16le",
            target,
        ]
    )
    return target


class Engines:
    def __init__(self, config):
        self.config = config

    def asr(self, engine, audio, language, directory, hotwords=()):
        directory.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        output = directory / "raw.json"
        if engine == "parakeet":
            run(
                [
                    self.config["fluid_binary"],
                    "transcribe",
                    audio,
                    "--model-version",
                    "ultra",
                    "--output-json",
                    output,
                ],
                directory / "engine.log",
            )
            raw = read(output)
            words = [
                {
                    "text": w["word"],
                    "start": w["startTime"],
                    "end": w["endTime"],
                    "confidence": w.get("confidence"),
                }
                for w in raw["wordTimings"]
            ]
            segments = []
        elif engine in {"qwen", "whisper"}:
            request = {
                "mode": engine,
                "audio": str(audio),
                "language": language,
                "model": self.config[engine + "_model"],
                "hotwords": list(hotwords),
                "output": str(output),
            }
            req = directory / "request.json"
            save(req, request)
            run(
                [
                    self.config["mlx_python"],
                    Path(__file__).with_name("mlx_worker.py"),
                    req,
                ],
                directory / "engine.log",
            )
            raw = read(output)
            words = [
                {
                    "text": w["word"],
                    "start": w["start"],
                    "end": w["end"],
                    "confidence": w.get("probability"),
                }
                for s in raw.get("segments", [])
                for w in s.get("words", [])
            ]
            segments = [
                {
                    "text": s["text"],
                    "start": s["start"],
                    "end": s["end"],
                    "language": s.get("language", language),
                }
                for s in raw.get("segments", [])
            ]
        else:
            raise ValueError(f"Unsupported ASR adapter: {engine}")
        return {
            "engine": engine,
            "text": raw["text"],
            "words": words,
            "segments": segments,
            "wall_seconds": time.monotonic() - started,
            "hotwords_applied": list(hotwords) if engine == "qwen" else [],
            "raw": str(output),
        }

    def diarize(self, engine, audio, directory, speakers=None):
        directory.mkdir(parents=True, exist_ok=True)
        output = directory / "raw.json"
        started = time.monotonic()
        if engine == "nemotron3":
            if speakers and speakers > 8:
                raise ValueError(
                    "Nemotron-3 supports at most 8 speakers; select community1"
                )
            cmd = [
                self.config["nemo_binary"],
                "diarize",
                audio,
                "--model",
                self.config["nemotron_model"],
                "--preset",
                "v3-offline",
                "--device",
                "metal",
                "--format",
                "json",
                "--output",
                output,
                "--force",
            ]
        elif engine == "community1":
            cmd = [
                self.config["fluid_binary"],
                "process",
                audio,
                "--mode",
                "offline",
                "--output",
                output,
            ]
            if speakers:
                cmd += ["--num-speakers", speakers]
        else:
            raise ValueError(f"Unsupported diarization adapter: {engine}")
        run(cmd, directory / "engine.log")
        raw = read(output)
        if engine == "nemotron3":
            segments = [
                {"speaker": str(s["speaker"]), "start": s["start"], "end": s["end"]}
                for s in raw["segments"]
            ]
        else:
            segments = [
                {
                    "speaker": s["speakerId"],
                    "start": s["startTimeSeconds"],
                    "end": s["endTimeSeconds"],
                }
                for s in raw["segments"]
            ]
        if any(s["end"] <= s["start"] or s["start"] < 0 for s in segments):
            raise ValueError("Invalid speaker interval returned by adapter")
        return {
            "engine": engine,
            "segments": segments,
            "count": len({s["speaker"] for s in segments}),
            "fixed_count": speakers if engine == "community1" else None,
            "wall_seconds": time.monotonic() - started,
            "raw": str(output),
        }

    def embed(self, audio, directory):
        # Extract from a confirmed/isolated single-speaker clip, not a meeting centroid.
        result = self.diarize("community1", audio, directory, speakers=1)
        segments = read(result["raw"])["segments"]
        if not segments:
            raise ValueError("No speech detected for voice sample")
        vector = normalized(segments[0]["embedding"])
        if len(vector) < 64:
            raise ValueError("Unexpected embedding dimensions")
        model_root = Path.home() / "Library/Application Support/FluidAudio/Models"
        artifacts = [
            p
            for p in model_root.rglob("*")
            if p.is_file()
            and (
                any(
                    part in {"Embedding.mlmodelc", "FBank.mlmodelc", "PldaRho.mlmodelc"}
                    for part in p.parts
                )
                or p.name == "plda-parameters.json"
            )
        ]
        if not artifacts:
            raise ValueError("Cannot fingerprint local speaker model files")
        fingerprint = digest(
            sorted((str(p.relative_to(model_root)), file_hash(p)) for p in artifacts)
        )
        model_id = "fluidaudio-community1-centroid-v1/" + fingerprint
        return {"embedding": vector, "model_id": model_id}

    def align(self, audio, text, language, directory):
        model = self.config.get("aligner_model")
        if not model or not Path(model).exists():
            raise ValueError(
                "Qwen ForcedAligner is not configured; cannot replace text while retaining old timestamps"
            )
        directory.mkdir(parents=True, exist_ok=True)
        output = directory / "raw.json"
        request = {
            "mode": "align",
            "audio": str(audio),
            "text": text,
            "language": language,
            "model": model,
            "output": str(output),
        }
        save(directory / "request.json", request)
        run(
            [
                self.config["mlx_python"],
                Path(__file__).with_name("mlx_worker.py"),
                directory / "request.json",
            ],
            directory / "engine.log",
        )
        return read(output)
