"""Conservative white-balloon analysis and pixel-local vertical typesetting."""
from __future__ import annotations

import math
import re

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from .fonts import load_font, lettering_font

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
    from .restoration import encode_mask
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


def fit_region_lettering(size, region, font_path, safe, target=None):
    """Fit glyphs without erasing/inpainting, so page planning is side-effect free."""
    w, h = size
    x1, y1, x2, y2 = region["bbox"]
    if not safe.any():
        raise ValueError("排版範圍為空")
    ys, xs = np.where(safe)
    box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
    boxes = [box, (max(box[0], x1), max(box[1], y1), min(box[2], x2), min(box[3], y2))]
    # A balloon's bounding box includes curved corners and tails. Search
    # interior rectangles as well, instead of shrinking text indefinitely.
    for inset in (.05, .10, .15):
        dx, dy = round((box[2] - box[0]) * inset), round((box[3] - box[1]) * inset)
        boxes.extend([(box[0] + dx, box[1] + dy, box[2] - dx, box[3] - dy),
                      (box[0], box[1] + dy, box[2], box[3] - dy)])
    minimum = max(12, round(min(w, h) * .012))
    initial = max(minimum, min(round(36 * max(1, min(w, h) / 1000)),
                              max(16, min(x2 - x1, y2 - y1))))
    if region["direction"] == "vertical":
        line_widths = [np.ptp(np.asarray(p)[:, 0]) + 1 for p in region.get("polygons", [])
                       if np.ptp(np.asarray(p)[:, 1]) > np.ptp(np.asarray(p)[:, 0]) * 1.5]
        if line_widths:
            initial = min(initial, max(minimum, round(float(np.median(line_widths)) * .9)))
    glyphs = None
    # Keep the source footprint when a modest size adjustment suffices. Using
    # every bit of balloon height first creates long, lopsided columns.
    override = region.get("font_size_override", 0)
    if override:
        if not isinstance(override, int) or not 1 <= override <= 512:
            raise ValueError("指定字級須為 1～512 px")
        # The requested size is a preferred maximum, not an all-or-nothing
        # constraint. Exhaust wrapping at each size before reducing it.
        searches = [(size, area) for size in range(override, min(minimum, override) - 1, -1)
                    for area in [boxes[1], boxes[0], *boxes[2:]]]
    elif target is None:
        searches = [(size, boxes[1]) for size in range(initial, max(minimum, round(initial * .75)) - 1, -1)]
        searches += [(size, area) for size in range(initial, minimum - 1, -1) for area in boxes]
    else:
        # Exhaust available balloon rectangles at the source size before shrinking.
        areas = [boxes[1], boxes[0], *boxes[2:]]
        searches = [(size, area) for size in range(target, min(minimum, target) - 1, -1) for area in areas]
    visited = set()
    for font_size, layout_box in searches:
        if (font_size, layout_box) in visited:
            continue
        visited.add((font_size, layout_box))
        if layout_box[2] <= layout_box[0] or layout_box[3] <= layout_box[1]:
            continue
        layout_info = {}
        candidate = glyph_layer((w, h), region["translation"], layout_box, font_path, font_size,
                                region["direction"] == "vertical", region.get("protected_terms", ()), layout_info)
        if candidate is not None and candidate.any() and not np.any((candidate > 0) & ~safe):
            glyphs = candidate
            lines = layout_info["lines"]
            break
    if glyphs is None:
        if override:
            raise ValueError("換行及縮小後仍放不下，請放大框選或縮短譯文")
        raise ValueError("中文無法以可讀字級放入區域，請縮短譯文或保留原文")
    return glyphs, font_size, lines


def plan_page_lettering(image, regions, font_path):
    """Prefer each region's source size; use a page baseline only as fallback."""
    from .restoration import decode_mask
    from .source_size import estimate_source_font_size
    candidates = []
    source_sizes = {}
    for region in regions:
        for key in ("font_target", "font_style", "font_size_warning", "source_font_size"):
            region.pop(key, None)
        if not region.get("enabled", True) or not region.get("translation", "").strip():
            continue
        if region.get("font_size_override"):
            continue
        try:
            estimated = estimate_source_font_size(image, region)
            if estimated is not None:
                region.update(source_font_size=estimated, font_target=estimated, font_style="source")
                source_sizes[region["id"]] = estimated
                continue
            safe = decode_mask(region["layout_mask"], (image.height, image.width))
            _, fitted, _ = fit_region_lettering(image.size, region, font_path, safe)
        except (ValueError, KeyError):
            continue
        candidates.append((region, fitted, len(lettering_tokens(region["translation"]))))
    if len(candidates) < 2:
        return {"policy": "source-size-first-1", "source_sizes": source_sizes} if source_sizes else None
    dialogue = [fitted for _, fitted, length in candidates if length >= 9]
    baseline = round(float(np.median(dialogue or [f for _, f, _ in candidates])))
    for region, fitted, length in candidates:
        x1, y1, x2, y2 = region["bbox"]
        # Only enlarge a short line when its original footprint and its fit
        # both support emphasis. Punctuation alone is not a shout classifier.
        emphasized = length <= 8 and fitted >= baseline * 1.35 and min(x2-x1, y2-y1) >= baseline * 1.35
        region["font_style"] = "emphasis" if emphasized else "dialogue"
        region["font_target"] = round(baseline * 1.2) if emphasized else baseline
    return {"dialogue_size": baseline, "emphasis_size": round(baseline * 1.2),
            "policy": "source-size-first-1", "source_sizes": source_sizes}


