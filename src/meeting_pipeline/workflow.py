from __future__ import annotations
from importlib.resources import files
import json
from pathlib import Path
import shutil
import time
from . import __version__
from .adapters import Engines, prepare, crop
from .common import read, save, digest, file_hash, locked, load_config
from .knowledge import load, terms_for, match
from .quality import inspect_primary, compare, clean_spans, issue, text_between, tokens
from .state import State


def load_recipe(name):
    path = Path(name)
    recipe = (
        read(path)
        if path.is_file()
        else json.loads(
            files("meeting_pipeline").joinpath("recipes", name + ".json").read_text()
        )
    )
    if (
        recipe["primary_asr"] != "parakeet"
        or recipe["secondary_asr"] != "qwen"
        or recipe["fallback_asr"] != "whisper"
    ):
        raise ValueError(
            "This version supports Parakeet primary, Qwen secondary and Whisper fallback adapters"
        )
    if recipe["diarizer"] not in {"nemotron3", "community1"} or recipe[
        "secondary_scope"
    ] not in {"full", "flagged"}:
        raise ValueError("Unsupported recipe routing")
    if recipe.get("auto_replace_text"):
        raise ValueError(
            "Automatic text arbitration is not calibrated; use explicit reviewed replacements"
        )
    if (
        not 10 <= recipe["window_seconds"] <= 120
        or not 0 <= recipe["max_fallback_clips"] <= 30
    ):
        raise ValueError("Invalid recipe limits")
    return recipe


