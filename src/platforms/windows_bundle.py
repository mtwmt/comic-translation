"""Keep bundled DLL search paths out of externally installed translation CLIs."""
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import threading

_launch_lock = threading.Lock()


def popen_external(command, **kwargs):
    environment = dict(kwargs.get("env", os.environ))
    bundle = Path(sys._MEIPASS).resolve()
    environment["PATH"] = os.pathsep.join(
        entry for entry in environment.get("PATH", "").split(os.pathsep)
        if entry and not Path(entry).resolve().is_relative_to(bundle))
    kwargs["env"] = environment
    kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
    # SetDllDirectory is process-wide; restore it immediately after CreateProcess.
    with _launch_lock:
        kernel = ctypes.windll.kernel32
        size = kernel.GetDllDirectoryW(0, None)
        previous = ctypes.create_unicode_buffer(size + 1)
        kernel.GetDllDirectoryW(len(previous), previous)
        kernel.SetDllDirectoryW(None)
        try:
            return subprocess.Popen(command, **kwargs)
        finally:
            kernel.SetDllDirectoryW(previous.value or None)
