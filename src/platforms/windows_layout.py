"""Preserve artwork boundaries when Windows groups automatic text masks."""
from __future__ import annotations

import cv2
import numpy as np
import re

from src.offline.layout import find_regions

VERSION = "windows-balloon-boundaries-2"


def resolve_duplicate_regions(regions, *, revision=False):
    """Exclude broad artwork guesses that duplicate a smaller text detection.

    Require both matching Japanese and strong geometric containment; nearby
    repeated dialogue and explicitly edited/manual regions remain independent.
    Keep the excluded record available for inspection rather than deleting it.
    """
    def text(region):
        return "".join(re.findall(r"[ぁ-ヺ一-龯]", region.get("original", "")))

    for large in regions:
        if large.get("manual") or large.get("label") is not None or large.get("font_size_override") or large.get("mask_edited"):
            continue
        if revision and "enabled" in large:
            continue  # Explicit review choices take precedence over detection.
        words = text(large)
        if len(words) < 4:
            continue
        a, b, c, d = large["bbox"]
        area = (c-a)*(d-b)
        for small in regions:
            if small is large or small.get("manual") or small.get("enabled") is False or text(small) != words:
                continue
            x1,y1,x2,y2 = small["bbox"]
            small_area = (x2-x1)*(y2-y1)
            overlap = max(0, min(c,x2)-max(a,x1))*max(0, min(d,y2)-max(b,y1))
            if small_area > 0 and area >= small_area*3 and overlap >= small_area*.7:
                large.update(enabled=False, status="preserved", duplicate_of=small["id"],
                             reason=f"大範圍偵測與 {small['id']} 原文重複，已保留較小文字區域")
                large.pop("font_size", None)
                large.pop("layout_lines", None)
                break


def preserve_boundaries(image, detections, text_mask):
    """Do not let a learned text mask bridge through a balloon or sign outline.

    Keep long ink components that extend outside the detected text footprints.
    Bounded glyphs, including multiple columns in one balloon, remain available
    to the existing character completion and grouping algorithm.
    """
    gray = np.asarray(image.convert("L"))
    support = np.zeros(gray.shape, np.uint8)
    for polygon, _ in detections:
        cv2.fillPoly(support, [np.asarray(polygon, np.int32)], 1)
    _, labels, stats, _ = cv2.connectedComponentsWithStats(
        (gray < 215).astype(np.uint8), connectivity=8)
    inside = np.bincount(labels[support > 0], minlength=len(stats))
    protected = np.zeros(len(stats), bool)
    limit = max(48, min(image.size) * .09)
    for label, (_, _, width, height, area) in enumerate(stats[1:], 1):
        protected[label] = max(width, height) > limit and inside[label] < area * .92
    return np.asarray(text_mask, bool) & ~protected[labels]


def refine_mask(image, detections, completed):
    """Mask refinement hook for the shared prepare_masked_regions."""
    groups, _ = find_regions(image, detections, completed)
    merged = np.zeros(completed.shape, bool)
    for group in groups:
        if len(group["polygons"]) > 1:
            x1, y1, x2, y2 = group["bbox"]
            merged[y1:y2, x1:x2] = True
    # Refine existing merged blocks only. Changing the topology of unrelated
    # single detections could otherwise make them merge into a nearby block.
    protected = preserve_boundaries(image, detections, completed)
    return completed & (~merged | protected)
