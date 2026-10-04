"""One source-image policy for translation and local revision."""
from pathlib import Path

from PIL import Image, ImageOps

MAX_PIXELS = 40_000_000


def load_image(source: Path) -> Image.Image:
    with Image.open(source) as decoded:
        if decoded.width * decoded.height > MAX_PIXELS:
            raise ValueError("圖片超過原型版 4,000 萬像素限制")
        if decoded.mode in ("RGBA", "LA") or "transparency" in decoded.info:
            if decoded.convert("RGBA").getchannel("A").getextrema() != (255, 255):
                raise ValueError("原型版尚不處理透明圖片，避免破壞透明度")
        return ImageOps.exif_transpose(decoded).convert("RGB")
