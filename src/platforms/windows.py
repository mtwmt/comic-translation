"""Windows-only DPI, process pipes, file locks, paths and checkbox retention."""
from __future__ import annotations

import subprocess
import threading
from contextlib import contextmanager

IGNORE_TEMPORARY_CLEANUP_ERRORS = True
START_NEW_SESSION = False
CACHE_MODEL_CATALOG = True
DELETE_DETECTED_REGIONS = True
SCROLL_REVIEW_REGIONS = True
TRANSLATION_OPTIONS = True
STOP_MESSAGE = "停止中：正在終止目前處理，保留已完成結果；未完成圖片可續跑。"
_detector_lock = threading.Lock()


def configure_translator_controls(gui):
    from .windows_widgets import configure_translator_controls as configure
    configure(gui)


def configure_output_row(gui):
    for control in (gui.output_entry, gui.choose_output_button, gui.reset_output_button):
        control.grid_configure(sticky="nsew")


def configure_app_icon(root):
    import ctypes
    from pathlib import Path
    from tkinter import TclError

    icon = Path(__file__).resolve().parents[2] / "assets" / "icons" / "comic-translator-v2.ico"
    if not icon.is_file():
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("ComicTranslation.Desktop")
        root.iconbitmap(default=str(icon))
        root.iconbitmap(str(icon))
        from .windows_icon import apply_dpi_icons
        root.after_idle(lambda: apply_dpi_icons(root, icon))
    except (AttributeError, OSError, TclError):
        pass


def find_installed_cli(name):
    from .windows_cli import find_installed_cli as find
    return find(name)


def query_agy_configuration(run, arguments):
    from .windows_agy import query_configuration
    return query_configuration(run, arguments)


def agy_call_label(arguments, timeout):
    from .windows_agy import call_label
    return call_label(arguments, timeout)


def create_pipeline(models, choice, stop_event):
    from .windows_worker import WindowsPipeline
    return WindowsPipeline(models, choice, stop_event)


def create_local_pipeline(models, translator=None):
    from src.offline.pipeline import TranslationPipeline
    from . import windows_layout
    return TranslationPipeline(models, translator=translator, region_layout=windows_layout)


def load_onnx_model(path):
    import cv2
    import numpy as np
    # OpenCV's Windows C++ filename reader cannot open some Unicode paths.
    return cv2.dnn.readNetFromONNX(np.frombuffer(path.read_bytes(), dtype=np.uint8))


def load_repair_model(path):
    import torch
    # A Python file object bypasses TorchScript's narrow Windows filename reader.
    with path.open("rb") as stream:
        return torch.jit.load(stream, map_location="cpu").eval()


@contextmanager
def detector_context(path):
    import os
    from pathlib import Path
    if str(path).isascii():
        yield str(path)
        return
    # Paddle's PIR reader also uses narrow C++ filenames. Relative ASCII names
    # work from a Unicode Windows cwd. Keep lazy prediction inside this scope.
    with _detector_lock:
        previous = Path.cwd()
        os.chdir(path)
        try:
            yield "."
        finally:
            os.chdir(previous)


def finish_pipeline(pipeline):
    from .windows_worker import WindowsPipeline
    if isinstance(pipeline, WindowsPipeline):
        pipeline.close()
        return None
    return pipeline


def enable_dpi_awareness():
    """Run before creating Tk windows to avoid bitmap enlargement."""
    import ctypes

    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        try:
            set_context = user32.SetProcessDpiAwarenessContext
            set_context.argtypes = [ctypes.c_void_p]
            set_context.restype = ctypes.c_int
            # Tk 8.6 uses startup system DPI, not per-monitor resizing.
            if set_context(ctypes.c_void_p(-2)) or ctypes.get_last_error() == 5:
                return  # A caller or manifest may have already set the DPI mode.
        except AttributeError:
            pass
        set_aware = user32.SetProcessDPIAware
        set_aware.argtypes = []
        set_aware.restype = ctypes.c_int
        set_aware()
    except (AttributeError, OSError):
        pass


def window_scale(root):
    return max(1.0, root.winfo_fpixels("1i") / 96.0)


@contextmanager
def cli_input(process, text):
    """Keep a blocked stdin write from preventing communicate() timeouts."""
    if text is None:
        yield None
        return
    stream = process.stdin
    stream.reconfigure(newline="")  # Preserve LF rather than converting to CRLF.
    process.stdin = None

    def feed_input():
        try:
            with stream:
                stream.write(text)
        except OSError:
            pass  # An exited or terminated CLI can close its pipe early.

    writer = threading.Thread(target=feed_input, daemon=True)
    writer.start()
    try:
        yield None
    finally:
        writer.join(timeout=1)


def terminate(process):
    kill_process_tree(process.pid)
    try:
        process.kill()  # taskkill is best effort; also stop the direct child.
    except OSError:
        pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    # communicate() reader threads own their pipes and close them at EOF.
    # If taskkill failed, a descendant may hold those pipes indefinitely.
    # Neither draining nor closing a pipe locked by a reader is safe here.
    for name in ("stdout", "stderr"):
        stream = getattr(process, name, None)
        reader = getattr(process, name + "_thread", None)
        if stream is not None and (reader is None or not reader.is_alive()):
            try:
                stream.close()
            except OSError:
                pass


def kill_process_tree(pid):
    """Best effort: a slow or missing taskkill must not abort the caller's cleanup."""
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=5,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired):
        pass


def capture_selection(row_ids, row_keys):
    return {row_keys[iid] for iid in row_ids if iid in row_keys}


def restore_selection(selected, row_keys):
    return [iid for iid, key in row_keys.items() if key in selected]


def after_submit(source_list):
    """Keep checks when staged images move into processing/history rows."""
