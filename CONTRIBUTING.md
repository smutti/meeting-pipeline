# Contributing

The project separates its Python engine, local adapters, recipes and skills. Before adding a backend, read [ARCHITECTURE.md](docs/ARCHITECTURE.md). Preserve raw outputs, provenance and timestamps, and state the backend's limits.

All documentation, skill descriptions, help text and report interface labels should be in English. Meeting transcripts and multilingual test fixtures retain their source language.

## Local checks

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q src scripts
```

These checks do not require models or recordings. Inference currently requires Apple Silicon macOS and the separate runtime described in the README. Public-corpus inference is an explicit local evaluation, not a default GitHub Actions job.

Use synthetic fixtures for unit tests. Do not include meeting recordings, real transcripts, credentials, databases, voice profiles or personal glossaries. An HTML comparison contains text and local paths: it is private data even when the tool producing it is public.

Quality changes must document corpus, versions, parameters, normalization, reference provenance, hardware and timing boundaries. Evaluate the same audio and report regressions. A correct speaker count does not establish correct diarization; agreement between ASR engines does not verify their text.

Pull requests should explain the problem, resulting behavior and validation. Original code is licensed under Apache 2.0; dependencies and models retain their own licenses. New adapters must document those sources and terms.
