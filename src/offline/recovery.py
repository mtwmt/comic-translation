"""Recover text the comic text detector misses (large or stylised lettering).

The block/segmentation detector is tuned for balloon-sized text and can give
near-zero confidence to display lettering such as titles. The general text
detector sees them, so its polygons are added when the first detector found
nothing there. The OCR language gate and review flags still apply afterwards.
"""
from __future__ import annotations

import cv2
import numpy as np

# Looser than the detector defaults: this pass only fills gaps, and the OCR
# language gate rejects most false boxes afterwards.
LOOSE_DETECTION = {"thresh": .2, "box_thresh": .4, "unclip_ratio": 2.0}
MIN_AREA_FRACTION = .001
MIN_COMPONENT_SHARE = .04
MAX_GROW_GLYPH = .12   # a glyph wider than this share of the page is not grown
MAX_GROW_LENGTH = 6    # nor beyond this many glyph sizes long
MAX_ASPECT = 10  # longer/thinner runs are panel borders, not glyphs
MIN_SIDE = 12
MAX_OVERLAP = .3
# Gap-filling boxes are the likeliest false positives (eyes, hatching, sound
# effects read as one stray kana), so their OCR text must be a real phrase.
MIN_RECOVERED_CHARACTERS = 3


def _bounds(poly):
    poly = np.asarray(poly)
    return poly[:, 0].min(), poly[:, 1].min(), poly[:, 0].max(), poly[:, 1].max()


def _overlap(box, others):
    area = max(1, (box[2] - box[0]) * (box[3] - box[1]))
    best = 0
    for other in others:
        w = min(box[2], other[2]) - max(box[0], other[0])
        h = min(box[3], other[3]) - max(box[1], other[1])
        if w > 0 and h > 0:
            best = max(best, w * h / area)
    return best


def _close(mask, size=5):
    """Morphological close that does not smear ink to the array border."""
    pad = size
    padded = cv2.copyMakeBorder(mask.astype(np.uint8), pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    closed = cv2.morphologyEx(padded, cv2.MORPH_CLOSE, np.ones((size, size), np.uint8))
    return closed[pad:-pad, pad:-pad]


def _glyph_like(stat):
    width, height = stat[cv2.CC_STAT_WIDTH], stat[cv2.CC_STAT_HEIGHT]
    return max(width, height) <= max(1, min(width, height)) * MAX_ASPECT


def _thick_ink(gray, box, size=None):
    """Thick, solid-looking ink in `box` (page coordinates) and the opening size used."""
    x1, y1, x2, y2 = box
    window = gray[y1:y2, x1:x2] < 128
    # Screentone-filled lettering is a field of dots: close it first.
    solid = _close(window)
    if size is None:
        size = min(9, max(3, round(min(x2 - x1, y2 - y1) * .04)))
        if solid.any():
            # Lettering strokes are thicker than panel borders that touch them, so
            # open by about 1.5x the typical stroke radius (most of its thickness).
            radius = np.percentile(cv2.distanceTransform(solid, cv2.DIST_L2, 3)[solid > 0], 90)
            if radius >= 4:  # thinner strokes cannot be told apart from borders
                size = min(21, max(size, 2 * round(radius * .75) + 1))
    return cv2.morphologyEx(solid, cv2.MORPH_OPEN, np.ones((size, size), np.uint8)) > 0, size


def _lettering(gray, box):
    """Full-page mask of the lettering inside a detector box, or None.

    Detector boxes are padded and swallow balloon or burst outlines, hearts and
    specks. Lettering strokes are thicker than those, so keep ink by thickness
    and drop what is left over by size. Ink that touches the box edge is kept
    (display lettering often touches the burst around it), and strokes just
    outside the box that sit next to the lettering are pulled in, since the
    detector often stops short of a final stroke.
    """
    height, width = gray.shape
    x1, y1, x2, y2 = box
    reach = max(6, round(min(x2 - x1, y2 - y1) * .08))
    wx1, wy1, wx2, wy2 = max(0, x1 - reach), max(0, y1 - reach), min(width, x2 + reach + 1), min(height, y2 + reach + 1)
    thick, size = _thick_ink(gray, (wx1, wy1, wx2, wy2))
    inside = np.zeros_like(thick)
    inside[y1 - wy1:y2 - wy1 + 1, x1 - wx1:x2 - wx1 + 1] = True
    count, parts, stats, _ = cv2.connectedComponentsWithStats((thick & inside).astype(np.uint8), 8)
    keep = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= (thick & inside).sum() * MIN_COMPONENT_SHARE
            and _glyph_like(stats[i])]
    if not keep:
        return None
    core = np.isin(parts, keep)
    near = cv2.dilate(core.astype(np.uint8), np.ones((2 * reach + 1,) * 2, np.uint8)) > 0
    count, parts, stats, _ = cv2.connectedComponentsWithStats(thick.astype(np.uint8), 8)
    # Neighbouring strokes join only when they are solid enough to be letters.
    joined = [i for i in range(1, count) if (near & (parts == i)).any() and _glyph_like(stats[i])
              and stats[i, cv2.CC_STAT_AREA] >= core.sum() * MIN_COMPONENT_SHARE]
    full = np.zeros((height, width), bool)
    full[wy1:wy2, wx1:wx2] = core | np.isin(parts, joined)
    return _add_leftover_ink(gray, _restore_edges(gray, full, size)), size


