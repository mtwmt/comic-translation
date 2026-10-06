"""Build a portable Windows x64 ZIP without copying any user state or artwork."""
from pathlib import Path
from importlib import metadata
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# The Lite ZIP swaps this step of docs/USER_GUIDE.txt for the download instructions.
FULL_MODELS_STEP = "完整版已內附這些檔案，這個步驟可以直接跳過。"
LITE_MODELS_STEP = ("1. 按視窗左下的「下載／檢查所需檔案…」，再按「是」。\n"
                    "2. 等待下載完成（約 750 MB，時間依網路速度而定），\n"
                    "   下方出現「翻譯所需檔案已就緒，可以加入圖片。」就代表完成。\n"
                    "\n"
                    "這些檔案只需要下載一次，之後會留在程式資料夾的 models 裡。")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-build", action="store_true", help="Package an already built dist folder")
    parser.add_argument("--without-models", action="store_true",
                        help="Create a smaller ZIP; users download models through the GUI on first use")
    args = parser.parse_args()
    if sys.platform != "win32" or sys.version_info[:2] != (3, 11):
        parser.error("Build with Windows x64 Python 3.11 and requirements-build.txt")
    from src.offline.models import verify_models
    from src.offline.restoration import verify_restoration_models
    from src.offline.fonts import ensure_bundled_font
    if not args.without_models:
        verify_models(ROOT / "models")
        verify_restoration_models(ROOT / "models")
    ensure_bundled_font()
    folder = ROOT / "dist/ComicTranslator"
    for name in (".comic-translator", ".cache", "translated", "input", "output"):
        if (folder / name).exists():
            raise RuntimeError(f"Build folder contains runtime/user data: {name}. Move it out before rebuilding.")
    if not args.skip_build:
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm",
                        str(ROOT / "tools/packaging/windows.spec")], cwd=ROOT, check=True)
    if not (folder / "ComicTranslator.exe").is_file():
        raise RuntimeError("Build the executable first")
    # Release contents are explicitly selected, never the checkout or home folder.
    if not args.without_models:
        shutil.copytree(ROOT / "models", folder / "models", dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns(".cache", "*.lock", "*.part", "*.download"))
    guide = (ROOT / "docs/USER_GUIDE.txt").read_text(encoding="utf-8")
    if FULL_MODELS_STEP not in guide:
        raise RuntimeError("docs/USER_GUIDE.txt no longer contains the bundled-models step")
    # Windows Notepad needs CRLF and a BOM to show this reliably on older builds.
    (folder / "使用說明.txt").write_text(guide, encoding="utf-8-sig", newline="\r\n")
    licenses = folder / "licenses"
    licenses.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "assets/fonts/OFL.txt", licenses / "Noto-OFL.txt")
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        shutil.copy2(python_license, licenses / "Python-LICENSE.txt")
    dependencies = []
    for distribution in metadata.distributions():
        name = distribution.metadata["Name"]
        if name.lower() in {"pytest", "pyinstaller-hooks-contrib", "altgraph", "pefile", "pywin32-ctypes"}:
            continue
        dependencies.append({"name": name, "version": distribution.version,
                             "license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License", ""),
                             "project_urls": distribution.metadata.get_all("Project-URL", [])})
        for entry in distribution.files or []:
            if entry.name.lower().startswith(("license", "copying", "notice")):
                path = Path(distribution.locate_file(entry))
                if path.is_file():
                    target = licenses / name / str(entry).replace("../", "")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
    (licenses / "dependencies.json").write_text(json.dumps(dependencies, indent=2, ensure_ascii=False), encoding="utf-8")
    (licenses / "model-sources.txt").write_text(
        "Detector: https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_det\n"
        "Manga OCR: https://huggingface.co/kha-white/manga-ocr-base\n"
        "CTD: https://github.com/zyddnys/comic-text-detector\n"
        "LaMa: https://github.com/advimman/lama\n"
        "Model revisions and hashes are recorded in models/manifest-vision.json and models/restoration/manifest.json.\n",
        encoding="utf-8")
    if not args.without_models:
        verify_models(folder / "models")
        verify_restoration_models(folder / "models")
    # Reject user data accidentally left by smoke tests before releasing.
    for name in (".comic-translator", ".cache", "translated", "input", "output"):
        if (folder / name).exists():
            raise RuntimeError(f"Release folder contains runtime/user data: {name}. Move diagnostics out before packaging.")
    suffix = "-Lite" if args.without_models else ""
    archive = ROOT / f"dist/ComicTranslator-Windows-x64{suffix}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as out:
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                if args.without_models and path.relative_to(folder).parts[0] == "models":
                    continue
                if args.without_models and path.name == "使用說明.txt" and path.parent == folder:
                    instructions = guide.replace(FULL_MODELS_STEP, LITE_MODELS_STEP).replace("\n", "\r\n")
                    out.writestr(path.relative_to(folder.parent).as_posix(), instructions.encode("utf-8-sig"))
                    continue
                out.write(path, path.relative_to(folder.parent).as_posix())
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"Portable ZIP: {archive} ({archive.stat().st_size / 1024**3:.2f} GiB)")


if __name__ == "__main__":
    main()
