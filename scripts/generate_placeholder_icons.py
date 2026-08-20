"""Generate the PWA placeholder icon set.

THESE ARE PLACEHOLDERS. The repo contains no brand mark of any kind (a search
for *.png/*.svg/*.ico/*.jpg/*.webp outside node_modules returns nothing), so
these are a solid theme-coloured square with the app initials — enough for the
manifest to be technically valid and for an install prompt to work. Replace
them with real artwork before any store or PWA launch; re-running this script
regenerates the placeholders, it does not preserve anything hand-made.

Colours come from frontend/public/manifest.json so the icons match the splash:
    theme_color      #0f172a  (background of the mark)
    background_color #ffffff  (the initials)

Usage:  python -m scripts.generate_placeholder_icons
"""
from __future__ import annotations

import json
import pathlib

from PIL import Image, ImageDraw, ImageFont

INITIALS = "CH"
PUBLIC = pathlib.Path(__file__).resolve().parents[1] / "frontend" / "public"
MANIFEST = PUBLIC / "manifest.json"
ICON_DIR = PUBLIC / "icons"

# (filename, size, maskable)
#
# A maskable icon is cropped to a circle by Android, so its mark must sit
# inside the "safe zone" — the middle 80% of the canvas. The plain icons use a
# larger mark; the maskable one insets it.
SPECS = [
    ("icon-192.png", 192, False),
    ("icon-512.png", 512, False),
    ("icon-maskable-512.png", 512, True),
]


def _font(px: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """A bold sans face if the platform has one, else Pillow's bitmap default."""
    for candidate in ("arialbd.ttf", "DejaVuSans-Bold.ttf", "Arial Bold.ttf",
                      "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(candidate, px)
        except OSError:
            continue
    return ImageFont.load_default()


def _render(size: int, maskable: bool, bg: str, fg: str) -> Image.Image:
    img = Image.new("RGBA", (size, size), bg)
    draw = ImageDraw.Draw(img)

    # Mark occupies 46% of the canvas normally, 36% when it must survive a
    # circular mask.
    target = size * (0.36 if maskable else 0.46)
    font = _font(max(8, int(target)))

    left, top, right, bottom = draw.textbbox((0, 0), INITIALS, font=font)
    draw.text(
        ((size - (right - left)) / 2 - left, (size - (bottom - top)) / 2 - top),
        INITIALS, font=font, fill=fg,
    )
    return img


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    bg = manifest.get("theme_color", "#0f172a")
    fg = manifest.get("background_color", "#ffffff")

    ICON_DIR.mkdir(parents=True, exist_ok=True)

    icons = []
    for name, size, maskable in SPECS:
        _render(size, maskable, bg, fg).save(ICON_DIR / name, format="PNG",
                                             optimize=True)
        icons.append({
            "src": f"/icons/{name}",
            "sizes": f"{size}x{size}",
            "type": "image/png",
            "purpose": "maskable" if maskable else "any",
        })
        print(f"  wrote {ICON_DIR / name}  ({size}x{size}, "
              f"{'maskable' if maskable else 'any'})")

    manifest["icons"] = icons
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"  updated {MANIFEST} with {len(icons)} icons")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