def render_masked_region(image, region, font_path, restorer):
    """Validate lettering first. An unsuccessful region never leaves a hole."""
    from .restoration import decode_mask
    rgb = np.asarray(image)
    h, w = rgb.shape[:2]
    erase = decode_mask(region["erase_mask"], (h, w))
    safe = decode_mask(region["layout_mask"], (h, w))
    # Upgrade old automatic masks once; never override a user's brush edits.
    if region.get("mask_version") != MASK_VERSION and region.get("layout_version") not in {"mask-lettering-2", "mask-lettering-3", "mask-lettering-4", LAYOUT_VERSION} and not region.get("mask_edited") and region.get("polygons"):
        refined = complete_character_mask(image, erase, region["polygons"])
        regions, _ = prepare_masked_regions(image, [(p, 1.0) for p in region["polygons"]], refined)
        if len(regions) == 1:
            for key in ("label", "erase_mask", "layout_mask", "interior_mask", "requires_review"):
                if key in regions[0]:
                    region[key] = regions[0][key]
            erase = decode_mask(region["erase_mask"], (h, w))
            safe = decode_mask(region["layout_mask"], (h, w))
        region["layout_version"] = LAYOUT_VERSION
    region["mask_version"] = MASK_VERSION
    region["layout_version"] = LAYOUT_VERSION
    if not erase.any() or not safe.any():
        raise ValueError("文字遮罩或排版範圍為空，請在預覽調整")
    x1, y1, x2, y2 = region["bbox"]
    # Local masks must not become a way to authorize erasing a whole page.
    allowed = np.zeros((h, w), np.uint8)
    margin = max(3, round(min(w, h) * .005))
    allowed[max(0, y1 - margin):min(h, y2 + margin), max(0, x1 - margin):min(w, x2 + margin)] = 1
    if np.any(erase & ~(allowed > 0)) or erase.sum() > h * w * .15:
        raise ValueError("清字遮罩超出文字區域，保留原文")
    if region.get("label") is not None:
        # Layout has an eroded margin; allow character antialiasing near it,
        # but do not permit a mask across a balloon boundary.
        interior = decode_mask(region["interior_mask"], (h, w))
        if np.any(erase & ~interior):
            raise ValueError("文字遮罩碰到框線，請在預覽調整")
    glyphs, font_size, lines = fit_region_lettering(image.size, region, font_path, safe,
                                                 region.get("font_target"))
    region["layout_lines"] = lines
    region.pop("font_size_warning", None)
    if region.get("font_size_override") and font_size < region["font_size_override"]:
        region["font_size_warning"] = f"指定 {region['font_size_override']} px；換行後仍超出範圍，已縮小至 {font_size} px"
    elif region.get("font_target") and font_size < round(region["font_target"] * .85):
        region["font_size_warning"] = "空間不足，字級低於原文或建議大小；可放大框選或縮短譯文後重排"
        region["requires_review"] = True
    ring = cv2.dilate(erase.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool) & ~erase & safe
    background = rgb[ring]
    uniform = len(background) >= 30 and np.max(np.std(background.astype(float), axis=0)) < 6
    # Paper with a few outline or screentone specks in the ring is still blank
    # paper: filling it flat beats inpainting, which smudges grey noise.
    mostly_white = (len(background) >= 30 and np.median(background) >= 240
                    and np.mean(background.min(axis=1) >= 235) >= .85)
    if region.get("cleaning_mode") == "white":
        # Explicit white-balloon cleanup fills only the editable character mask.
        # Never allow it to spill onto the protected outline or outside the box.
        output = rgb.copy()
        output[erase] = 255
        region["cleaning"] = "white-fill"
        region["requires_review"] = True
    elif uniform or mostly_white:
        output = rgb.copy()
        color = np.median(background, axis=0).astype(np.uint8)
        output[erase] = color
        region["cleaning"] = "solid-fill"
    else:
        output = np.asarray(restorer.inpaint(image, erase)).copy()
        # Enforce preservation even if a model adapter changes its behavior.
        output[~erase] = rgb[~erase]
        region["cleaning"] = "lama"
        region["requires_review"] = True
    # Use white lettering on a predominantly dark local background.
    text_color = 255 if np.median(output[safe]) < 110 else 0
    alpha = glyphs.astype(float)[:, :, None] / 255
    output = np.rint(output * (1 - alpha) + text_color * alpha).astype(np.uint8)
    region["font_size"] = font_size
    region["reason"] = ""
    return Image.fromarray(output), erase | (glyphs > 0)


