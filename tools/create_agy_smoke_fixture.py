"""Create an original Japanese test image locally, not a user manga upload."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def main():
    root = Path(__file__).resolve().parents[1]
    target = root / "offline-runs/agy-smoke/source-columns.png"
    if target.exists():
        raise SystemExit("Fixture already exists; preserving it.")
    image = Image.new("RGB", (760, 560), (140, 140, 140))
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(root / "assets/fonts/NotoSansCJKtc-Bold.otf"), 30)
    for x, text in [(70, "ここで待たなくてもいい。"), (430, "ここで待ってはいけない。")]:
        draw.rounded_rectangle((x, 80, x + 200, 390), radius=50, fill="white", outline="black", width=4)
        for i, char in enumerate(text):
            draw.text((x + 130 - (i // 7) * 45, 125 + (i % 7) * 33), char, font=font, fill="black", anchor="mm")
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target)
    print(target)


if __name__ == "__main__":
    main()
