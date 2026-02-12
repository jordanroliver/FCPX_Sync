"""Generate a chain-link app icon for FCPX Sync.

Large, clean interlocking links that read clearly at any size.
"""

from PIL import Image, ImageDraw, ImageFilter

SIZE = 1024
CX, CY = SIZE // 2, SIZE // 2


def make_link(cx, cy, w, h, thick, fill, border_color, angle):
    """Create a single chain link ring as an RGBA image."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    r = h // 2
    x0, y0 = cx - w // 2, cy - h // 2
    x1, y1 = cx + w // 2, cy + h // 2

    # Outer pill with border
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill)
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, outline=border_color, width=5)

    # Inner cutout
    ix0, iy0 = x0 + thick, y0 + thick
    ix1, iy1 = x1 - thick, y1 - thick
    ir = max((iy1 - iy0) // 2, 1)
    d.rounded_rectangle([ix0, iy0, ix1, iy1], radius=ir, fill=(0, 0, 0, 0))

    img = img.rotate(angle, center=(cx, cy), resample=Image.BICUBIC)
    return img


def main():
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # macOS rounded-square background
    m = 24
    draw.rounded_rectangle([m, m, SIZE - m, SIZE - m], radius=200,
                           fill=(19, 19, 26, 255))

    # --- BIG chain links filling the icon ---
    link_w = 480
    link_h = 300
    thick = 76
    angle = 45
    gap = 115

    l1_cx, l1_cy = CX - gap // 2, CY - gap // 2
    l2_cx, l2_cy = CX + gap // 2, CY + gap // 2

    link1 = make_link(l1_cx, l1_cy, link_w, link_h, thick,
                      fill=(110, 165, 247, 255),       # ACCENT blue
                      border_color=(80, 130, 210, 255),
                      angle=angle)

    link2 = make_link(l2_cx, l2_cy, link_w, link_h, thick,
                      fill=(92, 212, 192, 255),         # TEAL
                      border_color=(60, 175, 160, 255),
                      angle=angle)

    # === INTERLOCKING ===
    # 1. Draw link1
    # 2. Draw link2 on top
    # 3. Re-draw link1's upper-right arm on top of link2 (masked)
    #
    # The mask splits along the -45° line through center.
    # Upper-right half = link1 in front.

    canvas.alpha_composite(link1)
    canvas.alpha_composite(link2)

    # Mask: everything above the -45° line through center
    # (perpendicular to the link axis) = where link1 is in front
    mask = Image.new("L", (SIZE, SIZE), 0)
    md = ImageDraw.Draw(mask)
    # The -45° line through (CX,CY): points going upper-left to lower-right
    # We want everything ABOVE this line (upper-right half)
    md.polygon([
        (CX, CY),
        (0, 0),
        (SIZE, 0),
        (SIZE, CY),
    ], fill=255)
    # Rotate mask -45° to align with the perpendicular of the link angle
    mask = mask.rotate(-45, center=(CX, CY), resample=Image.BICUBIC)
    mask = mask.filter(ImageFilter.GaussianBlur(radius=2))

    front = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    front.paste(link1, mask=mask)
    canvas.alpha_composite(front)

    canvas.save("icon.png", "PNG")
    print("Saved icon.png (1024x1024)")


if __name__ == "__main__":
    main()
