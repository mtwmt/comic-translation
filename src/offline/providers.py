from __future__ import annotations

import os
from pathlib import Path

from .models import ModelError


class LocalModels:
    """Lazy local-only adapters; one instance is reused across a batch."""
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.detector = self.ocr = None
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        os.environ["PADDLE_PDX_CACHE_HOME"] = str(self.root.parent / ".cache" / "paddlex")

    def detect(self, image, **options):
        import numpy as np
        if self.detector is None:
            try:
                from paddleocr import TextDetection
                self.detector = TextDetection(model_name="PP-OCRv5_mobile_det",
                                              model_dir=str(self.root / "detector"),
                                              device="cpu", enable_mkldnn=False)
            except Exception as error:
                raise ModelError(f"文字偵測模型載入失敗：{error}") from error
        result = next(iter(self.detector.predict(np.array(image)[:, :, ::-1],
                                                 limit_side_len=1536, limit_type="max", **options)))
        return [(np.asarray(poly).astype(int), float(score))
                for poly, score in zip(result["dt_polys"], result["dt_scores"])]

    def recognize(self, image):
        if self.ocr is None:
            try:
                from manga_ocr import MangaOcr
                self.ocr = MangaOcr(str(self.root / "ocr"), force_cpu=True)
            except Exception as error:
                raise ModelError(f"日文 OCR 載入失敗：{error}") from error
        return self.ocr(image)
