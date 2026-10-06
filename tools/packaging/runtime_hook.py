"""Windowed dependencies still need streams; keep diagnostics beside the exe."""
import os
from pathlib import Path
import sys

log_dir = Path(sys.executable).resolve().parent / ".comic-translator" / "logs"
try:
    log_dir.mkdir(parents=True, exist_ok=True)
    stream = open(log_dir / f"runtime-{os.getpid()}.log", "a", encoding="utf-8", buffering=1)
except OSError:
    stream = open(os.devnull, "w", encoding="utf-8")
if sys.stdout is None:
    sys.stdout = stream
if sys.stderr is None:
    sys.stderr = stream
if sys.stdin is None:
    sys.stdin = open(os.devnull, "r", encoding="utf-8")

# Preparation explicitly re-enables Hugging Face downloads in its own child.
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
if not os.environ.get("PROCESSOR_ARCHITECTURE"):
    os.environ["PROCESSOR_ARCHITECTURE"] = "AMD64"
