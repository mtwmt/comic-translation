"""Original macOS/POSIX behavior, independent of Windows compatibility fixes."""
from __future__ import annotations

import os
import signal
from contextlib import contextmanager

IGNORE_TEMPORARY_CLEANUP_ERRORS = False
START_NEW_SESSION = True
CACHE_MODEL_CATALOG = False
DELETE_DETECTED_REGIONS = False
SCROLL_REVIEW_REGIONS = False
TRANSLATION_OPTIONS = False
STOP_MESSAGE = "停止中：等待目前頁面安全保存，不會開始下一頁。"


def configure_translator_controls(gui):
    """Keep the native macOS control geometry and entry click behavior."""


def configure_output_row(gui):
    """Keep the existing macOS output row geometry."""


def configure_app_icon(root):
    """macOS uses the .icns configured by the future application bundle."""


def find_installed_cli(name):
    """Keep the existing PATH-only lookup on macOS/POSIX."""
    return None


def query_agy_configuration(run, arguments):
    return run(arguments, 45)


def agy_call_label(arguments, timeout):
    return "AGY"


def create_pipeline(models, choice, stop_event):
    from src.offline.pipeline import TranslationPipeline
    from src.offline.translators import create_translator
    return TranslationPipeline(models, translator=create_translator(*choice))


def finish_pipeline(pipeline):
    return pipeline


def create_local_pipeline(models, translator=None):
    from src.offline.pipeline import TranslationPipeline
    return TranslationPipeline(models, translator=translator)


def load_onnx_model(path):
    import cv2
    return cv2.dnn.readNetFromONNX(str(path))


def load_repair_model(path):
    import torch
    return torch.jit.load(str(path), map_location="cpu").eval()


@contextmanager
def detector_context(path):
    yield str(path)


def enable_dpi_awareness():
    """Tk and macOS manage display scaling without Windows API calls."""


def window_scale(root):
    return 1.0


@contextmanager
def cli_input(process, text):
    """Use the original synchronous POSIX communicate() input path."""
    yield text


def terminate(process):
    kill_process_tree(process.pid)
    process.communicate()


def kill_process_tree(pid):
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def capture_selection(row_ids, row_keys):
    return set(row_ids)


def restore_selection(selected, row_keys):
    return [iid for iid in row_keys if iid in selected]


def after_submit(source_list):
    if hasattr(source_list, "selection_remove"):
        source_list.selection_remove(source_list.selection())
