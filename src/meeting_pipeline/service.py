"""Local folder polling; snapshots must remain stable before ingestion."""

from __future__ import annotations
import json
from pathlib import Path
import shutil
import time
from .common import read, save, file_hash, digest, load_config, locked
from .state import State
from .workflow import process


def scan_once(home, stable_seconds=30):
    with locked(home / "inbox.lock"):
        return _scan_once(home, stable_seconds)


def _scan_once(home, stable_seconds):
    config = load_config(home)
    inbox = Path(config["inbox"])
    inbox.mkdir(parents=True, exist_ok=True)
    cache_path = home / "inbox-state.json"
    cache = read(cache_path) if cache_path.exists() else {}
    now = time.time()
    results = []
    for path in sorted(inbox.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in {
            ".wav",
            ".mp3",
            ".m4a",
            ".flac",
            ".mp4",
            ".aac",
        }:
            continue
        key = str(path.resolve())
        stat = path.stat()
        signature = [stat.st_size, stat.st_mtime_ns]
        sidecar = path.with_name(path.name + ".json")
        try:
            metadata = read(sidecar) if sidecar.exists() else {}
            allowed = {"project", "language", "recipe", "speakers"}
            if set(metadata) - allowed:
                raise ValueError("Unknown metadata keys")
        except (ValueError, json.JSONDecodeError) as error:
            results.append({"source": key, "error": str(error)})
            continue
        signature.append(digest(metadata))
        previous = cache.get(key, {})
        if previous.get("signature") != signature:
            cache[key] = {"signature": signature, "first_seen": now}
            continue
        if (
            previous.get("job")
            or now - previous["first_seen"] < stable_seconds
            or now - stat.st_mtime < stable_seconds
        ):
            continue
        if previous.get("retry_after", 0) > now:
            continue
        try:
            result = process(
                home,
                path,
                project=metadata.get("project", "general"),
                language=metadata.get("language", "auto"),
                recipe_name=metadata.get("recipe", "quality"),
                speakers=metadata.get("speakers"),
            )
            cache[key]["job"] = result["job"]
            results.append(result)
            destination = config.get("auto_export_directory")
            if destination and result["status"] in {"ready", "reviewed"}:
                export(home, result["job"], destination)
        except Exception as error:
            cache[key]["error"] = str(error)
            attempts = previous.get("attempts", 0) + 1
            cache[key].update(
                attempts=attempts,
                retry_after=now + min(3600, 60 * 2 ** min(attempts, 6)),
            )
            results.append({"source": key, "error": str(error)})
        save(cache_path, cache)
    save(cache_path, cache)
    return results


def export(home, job_id, directory, draft=False):
    state = State(home)
    job = state.job(job_id)
    if job["status"] not in {"ready", "reviewed"} and not draft:
        raise ValueError(
            "Unresolved review items; use --draft only when a draft export is intended"
        )
    source = home / "jobs" / job_id / "transcript.md"
    target = Path(directory).expanduser().resolve() / (
        job_id + ("-draft" if draft else "") + ".md"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and file_hash(target) != file_hash(source):
        raise ValueError(
            "Destination already contains a different note; choose a new directory"
        )
    shutil.copyfile(source, target)
    state.event(job_id, "export", {"destination": str(target), "draft": draft})
    return {"file": str(target)}
