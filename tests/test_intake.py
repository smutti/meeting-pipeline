from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from meeting_pipeline.calendar_match import recording_time, match_event, meeting_stem
from meeting_pipeline.common import save, file_hash
from meeting_pipeline.intake import discover, apply_calendar, set_time
from meeting_pipeline.service import scan_once, export
from meeting_pipeline.state import State
from meeting_pipeline.report import render


def event(
    identifier="one",
    title="Engineering / sync",
    start="2026-11-12T08:30:00Z",
    end="2026-11-12T09:30:00Z",
    **extra,
):
    return {"id": identifier, "subject": title, "start": start, "end": end, **extra}


def snapshot(events):
    return {
        "start_datetime": "2026-11-12T08:00:00Z",
        "end_datetime": "2026-11-12T10:00:00Z",
        "complete": True,
        "events": events,
    }


class CalendarTest(unittest.TestCase):
    def test_timezone_and_dst_never_use_airdrop_time(self):
        self.assertEqual(
            recording_time("2026-11-12 09_35_31.mp3", "Europe/Rome"),
            "2026-11-12T09:35:31+01:00",
        )
        self.assertEqual(
            recording_time("2026-07-12 09_35_31.mp3", "Europe/Rome"),
            "2026-07-12T09:35:31+02:00",
        )
        for name in [
            "renamed.mp3",
            "2026-10-25 02_30_00.mp3",
            "2026-03-29 02_30_00.mp3",
        ]:
            self.assertIsNone(recording_time(name, "Europe/Rome"))

    def test_unique_match_excludes_cancelled_and_all_day_and_deduplicates(self):
        result = match_event(
            "2026-11-12T09:35:31+01:00",
            1625,
            snapshot(
                [
                    event(),
                    event(),
                    event("two", is_cancelled=True),
                    event("three", is_all_day=True),
                ]
            ),
        )
        self.assertEqual(result["status"], "matched")
        self.assertEqual(result["event"]["id"], "one")

    def test_overlapping_events_do_not_silently_pick_best(self):
        result = match_event(
            "2026-11-12T09:35:31+01:00",
            1625,
            snapshot(
                [
                    event(),
                    event(
                        "two", start="2026-11-12T08:45:00Z", end="2026-11-12T09:00:00Z"
                    ),
                ]
            ),
        )
        self.assertEqual(result["status"], "ambiguous")
        self.assertIsNone(result["event"])

    def test_partial_calendar_or_naive_timestamps_cannot_auto_match(self):
        for changes in [
            {"complete": False},
            {"next_link": "more"},
            {"start_datetime": "2026-11-12T09:00:00Z"},
        ]:
            with self.assertRaises(ValueError):
                match_event(
                    "2026-11-12T09:35:31+01:00", 1625, snapshot([event()]) | changes
                )
        with self.assertRaises(ValueError):
            match_event("2026-11-12T09:35:31", 1625, snapshot([event()]))

    def test_graph_utc_and_duration_mismatch(self):
        one = event(
            start={"dateTime": "2026-11-12T08:30:00.0000000", "timeZone": "UTC"}
        )
        self.assertEqual(
            match_event("2026-11-12T09:35:31+01:00", 1625, snapshot([one]))["status"],
            "matched",
        )
        result = match_event(
            "2026-11-12T09:35:31+01:00",
            1625,
            snapshot([event(end="2026-11-12T08:40:00Z")]),
        )
        self.assertEqual(result["status"], "unmatched")


class IntakeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / "private"
        self.downloads = self.root / "Downloads"
        self.downloads.mkdir()
        self.name = "2026-11-12 09_35_31.mp3"
        save(self.home / "config.json", {"inbox": str(self.home / "inbox")})
        self.snapshot = self.home / "snapshot.json"
        save(self.snapshot, snapshot([event()]))

    def tearDown(self):
        self.tmp.cleanup()

    def bundle(self, name="Meeting Upload.zip", members=None):
        path = self.downloads / name
        with zipfile.ZipFile(path, "w") as archive:
            for key, value in (
                members or {self.name: b"synthetic audio fixture"}
            ).items():
                archive.writestr(key, value)
        return path

    def discover(self):
        with patch("meeting_pipeline.intake.duration", return_value=1625):
            return discover(self.home, self.downloads, stable_seconds=0)

    def test_archive_queue_watcher_and_export_preserve_title_and_source(self):
        original = self.bundle()
        original_hash = file_hash(original)
        item = self.discover()["pending"][0]
        queued = apply_calendar(self.home, item["id"], self.snapshot)
        audio = Path(queued["audio"])
        self.assertIn("Engineering - sync", audio.name)
        self.assertEqual(file_hash(original), original_hash)
        self.assertEqual(audio.read_bytes(), b"synthetic audio fixture")
        self.assertEqual(
            apply_calendar(self.home, item["id"], self.snapshot)["audio"], str(audio)
        )
        self.bundle("Meeting Upload 2.zip")
        self.assertEqual(self.discover()["pending"], [])
        self.assertEqual(len(list((self.home / "inbox").rglob("*.mp3"))), 1)
        with patch(
            "meeting_pipeline.service.process",
            return_value={"job": "j", "status": "needs_review"},
        ) as process:
            scan_once(self.home, 0)
            scan_once(self.home, 0)
            self.assertEqual(
                process.call_args.kwargs["meeting"]["title"], "Engineering / sync"
            )
        state = State(self.home)
        state.register("j", audio)
        state.status("j", "ready")
        job = self.home / "jobs/j"
        job.mkdir(parents=True)
        save(job / "manifest.json", {"meeting": queued["meeting"]})
        (job / "transcript.md").write_text("Synthetic transcript")
        target = export(self.home, "j", self.home / "out")["file"]
        self.assertIn("Engineering - sync", target)

    def test_unrelated_downloads_and_unsafe_archives_are_ignored_or_rejected(self):
        self.bundle("unrelated.zip")
        self.assertEqual(self.discover()["pending"], [])
        for member in ["../escape.mp3", "/absolute.mp3", "note.txt"]:
            self.bundle(members={member: b"fixture"})
            result = self.discover()
            self.assertEqual(len(result["errors"]), 1)
            self.assertEqual(result["pending"], [])
        self.assertFalse((self.root / "escape.mp3").exists())

    def test_ambiguous_match_requires_explicit_resolution(self):
        self.bundle()
        item = self.discover()["pending"][0]
        save(self.snapshot, snapshot([event(), event("two", "Other meeting")]))
        result = apply_calendar(self.home, item["id"], self.snapshot)
        self.assertEqual(result["status"], "needs_calendar_review")
        self.assertFalse((self.home / "inbox").exists())
        result = apply_calendar(self.home, item["id"], self.snapshot, event_id="two")
        self.assertEqual(result["meeting"]["title_source"], "user_confirmed_outlook")
        self.assertEqual(result["meeting"]["title"], "Other meeting")

    def test_missing_timestamp_requires_user_offset_and_source_hash_is_checked(self):
        self.bundle(members={"renamed.mp3": b"fixture"})
        item = self.discover()["pending"][0]
        self.assertEqual(item["status"], "needs_recording_time")
        with self.assertRaises(ValueError):
            apply_calendar(self.home, item["id"], self.snapshot)
        set_time(self.home, item["id"], "2026-11-12T09:35:31+01:00")
        (self.home / "intake" / item["id"] / "renamed.mp3").write_bytes(b"changed")
        with self.assertRaises(ValueError):
            apply_calendar(self.home, item["id"], self.snapshot)

    def test_safe_unicode_filename_has_room_for_extensions(self):
        name = meeting_stem(
            {
                "title": "../" + "🟢" * 200 + "\n",
                "recorded_at": "2026-11-12T09:35:31+01:00",
            },
            "a" * 24,
        )
        self.assertLess(len((name + "-draft.md").encode()), 255)
        self.assertNotIn("/", name)

    def test_calendar_title_is_literal_in_markdown_and_html(self):
        state = State(self.home)
        state.register("j", "original.mp3")
        state.status("j", "ready")
        job = self.home / "jobs/j"
        title = '![image](https://example.invalid/pixel) <img src="https://example.invalid/pixel">'
        save(
            job / "manifest.json",
            {"source_name": "original.mp3", "meeting": {"title": title}},
        )
        save(job / "selected.json", {"words": []})
        save(job / "diarization.json", {"segments": []})
        save(job / "issues.json", [])
        save(job / "speaker-names.json", {})
        render(self.home, "j")
        markdown = (job / "transcript.md").read_text()
        self.assertIn(r"\!\[image\]", markdown)
        self.assertNotIn("<img src=", (job / "review.html").read_text())


if __name__ == "__main__":
    unittest.main()
