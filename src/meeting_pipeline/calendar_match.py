"""Conservative, read-only calendar matching. No calendar credentials or writes."""

from datetime import datetime, timedelta, timezone
import math
import re
import unicodedata
from zoneinfo import ZoneInfo


def instant(value):
    if isinstance(value, dict):
        parsed = datetime.fromisoformat(value["dateTime"].replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            zone = value.get("timeZone", "")
            if zone not in {"UTC", "Etc/UTC"}:
                raise ValueError(
                    "Export calendar dates in UTC or with explicit offsets"
                )
            parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("A recording/calendar timestamp requires a UTC offset")
    return parsed


def recording_time(name, zone):
    """Comu filenames encode device-local wall time; never use transfer mtime."""
    found = re.match(
        r"^(\d{4}-\d{2}-\d{2})[ T](\d{2})[_:](\d{2})[_:](\d{2})(?:\D|$)", name
    )
    if not found:
        return None
    day, hour, minute, second = found.groups()
    try:
        local = datetime.fromisoformat(f"{day}T{hour}:{minute}:{second}")
    except ValueError:
        return None
    tz = ZoneInfo(zone)
    a, b = (local.replace(tzinfo=tz, fold=f) for f in (0, 1))
    # Reject both repeated and nonexistent local times around DST changes.
    if (
        a.utcoffset() != b.utcoffset()
        or a.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None) != local
    ):
        return None
    return a.isoformat()


def query_window(recorded_at, duration):
    start = instant(recorded_at).astimezone(timezone.utc)
    if not math.isfinite(duration) or not 0 < duration <= 24 * 3600:
        raise ValueError("Recording duration must be between zero and 24 hours")
    return {
        "start_datetime": (start - timedelta(minutes=15)).isoformat(),
        "end_datetime": (start + timedelta(seconds=duration, minutes=15)).isoformat(),
    }


def match_event(recorded_at, duration, snapshot):
    window = query_window(recorded_at, duration)
    if (
        snapshot.get("complete") is not True
        or snapshot.get("next_link")
        or snapshot.get("@odata.nextLink")
    ):
        raise ValueError("A complete, unpaginated calendar snapshot is required")
    if instant(snapshot["start_datetime"]) > instant(
        window["start_datetime"]
    ) or instant(snapshot["end_datetime"]) < instant(window["end_datetime"]):
        raise ValueError("Calendar snapshot does not cover the requested window")
    start = instant(recorded_at)
    end = start + timedelta(seconds=duration)
    candidates, seen = [], set()
    for event in snapshot["events"]:
        if event.get("is_all_day", event.get("isAllDay", False)) or event.get(
            "is_cancelled", event.get("isCancelled", False)
        ):
            continue
        begin, finish = instant(event["start"]), instant(event["end"])
        if finish <= begin:
            raise ValueError("Calendar event has an invalid interval")
        key = (str(event["id"]), begin.isoformat())
        if key in seen:
            continue
        seen.add(key)
        overlap = max(0, (min(end, finish) - max(start, begin)).total_seconds())
        coverage = overlap / duration
        if coverage < 0.1 or not str(event.get("subject", "")).strip():
            continue
        candidates.append(
            {
                "id": str(event["id"]),
                "title": event["subject"].strip(),
                "start": begin.isoformat(),
                "end": finish.isoformat(),
                "recording_coverage": round(coverage, 4),
                "eligible": coverage >= 0.8
                and begin - timedelta(minutes=10) <= start < finish,
            }
        )
    candidates.sort(key=lambda e: (-e["recording_coverage"], e["id"]))
    matched = len(candidates) == 1 and candidates[0]["eligible"]
    return {
        "status": "matched"
        if matched
        else "ambiguous"
        if len(candidates) > 1
        else "unmatched",
        "event": candidates[0] if matched else None,
        "candidates": candidates,
        "policy": "single-event-80pct-coverage-10min-early-v1",
    }


def filename_title(value):
    value = unicodedata.normalize("NFC", value)
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f\x7f]', "-", value)
    value = " ".join(value.split()).strip(" .-") or "Untitled meeting"
    # Leave room for date, content/job ID, extension and draft suffix on APFS.
    while len(value.encode("utf-8")) > 140:
        value = value[:-1]
    return value


def meeting_stem(meeting, identifier):
    stamp = instant(meeting["recorded_at"]).strftime("%Y-%m-%d %H_%M_%S")
    return f"{stamp} - {filename_title(meeting['title'])} - {identifier[:12]}"