VERTICAL_FORMS = str.maketrans({"。": "︒", "、": "︑", "，": "︐", "：": "︓", "；": "︔",
                               "！": "︕", "？": "︖", "（": "︵", "）": "︶", "「": "﹁", "」": "﹂",
                               "『": "﹃", "』": "﹄", "…": "︙", "—": "︱", "ー": "︱", "～": "︴", "~": "︴", "〜": "︴",
                               "!": "︕", "?": "︖", ",": "︐", ":": "︓"})


def lettering_tokens(text):
    """Treat paired exclamation/question marks as one vertical character cell."""
    text = re.sub(r"\s+", "", text)
    return re.findall(r"[！!？?]{1,3}|.", text)


def wrap_tokens(tokens, capacity, max_lines, protected_terms=(), hard_breaks=()):
    """Choose word/phrase boundaries before balancing the column lengths."""
    from functools import lru_cache
    from .linebreak import boundary_costs
    text = "".join(tokens)
    costs = boundary_costs(text, tuple(sorted(set(protected_terms))))
    offsets = [0]
    for token in tokens:
        offsets.append(offsets[-1] + len(token))
    closing = set("。，、！？!?：；）］」』】…～~〜")
    expressive = set("～~〜♡♥")
    opening = set("（［「『【")
    overall = (float("inf"), None)
    for count in range(max(1, math.ceil(len(tokens) / capacity)), min(max_lines, len(tokens)) + 1):
        target = len(tokens) / count
        @lru_cache(None)
        def fit(start, remaining):
            if remaining == 0:
                return (0, ()) if start == len(tokens) else (float("inf"), ())
            best = (float("inf"), ())
            for end in range(start + 1, min(len(tokens), start + capacity) + 1):
                expressive_tail = end == len(tokens) and all(set(t) <= expressive for t in tokens[start:end])
                if end - start == 1 and len(tokens) > 3 and end not in hard_breaks and not expressive_tail:
                    continue
                if len(tokens) > 3 and all(not re.search(r"[\w一-龯]", token) for token in tokens[start:end]) and not expressive_tail:
                    continue
                if any(start < boundary < end for boundary in hard_breaks):
                    continue
                if end < len(tokens) and (tokens[end][0] in closing - expressive or tokens[end-1][-1] in opening):
                    continue
                boundary_cost = costs.get(offsets[end], 0.0) if end < len(tokens) else 0.0
                if boundary_cost is None and end not in hard_breaks:
                    continue
                score, lines = fit(end, remaining - 1)
                score += .25 * (end - start - target) ** 2
                if expressive_tail:
                    score += 50  # Prefer keeping the ending with words when it fits.
                score += 0 if end in hard_breaks else boundary_cost or 0
                if end - start == 1 and len(tokens) > 2:
                    score += 15
                score += 8 * sum(tokens[i][-1:] in "，。；！？!?" for i in range(start, end - 1))
                if score < best[0]:
                    best = score, (tuple(tokens[start:end]),) + lines
            return best
        cost, lines = fit(0, count)
        # A slightly longer layout is preferable to joining the end of one
        # clause to the start of the next just to minimize the column count.
        cost += count * 4
        if cost < overall[0]:
            overall = (cost, lines)
    return overall[1]


