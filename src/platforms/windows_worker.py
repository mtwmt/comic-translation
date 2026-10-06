"""Windows GUI pipeline in a killable child; the parent alone commits results."""
from __future__ import annotations

import multiprocessing
import queue
import threading

from src.offline.cancellation import OperationCancelled
from src.offline.models import ModelError
from .windows import kill_process_tree


def _create_pipeline(models, choice):
    from .windows import create_local_pipeline
    from src.offline.translators import create_translator
    return create_local_pipeline(models, translator=create_translator(*choice))


def _serve(connection, factory, arguments):
    try:
        pipeline = factory(*arguments)
        connection.send(("ready", pipeline.fingerprint))
        while True:
            request = connection.recv()
            if request is None:
                return
            source, glossary = request
            try:
                result = pipeline.process(source, glossary,
                    lambda stage: connection.send(("stage", stage)))
                connection.send(("result", result))
            except Exception as error:
                connection.send(("error", error))
    except EOFError:
        pass
    except Exception as error:
        connection.send(("error", error))
    finally:
        connection.close()


class WindowsPipeline:
    """Reuse loaded models within a run; stop kills OCR and descendant CLIs."""
    def __init__(self, models, choice, stop_event, *, factory=_create_pipeline):
        self.stop_event = stop_event
        self.messages = queue.Queue()
        context = multiprocessing.get_context("spawn")
        self.connection, child = context.Pipe()
        self.process_handle = context.Process(target=_serve, args=(child, factory, (models, choice)))
        self.process_handle.start()
        child.close()

        def read():
            try:
                while True:
                    self.messages.put(self.connection.recv())
            except (EOFError, OSError):
                self.messages.put(("exit", None))

        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()
        try:
            self.fingerprint = self._receive("ready")
        except BaseException:
            self.close()
            raise

    def check_cancel(self):
        if self.stop_event.is_set():
            self.close()
            raise OperationCancelled("使用者已停止；未完成圖片可繼續翻譯。")

    def _receive(self, expected, progress=lambda stage: None):
        while True:
            self.check_cancel()
            try:
                kind, value = self.messages.get(timeout=0.05)
            except queue.Empty:
                continue
            if kind == "stage":
                progress(value)
            elif kind == "error":
                raise value
            elif kind == expected:
                self.check_cancel()
                return value
            elif kind == "exit":
                raise ModelError("Windows 圖片處理程序提前結束；已保留批次，可重新開始。")

    def process(self, source, glossary, progress):
        self.check_cancel()
        try:
            self.connection.send((source, glossary))
        except (EOFError, OSError) as error:
            raise ModelError("Windows 圖片處理程序已結束；請重新開始。") from error
        return self._receive("result", progress)

    def close(self):
        process = self.process_handle
        if process.is_alive():
            # Force-stop before the parent commits a PNG/report. The child
            # never writes outputs, so killing it cannot leave a half PNG.
            kill_process_tree(process.pid)
            process.kill()
        process.join(timeout=5)
        self.reader.join(timeout=1)
        self.connection.close()
