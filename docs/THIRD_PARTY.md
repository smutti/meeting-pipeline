# Code, runtimes and models

The repository's MIT license covers the original code and documentation distributed here. It does not change licenses for dependencies, weights, conversions or user data. Model weights and recordings are not distributed in the repository; setup downloads runtimes separately.

Consult the sources for the exact revisions being used:

| Component | Source and published license |
|---|---|
| FluidAudio Core ML runtime | [Repository and Apache 2.0 license](https://github.com/FluidInference/FluidAudio) |
| NeMo-Speech.cpp | [Repository and license](https://github.com/NVIDIA/NeMo-Speech.cpp) |
| mlx-audio | [Repository and license](https://github.com/Blaizzy/mlx-audio) |
| mlx-whisper | [Repository and license](https://github.com/ml-explore/mlx-examples/tree/main/whisper) |
| Qwen3-ASR | [Original model, Apache 2.0](https://huggingface.co/Qwen/Qwen3-ASR-1.7B), [MLX conversion](https://huggingface.co/mlx-community/Qwen3-ASR-1.7B-bf16) |
| Qwen3 ForcedAligner | [Original model](https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B), [MLX conversion](https://huggingface.co/mlx-community/Qwen3-ForcedAligner-0.6B-8bit) |
| Whisper large-v3 | [Original model](https://huggingface.co/openai/whisper-large-v3), [MLX conversion](https://huggingface.co/mlx-community/whisper-large-v3-mlx) |
| Parakeet Ultra Core ML | [Weights and attribution](https://huggingface.co/FluidInference/parakeet-ultra-coreml) |
| Nemotron-3 Diarization | [Model card and OpenMDW 1.1](https://huggingface.co/nvidia/Nemotron-3-Diarization) |
| Community-1 | [Original pipeline, CC BY 4.0](https://huggingface.co/pyannote/speaker-diarization-community-1), [Core ML conversion and components](https://huggingface.co/FluidInference/speaker-diarization-coreml) |
| FLEURS evaluation data | [Google FLEURS dataset, CC BY 4.0](https://huggingface.co/datasets/google/fleurs) |

Original-model links do not replace the terms of conversions or their components. Distributing a complete runtime also requires preserving the licenses and attribution of included artifacts. Setup revisions are listed in `scripts/setup_runtime.py`; embedding identities include hashes of the Core ML files actually loaded. FLEURS audio and references are downloaded locally for explicit evaluation and are not bundled with this project.
