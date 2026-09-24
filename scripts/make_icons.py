"""ホーム画面用のアプリアイコン（黒大理石に金の「美」）を docs/icons/ に書き出す。一度作ればよい。

    uv run --with pillow scripts/make_icons.py
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from common import SITE

FONT = "C:/Windows/Fonts/yumindb.ttf"  # 游明朝 Demibold
GOLD = (212, 180, 116)


def icon(size: int, glyph_ratio: float) -> Image.Image:
    """黒大理石の背景（docs/marble-dark.jpg の中央を切り出し）に、金の細い枠と「美」を置く。
    glyph_ratio は文字の高さの割合。maskable アイコンは端が切られるので小さめにする。"""
    bg = Image.open(SITE / "marble-dark.jpg").convert("RGB")
    side = min(bg.size)
    bg = bg.crop(((bg.width - side) // 2, (bg.height - side) // 2, (bg.width + side) // 2, (bg.height + side) // 2))
    img = bg.resize((size, size), Image.LANCZOS)
    d = ImageDraw.Draw(img)
    inset = round(size * (0.5 - glyph_ratio * 0.72))
    d.rectangle([inset, inset, size - inset, size - inset], outline=GOLD, width=max(1, size // 128))
    font = ImageFont.truetype(FONT, round(size * glyph_ratio))
    box = d.textbbox((0, 0), "美", font=font)
    x = (size - (box[2] - box[0])) / 2 - box[0]
    y = (size - (box[3] - box[1])) / 2 - box[1]
    d.text((x, y), "美", font=font, fill=GOLD)
    return img


def main() -> None:
    out = SITE / "icons"
    out.mkdir(exist_ok=True)
    icon(512, 0.56).save(out / "icon-512.png", optimize=True)
    icon(192, 0.56).save(out / "icon-192.png", optimize=True)
    icon(180, 0.56).save(out / "apple-touch-icon.png", optimize=True)   # iPhone のホーム画面用
    icon(512, 0.42).save(out / "maskable-512.png", optimize=True)       # Android の丸や角丸に切られても収まる版
    for p in sorted(out.glob("*.png")):
        print(p.name, p.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
