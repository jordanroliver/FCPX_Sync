"""Generate a chain-link app icon for FCPX Sync."""

from PIL import Image, ImageDraw

SIZE = 1024
PAD = 100


def draw_link(img, cx, cy, angle, color, outline, thickness=48):
    """Draw a single rounded chain link centered at (cx, cy)."""
    link = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(link)

    # Link dimensions
    w, h = 260, 160
    r = h // 2  # corner radius = half height for pill shape

    # Draw outer pill shape
    x0, y0 = cx - w // 2, cy - h // 2
    x1, y1 = cx + w // 2, cy + h // 2
    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=color, outline=outline, width=6)

    # Cut out the center to make it a ring
    inner_shrink = thickness
    ix0 = x0 + inner_shrink
    iy0 = y0 + inner_shrink
    ix1 = x1 - inner_shrink
    iy1 = y1 - inner_shrink
    ir = max((iy1 - iy0) // 2, 1)
    d.rounded_rectangle([ix0, iy0, ix1, iy1], radius=ir, fill=(0, 0, 0, 0))

    # Rotate
    link = link.rotate(angle, center=(cx, cy), resample=Image.BICUBIC)
    img.alpha_composite(link)


def main():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # macOS-style rounded square background
    bg_margin = 20
    draw.rounded_rectangle(
        [bg_margin, bg_margin, SIZE - bg_margin, SIZE - bg_margin],
        radius=200,
        fill=(30, 30, 46, 255),  # dark bg matching app theme
    )

    # Two interlocking chain links at 45-degree angles
    # Link 1: upper-left, blue
    draw_link(img, SIZE // 2 - 70, SIZE // 2 - 10, 45,
              color=(137, 180, 250, 255),   # ACCENT blue
              outline=(116, 199, 236, 255))  # lighter blue edge

    # Link 2: lower-right, lighter blue
    draw_link(img, SIZE // 2 + 70, SIZE // 2 + 10, 45,
              color=(166, 227, 161, 255),   # green accent
              outline=(137, 180, 250, 255))  # blue edge

    img.save("icon.png", "PNG")
    print("Saved icon.png (1024x1024)")


if __name__ == "__main__":
    main()
