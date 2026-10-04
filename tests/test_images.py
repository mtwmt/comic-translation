import pytest
from PIL import Image

from src.offline import images
from src.offline.review import load_source
from src.offline.storage import sha256


@pytest.mark.parametrize("mode", ["RGBA", "LA", "P"])
def test_translation_and_revision_reject_transparency(tmp_path, mode):
    source = tmp_path / "source.png"
    image = Image.new(mode, (10, 20))
    if mode == "P":
        image.info["transparency"] = 0
    image.save(source)
    report = {"source": str(source), "source_hash": sha256(source), "image_size": [10, 20]}
    for load in (lambda: images.load_image(source), lambda: load_source(report)):
        with pytest.raises(ValueError, match="透明"):
            load()


def test_opaque_rgba_and_exif_orientation_have_one_revision_policy(tmp_path):
    source = tmp_path / "opaque.png"
    Image.new("RGBA", (10, 20), (12, 34, 56, 255)).save(source)
    assert images.load_image(source).getpixel((0, 0)) == (12, 34, 56)
    source = tmp_path / "rotated.jpg"
    exif = Image.Exif()
    exif[274] = 6
    Image.new("RGB", (10, 20), "white").save(source, exif=exif)
    report = {"source": str(source), "source_hash": sha256(source), "image_size": [20, 10]}
    assert images.load_image(source).size == load_source(report).size == (20, 10)
    report["image_size"] = [10, 20]
    with pytest.raises(ValueError, match="尺寸"):
        load_source(report)


def test_pixel_limit_is_shared_with_revision(tmp_path, monkeypatch):
    source = tmp_path / "source.png"
    Image.new("RGB", (10, 20)).save(source)
    monkeypatch.setattr(images, "MAX_PIXELS", 199)
    report = {"source": str(source), "source_hash": sha256(source), "image_size": [10, 20]}
    for load in (lambda: images.load_image(source), lambda: load_source(report)):
        with pytest.raises(ValueError, match="像素限制"):
            load()
