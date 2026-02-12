"""Generate a chain-link app icon for FCPX Sync.

Creates two truly interlocking chain links where one passes through the other.
"""

from PIL import Image, ImageDraw, ImageFilter

SIZE = 1024
CX, CY = SIZE // 2, SIZE // 2


def make_link(cx, cy, w, h, thickness, fill, highlight, shadow, angle):
    """Create a single chain link as an RGBA image with depth shading."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    r_outer = h // 2
    x0, y0 = cx - w // 2, cy - h // 2
    x1, y1 = cx + w // 2, cy + h // 2

    # Drop shadow (offset slightly)
    shadow_img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow_img)
    sd.rounded_rectangle([x0 + 6, y0 + 6, x1 + 6, y1 + 6], radius=r_outer,
                         fill=(0, 0, 0, 80))
    shadow_img = shadow_img.rotate(angle, center=(cx, cy), resample=Image.BICUBIC)
    shadow_img = shadow_img.filter(ImageFilter.GaussianBlur(radius=12))

    # Outer shape
    d.rounded_rectangle([x0, y0, x1, y1], radius=r_outer, fill=fill)

    # Top highlight edge (gives 3D feel)
    d.rounded_rectangle([x0 + 2, y0 + 2, x1 - 2, y0 + h // 3],
                         radius=r_outer, fill=highlight)

    # Re-draw the main fill slightly inset to blend the highlight
    d.rounded_rectangle([x0 + 3, y0 + thickness // 3, x1 - 3, y1 - 3],
                         radius=r_outer - 3, fill=fill)

    # Outer border
    d.rounded_rectangle([x0, y0, x1, y1], radius=r_outer, outline=shadow, width=3)

    # Inner cutout
    ix0, iy0 = x0 + thickness, y0 + thickness
    ix1, iy1 = x1 - thickness, y1 - thickness
    r_inner = max((iy1 - iy0) // 2, 1)

    # Inner shadow (dark ring around hole)
    d.rounded_rectangle([ix0 - 4, iy0 - 4, ix1 + 4, iy1 + 4],
                         radius=r_inner + 4, fill=shadow)
    # Punch the hole
    d.rounded_rectangle([ix0, iy0, ix1, iy1], radius=r_inner, fill=(0, 0, 0, 0))

    # Rotate
    img = img.rotate(angle, center=(cx, cy), resample=Image.BICUBIC)

    return shadow_img, img


def main():
    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # macOS rounded-square background
    margin = 24
    # Gradient-like background: darker center for depth
    draw.rounded_rectangle(
        [margin, margin, SIZE - margin, SIZE - margin],
        radius=200, fill=(30, 30, 46, 255),
    )
    # Subtle vignette ring
    draw.rounded_rectangle(
        [margin + 3, margin + 3, SIZE - margin - 3, SIZE - margin - 3],
        radius=197, outline=(22, 22, 36, 200), width=3,
    )

    # --- Chain link geometry ---
    link_w = 340
    link_h = 200
    thickness = 56
    angle = 45
    gap = 88  # distance between centers

    # Link 1 (blue) — upper-left
    l1_cx, l1_cy = CX - gap // 2, CY - gap // 2
    l1_shadow, l1_full = make_link(
        l1_cx, l1_cy, link_w, link_h, thickness, angle=angle,
        fill=(120, 165, 240, 255),
        highlight=(170, 200, 255, 200),
        shadow=(80, 120, 200, 255),
    )

    # Link 2 (teal) — lower-right
    l2_cx, l2_cy = CX + gap // 2, CY + gap // 2
    l2_shadow, l2_full = make_link(
        l2_cx, l2_cy, link_w, link_h, thickness, angle=angle,
        fill=(115, 210, 200, 255),
        highlight=(170, 240, 230, 200),
        shadow=(70, 160, 155, 255),
    )

    # === INTERLOCKING COMPOSITING ===
    # The trick: link1's upper-right arm passes IN FRONT of link2,
    # but link1's lower-left arm passes BEHIND link2.
    #
    # Layering order:
    #   1. Shadows
    #   2. Link 1 (full)
    #   3. Link 2 (full) — covers link1 in overlap zone
    #   4. Link 1 again, but MASKED to only the front-crossing arm
    #
    # The mask dividing line runs perpendicular to the 45° link angle,
    # i.e. at -45° through the overlap center. Everything on the
    # upper-right side of this line is where link1 is in front.

    # Step 1: shadows
    canvas.alpha_composite(l1_shadow)
    canvas.alpha_composite(l2_shadow)

    # Step 2: link1 full
    canvas.alpha_composite(l1_full)

    # Step 3: link2 full (covers link1 in overlap)
    canvas.alpha_composite(l2_full)

    # Step 4: re-draw link1 masked to upper-right crossing arm only
    # The dividing line goes perpendicular to the 45° link axis,
    # i.e. from lower-left to upper-right (-45°), through the center.
    # Everything ABOVE this line = link1 is in front.
    front_mask = Image.new("L", (SIZE, SIZE), 0)
    fm = ImageDraw.Draw(front_mask)

    # The -45° line through center: y = -x + (CX+CY)
    # Everything above-right of this line is where link1 crosses in front
    fm.polygon([
        (CX - 400, CY - 400),   # far upper-left
        (CX + 400, CY - 400),   # far upper-right
        (CX + 400, CY),         # right of center
        (CX, CY),               # center
    ], fill=255)

    # Feather the mask edge for clean transition
    front_mask = front_mask.filter(ImageFilter.GaussianBlur(radius=4))

    l1_front = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    l1_front.paste(l1_full, mask=front_mask)
    canvas.alpha_composite(l1_front)

    canvas.save("icon.png", "PNG")
    print("Saved icon.png (1024x1024)")


if __name__ == "__main__":
    main()
