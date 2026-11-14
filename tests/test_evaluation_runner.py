import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "evaluation_runner", Path(__file__).parents[1] / "scripts/evaluate_asr.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class EvaluationRunnerTest(unittest.TestCase):
    def test_cache_invalidation_and_reference_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "synthetic.wav"
            audio.write_bytes(b"synthetic fixture; decoder is stubbed")
            corpus = root / "corpus.json"
            data = {
                "reference_kind": "human_verified",
                "samples": [
                    {
                        "sample_id": "sample-1",
                        "unit_id": "prompt-1",
                        "language": "it",
                        "audio": audio.name,
                        "audio_hash": hashlib.sha256(audio.read_bytes()).hexdigest(),
                        "reference": "uno due",
                        "reference_hash": hashlib.sha256(b"uno due").hexdigest(),
                    }
                ],
            }
            corpus.write_text(json.dumps(data))

            def normalize(source, target):
                target.write_bytes(source.read_bytes())
                return {"duration": 1}

            with (
                patch.object(runner, "data_home", return_value=root),
                patch.object(runner, "load_config", return_value={"runtime": {}}),
                patch.object(
                    runner,
                    "runtime_identity",
                    return_value={"fingerprint": "model-and-sdk-v1"},
                ) as identity,
                patch.object(runner, "prepare", side_effect=normalize),
                patch.object(runner, "Engines") as engines,
            ):
                engines.return_value.asr.return_value = {
                    "text": "uno due",
                    "wall_seconds": 1,
                }
                first = runner.run_corpus(corpus, root / "run")
                self.assertEqual(engines.return_value.asr.call_count, 3)
                second = runner.run_corpus(corpus, root / "run")
                self.assertEqual(engines.return_value.asr.call_count, 3)
                self.assertEqual(first["totals"], second["totals"])
                identity.return_value = {"fingerprint": "model-and-sdk-v2"}
                runner.run_corpus(corpus, root / "run")
                self.assertEqual(engines.return_value.asr.call_count, 6)
                data["samples"][0]["reference"] = "different reference"
                corpus.write_text(json.dumps(data))
                with self.assertRaisesRegex(ValueError, "reference changed"):
                    runner.run_corpus(corpus, root / "run")
