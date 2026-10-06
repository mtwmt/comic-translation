"""Pinned local vision models; preparation is the only network entry point."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .storage import atomic_json, sha256

MODEL_SPECS = {
    "detector": ("PaddlePaddle/PP-OCRv5_mobile_det", "0d63e78e2b680928f6b1747d76a08db6e645efb7",
                 ["config.json", "inference.json", "inference.pdiparams", "inference.yml", "README.md"]),
    "ocr": ("kha-white/manga-ocr-base", "aa6573bd10b0d446cbf622e29c3e084914df9741",
            ["*.json", "vocab.txt", "pytorch_model.bin", "README.md"]),
}


class ModelError(RuntimeError):
    """A batch-wide model problem, not a bad input page."""


def prepare_models(root: Path) -> None:
    from huggingface_hub import snapshot_download

    root.mkdir(parents=True, exist_ok=True)
    for name, (repo, revision, patterns) in MODEL_SPECS.items():
        print(f"下載／驗證 {name}: {repo}@{revision}", flush=True)
        snapshot_download(repo, revision=revision, allow_patterns=patterns, local_dir=root / name)
    # The fallback lettering font is not stored in git; fetch it (hash-checked).
    from .fonts import ensure_bundled_font
    print("下載／驗證內附字型 Noto Sans CJK TC Bold", flush=True)
    ensure_bundled_font()
    files = {p.relative_to(root).as_posix(): sha256(p)
             for name in MODEL_SPECS for p in (root / name).rglob("*")
             if p.is_file() and ".cache" not in p.parts}
    atomic_json(root / "manifest-vision.json", {"schema": 1, "specs": MODEL_SPECS, "files": files})
    print("辨識模型已完成；圖片處理在本機，訂閱 CLI 文字翻譯需網路。", flush=True)


def verify_models(root: Path) -> str:
    manifest_path = root / "manifest-vision.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("schema") != 1 or manifest["specs"] != json.loads(json.dumps(MODEL_SPECS)):
            raise ModelError("模型包版本不符，請重新準備模型。")
        files = manifest["files"]
        if not isinstance(files, dict) or any(not isinstance(name, str) or "\\" in name
                or name.split("/")[0] not in MODEL_SPECS for name in files):
            raise ModelError("辨識模型清單格式不符，請執行 offline.py prepare-models。")
        required = ["detector/inference.pdiparams", "detector/inference.json", "detector/inference.yml",
                    "ocr/pytorch_model.bin"]
        if not all(name in files for name in required):
            raise ModelError("模型包不完整。")
        for name, expected in files.items():
            path = (root / name).resolve()
            if not path.is_relative_to(root.resolve()) or not path.is_file() or sha256(path) != expected:
                raise ModelError(f"模型檔缺失或損壞：{name}")
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        raise ModelError("辨識模型包缺失或無法讀取；請執行 offline.py prepare-models。") from error
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
