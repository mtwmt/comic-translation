"""Local CTD segmentation and LaMa repair, composed through explicit masks.

Adapters use the published model tensor interfaces; no upstream application
code is vendored. Downloads are confined to prepare_restoration_models().
"""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import urllib.request

import cv2
import numpy as np
from PIL import Image

from .models import ModelError
from .storage import atomic_json, sha256

RESTORATION_VERSION = "ctd-lama-1"
RESTORATION_SPECS = {
    "comictextdetector.pt.onnx": {
        "url": "https://github.com/zyddnys/manga-image-translator/releases/download/beta-0.2.1/comictextdetector.pt.onnx",
        "sha256": "1a86ace74961413cbd650002e7bb4dcec4980ffa21b2f19b86933372071d718f",
        "bytes": 94669756,
    },
    "big-lama.pt": {
        "url": "https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt",
        "sha256": "7ba7aa7ac37a4d41fdbbeba3a2af7ead18058552997e3a3cd1a3b2210c9e6b4c",
        "bytes": 205803670,
    },
}


def prepare_restoration_models(root: Path):
    folder = root / "restoration"
    folder.mkdir(parents=True, exist_ok=True)
    for name, spec in RESTORATION_SPECS.items():
        target = folder / name
        if target.is_file() and sha256(target) == spec["sha256"]:
            continue
        print(f"下載局部修補模型：{name} ({spec['bytes'] / 1_000_000:.1f} MB)", flush=True)
        fd, temporary = tempfile.mkstemp(prefix=name, suffix=".download", dir=folder)
        os.close(fd)
        try:
            with urllib.request.urlopen(spec["url"], timeout=60) as response, open(temporary, "wb") as stream:
                while chunk := response.read(1024 * 1024):
                    stream.write(chunk)
            if sha256(Path(temporary)) != spec["sha256"]:
                raise ModelError(f"模型雜湊不符：{name}")
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    atomic_json(folder / "manifest.json", {"schema": 1, "specs": RESTORATION_SPECS})


def verify_restoration_models(root: Path):
    import json
    folder = root / "restoration"
    try:
        manifest = json.loads((folder / "manifest.json").read_text())
        if manifest != {"schema": 1, "specs": RESTORATION_SPECS}:
            raise ValueError("manifest mismatch")
        for name, spec in RESTORATION_SPECS.items():
            if sha256(folder / name) != spec["sha256"]:
                raise ValueError(f"checksum mismatch: {name}")
    except (OSError, ValueError) as error:
        raise ModelError("局部修補模型缺失或損壞；請執行 offline.py prepare-restoration。") from error
    return {"version": RESTORATION_VERSION,
            "files": {name: spec["sha256"] for name, spec in RESTORATION_SPECS.items()}}


def encode_mask(mask):
    """Tight crop + runs of true pixels; masks stay editable without model calls."""
    ys, xs = np.where(mask)
    if not len(xs):
        return {"box": [0, 0, 0, 0], "runs": []}
    x1, y1, x2, y2 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    flat = mask[y1:y2, x1:x2].astype(np.uint8).ravel()
    edges = np.diff(np.pad(flat.astype(np.int8), (1, 1)))
    starts, ends = np.where(edges == 1)[0], np.where(edges == -1)[0]
    return {"box": [x1, y1, x2, y2], "runs": [[int(s), int(e - s)] for s, e in zip(starts, ends)]}


def decode_mask(encoded, shape):
    h, w = shape
    x1, y1, x2, y2 = encoded["box"]
    if not all(isinstance(v, int) for v in encoded["box"]) or not (0 <= x1 <= x2 <= w and 0 <= y1 <= y2 <= h):
        raise ValueError("遮罩座標超出圖片")
    mask = np.zeros(shape, dtype=bool)
    flat = np.zeros((y2 - y1) * (x2 - x1), dtype=bool)
    for start, length in encoded["runs"]:
        if not isinstance(start, int) or not isinstance(length, int) or not (0 <= start <= start + length <= len(flat)):
            raise ValueError("遮罩資料不合法")
        flat[start:start + length] = True
    mask[y1:y2, x1:x2] = flat.reshape(y2 - y1, x2 - x1)
    return mask


