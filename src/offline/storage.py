"""Shared file integrity and atomic output primitives, independent of models/jobs."""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image


def available_path(path: Path, reserved: set[str], owner: str | None = None,
                   metadata_dir: Path | None = None) -> Path:
    """Reserve a new output name without replacing existing images or reports."""
    original = path
    count = 1
    while True:
        metadata = (metadata_dir / path.name) if metadata_dir else path
        if not (str(path) in reserved or path.exists() or metadata.with_suffix(".json").exists()
                or metadata.with_name(metadata.stem + ".mask.png").exists() or metadata.with_suffix(".reserve").exists()):
            if owner is None:
                break
            try:
                # Persistent exclusive reservation protects different batches/processes.
                with metadata.with_suffix(".reserve").open("x", encoding="utf-8") as stream:
                    stream.write(owner)
                break
            except FileExistsError:
                pass
        count += 1
        path = original.with_name(f"{original.stem}_{count}{original.suffix}")
    reserved.add(str(path))
    return path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


@contextmanager
def _temporary_output(path: Path):
    """Use a unique sibling so concurrent writers cannot share a temporary file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            yield temporary, stream
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: Path, data: dict) -> None:
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    with _temporary_output(path) as (_, stream):
        stream.write(payload)


def save_png(path: Path, image: Image.Image) -> None:
    from PIL import Image

    with _temporary_output(path) as (temporary, stream):
        image.save(stream, format="PNG")
        stream.flush()
        with Image.open(temporary) as decoded:
            decoded.verify()
