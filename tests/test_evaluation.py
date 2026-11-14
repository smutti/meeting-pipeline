import unittest

from meeting_pipeline.evaluation import metrics, paired_comparison


def paired(count=20, old=4, new=1):
    rows = []
    for i in range(count):
        for engine, edits in [("whisper", old), ("parakeet", new)]:
            rows.append(
                {
                    "language": "it",
                    "sample_id": str(i),
                    "unit_id": str(i),
                    "engine": engine,
                    "reference_hash": "same-reference",
                    "audio_hash": "same-audio",
                    "reference_words": 10,
                    "word_edits": edits,
                }
            )
    return rows


class EvaluationTest(unittest.TestCase):
    def test_words_characters_and_normalization(self):
        self.assertEqual(metrics("È pronto!", "è pronto")["wer"], 0)
        self.assertEqual(metrics("non inviare 15", "inviare 50")["word_edits"], 2)
        self.assertEqual(metrics("abc", "adc")["cer"], 1 / 3)
        self.assertEqual(metrics("a", "a b c")["wer"], 2)
        with self.assertRaises(ValueError):
            metrics("...", "words")

    def test_paired_improvement_and_regression(self):
        result = paired_comparison(paired(), repeats=200)
        self.assertAlmostEqual(result["delta_wer"], -0.3)
        self.assertEqual(result["verdict"], "lower_wer_on_this_sample")
        result = paired_comparison(paired(old=1, new=4), repeats=200)
        self.assertEqual(result["verdict"], "higher_wer_on_this_sample")

    def test_no_gain_or_insufficient_sample_is_not_a_pass(self):
        self.assertEqual(
            paired_comparison(paired(old=1, new=1), repeats=200)["verdict"],
            "inconclusive",
        )
        self.assertEqual(
            paired_comparison(paired(count=2), repeats=200)["verdict"],
            "insufficient_sample",
        )

    def test_invalid_pair_is_not_silently_dropped(self):
        rows = paired()
        with self.assertRaises(ValueError):
            paired_comparison(rows[:-1])
        with self.assertRaises(ValueError):
            paired_comparison(rows + [rows[0]])
        rows[1]["reference_hash"] = "different"
        with self.assertRaises(ValueError):
            paired_comparison(rows)

    def test_prompt_duplicates_are_clustered(self):
        rows = paired()
        for row in rows:
            row["unit_id"] = "same-prompt"
        result = paired_comparison(rows, repeats=200)
        self.assertEqual(result["independent_prompt_groups"], 1)
        self.assertEqual(result["verdict"], "insufficient_sample")

    def test_bootstrap_is_reproducible_and_weighted_by_words(self):
        rows = paired(count=2, old=1, new=0)
        rows[0]["reference_words"] = rows[1]["reference_words"] = 90
        first = paired_comparison(rows, repeats=200, minimum_units=2)
        self.assertEqual(first, paired_comparison(rows, repeats=200, minimum_units=2))
        self.assertEqual(first["baseline_wer"], 0.02)