class RestorationModels:
    def __init__(self, root):
        self.fingerprint = verify_restoration_models(root)
        self.root = Path(root) / "restoration"
        self.detector = self.lama = None

    def detect(self, image):
        """CTD ONNX: RGB [0,1], top-left letterbox, YOLO blocks + segmentation."""
        rgb = np.asarray(image.convert("RGB"))
        h, w = rgb.shape[:2]
        ratio = 1024 / max(h, w)
        rw, rh = max(1, round(w * ratio)), max(1, round(h * ratio))
        canvas = np.full((1024, 1024, 3), 114, dtype=np.uint8)
        canvas[:rh, :rw] = cv2.resize(rgb, (rw, rh))
        try:
            if self.detector is None:
                self.detector = cv2.dnn.readNetFromONNX(str(self.root / "comictextdetector.pt.onnx"))
            self.detector.setInput(cv2.dnn.blobFromImage(canvas, 1 / 255.0))
            outputs = self.detector.forward(self.detector.getUnconnectedOutLayersNames())
            # Resolve by shape: output ordering differs between OpenCV releases.
            blocks = next(o[0] for o in outputs if o.ndim == 3)
            segmentation = next(o[0, 0] for o in outputs if o.ndim == 4 and o.shape[1] == 1)
            line_probability = next(o[0, 0] for o in outputs if o.ndim == 4 and o.shape[1] == 2)
        except Exception as error:
            raise ModelError(f"漫畫文字分割模型執行失敗：{error}") from error
        confidence = blocks[:, 4] * blocks[:, 5:].max(axis=1)
        chosen = blocks[confidence >= .4]
        scores = confidence[confidence >= .4]
        boxes = chosen[:, :4].copy()
        boxes[:, :2] -= boxes[:, 2:] / 2
        indices = np.asarray(cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), .4, .35)).ravel()
        detections = []
        for i in indices:
            x, y, bw, bh = boxes[i]
            x1, x2 = np.clip(np.rint(np.array([x, x + bw]) * w / rw), 0, w).astype(int)
            y1, y2 = np.clip(np.rint(np.array([y, y + bh]) * h / rh), 0, h).astype(int)
            if x2 - x1 >= 3 and y2 - y1 >= 3:
                detections.append((np.array([[x1, y1], [x2 - 1, y1], [x2 - 1, y2 - 1], [x1, y2 - 1]]), float(scores[i])))
        probability = cv2.resize(segmentation[:rh, :rw], (w, h))
        line_map = cv2.resize(line_probability[:rh, :rw], (w, h))
        contours, _ = cv2.findContours((line_map > .3).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        line_boxes = [cv2.boundingRect(c) for c in contours if cv2.contourArea(c) >= 6]
        # The block head can miss an entire balloon even when the line and
        # character heads detect it. Recover elongated, well-supported lines.
        for x, y, lw, lh in line_boxes:
            if min(lw, lh) < 3 or max(lw, lh) < max(12, min(lw, lh) * 1.5):
                continue
            if any(poly[:, 0].min() <= x + lw / 2 <= poly[:, 0].max()
                   and poly[:, 1].min() <= y + lh / 2 <= poly[:, 1].max() for poly, _ in detections):
                continue
            line_score = float(line_map[y:y + lh, x:x + lw].mean())
            if line_score < .55 or (probability[y:y + lh, x:x + lw] >= .5).sum() < 12:
                continue
            pad = max(2, round(min(lw, lh) * .2))
            x1, y1, x2, y2 = max(0, x - pad), max(0, y - pad), min(w - 1, x + lw + pad), min(h - 1, y + lh + pad)
            detections.append((np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]]), line_score))
        # Restrict the learned mask to detected text blocks and a small margin.
        support = np.zeros((h, w), np.uint8)
        for poly, _ in detections:
            cv2.fillPoly(support, [poly], 1)
        radius = max(1, round(min(w, h) / 900))
        kernel = np.ones((radius * 2 + 1,) * 2, np.uint8)
        support = cv2.dilate(support, kernel)
        mask = cv2.dilate((probability >= .5).astype(np.uint8), kernel) & support
        # Protect long ruling lines before balloon analysis. Dilation must not
        # turn a nearby panel border into part of the character mask.
        ink = (cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY) < 160).astype(np.uint8)
        line_length = max(25, round(min(w, h) * .045))
        horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, line_length), np.uint8))
        vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((line_length, 1), np.uint8))
        protected = cv2.dilate(horizontal | vertical, np.ones((3, 3), np.uint8))
        mask &= 1 - protected
        return detections, mask.astype(bool), line_boxes

    def inpaint(self, image, mask):
        """Use a bounded crop for inference, then copy ONLY masked pixels back."""
        import torch
        rgb = np.asarray(image).copy()
        if mask.shape != rgb.shape[:2] or not np.any(mask):
            raise ValueError("修補遮罩為空或尺寸不符")
        ys, xs = np.where(mask)
        margin = max(32, round(max(np.ptp(xs), np.ptp(ys)) * .25))
        x1, y1 = max(0, int(xs.min()) - margin), max(0, int(ys.min()) - margin)
        x2, y2 = min(rgb.shape[1], int(xs.max()) + margin + 1), min(rgb.shape[0], int(ys.max()) + margin + 1)
        crop, hole = rgb[y1:y2, x1:x2], mask[y1:y2, x1:x2]
        h, w = crop.shape[:2]
        scale = min(1, 768 / max(h, w))
        rw, rh = max(1, round(w * scale)), max(1, round(h * scale))
        resized = cv2.resize(crop, (rw, rh))
        resized_mask = cv2.resize(hole.astype(np.float32), (rw, rh), interpolation=cv2.INTER_AREA) > 0
        ph, pw = (-rh) % 8, (-rw) % 8
        pixels = np.pad(resized, ((0, ph), (0, pw), (0, 0)), mode="symmetric")
        holes = np.pad(resized_mask, ((0, ph), (0, pw)), mode="symmetric")
        try:
            if self.lama is None:
                self.lama = torch.jit.load(str(self.root / "big-lama.pt"), map_location="cpu").eval()
            with torch.inference_mode():
                prediction = self.lama(torch.from_numpy(pixels.transpose(2, 0, 1).copy()).float()[None] / 255,
                                       torch.from_numpy(holes.copy()).float()[None, None])
            filled = prediction[0].permute(1, 2, 0).cpu().numpy()[:rh, :rw]
            if not np.isfinite(filled).all():
                raise ValueError("LaMa 回傳非有限像素")
            filled = cv2.resize(np.clip(np.rint(filled * 255), 0, 255).astype(np.uint8), (w, h))
        except Exception as error:
            raise ModelError(f"局部修補模型執行失敗：{error}") from error
        rgb[y1:y2, x1:x2][hole] = filled[hole]
        return Image.fromarray(rgb)
