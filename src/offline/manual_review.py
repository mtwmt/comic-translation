"""Bounded manual text regions; no detector or cloud calls on box selection."""
from __future__ import annotations

from copy import deepcopy
import cv2
import numpy as np
from PIL import Image

from .layout import LAYOUT_VERSION, MASK_VERSION
from .restoration import decode_mask, encode_mask


def manual_region(image, box, regions, glossary, ink_threshold=225):
    w, h = image.size
    ax, ay, bx, by = map(round, box)
    x1, x2 = sorted((max(0, min(w, ax)), max(0, min(w, bx))))
    y1, y2 = sorted((max(0, min(h, ay)), max(0, min(h, by))))
    if x2 - x1 < 8 or y2 - y1 < 8:
        raise ValueError("框選範圍太小，請框住完整文字並留少許空白。")
    if (x2 - x1) * (y2 - y1) > w * h * .15:
        raise ValueError("請一次只框一段對白，範圍不可超過整頁的 15%。")
    for region in regions:
        a, b, c, d = region["bbox"]
        if max(x1, a) < min(x2, c) and max(y1, b) < min(y2, d):
            raise ValueError(f"與 {region['id']} 重疊；請選取既有區域修改，或重新框選。")
    gray = np.asarray(image.convert("L"))[y1:y2, x1:x2]
    # Keep boundary protection based on dark strokes: faint JPEG noise must not
    # connect every character to the balloon outline at a higher threshold.
    _, labels = cv2.connectedComponents((gray < 225).astype(np.uint8), connectivity=8)
    # Any ink connected to an edge may continue into artwork outside the box.
    edges = np.unique(np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1], [0])))
    ink = (labels > 0) & ~np.isin(labels, edges)
    radius = max(1, round(min(w, h) / 650))
    kernel = np.ones((radius * 2 + 1,) * 2, np.uint8)
    protected = cv2.dilate(((labels > 0) & ~ink).astype(np.uint8), kernel) > 0
    ink |= (gray >= 225) & (gray < ink_threshold) & ~protected
    local_mask = (cv2.dilate(ink.astype(np.uint8), kernel) > 0) & ~protected
    erase = np.zeros((h, w), bool)
    erase[y1:y2, x1:x2] = local_mask
    safe = np.zeros_like(erase)
    safe[y1:y2, x1:x2] = ~protected
    used = {r["id"] for r in regions}
    number = 1
    while f"r{number:03}" in used:
        number += 1
    return {"id": f"r{number:03}", "bbox": [x1, y1, x2, y2], "polygons": [],
            "label": None, "manual": True, "enabled": True, "requires_review": True,
            "direction": "vertical", "original": "", "translation": "", "status": "preserved",
            "reason": "手動新增：請核對原文與紅色清字範圍，再翻譯或填入譯文。",
            "protected_terms": sorted(set(glossary.values())),
            "erase_mask": encode_mask(erase), "layout_mask": encode_mask(safe),
            "mask_version": MASK_VERSION, "layout_version": LAYOUT_VERSION}


def recognize_manual_region(image, region, recognizer):
    """Retain an editable region even when local OCR cannot read its lettering."""
    try:
        region["original"] = recognizer.recognize(image.crop(region["bbox"])).strip()
        if not region["original"]:
            region["reason"] = "未辨識出文字；可直接填寫原文或繁中譯文。"
    except Exception as error:
        region["reason"] = f"本機辨識失敗，仍可手動填寫：{error}"
    return region


def ocr_candidates(image, region, recognizer, limit=6):
    """Read a region several ways so a user who cannot type Japanese can pick one.

    Variants: the plain crop, the crop with everything but the text mask
    whitened (removes balloon/burst lines), and each vertical column of that
    cleaned crop read separately and joined right to left.
    """
    x1, y1, x2, y2 = region["bbox"]
    box = (max(0, x1 - 2), max(0, y1 - 2), min(image.width, x2 + 2), min(image.height, y2 + 2))
    crops = [image.crop(box)]
    columns = []
    if "erase_mask" in region:
        rgb = np.asarray(image.convert("RGB"))
        mask = decode_mask(region["erase_mask"], rgb.shape[:2])
        clean = np.full_like(rgb, 255)
        clean[mask] = rgb[mask]
        crops.append(Image.fromarray(clean[box[1]:box[3], box[0]:box[2]]))
        local = mask[box[1]:box[3], box[0]:box[2]]
        weight = local.sum(axis=0).astype(float)
        if region.get("direction") == "vertical" and weight.max() > 0:
            start = None
            for x, filled in enumerate(list(weight > weight.max() * .2) + [False]):
                if filled and start is None:
                    start = x
                elif not filled and start is not None:
                    rows = np.where(local[:, start:x].any(axis=1))[0]
                    columns.append(crops[1].crop((max(0, start - 4), int(rows.min()), x + 4, int(rows.max()) + 1)))
                    start = None
    found = []
    def add(text):
        text = (text or "").strip()
        if text and text not in found:
            found.append(text)
    for crop in crops:
        add(recognizer.recognize(crop))
    if len(columns) > 1:
        add("".join(recognizer.recognize(column).strip() for column in reversed(columns)))
    return found[:limit]


def resize_manual_region(image, region, box, regions, glossary):
    """Rebuild a region's geometry from a new box. Works for detected regions too:
    the detector's polygons and balloon topology are replaced by the box, exactly
    as for a hand-drawn region, while text and translation are kept."""
    geometry = manual_region(image, box, [r for r in regions if r["id"] != region["id"]], glossary,
                             ink_threshold=254 if region.get("cleaning_mode") == "white" else 225)
    result = deepcopy(region)
    for key in ("bbox", "erase_mask", "layout_mask", "mask_version", "layout_version"):
        result[key] = geometry[key]
    for key in ("font_size", "font_target", "source_font_size", "font_style", "font_size_warning", "layout_lines", "cleaning",
                "interior_mask"):
        result.pop(key, None)
    result.update(manual=True, polygons=[], label=None, status="preserved", requires_review=True, mask_edited=False,
                  reason="框選大小已調整，清字範圍已重建；請核對紅色範圍與預覽，完成後儲存成品。原文與譯文保留。")
    return result


def strengthen_white_cleaning(image, region, regions, glossary):
    updated = deepcopy(region)
    updated["cleaning_mode"] = "white"
    updated = resize_manual_region(image, updated, region["bbox"], regions, glossary)
    updated["reason"] = "已重建白底清字範圍，包含淡灰殘字；請確認遮罩與預覽沒有蓋到插圖，再儲存成品。"
    return updated


def translate_region(region, glossary, translator):
    original = region.get("original", "").strip()
    if not original:
        raise ValueError("請先填寫或更正辨識原文。")
    record = {"id": region["id"], "text": original}
    # Other OCR readings only apply while the user has not corrected the text.
    if region.get("ocr_alternatives") and original == region.get("ocr_primary"):
        record["alternatives"] = list(region["ocr_alternatives"])
    records = [record]
    result = translator.translate(records, glossary)
    text = result[region["id"]].strip()
    if not text:
        raise ValueError("此區翻譯為空，請重試或手動填寫。")
    return text
