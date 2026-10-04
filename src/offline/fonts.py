"""Automatic platform lettering fonts, with a bundled Traditional Chinese fallback."""
from pathlib import Path
from dataclasses import dataclass
from functools import lru_cache
import os
import sys

from PIL import ImageFont

from .models import ModelError
from .storage import sha256

BUNDLED_FONTS = Path(__file__).resolve().parents[2] / "assets/fonts"
BUNDLED_FONT = "NotoSansCJKtc-Bold.otf"
# Not stored in git: prepare-models downloads it. Source and licence: assets/fonts/README.txt.
BUNDLED_FONT_URL = "https://github.com/notofonts/noto-cjk/raw/Sans2.004/Sans/OTF/TraditionalChinese/NotoSansCJKtc-Bold.otf"
BUNDLED_FONT_SHA256 = "3ee160e5015106e3ec1a394301df54fa9bbbf8a251519984aec5c0abc50840c0"


@dataclass(frozen=True)
class FontFace:
    path: Path
    index: int = 0


def load_font(face, size):
    if isinstance(face, FontFace):
        return ImageFont.truetype(str(face.path), size, index=face.index)
    return ImageFont.truetype(str(face), size)


def _has_glyph(font, text):
    mask = font.getmask(text)
    if not mask.getbbox():
        return False
    # Some fonts draw a .notdef box instead of returning an empty glyph.
    missing = font.getmask("\uffff")
    return mask.size != missing.size or bytes(mask) != bytes(missing)


@lru_cache(maxsize=32)
def _symbol_fallback(size):
    return load_font(BUNDLED_FONTS / "NotoSansCJKtc-Bold.otf", size)


def lettering_font(primary, text):
    """Keep the chosen face; fill missing glyphs with the bundled CJK font."""
    if _has_glyph(primary, text):
        return primary
    try:
        fallback = _symbol_fallback(primary.size)
    except OSError:
        return primary
    return fallback if _has_glyph(fallback, text) else primary


def system_font_candidates():
    if sys.platform == "darwin":
        paths = [Path("/System/Library/Fonts/PingFang.ttc"),
                 Path("/System/Library/Fonts/Supplemental/PingFang.ttc")]
        paths += sorted(Path("/System/Library/AssetsV2").glob(
            "com_apple_MobileAsset_Font*/*.asset/AssetData/PingFang.ttc"), reverse=True)
        return [(p, "PingFang TC", "Semibold") for p in paths]
    if sys.platform == "win32":
        folder = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        return [(folder / name, "Microsoft JhengHei", "Bold") for name in ("msjhbd.ttc", "msjhbd.ttf")]
    return []


def match_face(path, family, style):
    """TTC face zero may be another language; find the exact family and weight."""
    if not path.is_file():
        return None
    for index in range(64):
        try:
            actual_family, actual_style = ImageFont.truetype(str(path), 32, index=index).getname()
        except (OSError, ValueError):
            break
        if (actual_family, actual_style) == (family, style):
            return path, {"family": family, "style": style, "index": index, "sha256": sha256(path)}
    return None


def resolve_font(models):
    for candidate in system_font_candidates():
        matched = match_face(*candidate)
        if matched:
            return matched
    fallback = BUNDLED_FONTS / "NotoSansCJKtc-Bold.otf"
    matched = match_face(fallback, "Noto Sans CJK TC", "Bold")
    if matched:
        return matched
    raise ModelError("無法載入系統中文字型，且程式內附的 Noto 繁中粗體缺失或損壞。請執行 offline.py prepare-models 下載字型。")


def ensure_bundled_font(destination=None, url=BUNDLED_FONT_URL, expected=BUNDLED_FONT_SHA256):
    """Download the fallback font once; an existing, intact copy is left alone."""
    import tempfile
    import urllib.request
    destination = Path(destination or BUNDLED_FONTS / BUNDLED_FONT)
    if destination.is_file() and sha256(destination) == expected:
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".part", delete=False) as partial:
        temporary = Path(partial.name)
    try:
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as out:
            while chunk := response.read(1 << 20):
                out.write(chunk)
        if sha256(temporary) != expected:
            raise ModelError("下載的字型校驗碼不符，已丟棄；請稍後重試。")
        temporary.replace(destination)
    except OSError as error:
        raise ModelError(f"無法下載內附字型（{error}）；請手動下載並放入 assets/fonts，見該資料夾的 README。") from error
    finally:
        temporary.unlink(missing_ok=True)
    return destination
