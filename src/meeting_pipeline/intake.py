"""Stage explicitly marked AirDrop bundles, then queue calendar-enriched audio."""

import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import time
import zipfile

from .calendar_match import (
    instant,
    recording_time,
    query_window,
    match_event,
    meeting_stem,
)
from .common import digest, file_hash, load_config, locked, read, save

MARKER = re.compile(r"^Meeting Upload(?:[ -]\d+| \(\d+\))?\.zip$", re.I)
AUDIO = {".mp3", ".m4a", ".wav", ".flac", ".aac", ".mp4"}
MAX_BYTES = 2 * 1024**3


def duration(path):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    value = float(json.loads(result.stdout)["format"]["duration"])
    if not math.isfinite(value) or not 0 < value <= 86400:
        raise ValueError("Invalid recording duration")
    return value


def _directory(home, intake_id):
    if not re.fullmatch(r"[a-f0-9]{24}", intake_id):
        raise ValueError("Invalid intake ID")
    return home / "intake" / intake_id


def _pending(home):
    items = [read(p) for p in sorted((home / "intake").glob("*/request.json"))]
    return [item for item in items if item["status"] != "queued"]


def discover(home, directory, zone="Europe/Rome", stable_seconds=30):
    """No inference, calendar access, deletion or modification of source bundles."""
    if stable_seconds < 0:
        raise ValueError("Invalid stability interval")
    root = Path(directory).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("AirDrop directory does not exist")
    home.mkdir(parents=True, exist_ok=True)
    with locked(home / "intake.lock"):
        cache_path = home / "intake-archives.json"
        cache = read(cache_path) if cache_path.exists() else {}
        errors = []
        for bundle in sorted(root.iterdir()):
            if (
                bundle.is_symlink()
                or not bundle.is_file()
                or not MARKER.fullmatch(bundle.name)
            ):
                continue
            before = bundle.stat()
            if time.time() - before.st_mtime < stable_seconds:
                continue
            signature = [before.st_size, before.st_mtime_ns]
            if cache.get(str(bundle)) == signature:
                continue
            try:
                if before.st_size > MAX_BYTES:
                    raise ValueError("Bundle exceeds 2 GiB")
                with zipfile.ZipFile(bundle) as archive:
                    members = [
                        m
                        for m in archive.infolist()
                        if not m.is_dir() and not m.filename.startswith("__MACOSX/")
                    ]
                    if (
                        not 1 <= len(members) <= 32
                        or sum(m.file_size for m in members) > MAX_BYTES
                    ):
                        raise ValueError(
                            "Bundle must contain 1–32 audio files, at most 2 GiB total"
                        )
                    names = set()
                    for member in members:
                        path = PurePosixPath(member.filename)
                        if (
                            path.is_absolute()
                            or ".." in path.parts
                            or "\\" in member.filename
                            or stat.S_ISLNK(member.external_attr >> 16)
                        ):
                            raise ValueError("Unsafe archive member")
                        if path.suffix.lower() not in AUDIO or path.name in names:
                            raise ValueError(
                                "Bundle contains unsupported or duplicate filenames"
                            )
                        names.add(path.name)
                    # Validate every member before publishing any staged request.
                    with tempfile.TemporaryDirectory(
                        dir=home, prefix=".intake-"
                    ) as tmp:
                        staged = []
                        for member in members:
                            name = PurePosixPath(member.filename).name
                            audio = Path(tmp) / name
                            with (
                                archive.open(member) as source,
                                audio.open("wb") as target,
                            ):
                                shutil.copyfileobj(source, target)
                            content_hash = file_hash(audio)
                            intake_id = digest([content_hash, name])[:24]
                            recorded_at = recording_time(name, zone)
                            length = duration(audio)
                            request = {
                                "id": intake_id,
                                "source_name": name,
                                "source_hash": content_hash,
                                "bundle": str(bundle),
                                "duration": length,
                                "recorded_at": recorded_at,
                                "status": "pending_calendar"
                                if recorded_at
                                else "needs_recording_time",
                                "timestamp_source": "comu_filename"
                                if recorded_at
                                else None,
                            }
                            if recorded_at:
                                request["query"] = query_window(recorded_at, length)
                            staged.append((audio, request))
                        after = bundle.stat()
                        if [after.st_size, after.st_mtime_ns] != signature:
                            raise ValueError(
                                "Bundle changed during import; retry when stable"
                            )
                        for audio, request in staged:
                            target = _directory(home, request["id"])
                            if (target / "request.json").exists():
                                continue
                            target.mkdir(parents=True, exist_ok=True)
                            audio.replace(target / audio.name)
                            save(target / "request.json", request)
                cache[str(bundle)] = signature
                save(cache_path, cache)
            except (
                ValueError,
                OSError,
                zipfile.BadZipFile,
                subprocess.SubprocessError,
                KeyError,
            ) as error:
                errors.append({"bundle": str(bundle), "error": str(error)})
        return {"pending": _pending(home), "errors": errors}


