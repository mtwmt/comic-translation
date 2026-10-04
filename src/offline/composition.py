"""Compose independent regions from the source, with one preservation/status policy."""
import numpy as np
from PIL import Image


def render_page(original, regions, render, *, retry_preserved=False,
                missing_reason="缺少譯文", text_status=None):
    """Rendering failures preserve a region; overlap never replaces earlier pixels.

    Translation respects detection decisions. Revision retries edited regions,
    including ones previously preserved, while honoring explicit user exclusions.
    The caller owns the records and chooses the region renderer/font/model.
    """
    baseline = np.asarray(original)
    result = baseline.copy()
    changed = np.zeros(baseline.shape[:2], dtype=bool)
    for region in regions:
        if retry_preserved:
            region["status"] = "pending"
            if not region.get("enabled", True):
                region.update(status="preserved", reason="使用者保留原文")
                continue
        if region["status"] != "pending":
            continue
        if not region.get("translation", "").strip():
            region.update(status="preserved", reason=missing_reason)
            continue
        try:
            rendered, mask = render(region)
            if np.any(changed & mask):
                raise ValueError("與其他文字區域重疊，請調整遮罩或保留其中一區")
            result[mask] = np.asarray(rendered)[mask]
            changed |= mask
            region["status"] = "translated"
            if text_status:
                region["text_status"] = text_status
        except ValueError as error:
            region.update(status="preserved", reason=str(error))
    if not np.array_equal(result[~changed], baseline[~changed]):
        raise RuntimeError("保真檢查失敗：修改範圍外的像素被改動")
    count = sum(r["status"] == "translated" for r in regions)
    review_count = sum(r["status"] == "translated" and bool(r.get("requires_review")) for r in regions)
    summary = {"translated": count, "preserved": len(regions) - count,
               "review_required": review_count, "pixel_preservation": True,
               "status": "success" if count and count == len(regions) and not review_count
                         else "partial" if count else "failed"}
    return Image.fromarray(result), summary, Image.fromarray(changed.astype(np.uint8) * 255)
