#!/usr/bin/env python3
"""Build the pinned Apple Silicon runtime outside the repository. Several GB."""

import argparse
import hashlib
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import urllib.request

p = argparse.ArgumentParser()
p.add_argument("--path", required=True)
a = p.parse_args()
if platform.system() != "Darwin" or platform.machine() != "arm64":
    raise SystemExit("Model runtime requires Apple Silicon macOS")
root = Path(a.path).expanduser().resolve()
root.mkdir(parents=True, exist_ok=True)


def run(*args, cwd=None):
    subprocess.run([str(x) for x in args], check=True, cwd=cwd)


uv = shutil.which("uv")
if not uv:
    raise SystemExit(
        "Install uv first; also requires ffmpeg, Swift/Xcode command-line tools and git"
    )
for name in ["ffmpeg", "swift", "git"]:
    if not shutil.which(name):
        raise SystemExit(f"Missing tool: {name}")
if not (root / ".venv/bin/python").exists():
    run(uv, "venv", "--python", "3.12", root / ".venv")
python = root / ".venv/bin/python"
run(
    uv,
    "pip",
    "install",
    "--python",
    python,
    "mlx-audio==0.6.5",
    "mlx-whisper==0.4.3",
    "huggingface-hub==2.4.0",
    "gguf==0.19.0",
    "librosa==1.0.1",
)


def checkout(name, url, revision):
    dest = root / "vendor" / name
    if not dest.exists():
        dest.mkdir(parents=True)
        run("git", "init", dest)
        run("git", "-C", dest, "remote", "add", "origin", url)
        run("git", "-C", dest, "fetch", "--depth", "1", "origin", revision)
        run("git", "-C", dest, "checkout", "--detach", "FETCH_HEAD")
    actual = subprocess.check_output(
        ["git", "-C", str(dest), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != revision:
        raise SystemExit(
            f"Unexpected revision in {dest}; refusing to replace an existing checkout"
        )
    return dest


fluid = checkout(
    "FluidAudio",
    "https://github.com/FluidInference/FluidAudio.git",
    "16780f04d2ece24f67d0fc00efccd0296491c1a8",
)
run(
    "swift",
    "build",
    "-c",
    "release",
    "--product",
    "fluidaudiocli",
    "--jobs",
    "6",
    cwd=fluid,
)
nemo = checkout(
    "NeMo-Speech.cpp",
    "https://github.com/NVIDIA/NeMo-Speech.cpp.git",
    "e790e463b2913cff9f989a3df224c587f14b4c5c",
)
name = "nemo-speech-0.3.0-macos-aarch64-metal.tar.gz"
url = "https://github.com/NVIDIA/NeMo-Speech.cpp/releases/download/v0.3.0/" + name
dest = root / "vendor/nemo-binary"
dest.mkdir(exist_ok=True)
archive = dest / name
if not archive.exists():
    urllib.request.urlretrieve(url, archive)
expected = urllib.request.urlopen(url + ".sha256").read().decode().split()[0]
with archive.open("rb") as stream:
    actual = hashlib.file_digest(stream, "sha256").hexdigest()
if actual != expected:
    raise SystemExit("NeMo archive checksum mismatch")
with tarfile.open(archive) as tar:
    tar.extractall(dest, filter="data")
models = [
    (
        "mlx-community/whisper-large-v3-mlx",
        "49e6aa286ad60c14352c404340ded53710378a11",
        "whisper-large-v3",
    ),
    (
        "mlx-community/Qwen3-ASR-1.7B-bf16",
        "e1f6c266914abc5a46e8756e02580f834a6cf8a7",
        "qwen3-asr",
    ),
    (
        "mlx-community/Qwen3-ForcedAligner-0.6B-8bit",
        "0e1a68e91d815300c7c9754b2a7639378b23db15",
        "qwen-aligner",
    ),
]
for repo, revision, folder in models:
    code = "from huggingface_hub import snapshot_download; import sys; snapshot_download(sys.argv[1], revision=sys.argv[2], local_dir=sys.argv[3])"
    run(python, "-c", code, repo, revision, root / "models" / folder)
model = root / "models/nemotron3-f32.gguf"
if not model.exists():
    run(
        python,
        nemo / "convert_model.py",
        "nvidia/Nemotron-3-Diarization",
        "--revision",
        "52a432672732425e4c19765b9fec9b5810e6f4ba",
        "--outfile",
        model,
        "--outtype",
        "f32",
    )
print("Runtime ready:", root)
print("Core ML models download on first use. Run meet init --runtime-root", root)
