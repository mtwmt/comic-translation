# Frozen pre-cache layout functions from 96393c057d523fef55beaa416c0477c1b6f50585.
# Test oracle only; never imported by production.
import cv2
import numpy as np
from PIL import Image

LAYOUT_VERSION = "mask-lettering-5"
MASK_VERSION = "character-mask-2"

def complete_character_mask(image, seed, polygons):
    """Complete bounded ink components, including small furigana on white paper.

    Never grow through a component that leaves the detector's local footprint:
    that is often a panel border, balloon outline or an illustration stroke.
    """
    gray = np.asarray(image.convert("L"))
    h, w = gray.shape
    support = np.zeros((h, w), np.uint8)
    for poly in polygons:
        cv2.fillPoly(support, [np.asarray(poly, np.int32)], 1)
    radius = max(1, round(min(w, h) / 650))
    margin = max(3, round(min(w, h) * .005))
    support = cv2.dilate(support, np.ones((2 * margin + 1,) * 2, np.uint8)) > 0
    _, labels, stats, _ = cv2.connectedComponentsWithStats((gray < 225).astype(np.uint8), 8)
    contained = np.bincount(labels[support], minlength=len(stats))
    covered = np.bincount(labels[seed], minlength=len(stats))
    accepted = np.zeros(len(stats), bool)
    for label, (x, y, cw, ch, area) in enumerate(stats[1:], 1):
        if contained[label] != area or max(cw, ch) > max(48, min(w, h) * .09):
            continue
        # Small unsegmented annotation is accepted only on largely white paper.
        local = gray[max(0, y-radius*3):min(h, y+ch+radius*3),
                     max(0, x-radius*3):min(w, x+cw+radius*3)]
        if covered[label] >= area * .1 or (area < max(40, min(w, h) ** 2 * .0004)
                                           and np.mean(local > 240) > .55):
            accepted[label] = True
    complete = cv2.dilate(accepted[labels].astype(np.uint8), np.ones((2 * radius + 1,) * 2, np.uint8)) > 0
    return seed | (complete & support)


