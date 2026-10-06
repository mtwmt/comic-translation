from __future__ import annotations

import re
import time
from importlib.metadata import version
from pathlib import Path

from .models import ModelError, verify_models
from .manual_review import ocr_candidates
from .recovery import LOOSE_DETECTION, MIN_RECOVERED_CHARACTERS, is_recovered_region, recover_missed_text
from .storage import sha256
from .images import load_image
from .composition import render_page
from .providers import LocalModels
from .layout import prepare_masked_regions, render_masked_region, plan_page_lettering, LAYOUT_VERSION
from .fonts import resolve_font, FontFace

PIPELINE_VERSION = "comic-prototype-6"


class TranslationPipeline:
    def __init__(self, models: Path, translator=None, *, region_layout=None):
        self.translator = translator
        self.region_layout = region_layout
        model_hash = verify_models(models)
        self.fingerprint = {"pipeline": PIPELINE_VERSION, "models": model_hash,
                            "layout": LAYOUT_VERSION,
                            "dependencies": {name: version(name) for name in (
                                "paddleocr", "paddlepaddle", "manga-ocr", "transformers", "torch",
                                "Pillow", "opencv-contrib-python", "opencc-python-reimplemented", "jieba")}}
        self.fingerprint["translator"] = translator.fingerprint if translator else {"provider": "analysis-only"}
        if region_layout is not None:
            self.fingerprint["region_grouping"] = region_layout.VERSION
        self.models = LocalModels(models)
        if translator is None:
            self.font = None
        else:
            font_path, self.fingerprint["font"] = resolve_font()
            self.font = FontFace(font_path, self.fingerprint["font"].get("index", 0))
        from .restoration import RestorationModels
        self.restorer = RestorationModels(models)
        self.fingerprint["restoration"] = self.restorer.fingerprint

    def process(self, source: Path, glossary: dict, progress=lambda stage: None, analyze_only=False):
        if not analyze_only and self.translator is None:
            raise ValueError("翻譯需要設定翻譯引擎；只做本機辨識請使用 analyze。")
        start = time.monotonic()
        source_hash = sha256(source)
        if not analyze_only and self.translator is not None and hasattr(self.translator, "preflight"):
            progress("檢查所選翻譯引擎的訂閱與設定")
            self.translator.preflight()
        image = load_image(source)
        progress("偵測文字")
        detections, text_mask, line_boxes = self.restorer.detect(image)
        try:
            extra = self.models.detect(image, **LOOSE_DETECTION)
        except ModelError:
            extra = []
        found = len(detections)
        detections, text_mask = recover_missed_text(image, detections, text_mask, extra)
        recovered = [poly for poly, _ in detections[found:]]
        regions, _ = prepare_masked_regions(image, detections, text_mask, line_boxes,
                                            refine=getattr(self.region_layout, "refine_mask", None))
        for region in regions:
            region["recovered"] = any(is_recovered_region(region, poly) for poly in recovered)
        progress("日文辨識")
        records = []
        for region in regions:
            region["protected_terms"] = sorted(set(glossary.values()))
            x1, y1, x2, y2 = region["bbox"]
            crop = image.crop((max(0, x1 - 2), max(0, y1 - 2), min(image.width, x2 + 2), min(image.height, y2 + 2)))
            original = self.models.recognize(crop)
            region["original"] = original
            region["ocr_confidence"] = None
            region["text_status"] = "recognized"
            minimum = MIN_RECOVERED_CHARACTERS if region.get("recovered") else 1
            if not original.strip() or len(original) > 250 or len(re.findall(r"[ぁ-ヺー一-龯]", original)) < minimum:
                if region.get("recovered"):
                    # A gap-filling guess that reads as nothing is not a region:
                    # keeping it would only block the user from boxing it by hand.
                    region["discard"] = True
                    continue
                region.update(status="preserved", reason="OCR 沒有取得可驗證的日文文字")
                continue
            record = {"id": region["id"], "text": original}
            if region.get("recovered"):
                # Display lettering is often misread; other readings let the
                # translator infer the real phrase. Text only, nothing visual.
                alternatives = [t for t in ocr_candidates(image, region, self.models) if t != original][:3]
                if alternatives:
                    region["ocr_primary"], region["ocr_alternatives"] = original, alternatives
                    record["alternatives"] = alternatives
            records.append(record)
        regions = [region for region in regions if not region.get("discard")]
        if self.region_layout is not None:
            self.region_layout.resolve_duplicate_regions(regions)
            active_ids = {region["id"] for region in regions if region.get("enabled", True)}
            records = [record for record in records if record["id"] in active_ids]
        if not analyze_only:
            progress(f"{getattr(self.translator, 'provider', '').upper()} {getattr(self.translator, 'model', '')} 翻譯（僅傳文字）")
        translated = {}
        translation_error = ""
        if records and not analyze_only:
            try:
                translated = self.translator.translate(records, glossary)
            except ValueError as error:
                translation_error = str(error)
        progress("清字與排版")
        for region in regions:
            if region["id"] in translated:
                region["translation"] = translated[region["id"]]
                region["text_status"] = "translated"
        font_plan = None
        if not analyze_only:
            font_plan = plan_page_lettering(image, regions, self.font)

        def render(region):
            return render_masked_region(image, region, self.font, self.restorer)

        rendered, summary, mask = render_page(image, regions, render,
            missing_reason="尚未翻譯，可在預覽填寫譯文" if analyze_only else translation_error or "缺少譯文")
        if sha256(source) != source_hash:
            raise ValueError("處理期間來源檔案有變更，結果未保存")
        count = summary["translated"]
        report = {**summary,
                  "mode": "analysis" if analyze_only else "translation",
                  "text_translated": len(translated),
                  "glossary": dict(glossary), "font_plan": font_plan,
                  "source": str(source.resolve()), "source_hash": source_hash,
                  "image_size": list(image.size),
                  "regions": regions, "elapsed_seconds": round(time.monotonic() - start, 2),
                  "fingerprint": self.fingerprint,
                  "warnings": ["原型：文字偵測、分組、翻譯語意與局部修補仍須人工驗收。"],
                  "reason": "" if count else "沒有可安全完成翻譯的區域；不輸出原圖副本冒充譯圖"}
        if self.translator is not None:
            report["translator_metadata"] = getattr(self.translator, "last_metadata", {}) if records else {}
        return rendered if count else None, report, mask