def _restore_edges(gray, text, size):
    """Give back the ink the thickness opening shaved off the glyph edges.

    Only ink within about half the opening size of the kept strokes returns, so a panel
    border touching a glyph is nibbled at its contact point, not reattached.
    """
    ys, xs = np.where(text)
    x1, y1 = max(0, xs.min() - size), max(0, ys.min() - size)
    x2, y2 = min(gray.shape[1], xs.max() + size + 1), min(gray.shape[0], ys.max() + size + 1)
    ink = _close(gray[y1:y2, x1:x2] < 128) > 0
    near = cv2.dilate(text[y1:y2, x1:x2].astype(np.uint8), np.ones((size // 2 + 2,) * 2, np.uint8)) > 0
    restored = text.copy()
    restored[y1:y2, x1:x2] |= ink & near
    return restored


def _add_leftover_ink(gray, text):
    """Add specks, hearts and wavy marks around the lettering.

    Screentone dots and decorations are thinner than the lettering, so the
    thickness filter leaves them behind. Ink that lies completely inside a
    window around the lettering is part of the title; ink that crosses the
    window edge continues into the burst or artwork and is left alone.
    """
    height, width = gray.shape
    ys, xs = np.where(text)
    reach = max(6, round(min(xs.max() - xs.min(), ys.max() - ys.min()) * .04))
    x1, y1 = max(0, xs.min() - reach), max(0, ys.min() - reach)
    x2, y2 = min(width, xs.max() + reach + 1), min(height, ys.max() + reach + 1)
    window = gray[y1:y2, x1:x2] < 200
    # Bridge the gaps between dots so a dotted shape is one component.
    window = _close(window)
    _, labels = cv2.connectedComponents(window, connectivity=8)
    edge = np.unique(np.concatenate((labels[0], labels[-1], labels[:, 0], labels[:, -1], [0])))
    inside = (labels > 0) & ~np.isin(labels, edge) & (gray[y1:y2, x1:x2] < 200)
    result = text.copy()
    result[y1:y2, x1:x2] |= inside
    return result


def _grow(gray, text, blocked, size, rounds=10):
    """Extend a lettering fragment to the rest of the same display lettering.

    Large sound effects are detected one glyph at a time. Thick ink of similar
    size lying within a glyph-width or so of the text is the next glyph, so
    join it, repeatedly. Long thin runs (panel borders), pieces much larger
    than a glyph, and ink already claimed by another detection are ignored.
    """
    height, width = gray.shape
    ys, xs = np.where(text)
    w0, h0 = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
    glyph = max(8, min(w0, h0))
    # Only a lone glyph of a sound effect is worth extending: bigger or elongated
    # fragments are already whole lettering, and growing them wanders into artwork.
    if max(w0, h0) > glyph * 1.5 or glyph > min(width, height) * MAX_GROW_GLYPH:
        return text
    for _ in range(rounds):
        ys, xs = np.where(text)
        if max(xs.max() - xs.min(), ys.max() - ys.min()) + 1 > glyph * MAX_GROW_LENGTH:
            break
        gap = max(6, round(glyph * .6))
        # Search wider than the join distance so a whole next glyph fits inside.
        reach = round(glyph * 3.2)
        x1, y1 = max(0, xs.min() - reach), max(0, ys.min() - reach)
        x2, y2 = min(width, xs.max() + reach + 1), min(height, ys.max() + reach + 1)
        thick, _ = _thick_ink(gray, (x1, y1, x2, y2), size)
        near = cv2.dilate(text[y1:y2, x1:x2].astype(np.uint8), np.ones((2 * gap + 1,) * 2, np.uint8)) > 0
        count, parts, stats, _ = cv2.connectedComponentsWithStats(thick.astype(np.uint8), 8)
        tall = ys.max() - ys.min() > 1.3 * (xs.max() - xs.min())
        wide = xs.max() - xs.min() > 1.3 * (ys.max() - ys.min())
        found = {"column": [], "row": []}
        for i in range(1, count):
            x, y, w, h, area = stats[i]
            piece = parts == i
            if (piece & text[y1:y2, x1:x2]).any() or not (piece & near).any() or (piece & blocked[y1:y2, x1:x2]).any():
                continue
            if max(w, h) > min(w, h) * 6 or max(w, h) > glyph * 3 or area < glyph * glyph * .04:
                continue
            if x == 0 or y == 0 or x + w == x2 - x1 or y + h == y2 - y1:
                continue  # touches the search window: it continues into something else
            # Following glyphs continue along the lettering's own direction.
            cx, cy = x1 + x + w / 2, y1 + y + h / 2
            if xs.min() - glyph * .25 <= cx <= xs.max() + glyph * .25:
                found["column"].append((i, area))
            if ys.min() - glyph * .25 <= cy <= ys.max() + glyph * .25:
                found["row"].append((i, area))
        if tall:
            chosen = found["column"]
        elif wide:
            chosen = found["row"]
        else:
            # A single glyph: Japanese sound effects mostly run vertically, so
            # prefer a column unless a row clearly finds more real glyphs.
            weight = {key: sum(area for _, area in items if area >= glyph * glyph * .1) for key, items in found.items()}
            chosen = found["column"] if weight["column"] >= weight["row"] * .6 else found["row"]
        added = np.isin(parts, [i for i, _ in chosen])
        if not added.any():
            break
        grown = text.copy()
        grown[y1:y2, x1:x2] |= added
        text = _add_leftover_ink(gray, grown)
    return text


def recover_missed_text(image, detections, text_mask, extra):
    """Return (detections, text_mask) extended with `extra` polygons not already covered."""
    gray = np.asarray(image.convert("L"))
    height, width = gray.shape
    known = [_bounds(poly) for poly, _ in detections]
    candidates = []
    for poly, score in extra:
        poly = np.asarray(poly, np.int32).copy()
        poly[:, 0] = np.clip(poly[:, 0], 0, width - 1)
        poly[:, 1] = np.clip(poly[:, 1], 0, height - 1)
        box = _bounds(poly)
        w, h = box[2] - box[0] + 1, box[3] - box[1] + 1
        if min(w, h) >= MIN_SIDE and w * h >= width * height * MIN_AREA_FRACTION and _overlap(box, known) < MAX_OVERLAP:
            candidates.append([*map(int, box), float(score)])
    # One lettering block is often split into stacked pieces; merge those.
    merged = True
    while merged:
        merged = False
        for i, a in enumerate(candidates):
            for b in candidates[i + 1:]:
                if min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1]):
                    a[:] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]), max(a[4], b[4])]
                    candidates.remove(b)
                    merged = True
                    break
            if merged:
                break
    added = []
    mask = text_mask.copy()
    blocked = text_mask.copy()
    for x1, y1, x2, y2, _ in [*[[*b, 0] for b in known]]:
        blocked[y1:y2 + 1, x1:x2 + 1] = True
    for x1, y1, x2, y2, score in candidates:
        found = _lettering(gray, (x1, y1, x2, y2))
        if found is None:
            continue
        text = _grow(gray, found[0], blocked, found[1])
        ys, xs = np.where(text)
        pad = 3
        added.append((np.array([[max(0, xs.min() - pad), max(0, ys.min() - pad)],
                                [min(width - 1, xs.max() + pad), max(0, ys.min() - pad)],
                                [min(width - 1, xs.max() + pad), min(height - 1, ys.max() + pad)],
                                [max(0, xs.min() - pad), min(height - 1, ys.max() + pad)]]), score))
        mask |= cv2.dilate(text.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    return list(detections) + added, mask


def is_recovered_region(region, poly):
    """True when the region was built from the recovered polygon `poly`."""
    return any(np.array_equal(np.asarray(candidate), np.asarray(poly)) for candidate in region["polygons"])
