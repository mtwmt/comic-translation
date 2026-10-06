"""Resolve saved review data by source identity, never by basename alone."""
import json
from pathlib import Path


def find_source_report(source, known_reports=(), source_root=None):
    source = Path(source).resolve()
    candidates = {Path(path) for path in known_reports}
    directories = {path.parent for path in candidates}
    roots = {source.parent}
    if source_root:
        roots.add(Path(source_root).resolve())
    for root in roots:
        if source.is_relative_to(root):
            output = root / "translated" / source.relative_to(root).parent
            directories.add(output / "work")
    for directory in directories:
        candidates.update(directory.glob("*.json"))
    dated = []
    for path in candidates:
        try:
            dated.append((path.stat().st_mtime_ns, str(path), path))
        except OSError:
            continue
    for _, _, path in sorted(dated, reverse=True):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
            if (isinstance(report, dict) and report.get("source")
                    and Path(report["source"]).resolve() == source
                    and isinstance(report.get("regions"), list)
                    and report.get("source_hash") and report.get("image_size")):
                return path
        except (OSError, ValueError, TypeError):
            continue
    return None
