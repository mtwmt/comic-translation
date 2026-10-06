"""Sequential, resumable page jobs. This module does not depend on a GUI."""
from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import threading
import uuid
from collections import Counter
from pathlib import Path

from PIL import Image

from .models import ModelError
from .cancellation import OperationCancelled
from .storage import available_path, atomic_json, save_png, sha256

EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
EXCLUDED = {"translated", ".comic-translator", "models", ".cache", ".git", ".venv", "offline-runs"}
from src.runtime_paths import app_root

STATE_ROOT = app_root() / ".comic-translator"


def parse_glossary(text: str) -> dict[str, str]:
    result = {}
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"名稱表第 {number} 行請使用 日文=中文")
        source, target = (part.strip() for part in line.split("=", 1))
        if not source or not target or source in result:
            raise ValueError(f"名稱表第 {number} 行有空白或重複原名")
        result[source] = target
    return result


def natural_key(path: Path):
    return tuple((0, int(part)) if part.isdigit() else (1, part.casefold())
                 for part in re.split(r"(\d+)", path.as_posix()))


def discover(inputs: list[Path], output: Path | None = None):
    found = {}
    excluded_output = output.resolve() if output else None
    for selected in sorted(inputs, key=lambda p: str(p.absolute())):
        if selected.is_symlink():
            continue
        selected = selected.resolve()
        if not selected.exists():
            raise FileNotFoundError(f"來源不存在：{selected}")
        root = selected if selected.is_dir() else selected.parent
        def is_output(path):
            if not excluded_output or not path.is_relative_to(excluded_output):
                return False
            # The chosen destination may also contain the original images.
            # In that case exclude generated subfolders, rather than all sources.
            if root.is_relative_to(excluded_output):
                return any(part in {"final", "work"} for part in path.relative_to(excluded_output).parts)
            return True

        if selected.is_dir():
            candidates = []
            for directory, dirs, files in os.walk(selected, followlinks=False):
                dirs[:] = sorted(d for d in dirs if d not in EXCLUDED
                                 and not (Path(directory) / d).is_symlink()
                                 and not is_output((Path(directory) / d).resolve()))
                candidates.extend(Path(directory) / file for file in files)
        else:
            candidates = [selected]
        for path in candidates:
            if (path.is_symlink() or path.suffix.lower() not in EXTENSIONS or not path.is_file()
                    or any(part in EXCLUDED for part in path.relative_to(root).parts[:-1])
                    or is_output(path)):
                continue
            # Explicit source aliases that traverse symlinked parent directories are rejected too.
            if path.resolve() != path.absolute():
                continue
            found.setdefault(path.resolve(), root)
    return sorted(found.items(), key=lambda pair: (str(pair[1]), natural_key(pair[0].relative_to(pair[1])), str(pair[0])))


def create_batch(inputs, fingerprint, glossary, output=None, state_root=STATE_ROOT, source_roots=None) -> Path:
    sources = discover(inputs, output)
    if source_roots:
        # GUI expands folders into individually removable pages; preserve the
        # original folder's output layout even when only a subset is submitted.
        grouped = []
        for source, root in sources:
            root = Path(source_roots.get(source, root)).resolve()
            if not root.is_dir() or not source.is_relative_to(root):
                raise ValueError("圖片不在指定的來源資料夾中")
            grouped.append((source, root))
        sources = sorted(grouped, key=lambda pair: (str(pair[1]), natural_key(pair[0].relative_to(pair[1]))))
    if not sources:
        raise ValueError("沒有找到 PNG、JPEG 或 WebP 圖片")
    identifier = uuid.uuid4().hex
    roots = {root for _, root in sources}
    reserved, pages = set(), []
    for source, root in sources:
        destination = output.resolve() if output else root / "translated"
        if output and len(roots) > 1:
            destination /= root.name + "-" + hashlib.sha256(str(root).encode()).hexdigest()[:8]
        destination /= source.relative_to(root).parent
        try:
            destination.mkdir(parents=True, exist_ok=True)
            probe = destination / f".write-test-{identifier}"
            with probe.open("xb"):
                pass
            probe.unlink()
        except PermissionError:
            if output:
                raise
            destination = state_root / "outputs" / (root.name + "-" + hashlib.sha256(str(root).encode()).hexdigest()[:8]) / source.relative_to(root).parent
            destination.mkdir(parents=True, exist_ok=True)
        final_dir, metadata_dir = destination / "final", destination / "work"
        final_dir.mkdir(parents=True, exist_ok=True)
        metadata_dir.mkdir(parents=True, exist_ok=True)
        target = available_path(final_dir / f"{source.stem}_zh-TW.png", reserved, identifier, metadata_dir)
        pages.append({"source": str(source), "source_hash": sha256(source), "output": str(target),
                      "report": str(metadata_dir / (target.stem + ".json")),
                      "mask": str(metadata_dir / (target.stem + ".mask.png")),
                      "state": "waiting", "output_hash": None, "reason": ""})
    journal = state_root / "batches" / f"{identifier}.json"
    atomic_json(journal, {"schema": 1, "id": identifier, "fingerprint": fingerprint,
                          "glossary": dict(glossary), "glossary_hash": glossary_hash(glossary),
                          "pages": pages, "status": "waiting"})
    return journal


