"""ホーム画面用のアプリアイコン（黒大理石に金の「美」）を docs/icons/ に、
SNS で共有されたときのカード画像（1200x630）を docs/og.png に書き出す。一度作ればよい。

    uv run --with pillow scripts/make_icons.py
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from common import SITE

FONT = "C:/Windows/Fonts/yumindb.ttf"  # 游明朝 Demibold
SANS = "C:/Windows/Fonts/YuGothM.ttc"   # 游ゴシック Medium
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


def og_card() -> Image.Image:
    """X などのリンクカード用（summary_large_image は 1.91:1）。黒大理石に金の枠、サイト名と一行の説明。"""
    w, h = 1200, 630
    bg = Image.open(SITE / "marble-dark.jpg").convert("RGB")
    scale = max(w / bg.width, h / bg.height)
    bg = bg.resize((round(bg.width * scale), round(bg.height * scale)), Image.LANCZOS)
    img = bg.crop(((bg.width - w) // 2, (bg.height - h) // 2, (bg.width + w) // 2, (bg.height + h) // 2))
    d = ImageDraw.Draw(img)
    d.rectangle([36, 36, w - 36, h - 36], outline=GOLD, width=3)
    d.rectangle([48, 48, w - 48, h - 48], outline=GOLD, width=1)

    def center(text: str, font: ImageFont.FreeTypeFont, y: int, fill) -> None:
        box = d.textbbox((0, 0), text, font=font)
        d.text(((w - (box[2] - box[0])) / 2 - box[0], y), text, font=font, fill=fill)

    center("MUSEUM WATCH", ImageFont.truetype(SANS, 30), 150, GOLD)
    center("美術館ウォッチ", ImageFont.truetype(FONT, 118), 205, (240, 232, 214))
    center("全国の美術館の 今日の開館・時間・料金・展覧会", ImageFont.truetype(SANS, 36), 400, (220, 212, 196))
    center("毎週更新", ImageFont.truetype(SANS, 28), 470, GOLD)
    return img


def main() -> None:
    out = SITE / "icons"
    out.mkdir(exist_ok=True)
    icon(512, 0.56).save(out / "icon-512.png", optimize=True)
    icon(192, 0.56).save(out / "icon-192.png", optimize=True)
    icon(180, 0.56).save(out / "apple-touch-icon.png", optimize=True)   # iPhone のホーム画面用
    icon(512, 0.42).save(out / "maskable-512.png", optimize=True)       # Android の丸や角丸に切られても収まる版
    og_card().save(SITE / "og.png", optimize=True)
    print("og.png", (SITE / "og.png").stat().st_size // 1024, "KB")
    for p in sorted(out.glob("*.png")):
        print(p.name, p.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
