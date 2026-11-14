# Codice, runtime e modelli

La licenza MIT del repository riguarda il codice e la documentazione originali qui distribuiti. Non cambia la licenza delle dipendenze, dei pesi, delle conversioni o dei dati dell'utente. Il repository non distribuisce pesi né registrazioni; il setup scarica il runtime separatamente.

Fonti da consultare per le revisioni effettivamente usate:

| Componente | Fonte e licenza pubblicata |
|---|---|
| FluidAudio, runtime Core ML | [Repository e licenza Apache 2.0](https://github.com/FluidInference/FluidAudio) |
| NeMo-Speech.cpp | [Repository e licenza](https://github.com/NVIDIA/NeMo-Speech.cpp) |
| mlx-audio | [Repository e licenza](https://github.com/Blaizzy/mlx-audio) |
| mlx-whisper | [Repository e licenza](https://github.com/ml-explore/mlx-examples/tree/main/whisper) |
| Qwen3-ASR | [Modello originale, Apache 2.0](https://huggingface.co/Qwen/Qwen3-ASR-1.7B), [conversione MLX](https://huggingface.co/mlx-community/Qwen3-ASR-1.7B-bf16) |
| Qwen3 ForcedAligner | [Modello originale](https://huggingface.co/Qwen/Qwen3-ForcedAligner-0.6B), [conversione MLX](https://huggingface.co/mlx-community/Qwen3-ForcedAligner-0.6B-8bit) |
| Whisper large-v3 | [Modello originale](https://huggingface.co/openai/whisper-large-v3), [conversione MLX](https://huggingface.co/mlx-community/whisper-large-v3-mlx) |
| Parakeet Ultra Core ML | [Pesi e attribuzioni](https://huggingface.co/FluidInference/parakeet-ultra-coreml) |
| Nemotron-3 Diarization | [Model card e OpenMDW 1.1](https://huggingface.co/nvidia/Nemotron-3-Diarization) |
| Community-1 | [Pipeline originale, CC BY 4.0](https://huggingface.co/pyannote/speaker-diarization-community-1), [conversione Core ML e componenti](https://huggingface.co/FluidInference/speaker-diarization-coreml) |

I link ai modelli originali non sostituiscono le condizioni delle conversioni o dei singoli componenti. Per ridistribuire un runtime completo occorre conservare anche licenze e attribuzioni degli artefatti inclusi. Le versioni di setup sono in `scripts/setup_runtime.py`; l'identità degli embedding include gli hash dei file Core ML effettivamente caricati.