def set_time(home, intake_id, recorded_at):
    parsed = instant(recorded_at).isoformat()
    with locked(home / "intake.lock"):
        path = _directory(home, intake_id) / "request.json"
        item = read(path)
        if item["status"] == "queued":
            raise ValueError("Recording already queued; keep its original provenance")
        item.update(
            recorded_at=parsed, timestamp_source="user", status="pending_calendar"
        )
        item["query"] = query_window(parsed, item["duration"])
        save(path, item)
        return item


def apply_calendar(home, intake_id, snapshot_path, event_id=None, without_title=False):
    if event_id and without_title:
        raise ValueError("Choose an event or queue without a title, not both")
    with locked(home / "intake.lock"):
        folder = _directory(home, intake_id)
        item = read(folder / "request.json")
        if item["status"] == "queued":
            return item
        if not item["recorded_at"]:
            raise ValueError("Set the original recording time first")
        snapshot = read(snapshot_path)
        outcome = match_event(item["recorded_at"], item["duration"], snapshot)
        event = outcome["event"]
        if event_id:
            event = next(
                (e for e in outcome["candidates"] if e["id"] == event_id), None
            )
            if not event:
                raise ValueError("Selected event is not an overlapping candidate")
        # Persist only the small result, not bodies, attendees or auth tokens.
        save(folder / "calendar-match.json", outcome)
        if not event and not without_title:
            item.update(status="needs_calendar_review", calendar=outcome)
            save(folder / "request.json", item)
            return item
        meeting = {
            "recorded_at": item["recorded_at"],
            "original_name": item["source_name"],
            "timestamp_source": item["timestamp_source"],
            "calendar_provider": "outlook",
            "title": event["title"] if event else Path(item["source_name"]).stem,
            "event_id": event["id"] if event else None,
            "title_source": "user_confirmed_outlook"
            if event_id
            else "outlook_time_match"
            if event
            else "original_filename",
            "match_policy": outcome["policy"],
        }
        source = folder / item["source_name"]
        if file_hash(source) != item["source_hash"]:
            raise ValueError("Staged recording hash mismatch")
        inbox = Path(load_config(home)["inbox"]).expanduser().resolve()
        inbox.mkdir(parents=True, exist_ok=True)
        destination = inbox / ("airdrop-" + intake_id)
        name = meeting_stem(meeting, intake_id) + source.suffix.lower()
        metadata = {"meeting": meeting}
        if destination.exists():
            if (
                not (destination / name).is_file()
                or file_hash(destination / name) != item["source_hash"]
                or read(destination / (name + ".json")) != metadata
            ):
                raise ValueError("Existing intake destination differs")
        else:
            # Publish audio and sidecar together; the watcher never sees a half-copy.
            with tempfile.TemporaryDirectory(dir=inbox.parent, prefix=".queue-") as tmp:
                shutil.copyfile(source, Path(tmp) / name)
                if file_hash(Path(tmp) / name) != item["source_hash"]:
                    raise ValueError("Audio copy changed")
                save(Path(tmp) / (name + ".json"), metadata)
                Path(tmp).rename(destination)
        item.update(status="queued", audio=str(destination / name), meeting=meeting)
        item.pop("calendar", None)
        save(folder / "request.json", item)
        return item