def glossary_hash(glossary):
    return hashlib.sha256(json.dumps(glossary, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class BatchRunner:
    def __init__(self, pipeline, on_event=lambda event: None):
        self.pipeline, self.on_event = pipeline, on_event
        self.stop = threading.Event()
        self._lock = threading.Lock()

    def run(self, journal: Path, retry_failed=False, retry_partial=False):
        if not self._lock.acquire(blocking=False):
            raise RuntimeError("已有批次執行中")
        # A file lock also protects journals across multiple application processes.
        lock_path = journal.with_suffix(".lock")
        lock_file = None
        try:
            lock_file = lock_path.open("a+b")
            if os.name == "nt":
                import msvcrt
                lock_file.write(b"0")
                lock_file.flush()
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return self._run(journal, retry_failed, retry_partial)
        finally:
            if lock_file:
                lock_file.close()
            self._lock.release()

    def _run(self, journal, retry_failed, retry_partial):
        data = json.loads(journal.read_text(encoding="utf-8"))
        if data.get("schema") != 1:
            raise ValueError("不支援的批次紀錄版本")
        if any("report" not in page or "mask" not in page for page in data["pages"]):
            raise ValueError("批次紀錄缺少報告或遮罩位置，請建立新批次")
        if data["fingerprint"] != self.pipeline.fingerprint:
            raise ValueError("模型或程式版本已變更，請建立新批次以保留舊結果")
        if data.get("glossary_hash") != glossary_hash(data["glossary"]):
            raise ValueError("名稱表快照已變更，請建立新批次")
        data["status"] = "running"
        atomic_json(journal, data)
        skipped = 0
        self.on_event({"progress": 0, "total": len(data["pages"])})
        reserved = {page["output"] for page in data["pages"]}
        for index, page in enumerate(data["pages"]):
            if self.stop.is_set():
                data["status"] = "stopped"
                break
            source, output = Path(page["source"]), Path(page["output"])
            try:
                current_hash = sha256(source)
                valid = False
                if page["output_hash"] and output.exists() and current_hash == page["source_hash"]:
                    valid = sha256(output) == page["output_hash"]
                    if valid:
                        try:
                            with Image.open(output) as decoded:
                                decoded.verify()
                        except Exception:
                            valid = False
                if valid and (page["state"] == "success" or page["state"] == "partial" and not retry_partial):
                    skipped += 1
                    self.on_event({"progress": index + 1, "total": len(data["pages"]), "stage": "略過已完成圖片"})
                    continue
                if page["state"] == "failed" and not retry_failed and current_hash == page["source_hash"]:
                    self.on_event({"progress": index + 1, "total": len(data["pages"]), "stage": "略過先前失敗圖片；可選擇重試"})
                    continue
                metadata_dir = Path(page["report"]).parent
                report_path = Path(page["report"])
                if output.exists() or report_path.exists():
                    output = available_path(output, reserved, data["id"], metadata_dir)
                    page["output"] = str(output)
                    page["report"] = str(metadata_dir / (output.stem + ".json"))
                    page["mask"] = str(metadata_dir / (output.stem + ".mask.png"))
                report_path = Path(page["report"])
                mask_path = Path(page["mask"])
                page.update(state="running", source_hash=current_hash, output_hash=None, reason="")
                atomic_json(journal, data)
                self.on_event({"index": index + 1, "total": len(data["pages"]), "source": str(source), "stage": "開始"})
                image, report, mask = self.pipeline.process(source, data["glossary"],
                    lambda stage: self.on_event({"index": index + 1, "total": len(data["pages"]),
                                                 "source": str(source), "stage": stage}))
                if hasattr(self.pipeline, "check_cancel"):
                    self.pipeline.check_cancel()
                if sha256(source) != current_hash:
                    raise ValueError("處理期間來源檔案有變更，結果未保存")
                output.parent.mkdir(parents=True, exist_ok=True)
                if image is not None:
                    save_png(output, image)
                    save_png(mask_path, mask)
                    page["output_hash"] = sha256(output)
                report["output_path"] = str(output)
                report["metadata_dir"] = str(metadata_dir)
                atomic_json(report_path, report)
                page.update(state=report["status"], reason=report.get("reason", ""),
                            translated=report["translated"], preserved=report["preserved"],
                            text_translated=report.get("text_translated", report["translated"]),
                            review_required=report.get("review_required", 0))
            except OperationCancelled as error:
                page.update(state="stopped", reason=str(error))
                data["status"] = "stopped"
                atomic_json(journal, data)
                break
            except (ModelError, MemoryError) as error:
                page.update(state="stopped", reason=str(error))
                data["status"] = "stopped"
                atomic_json(journal, data)
                self.on_event({"error": str(error), "systemic": True})
                break
            except OSError as error:
                if error.errno in (errno.ENOSPC, errno.EACCES, errno.EROFS, errno.ENOMEM):
                    page.update(state="stopped", reason=str(error))
                    data["status"] = "stopped"
                    atomic_json(journal, data)
                    self.on_event({"error": str(error), "systemic": True})
                    break
                page.update(state="failed", reason=str(error))
            except Exception as error:
                page.update(state="failed", reason=str(error))
            atomic_json(journal, data)
            self.on_event({"index": index + 1, "total": len(data["pages"]), "source": str(source),
                           "state": page["state"], "reason": page["reason"], "output": page["output"],
                           "report": page["report"],
                           "progress": index + 1,
                           "translated": page.get("translated", 0), "preserved": page.get("preserved", 0),
                           "review_required": page.get("review_required", 0)})
        else:
            data["status"] = "completed"
        atomic_json(journal, data)
        return {"status": data["status"], "counts": dict(Counter(p["state"] for p in data["pages"])), "skipped": skipped}
