"""Windows x64 folder bundle. Models are copied separately after verification."""
from pathlib import Path
from importlib import metadata
import os
from PyInstaller.utils.hooks import collect_all, copy_metadata

root = Path(SPECPATH).parents[1]
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
os.environ.setdefault("PROCESSOR_ARCHITECTURE", "AMD64")
datas = [(str(root / "assets" / "icons" / "comic-translator-v2.ico"), "assets/icons"),
         (str(root / "assets" / "fonts"), "assets/fonts")]
binaries = []
hiddenimports = ["offline", "src.platforms.windows_smoke", "src.platforms.windows_bundle"]
# These libraries load modules and model configs dynamically, beyond import analysis.
for package in ("paddle", "paddleocr", "paddlex", "manga_ocr", "transformers",
                "fugashi", "unidic_lite", "jieba", "opencc", "tkinterdnd2"):
    data, binary, hidden = collect_all(package)
    datas += data
    binaries += binary
    hiddenimports += hidden
# PaddleX checks distribution metadata even for importable modules (e.g. pyclipper).
# Match the runtime environment instead of presenting installed libraries as missing.
build_only = {"pyinstaller", "pyinstaller-hooks-contrib", "altgraph", "pefile", "pywin32-ctypes",
              "pytest", "iniconfig", "pluggy", "pygments"}
for distribution in metadata.distributions():
    name = distribution.metadata["Name"]
    if name.lower() not in build_only:
        datas += copy_metadata(name)

a = Analysis([str(root / "offline_gui.py")], pathex=[str(root)], binaries=binaries,
             datas=datas, hiddenimports=hiddenimports,
             runtime_hooks=[str(root / "tools/packaging/runtime_hook.py")],
             excludes=["pytest", "IPython", "notebook", "tensorflow", "jax", "jaxlib"],
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ComicTranslator",
          debug=False, strip=False, upx=False, console=False,
          icon=str(root / "assets/icons/comic-translator-v2.ico"),
          version=str(root / "tools/packaging/version_info.txt"))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ComicTranslator")