def process(
    home,
    source,
    project="general",
    language="auto",
    recipe_name="quality",
    speakers=None,
    engines=None,
):
    if language not in {"it", "en", "auto"}:
        raise ValueError("Language must be it, en or auto")
    if speakers is not None and speakers < 1:
        raise ValueError("Speaker count must be positive")
    source = Path(source).expanduser().resolve()
    if not source.is_file():
        raise ValueError("Audio file not found")
    config = load_config(home)
    recipe = load_recipe(recipe_name)
    knowledge = load(home)
    terms = (
        terms_for(knowledge, project, language)
        if language != "auto"
        else list(
            {
                t["id"]: t
                for lang in ["it", "en"]
                for t in terms_for(knowledge, project, lang)
            }.values()
        )
    )
    content_hash = file_hash(source)
    parameters = {
        "project": project,
        "language": language,
        "expected_speakers": speakers,
        "recipe": recipe,
        "knowledge": knowledge,
        "runtime": config["runtime"],
        "code_version": __version__,
    }
    job_id = digest([content_hash, parameters])[:24]
    state = State(home)
    state.register(job_id, source)
    directory = home / "jobs" / job_id
    directory.mkdir(parents=True, exist_ok=True)
    with locked(home / "worker.lock"):
        if state.job(job_id)["status"] in {"ready", "needs_review", "reviewed"}:
            return {
                "job": job_id,
                "status": state.job(job_id)["status"],
                "directory": str(directory),
                "reused": True,
            }
        state.status(job_id, "running")
        engines = engines or Engines(config["runtime"])
        try:
            original = directory / ("original" + source.suffix.lower())
            if not original.exists():
                tmp = original.with_suffix(original.suffix + ".copying")
                shutil.copyfile(source, tmp)
                if file_hash(tmp) != content_hash:
                    raise ValueError("Source changed during copy; retry once stable")
                tmp.replace(original)
            if file_hash(original) != content_hash:
                raise ValueError("Stored recording hash mismatch")
            manifest = {
                "schema": 1,
                "job": job_id,
                "source_hash": content_hash,
                "original": str(original),
                "source_name": source.name,
                "parameters": parameters,
                "created": time.time(),
            }
            save(directory / "manifest.json", manifest)
            audio = state.step(
                job_id,
                "audio",
                [content_hash, "pcm16-mono-16k-v1"],
                lambda: prepare(original, directory / "audio.wav"),
            )
            wav = Path(audio["wav"])

            def step(name, fn, dependencies=()):
                print(f"[{job_id}] {name}", flush=True)
                return state.step(job_id, name, [parameters, dependencies], fn)

            primary = step(
                "primary",
                lambda: engines.asr("parakeet", wav, language, directory / "primary"),
            )
            diar_engine = (
                "community1" if speakers and speakers > 8 else recipe["diarizer"]
            )
            diar = step(
                "diarization",
                lambda: engines.diarize(
                    diar_engine, wav, directory / "diarization", speakers
                ),
            )
            issues = inspect_primary(
                primary, diar, audio["duration"], recipe, terms, speakers
            )
            hotwords = [t["canonical"] for t in terms]
            secondary = None
            if recipe["secondary_scope"] == "full":
                secondary = step(
                    "secondary",
                    lambda: engines.asr(
                        "qwen", wav, language, directory / "secondary", hotwords
                    ),
                )
                issues += compare(primary, secondary, recipe["disagreement_ratio"])
            else:
                targets = [i for i in issues if i["kind"] == "text"]
                parts = []
                for i, item in enumerate(targets):
                    start = max(0, item["start"] - recipe["context_seconds"])
                    end = min(
                        audio["duration"], item["end"] + recipe["context_seconds"]
                    )
                    clip = crop(wav, directory / f"secondary-{i}.wav", start, end)
                    result = step(
                        f"secondary-{i}",
                        lambda c=clip, i=i: engines.asr(
                            "qwen", c, language, directory / f"secondary-{i}", hotwords
                        ),
                        [start, end],
                    )
                    issues += compare(
                        primary, result, recipe["disagreement_ratio"], offset=start
                    )
                    parts += [
                        {**s, "start": s["start"] + start, "end": s["end"] + start}
                        for s in result["segments"]
                    ]
                secondary = {"engine": "qwen", "segments": parts, "scope": "flagged"}
                save(directory / "secondary.json", secondary)
            # Exact agreement can resolve score-only alerts, never a glossary or speaker conflict.
            for item in issues:
                if (
                    item["kind"] == "text"
                    and ";" not in item["reason"]
                    and "low decoder scores" in item["reason"]
                ):
                    for s in secondary["segments"]:
                        if (
                            s["start"] <= item["start"]
                            and s["end"] >= item["end"]
                            and tokens(
                                text_between(primary["words"], s["start"], s["end"])
                            )
                            == tokens(s["text"])
                        ):
                            item.update(
                                status="supported",
                                resolution="independent agreement; not human verified",
                            )
            if (
                recipe["check_diarization"]
                and diar_engine != "community1"
                and any(i["kind"].startswith("speaker") for i in issues)
            ):
                alternative = step(
                    "diarization-alternative",
                    lambda: engines.diarize(
                        "community1",
                        wav,
                        directory / "diarization-alternative",
                        speakers,
                    ),
                )
                # Keep both global label systems; equal counts do not resolve assignment errors.
                save(
                    directory / "diarization-comparison.json",
                    {
                        "primary_count": diar["count"],
                        "alternative_count": alternative["count"],
                        "automatically_selected": diar_engine,
                    },
                )
            unresolved = [
                i
                for i in issues
                if i["kind"] == "disagreement" and i["status"] == "open"
            ]
            unresolved.sort(key=lambda i: i["disagreement"], reverse=True)
            for index, item in enumerate(unresolved[: recipe["max_fallback_clips"]]):
                start = max(0, item["start"] - recipe["context_seconds"])
                end = min(audio["duration"], item["end"] + recipe["context_seconds"])
                clip = crop(wav, directory / f"fallback-{index}.wav", start, end)
                alternative = step(
                    f"fallback-{index}",
                    lambda c=clip, i=index: engines.asr(
                        "whisper", c, language, directory / f"fallback-{i}"
                    ),
                    [start, end],
                )
                item["third_reading"] = {
                    "text": alternative["text"],
                    "context_start": start,
                    "context_end": end,
                }
            identities = {}
            for speaker in sorted({s["speaker"] for s in diar["segments"]}):
                spans = clean_spans(
                    diar["segments"], speaker, count=recipe["voice_samples_per_speaker"]
                )
                vectors = []
                model_id = config["runtime"]["embedding_model_id"]
                if knowledge["voices"]:
                    for index, (start, end) in enumerate(spans):
                        name = f"voice-{digest(speaker)[:8]}-{index}"
                        clip = crop(wav, directory / (name + ".wav"), start, end)
                        value = step(
                            name,
                            lambda c=clip, n=name: engines.embed(c, directory / n),
                            [start, end],
                        )
                        if vectors and model_id != value["model_id"]:
                            raise ValueError(
                                "Speaker model changed during embedding extraction"
                            )
                        model_id = value["model_id"]
                        vectors.append(value["embedding"])
                identity = match(
                    vectors, knowledge, model_id, exclude_source=content_hash
                )
                identities[speaker] = {**identity, "sample_spans": spans}
                if identity["status"] != "matched":
                    segment = next(
                        s for s in diar["segments"] if s["speaker"] == speaker
                    )
                    start, end = (
                        spans[0] if spans else (segment["start"], segment["end"])
                    )
                    issues.append(
                        issue(
                            "identity",
                            start,
                            end,
                            "Name not confirmed for this speaker",
                            speaker=speaker,
                            candidates=identity["candidates"],
                        )
                    )
            save(directory / "identities.json", identities)
            save(directory / "issues.json", issues)
            save(
                directory / "selected.json",
                {"words": primary["words"], "source": "parakeet", "reviewed_edits": []},
            )
            save(
                directory / "speaker-names.json",
                {s: i["name"] for s, i in identities.items() if i["name"]},
            )
            status = (
                "needs_review"
                if any(i["status"] == "open" for i in issues)
                else "ready"
            )
            state.status(job_id, status)
            from .report import render

            render(home, job_id)
            state.event(job_id, "processed", {"status": status, "issues": len(issues)})
            return {
                "job": job_id,
                "status": status,
                "directory": str(directory),
                "issues": sum(i["status"] == "open" for i in issues),
            }
        except Exception as error:
            state.status(job_id, "failed", str(error))
            raise
