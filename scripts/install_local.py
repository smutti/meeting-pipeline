#!/usr/bin/env python3
"""Install skill links and an optional Mac inbox service outside protected folders."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser()
p.add_argument("--service", action="store_true")
p.add_argument("--home", default="~/.local/share/meeting-pipeline")
p.add_argument("--uv", default=shutil.which("uv"))
args = p.parse_args()
home = Path(args.home).expanduser().resolve()
binary = root / ".venv/bin/meet"
if not binary.exists():
    raise SystemExit("Create .venv and install this package first")


def run(*command):
    subprocess.run([str(x) for x in command], check=True)


def link(target, destination, replace_targets=()):
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        current = destination.resolve()
        if current == target.resolve():
            return
        if current in [p.resolve() for p in replace_targets]:
            destination.unlink()
    if destination.exists() or destination.is_symlink():
        raise SystemExit(f"Existing different installation: {destination}")
    destination.symlink_to(target)


def protected(path):
    path = Path(path).resolve()
    return any(
        path.is_relative_to(Path.home() / folder)
        for folder in ["Documents", "Desktop", "Downloads"]
    )


def clone(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temporary = target.with_name(target.name + ".copying")
        if temporary.exists():
            raise SystemExit(f"Interrupted copy at {temporary}; inspect before retry")
        run("cp", "-cR", source, temporary)
        temporary.rename(target)
    return target


if args.service:
    if sys.platform != "darwin":
        raise SystemExit("Background service requires macOS")
    if not args.uv:
        raise SystemExit("uv is required; install it or provide --uv PATH")
    config_path = home / "config.json"
    if not config_path.exists():
        raise SystemExit("Run meet init first")
    lock = (home / "worker.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Worker active; retry installation after it finishes")
    config = json.loads(config_path.read_text())
    runtime = config["runtime"]
    service_env = home / "service-env"
    if not (service_env / "bin/python").exists():
        run(args.uv, "venv", "--python", "3.12", service_env)
    if protected(runtime["mlx_python"]):
        frozen = subprocess.check_output(
            [args.uv, "pip", "freeze", "--python", runtime["mlx_python"]], text=True
        )
        requirements = home / "runtime/python-requirements.lock.txt"
        requirements.parent.mkdir(parents=True, exist_ok=True)
        requirements.write_text(frozen)
        run(
            args.uv,
            "pip",
            "install",
            "--python",
            service_env / "bin/python",
            "-r",
            requirements,
        )
        runtime["mlx_python"] = str(service_env / "bin/python")
    for key in ["qwen_model", "whisper_model", "aligner_model", "nemotron_model"]:
        value = runtime.get(key)
        if value and protected(value):
            runtime[key] = str(
                clone(Path(value), home / "runtime/models" / Path(value).name)
            )
    if protected(runtime["nemo_binary"]):
        source = Path(runtime["nemo_binary"]).parent.parent
        dest = clone(source, home / "runtime" / source.name)
        runtime["nemo_binary"] = str(dest / "bin/nemo-speech")
    if protected(runtime["fluid_binary"]):
        source = Path(runtime["fluid_binary"]).resolve().parent
        dest = clone(source, home / "runtime/fluidaudio-release")
        runtime["fluid_binary"] = str(dest / "fluidaudiocli")
    run(
        args.uv,
        "pip",
        "install",
        "--python",
        service_env / "bin/python",
        "--reinstall-package",
        "local-meeting-pipeline",
        root,
    )
    temporary = config_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(config, ensure_ascii=False, indent=2))
    temporary.replace(config_path)
    binary = service_env / "bin/meet"
    label = "local.meeting-pipeline.inbox"
    agent = Path.home() / "Library/LaunchAgents" / (label + ".plist")
    agent.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "Label": label,
        "ProgramArguments": [str(binary), "--home", str(home), "watch", "--once"],
        "StartInterval": 60,
        "RunAtLoad": True,
        "WorkingDirectory": str(home),
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
        },
        "StandardOutPath": str(home / "service.log"),
        "StandardErrorPath": str(home / "service-error.log"),
        "ProcessType": "Background",
    }
    if agent.exists():
        previous = plistlib.loads(agent.read_bytes())
        if previous.get("Label") != label:
            raise SystemExit("Unexpected existing service")
    domain = f"gui/{os.getuid()}"
    if (
        subprocess.run(
            ["launchctl", "print", domain + "/" + label], capture_output=True
        ).returncode
        == 0
    ):
        run("launchctl", "bootout", domain, str(agent))
    agent.write_bytes(plistlib.dumps(data))
    os.chmod(agent, 0o600)
    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()
    run("launchctl", "bootstrap", domain, str(agent))
    print("Service active:", agent)

link(
    binary,
    Path.home() / ".local/bin/meet",
    [root / ".venv/bin/meet", home / "service-env/bin/meet"],
)
for skill in (root / "skills").iterdir():
    if (skill / "SKILL.md").exists():
        link(
            skill,
            Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
            / "skills"
            / skill.name,
        )
print("Installed CLI and three skill links")
