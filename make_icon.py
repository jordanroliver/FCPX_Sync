"""Generate a chain-link app icon for FCPX Sync.

Large, clean interlocking links — no seam artifacts.

Approach: render two complete composites (one for each Z-order)
and blend between them with a soft-edged diagonal mask.  The
Gaussian blur on the mask eliminates the hard seam while the
parallel diagonal gives clear interlocking.  Rendered at 4x
resolution and downscaled for a crisp final image.
"""

from PIL import Image, ImageDraw, ImageFilter

OUTPUT = 1024
SCALE = 4
SIZE = OUTPUT * SCALE
CX, CY = SIZE // 2, SIZE // 2


def make_link(cx, cy, w, h, thick, fill, angle):
    """Create a single chain link ring as an RGBA image."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    r = h // 2
    x0, y0 = cx - w // 2, cy - h // 2
    x1, y1 = cx + w // 2, cy + h // 2

    d.rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill)

    ix0, iy0 = x0 + thick, y0 + thick
    ix1, iy1 = x1 - thick, y1 - thick
    ir = max((iy1 - iy0) // 2, 1)
    d.rounded_rectangle([ix0, iy0, ix1, iy1], radius=ir, fill=(0, 0, 0, 0))

    img = img.rotate(angle, center=(cx, cy), resample=Image.BICUBIC)
    return img


def make_bg():
    """Create the background rounded rectangle."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = 24 * SCALE
    r = 200 * SCALE
    d.rounded_rectangle([m, m, SIZE - m, SIZE - m], radius=r,
                        fill=(19, 19, 26, 255))
    return img


def main():
    link_w = 480 * SCALE
    link_h = 300 * SCALE
    thick = 76 * SCALE
    angle = 45
    gap = 115 * SCALE

    link1 = make_link(CX - gap // 2, CY - gap // 2,
                      link_w, link_h, thick,
                      fill=(110, 165, 247, 255), angle=angle)

    link2 = make_link(CX + gap // 2, CY + gap // 2,
                      link_w, link_h, thick,
                      fill=(92, 212, 192, 255), angle=angle)

    bg = make_bg()

    # Composite A: link1 on top  (upper-right region — blue in front)
    comp_a = bg.copy()
    comp_a.alpha_composite(link2)
    comp_a.alpha_composite(link1)

    # Composite B: link2 on top  (lower-left region — teal in front)
    comp_b = bg.copy()
    comp_b.alpha_composite(link1)
    comp_b.alpha_composite(link2)

    # PARALLEL diagonal mask (top-left to bottom-right — same angle as links).
    # This splits the overlap zone so each arm clearly passes in front.
    # Upper-right triangle = white (comp_a), lower-left = black (comp_b).
    mask = Image.new("L", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(mask)
    d.polygon([(0, 0), (SIZE, 0), (SIZE, SIZE)], fill=255)

    # Soften the mask edge with Gaussian blur — eliminates the hard seam
    # at the transition between the two composites.  At 4x resolution a
    # blur radius of 12 ≈ 3px at output — invisible at icon sizes.
    mask = mask.filter(ImageFilter.GaussianBlur(radius=12))

    # Blend: comp_b where mask=0, comp_a where mask=255, smooth between
    comp_b.paste(comp_a, mask=mask)

    # Downscale for clean output
    result = comp_b.resize((OUTPUT, OUTPUT), Image.LANCZOS)

    result.save("icon.png", "PNG")
    print(f"Saved icon.png ({OUTPUT}x{OUTPUT})")


if __name__ == "__main__":
    main()