def glyph_layer(size, text, box, font_path, font_size, vertical, protected_terms=(), layout_info=None):
    layer = Image.new("L", size, 0)
    font = load_font(font_path, font_size)
    glyph_fonts = {}
    x1, y1, x2, y2 = box
    step = math.ceil(font_size * 1.12)
    tokens = lettering_tokens(text) if vertical else list(re.sub(r"\s+", "", text))
    if not tokens:
        return np.asarray(layer)
    capacity = (y2-y1 if vertical else x2-x1) // step
    max_lines = (x2-x1 if vertical else y2-y1) // step
    if min(capacity, max_lines) < 1:
        return None
    # Explicit line breaks from the editor remain intentional column breaks.
    hard_breaks = []
    consumed = 0
    for paragraph in text.splitlines()[:-1]:
        consumed += len(lettering_tokens(paragraph)) if vertical else len(re.sub(r"\s+", "", paragraph))
        if consumed:
            hard_breaks.append(consumed)
    lines = wrap_tokens(tokens, capacity, max_lines, protected_terms, tuple(hard_breaks))
    if lines is None:
        return None
    if layout_info is not None:
        layout_info["lines"] = ["".join(line) for line in lines]
    count = len(lines)
    longest = max(map(len, lines))
    for line_index, line in enumerate(lines):
        for index, token in enumerate(line):
            cell = Image.new("L", (step*3, step*3), 0)
            draw = ImageDraw.Draw(cell)
            paired = vertical and len(token) > 1 and all(c in "！!？?" for c in token)
            display = token.translate(str.maketrans("！？", "!?")) if paired else token
            if vertical and not paired:
                display = token.translate(VERTICAL_FORMS)
            if display not in glyph_fonts:
                glyph_fonts[display] = lettering_font(font, display)
            draw.text((step*1.5, step*1.5), display, font=glyph_fonts[display], fill=255, anchor="mm")
            bounds = cell.getbbox()
            if not bounds:
                continue
            cell = cell.crop(bounds)
            if paired and cell.width > font_size:
                cell = cell.resize((font_size, cell.height), Image.Resampling.LANCZOS)
            if vertical:
                cx = (x1+x2+count*step)/2 - (line_index+.5)*step
                cy = (y1+y2-longest*step)/2 + (index+.5)*step
            else:
                cx = (x1+x2-len(line)*step)/2 + (index+.5)*step
                cy = (y1+y2-count*step)/2 + (line_index+.5)*step
            # Paste full glyph coverage, including antialiasing, without cropping
            # to the target box. The caller checks it against the balloon mask.
            layer.paste(cell, (round(cx-cell.width/2), round(cy-cell.height/2)))
    return np.asarray(layer)


def render_region(image, region, labels, font_path):
    height, width = labels.shape
    interior = (labels == region["label"]).astype("uint8")
    safe = cv2.erode(interior, np.ones((7, 7), np.uint8)) > 0
    erase = np.zeros_like(interior)
    for x1, y1, x2, y2 in region["erase_boxes"]:
        erase[y1:y2, x1:x2] = 1
    erase = erase > 0
    rgb = np.asarray(image)
    erase &= rgb.min(axis=2) < 250
    if not np.any(erase):
        raise ValueError("無法安全分離原文字筆畫")
    # Erasure has its own boundary: it must stay inside the balloon but does
    # not need the larger margin used for newly placed Chinese glyphs.
    if np.any(erase & ~(interior > 0)):
        raise ValueError("原字太靠近框線，保留原文")
    background = rgb[safe & ~erase]
    if len(background) < 100 or np.quantile(background.min(axis=1), 0.05) < 230:
        raise ValueError("對話框不是乾淨白底，保留原文")
    ys, xs = np.where(safe)
    x1, y1, x2, y2 = region["bbox"]
    # Anchor layout near the original text, not the centroid of white space
    # that may include a balloon tail or other connected background.
    margin = max(4, min(16, int(min(x2 - x1, y2 - y1) * .15)))
    box = (max(int(xs.min()) + 2, x1 - margin), max(int(ys.min()) + 2, y1 - margin),
           min(int(xs.max()) - 1, x2 + margin), min(int(ys.max()) - 1, y2 + margin))
    minimum = max(12, round(min(width, height) * 0.012))
    scale = max(1.0, min(width, height) / 1000)
    initial = max(minimum, min(round(36 * scale),
                  max(round(16 * scale), int(min(x2 - x1, y2 - y1) / max(1, len(region["polygons"]))))))
    glyphs = None
    # Try the source footprint first, then the available balloon interior.
    # A longer translation must be able to use existing empty balloon space.
    boxes = [box, (int(xs.min()) + 2, int(ys.min()) + 2, int(xs.max()) - 1, int(ys.max()) - 1)]
    for layout_box in boxes:
        for font_size in range(initial, minimum - 1, -1):
            candidate = glyph_layer((width, height), region["translation"], layout_box, font_path, font_size,
                                    region["direction"] == "vertical")
            if candidate is not None and np.any(candidate) and not np.any((candidate > 0) & ~safe):
                glyphs = candidate
                break
        if glyphs is not None:
            break
    if glyphs is None:
        raise ValueError("中文無法以可讀字級放入安全區域，保留原文")
    output = rgb.copy()
    # Only original dark glyph pixels are erased, not the full rectangular crop.
    erase &= rgb.min(axis=2) < 250
    output[erase] = np.median(background, axis=0).astype("uint8")
    alpha = glyphs.astype(float) / 255
    output = np.rint(output * (1 - alpha[:, :, None])).astype("uint8")
    change_mask = erase | (glyphs > 0)
    region["font_size"] = font_size
    return Image.fromarray(output), change_mask
