"""Local revision from a saved report; never invokes OCR or a translator."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import uuid

from .composition import render_page
from .images import load_image
from .storage import available_path, atomic_json, save_png, sha256
from .restoration import RestorationModels
from .fonts import resolve_font, FontFace
from .layout import LAYOUT_VERSION, plan_page_lettering, render_masked_region
from src.platforms import current as platform_support


def load_source(report):
    source = Path(report["source"])
    if sha256(source) != report["source_hash"]:
        raise ValueError("原圖內容已改變，請重新建立翻譯報告")
    image = load_image(source)
    if list(image.size) != report["image_size"]:
        raise ValueError("原圖尺寸與報告不符")
    return image


def rerender(report, models: Path, restorer=None):
    """The report contains editable translations/masks; always start at source."""
    original = load_source(report)
    updated = deepcopy(report)
    if platform_support.DELETE_DETECTED_REGIONS:
        from src.platforms.windows_layout import resolve_duplicate_regions
        resolve_duplicate_regions(updated["regions"], revision=True)
    font_path, font_details = resolve_font()
    font = FontFace(font_path, font_details.get("index", 0))
    updated["fingerprint"]["font"] = font_details
    updated["fingerprint"]["layout"] = LAYOUT_VERSION
    if any("erase_mask" not in r for r in updated["regions"]):
        raise ValueError("此報告沒有可編輯遮罩，請用新版清字模式重新處理")
    restorer = restorer or RestorationModels(models)
    if report["fingerprint"].get("restoration") != restorer.fingerprint:
        raise ValueError("修補模型版本已變更，請重新建立報告")
    updated["font_plan"] = plan_page_lettering(original, updated["regions"], font)
    result, summary, mask = render_page(original, updated["regions"],
        lambda region: render_masked_region(original, region, font, restorer),
        retry_preserved=True, missing_reason="尚未填寫譯文", text_status="edited")
    if platform_support.DELETE_DETECTED_REGIONS:
        for region in updated["regions"]:
            if region.get("duplicate_of") and not region.get("enabled", True):
                region["reason"] = f"大範圍偵測與 {region['duplicate_of']} 原文重複，已保留較小文字區域"
    updated.update(summary)
    updated.update(mode="local-revision",
                   text_translated=sum(bool(r.get("translation", "").strip()) for r in updated["regions"]),
                   reason="" if summary["translated"] else "沒有完成貼字的區域；僅保存修訂報告")
    return result, updated, mask


def save_revision(report_path, image, report, mask):
    if sha256(Path(report["source"])) != report["source_hash"]:
        raise ValueError("修訂期間原圖有變更，結果未保存")
    metadata_dir = Path(report["metadata_dir"]) if report.get("metadata_dir") else None
    source_output = Path(report["output_path"]) if metadata_dir else report_path.with_suffix(".png")
    target = available_path(source_output.with_name(Path(report["source"]).stem + "_zh-TW_revised.png"), set(), uuid.uuid4().hex, metadata_dir)
    metadata = metadata_dir / target.name if metadata_dir else target
    if report["translated"] or (platform_support.DELETE_DETECTED_REGIONS and report.get("deleted_region_ids")):
        save_png(target, image)
        save_png(metadata.with_name(metadata.stem + ".mask.png"), mask)
    report["output_path"] = str(target)
    atomic_json(metadata.with_suffix(".json"), report)
    return metadata.with_suffix(".json")
