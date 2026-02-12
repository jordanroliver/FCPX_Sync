"""Generate a chain-link app icon for FCPX Sync."""

import math
from PIL import Image, ImageDraw


SIZE = 1024
CX, CY = SIZE // 2, SIZE // 2


def draw_rounded_rect_ring(draw, cx, cy, w, h, thickness, fill, outline, angle, img):
    """Draw a pill-shaped ring (chain link) at an angle using compositing."""
    # Create a temp image for this link
    link_img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    link_draw = ImageDraw.Draw(link_img)

    r_outer = h // 2

    # Outer pill
    x0, y0 = cx - w // 2, cy - h // 2
    x1, y1 = cx + w // 2, cy + h // 2
    link_draw.rounded_rectangle([x0, y0, x1, y1], radius=r_outer, fill=fill)

    # Outline
    link_draw.rounded_rectangle([x0, y0, x1, y1], radius=r_outer, outline=outline, width=4)

    # Inner cutout (transparent)
    shrink = thickness
    ix0, iy0 = x0 + shrink, y0 + shrink
    ix1, iy1 = x1 - shrink, y1 - shrink
    r_inner = max((iy1 - iy0) // 2, 1)
    link_draw.rounded_rectangle([ix0, iy0, ix1, iy1], radius=r_inner, fill=(0, 0, 0, 0))

    # Rotate
    link_img = link_img.rotate(angle, center=(cx, cy), resample=Image.BICUBIC)
    return link_img


def main():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # macOS-style rounded square background
    margin = 24
    draw.rounded_rectangle(
        [margin, margin, SIZE - margin, SIZE - margin],
        radius=200,
        fill=(30, 30, 46, 255),
    )

    # Subtle inner shadow / depth
    draw.rounded_rectangle(
        [margin + 4, margin + 4, SIZE - margin - 4, SIZE - margin - 4],
        radius=196,
        outline=(24, 24, 37, 180),
        width=4,
    )

    # Chain link parameters
    link_w = 380
    link_h = 220
    thickness = 60
    angle = 45
    offset = 100  # how far apart the centers are

    # The links need to interlock: draw bottom half of link1, full link2, top half of link1
    # This creates the visual illusion of interlocking

    # Link 1 (blue) — shifted upper-left
    link1 = draw_rounded_rect_ring(
        draw, CX - offset // 2, CY - offset // 2,
        link_w, link_h, thickness,
        fill=(137, 180, 250, 255),
        outline=(116, 160, 230, 255),
        angle=angle, img=img,
    )

    # Link 2 (teal/green) — shifted lower-right
    link2 = draw_rounded_rect_ring(
        draw, CX + offset // 2, CY + offset // 2,
        link_w, link_h, thickness,
        fill=(148, 226, 213, 255),
        outline=(120, 200, 190, 255),
        angle=angle, img=img,
    )

    # Create interlocking effect:
    # 1. Paste link1 fully
    img.alpha_composite(link1)

    # 2. Create a mask — only show link2 where it should be "in front"
    #    For a chain, the right side of link2 passes in front of link1
    #    We'll use a diagonal mask
    mask = Image.new("L", (SIZE, SIZE), 255)
    mask_draw = ImageDraw.Draw(mask)

    # Block link2 on the upper-left overlap region (link1 is in front there)
    # Use a diagonal line: everything above-left of center intersection is blocked
    cx_int = CX
    cy_int = CY
    # Triangle covering upper-left area where link1 should be on top
    mask_draw.polygon([
        (cx_int - 200, cy_int - 200),
        (cx_int + 60, cy_int - 200),
        (cx_int - 200, cy_int + 60),
    ], fill=0)

    # Apply masked link2
    link2_masked = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    link2_masked.paste(link2, mask=mask)
    img.alpha_composite(link2_masked)

    # Add a subtle shine/highlight on each link
    shine = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    shine_draw = ImageDraw.Draw(shine)
    # Small bright spots near the top of each link
    shine_draw.ellipse(
        [CX - offset // 2 - 30, CY - offset // 2 - 50,
         CX - offset // 2 + 30, CY - offset // 2 - 20],
        fill=(255, 255, 255, 40),
    )
    shine_draw.ellipse(
        [CX + offset // 2 - 30, CY + offset // 2 - 50,
         CX + offset // 2 + 30, CY + offset // 2 - 20],
        fill=(255, 255, 255, 40),
    )
    shine = shine.rotate(angle, center=(CX, CY), resample=Image.BICUBIC)
    img.alpha_composite(shine)

    img.save("icon.png", "PNG")
    print("Saved icon.png (1024x1024)")


if __name__ == "__main__":
    main()
