import importlib.util
import json
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "comparison", Path(__file__).parents[1] / "scripts/compare_transcripts.py"
)
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


class ComparisonTest(unittest.TestCase):
    def test_edit_distance_and_semantic_distinctions(self):
        self.assertEqual(comparison.errors("uno due tre", "uno quattro")["edits"], 2)
        self.assertEqual(comparison.errors("non inviare 15", "inviare 50")["edits"], 2)
        self.assertEqual(comparison.errors("È pronto!", "è pronto")["edits"], 0)
        with self.assertRaises(ValueError):
            comparison.errors("", "test")

    def test_gold_gate_and_clip_scope(self):
        manifest = {
            "clips": [
                {
                    "id": "a",
                    "recording": "IT-A",
                    "candidates": [
                        {"variant": "asr", "scope": "exact_clip", "text": "non pronto"},
                        {
                            "variant": "archive",
                            "scope": "approximate",
                            "text": "pronto",
                        },
                    ],
                }
            ]
        }
        ref = {"clip_id": "a", "text": "non pronto", "human_reviewed": False}
        self.assertEqual(comparison.score_clips(manifest, [ref])["totals"], [])
        ref["human_reviewed"] = True
        score = comparison.score_clips(manifest, [ref])
        self.assertEqual(len(score["clips"]), 1)
        self.assertEqual(score["totals"][0]["wer"], 0)
        with self.assertRaises(ValueError):
            comparison.score_clips(manifest, [ref, ref])

    def test_transcript_cannot_close_embedded_json(self):
        attack = "</script><img src=x onerror=alert(1)>"
        page = comparison.render({"text": attack}, {}, [])
        self.assertNotIn(attack, page)
        payload = page.split('type="application/json">')[1].split("</script>")[0]
        self.assertEqual(json.loads(payload)["manifest"]["text"], attack)
