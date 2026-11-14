import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from meeting_pipeline.common import save, locked, protected_runtime_path
from meeting_pipeline.knowledge import add_term, load, terms_for, enroll, match
from meeting_pipeline.quality import speaker_for, clean_spans, compare, tokens
from meeting_pipeline.state import State
from meeting_pipeline.workflow import load_recipe
from meeting_pipeline.service import scan_once, export


class LocalTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_service_migrates_venv_symlink_even_when_target_is_unprotected(self):
        shared = self.home / "shared-python"
        shared.write_text("interpreter fixture")
        interpreter = self.home / "Documents/project/.venv/bin/python"
        interpreter.parent.mkdir(parents=True)
        interpreter.symlink_to(shared)
        self.assertTrue(protected_runtime_path(interpreter, self.home))
        self.assertFalse(protected_runtime_path(shared, self.home))

    def test_glossary_scopes_and_confirmed_overrides(self):
        add_term(self.home, "Product X", ["product ex"], "*", "*", "global")
        add_term(self.home, "Product X", ["prod x"], "alpha", "it", "specific")
        add_term(self.home, "Unrelated", [], "beta", "en")
        self.assertEqual(
            terms_for(load(self.home), "alpha", "it")[0]["meaning"], "specific"
        )
        self.assertEqual(len(terms_for(load(self.home), "alpha", "it")), 1)
        self.assertEqual(
            terms_for(load(self.home), "alpha", "en")[0]["meaning"], "global"
        )

    def test_voice_identity_needs_confirmed_samples_and_calibration(self):
        with self.assertRaises(ValueError):
            enroll(self.home, "A", [1, 0], "v1", "one", 0, 10, False)
        enroll(self.home, "A", [1, 0], "v1", "one", 0, 10, True)
        enroll(self.home, "A", [0.99, 0.01], "v1", "two", 0, 10, True)
        data = load(self.home)
        result = match([[1, 0], [1, 0]], data, "v1")
        self.assertEqual(result["status"], "suggested")
        self.assertIsNone(result["name"])
        data["voice_policy"].update(
            auto_accept=True, evidence={"sha256": "reviewed-holdout-report"}
        )
        self.assertEqual(match([[1, 0], [1, 0]], data, "v1")["name"], "A")
        self.assertIsNone(match([[1, 0], [0, 1]], data, "v1")["name"])
        self.assertEqual(match([[1, 0]], data, "v2")["status"], "unknown")
        self.assertIsNone(
            match([[1, 0], [1, 0]], data, "v1", exclude_source="one")["name"]
        )

    def test_duplicate_sample_is_not_independent_evidence(self):
        enroll(self.home, "A", [1, 0], "v1", "same", 0, 10, True)
        enroll(self.home, "A", [1, 0], "v1", "same", 0, 10, True)
        self.assertEqual(len(load(self.home)["voices"]), 1)
        with self.assertRaises(ValueError):
            enroll(self.home, "B", [1, 0], "v1", "same", 0, 10, True)

    def test_new_enrollment_invalidates_voice_policy(self):
        data = load(self.home)
        data["voice_policy"].update(auto_accept=True, evidence={"sha256": "test"})
        save(self.home / "knowledge.json", data)
        enroll(self.home, "A", [1, 0], "v1", "one", 0, 10, True)
        self.assertFalse(load(self.home)["voice_policy"]["auto_accept"])

    def test_timestamps_preserve_overlaps_and_more_than_four_speakers(self):
        segments = [{"speaker": str(i), "start": i, "end": i + 2} for i in range(7)]
        self.assertEqual(speaker_for({"start": 6.1, "end": 6.4}, segments), ["5", "6"])
        self.assertEqual(speaker_for({"start": 20, "end": 21}, segments), [])
        self.assertEqual(
            speaker_for(
                {"start": 0, "end": 1}, [{"speaker": "a", "start": 0, "end": 0.3}] * 4
            ),
            [],
        )

    def test_enrollment_excerpts_exclude_other_voices(self):
        segments = [
            {"speaker": "a", "start": 0, "end": 40},
            {"speaker": "b", "start": 10, "end": 25},
        ]
        spans = clean_spans(segments, "a", minimum=6, count=2)
        self.assertEqual(len(spans), 2)
        self.assertTrue(all(end <= 10 or start >= 25 for start, end in spans))

    def test_content_differences_are_not_normalized_away(self):
        self.assertNotEqual(tokens("non il 15"), tokens("il 50"))
        primary = {
            "words": [
                {"text": "non", "start": 0, "end": 1},
                {"text": "15", "start": 1, "end": 2},
            ]
        }
        alternative = {"segments": [{"text": "50", "start": 0, "end": 2}]}
        self.assertEqual(compare(primary, alternative, 0.2)[0]["kind"], "disagreement")
        self.assertNotIn("wer", compare(primary, alternative, 0.2)[0])

    def test_checkpoint_resumes_and_invalidates_changed_input(self):
        s = State(self.home)
        s.register("j", "source")
        calls = []

        def action():
            calls.append(1)
            return {"calls": len(calls)}

        s.step("j", "asr", {"model": "one"}, action)
        s.step("j", "asr", {"model": "one"}, action)
        self.assertEqual(len(calls), 1)
        s.step("j", "asr", {"model": "two"}, action)
        self.assertEqual(len(calls), 2)

    def test_failure_never_commits_complete_checkpoint(self):
        s = State(self.home)
        s.register("j", "source")
        with self.assertRaises(RuntimeError):
            s.step(
                "j",
                "asr",
                {},
                lambda: (_ for _ in ()).throw(RuntimeError("engine crash")),
            )
        self.assertFalse((self.home / "jobs/j/asr.json").exists())
        self.assertEqual(s.step("j", "asr", {}, lambda: {"ok": True}), {"ok": True})

    def test_worker_lock_rejects_concurrent_processing(self):
        with locked(self.home / "worker.lock"):
            with self.assertRaises(RuntimeError):
                with locked(self.home / "worker.lock"):
                    pass

    def test_recipe_rejects_uncalibrated_text_replacement(self):
        value = load_recipe("quality")
        value["auto_replace_text"] = True
        path = self.home / "recipe.json"
        save(path, value)
        with self.assertRaises(ValueError):
            load_recipe(str(path))

    def test_watcher_waits_for_stability_and_deduplicates(self):
        inbox = self.home / "inbox"
        inbox.mkdir()
        audio = inbox / "with spaces.mp3"
        audio.write_bytes(b"unit fixture, not an audio inference test")
        save(self.home / "config.json", {"inbox": str(inbox)})
        later = audio.stat().st_mtime + 100
        with (
            patch("meeting_pipeline.service.time.time", return_value=later),
            patch("meeting_pipeline.service.process") as proc,
        ):
            scan_once(self.home, 30)
            proc.assert_not_called()
        with (
            patch("meeting_pipeline.service.time.time", return_value=later + 31),
            patch(
                "meeting_pipeline.service.process",
                return_value={"job": "123", "status": "needs_review"},
            ) as proc,
        ):
            self.assertEqual(len(scan_once(self.home, 30)), 1)
            proc.assert_called_once()
            self.assertEqual(scan_once(self.home, 30), [])

    def test_export_requires_ready_status_and_never_overwrites_other_note(self):
        s = State(self.home)
        s.register("j", "source")
        s.status("j", "needs_review")
        (self.home / "jobs/j").mkdir(parents=True)
        (self.home / "jobs/j/transcript.md").write_text("draft")
        with self.assertRaises(ValueError):
            export(self.home, "j", self.home / "out")
        target = export(self.home, "j", self.home / "out", draft=True)["file"]
        self.assertEqual(Path(target).read_text(), "draft")
        Path(target).write_text("user edits")
        with self.assertRaises(ValueError):
            export(self.home, "j", self.home / "out", draft=True)


if __name__ == "__main__":
    unittest.main()
