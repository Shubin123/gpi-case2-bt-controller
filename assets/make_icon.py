#!/usr/bin/env python3
"""Draws the RetroArch XMB icon for the "Bluetooth Controller" playlist.

Usage: make_icon.py <out_dir>  ->  bt_controller_white.png, bt_controller_color.png (256x256 RGBA)
"""
import sys
from PIL import Image, ImageDraw

S = 4                      # supersampling for smooth edges
W = 256 * S


def glyph(draw, fg, cut):
    """Gamepad + Bluetooth rune. fg = ink colour, cut = colour used to punch holes."""
    s = lambda v: int(v * S)
    # Gamepad body with two grips
    draw.rounded_rectangle([s(28), s(104), s(228), s(196)], radius=s(40), fill=fg)
    draw.ellipse([s(28), s(140), s(100), s(232)], fill=fg)
    draw.ellipse([s(156), s(140), s(228), s(232)], fill=fg)
    # D-pad (cut out)
    draw.rounded_rectangle([s(58), s(138), s(110), s(154)], radius=s(3), fill=cut)
    draw.rounded_rectangle([s(76), s(120), s(92), s(172)], radius=s(3), fill=cut)
    # Face buttons (cut out)
    for cx, cy in ((182, 128), (182, 164), (164, 146), (200, 146)):
        r = 9
        draw.ellipse([s(cx - r), s(cy - r), s(cx + r), s(cy + r)], fill=cut)
    # Bluetooth rune above the pad
    pts = [(116, 52), (140, 72), (116, 92)]
    lw = s(7)
    draw.line([(s(116), s(28)), (s(116), s(96))], fill=fg, width=lw)
    draw.line([(s(100), s(44)), (s(140), s(72)), (s(116), s(96))], fill=fg, width=lw, joint="curve")
    draw.line([(s(100), s(80)), (s(140), s(52)), (s(116), s(28))], fill=fg, width=lw, joint="curve")


def white():
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    glyph(ImageDraw.Draw(img), (255, 255, 255, 255), (0, 0, 0, 0))
    return img.resize((256, 256), Image.LANCZOS)


def color():
    img = Image.new("RGBA", (W, W), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8 * S, 8 * S, 248 * S, 248 * S], radius=48 * S, fill=(0, 112, 209, 255))
    glyph(d, (255, 255, 255, 255), (0, 112, 209, 255))
    return img.resize((256, 256), Image.LANCZOS)


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "."
    white().save(f"{out}/bt_controller_white.png")
    color().save(f"{out}/bt_controller_color.png")
