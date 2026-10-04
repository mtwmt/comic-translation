"""Estimate printed character size from source ink, not translated length."""
import cv2
import numpy as np
import re

from .restoration import decode_mask


def estimate_source_font_size(image, region):
    x1, y1, x2, y2 = region["bbox"]
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(image.width, x2), min(image.height, y2)
    if x2 <= x1 or y2 <= y1:
        return None
    gray = np.asarray(image.crop((x1,y1,x2,y2)).convert("L"))
    ink = gray > 190 if np.median(gray) < 110 else gray < 170
    if "erase_mask" in region:
        support = decode_mask(region["erase_mask"], (image.height,image.width))[y1:y2,x1:x2]
        ink &= support
    _, _, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    candidates = []
    vertical = region.get("direction", "vertical") == "vertical"
    for x, y, w, h, area in stats[1:]:
        # Discard cropped strokes, specks, long rulings and most punctuation.
        if x == 0 or y == 0 or x+w >= gray.shape[1] or y+h >= gray.shape[0]:
            continue
        if min(w,h) < 4 or area < 12 or max(w,h) > min(w,h)*4:
            continue
        # Connected display letters can span several glyphs along the line.
        extent = w if vertical and h > w*1.6 else h if not vertical and w > h*1.6 else max(w,h)
        candidates.append((float(extent), float(area)))
    single_character = len(re.findall(r"[一-龯ぁ-ゖァ-ヺ]", region.get("original", ""))) == 1
    if not candidates or len(candidates) < 2 and not single_character:
        return None
    # Weight by ink so furigana and disconnected kanji dots cannot dominate.
    # The upper-middle value favours full glyphs over individual radicals.
    candidates.sort()
    total = sum(weight for _, weight in candidates)
    accumulated = 0
    for extent, weight in candidates:
        accumulated += weight
        if accumulated >= total*.65:
            # Printed ink is typically smaller than the font's em square.
            return max(8, min(512, round(extent / .9)))
    return None
