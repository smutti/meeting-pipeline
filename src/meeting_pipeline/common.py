from __future__ import annotations
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(value, out, ensure_ascii=False, indent=2, allow_nan=False)
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(args, log=None, timeout=7200):
    env = {**os.environ, "HF_HUB_DISABLE_TELEMETRY": "1"}
    if log:
        with Path(log).open("w") as out:
            subprocess.run(
                [str(x) for x in args],
                check=True,
                stdout=out,
                stderr=subprocess.STDOUT,
                timeout=timeout,
                env=env,
            )
    else:
        subprocess.run([str(x) for x in args], check=True, timeout=timeout, env=env)


@contextlib.contextmanager
def locked(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with Path(path).open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(
                "Another local worker is running; retry after it finishes"
            ) from None
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def data_home(value=None):
    return (
        Path(
            value
            or os.environ.get(
                "MEETING_PIPELINE_HOME", "~/.local/share/meeting-pipeline"
            )
        )
        .expanduser()
        .resolve()
    )


def load_config(home):
    path = home / "config.json"
    if not path.exists():
        raise ValueError("Run 'meet init --runtime-root PATH' first")
    return read(path)


def protected_runtime_path(path, user_home=None):
    """Check lexical paths too: Python reads pyvenv.cfg beside a venv symlink."""
    base = Path(user_home) if user_home else Path.home()
    paths = [Path(path).expanduser().absolute(), Path(path).resolve()]
    return any(
        candidate.is_relative_to(base / folder)
        for candidate in paths
        for folder in ["Documents", "Desktop", "Downloads"]
    )
