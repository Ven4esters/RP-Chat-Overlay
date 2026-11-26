"""Build the Windows icon from the selected transparent app artwork.

Run from ``source`` with Pillow installed::

    python tools/make_icon.py

The same original PNG is used by the README and packaged as a multi-resolution
Windows ICO. The builder never redraws or overwrites the source artwork.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def build(target: Path, png: Path) -> Path:
    """Write all supported Windows icon sizes from *png* to *target*."""
    artwork = Image.open(png).convert("RGBA")
    if artwork.size != (512, 512):
        artwork = artwork.resize((512, 512), Image.Resampling.LANCZOS)
    if artwork.getchannel("A").getextrema()[0] == 255:
        raise ValueError(f"{png} has no transparent pixels; refusing to build an opaque icon")
    artwork.save(target, format="ICO", sizes=[(size, size) for size in SIZES])
    return target


if __name__ == "__main__":
    source = Path(__file__).resolve().parent.parent
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else source / "icon.ico"
    png_path = source / "icon.png"
    build(output, png_path)
    print(f"готово: {output} ({output.stat().st_size} байт, {len(SIZES)} размеров)")
