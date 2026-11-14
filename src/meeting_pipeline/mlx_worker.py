"""Executed with a separate, MLX-equipped interpreter on Apple Silicon."""

import dataclasses
import json
from pathlib import Path
import sys


def main():
    request = json.loads(Path(sys.argv[1]).read_text())
    mode = request["mode"]
    language = {"it": "Italian", "en": "English", "auto": None}[request["language"]]
    if mode == "whisper":
        import mlx.core as mx
        import mlx_whisper

        mx.random.seed(0)
        result = mlx_whisper.transcribe(
            request["audio"],
            path_or_hf_repo=request["model"],
            language=None if request["language"] == "auto" else request["language"],
            word_timestamps=True,
            verbose=None,
        )
    else:
        from mlx_audio.stt import load

        model = load(request["model"])
        if mode == "qwen":
            result = dataclasses.asdict(
                model.generate(
                    request["audio"],
                    language=language,
                    temperature=0,
                    chunk_duration=90,
                    max_tokens=65536,
                    hotwords=request["hotwords"],
                    verbose=False,
                )
            )
        elif mode == "align":
            if not language:
                raise ValueError("Alignment requires it or en language")
            aligned = model.generate(
                audio=request["audio"], text=request["text"], language=language
            )
            result = {
                "words": [
                    {"text": x.text, "start": x.start_time, "end": x.end_time}
                    for x in aligned.items
                ]
            }
        else:
            raise ValueError(mode)

    def convert(value):
        if hasattr(value, "tolist"):
            return value.tolist()
        if hasattr(value, "item"):
            return value.item()
        raise TypeError(type(value).__name__)

    Path(request["output"]).write_text(
        json.dumps(result, ensure_ascii=False, default=convert)
    )


if __name__ == "__main__":
    main()
