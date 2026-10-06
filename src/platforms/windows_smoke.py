"""Opt-in portable-build check using synthetic artwork and no cloud requests."""
from pathlib import Path
import json
import sys
import threading
import traceback
import time


class LocalTestTranslator:
    fingerprint = {"provider": "portable-local-test"}
    last_metadata = {}

    def translate(self, records, glossary):
        return {record["id"]: "你好！" for record in records}


def _pipeline(models, choice):
    from .windows import create_local_pipeline
    from PIL import Image
    pipeline = create_local_pipeline(models, translator=LocalTestTranslator())
    # Enhanced detection tolerates optional Paddle failures; explicitly test it.
    with Image.open(choice) as image:
        assert pipeline.models.detect(image.convert("RGB")), "Paddle detection returned no text"
    return pipeline


class SlowTestPipeline:
    fingerprint = {"provider": "portable-cancel-test"}

    def __init__(self, models, choice):
        pass

    def process(self, source, glossary, progress):
        progress("waiting-for-stop")
        time.sleep(60)


def main(arguments):
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path, help="New directory for synthetic diagnostics")
    args = parser.parse_args(arguments)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {"frozen": bool(getattr(sys, "frozen", False)), "checks": []}
    try:
        from src.runtime_paths import app_root
        from src.offline.models import verify_models
        from src.offline.restoration import verify_restoration_models, RestorationModels
        from src.offline.fonts import BUNDLED_FONTS, BUNDLED_FONT, BUNDLED_FONT_SHA256
        from src.offline.storage import sha256
        from PIL import Image, ImageDraw, ImageFont
        import numpy as np
        models = app_root() / "models"
        verify_models(models)
        verify_restoration_models(models)
        assert sha256(BUNDLED_FONTS / BUNDLED_FONT) == BUNDLED_FONT_SHA256
        result["checks"].append("model-and-font-checksums")

        import tkinter as tk
        from tkinterdnd2 import TkinterDnD
        from src.gui.app import OfflineGUI
        from src.gui import app, settings
        from .windows import enable_dpi_awareness
        from src.offline.model_catalog import ModelCatalog
        # Do not read saved batches or query the installed translation accounts.
        app.STATE_ROOT = output / "state"
        settings.list_models = lambda provider: ModelCatalog([("local-test", "local-test")], {})
        enable_dpi_awareness()
        root = TkinterDnD.Tk()
        root.withdraw()
        gui = OfflineGUI(root)
        root.update()
        assert gui.source_list.winfo_exists()
        assert gui.provider_box.winfo_exists()
        root.destroy()
        result["checks"].append("tk-gui-icon-and-drag-drop")

        image = Image.new("RGB", (640, 800), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 20, 620, 780), outline="black", width=4)
        draw.ellipse((90, 90, 550, 420), outline="black", width=3)
        font = ImageFont.truetype(str(BUNDLED_FONTS / BUNDLED_FONT), 52)
        draw.text((160, 180), "こんにちは", font=font, fill="black")
        draw.text((160, 260), "ありがとう", font=font, fill="black")
        source = output / "synthetic.png"
        image.save(source)
        stages = []
        from .windows_worker import WindowsPipeline
        pipeline = WindowsPipeline(models, source, threading.Event(), factory=_pipeline)
        try:
            translated, report, mask = pipeline.process(source, {}, stages.append)
            assert report["translated"] >= 1, "Synthetic text was not rendered"
            translated.save(output / "translated.png")
            mask.save(output / "mask.png")
            (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        finally:
            pipeline.close()
        result["checks"].append("spawn-paddle-manga-ocr-and-lettering")
        result["stages"] = stages

        # Exercise the TorchScript repair DLLs even if the white balloon did not need them.
        restorer = RestorationModels(models)
        repair_mask = np.zeros((64, 64), dtype=bool)
        repair_mask[25:35, 25:35] = True
        restorer.inpaint(Image.new("RGB", (64, 64), "gray"), repair_mask)
        result["checks"].append("lama-inpainting")

        from src.offline.cancellation import OperationCancelled
        stop = threading.Event()
        pipeline = WindowsPipeline(models, None, stop, factory=SlowTestPipeline)
        try:
            started = []
            def cancel(stage):
                started.append(time.monotonic())
                stop.set()
            try:
                pipeline.process(source, {}, cancel)
                raise AssertionError("Stop did not interrupt the worker")
            except OperationCancelled:
                assert started and time.monotonic() - started[0] < 3
                assert not pipeline.process_handle.is_alive()
        finally:
            pipeline.close()
        result["checks"].append("frozen-worker-immediate-stop")

        import os
        import subprocess
        from src.offline.cli_common import popen_cli
        process = popen_cli([str(Path(os.environ["WINDIR"]) / "System32/cmd.exe"),
                             "/c", "echo portable-ok"], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, env=dict(os.environ))
        stdout, _ = process.communicate(timeout=10)
        assert process.returncode == 0 and stdout.strip() == "portable-ok"
        result["checks"].append("external-program-dll-isolation")
        if result["frozen"]:
            from src.runtime_paths import offline_command
            assert subprocess.run(offline_command("--help"), timeout=20,
                                  creationflags=subprocess.CREATE_NO_WINDOW).returncode == 0
            result["checks"].append("bundled-download-cli-entry")
        result["ok"] = True
    except Exception:
        result["ok"] = False
        result["error"] = traceback.format_exc()
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    raise SystemExit(0 if result["ok"] else 1)