def find_regions(image: Image.Image, detections: list, text_mask=None) -> tuple[list[dict], np.ndarray]:
    gray = np.asarray(image.convert("L"))
    height, width = gray.shape
    white = (gray >= 215).astype("uint8")
    polygons = []
    detection_mask = np.zeros_like(white)
    for poly, score in detections:
        poly = np.asarray(poly, np.int32).copy()
        poly[:, 0] = np.clip(poly[:, 0], 0, width - 1)
        poly[:, 1] = np.clip(poly[:, 1], 0, height - 1)
        polygons.append((poly, score))
        cv2.fillPoly(detection_mask, [poly], 1)
    # Detector polygons include padding and sometimes overlap balloon borders.
    # Remove only small ink components contained in detections; keep long artwork
    # components and borders intact when estimating the balloon topology.
    _, ink_labels, ink_stats, _ = cv2.connectedComponentsWithStats((gray < 215).astype("uint8"), connectivity=8)
    total = np.bincount(ink_labels.ravel())
    inside = np.bincount(ink_labels[detection_mask > 0], minlength=len(total))
    glyph_boxes = []
    for label in range(1, len(total)):
        x, y, w, h, area = ink_stats[label]
        if inside[label] / total[label] >= 0.92 and w < max(48, width * .065) and h < max(48, height * .065):
            white[ink_labels == label] = 1
            glyph_boxes.append([max(0, int(x) - 1), max(0, int(y) - 1), min(width, int(x + w) + 1), min(height, int(y + h) + 1)])
    # Small threshold/antialias gaps are closed on the analysis copy only.
    white = cv2.morphologyEx(white, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    if text_mask is not None:
        # A learned character mask can connect the balloon interior without
        # removing its entire text rectangle or nearby artwork.
        white[text_mask] = 1
    _, labels, stats, _ = cv2.connectedComponentsWithStats(white, connectivity=4)
    groups = {}
    for number, (poly, score) in enumerate(polygons):
        x, y = np.mean(poly, axis=0).astype(int)
        label = int(labels[y, x])
        # Unbounded white background is not a safe dialogue balloon.
        bx, by, bw, bh, area = stats[label]
        safe = bool(label and bx > 0 and by > 0 and bx + bw < width and by + bh < height
                    and 150 < area < width * height * 0.15 and bw < width * 0.65 and bh < height * 0.65)
        key = label if safe else f"unsafe-{number}"
        group = groups.setdefault(key, {"label": label if safe else None, "polygons": [], "scores": [],
                                       "status": "pending" if safe else "preserved",
                                       "reason": "" if safe else "不是可安全處理的封閉白底區域"})
        group["polygons"].append(poly.tolist())
        group["scores"].append(float(score))
    regions = list(groups.values())
    for group in regions:
        points = np.concatenate(group["polygons"])
        x1, y1 = points.min(axis=0)
        x2, y2 = points.max(axis=0) + 1
        group["bbox"] = [int(x1), int(y1), int(x2), int(y2)]
        group["erase_boxes"] = [box for box in glyph_boxes
                                if x1 <= (box[0] + box[2]) / 2 <= x2 and y1 <= (box[1] + box[3]) / 2 <= y2
                                and group["label"] is not None
                                and int(labels[(box[1] + box[3]) // 2, (box[0] + box[2]) // 2]) == group["label"]]
        group["direction"] = "vertical" if y2 - y1 >= (x2 - x1) * 0.7 else "horizontal"
    # Geometric ordering is provisional; translation IDs prevent reordered outputs.
    regions.sort(key=lambda r: (r["bbox"][1] // max(1, height // 8), -r["bbox"][2], r["bbox"][1]))
    for index, region in enumerate(regions):
        region["id"] = f"r{index + 1:03}"
    return regions, labels


def prepare_masked_regions(image, detections, text_mask, line_boxes=()):
    from src.offline.restoration import encode_mask
    text_mask = complete_character_mask(image, text_mask, [p for p, _ in detections])
    regions, labels = find_regions(image, detections, text_mask)
    h, w = labels.shape
    for region in regions:
        x1, y1, x2, y2 = region["bbox"]
        # Multiple vertical columns can make the whole block wider than tall.
        # Estimate orientation from detected lines rather than the block ratio.
        vertical = horizontal = 0
        for x, y, lw, lh in line_boxes:
            if x1 <= x + lw / 2 < x2 and y1 <= y + lh / 2 < y2:
                if lh > lw * 1.4:
                    vertical += lw * lh
                elif lw > lh * 1.4:
                    horizontal += lw * lh
        if vertical or horizontal:
            region["direction"] = "vertical" if vertical >= horizontal else "horizontal"
        support = np.zeros((h, w), np.uint8)
        for polygon in region["polygons"]:
            cv2.fillPoly(support, [np.array(polygon, np.int32)], 1)
        radius = max(3, round(min(w, h) * .005))
        support = cv2.dilate(support, np.ones((radius * 2 + 1,) * 2, np.uint8)) > 0
        erase = text_mask & support
        if region["label"] is not None:
            interior = labels == region["label"]
            # Several detected columns can share one balloon. Furigana falls
            # in the gaps between their polygons, so refine their joint text
            # footprint only after confirming they share a closed balloon.
            block = np.array([[x1, y1], [x2-1, y1], [x2-1, y2-1], [x1, y2-1]])
            completed = complete_character_mask(image, erase, [block])
            candidates, local_labels = find_regions(image, [(block, 1.0)], completed)
            if len(candidates) == 1 and candidates[0]["label"] is not None:
                interior = local_labels == candidates[0]["label"]
                erase = completed
            # Never cut away a part of an erasure mask silently at a border.
            safe = cv2.erode(interior.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
            region["interior_mask"] = encode_mask(interior)
        else:
            # Complex artwork requires review, and typesetting stays within
            # the original text footprint; it cannot expand over the page.
            safe = support.copy()
        region["erase_mask"] = encode_mask(erase)
        region["layout_mask"] = encode_mask(safe)
        region["requires_review"] = region["label"] is None
        region["status"] = "pending"
        region["reason"] = ""
        region["layout_version"] = LAYOUT_VERSION
        region["mask_version"] = MASK_VERSION
    return regions, labels
