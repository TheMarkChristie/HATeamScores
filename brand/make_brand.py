"""Draw the brand images Home Assistant shows for this integration. Since Home Assistant 2026.3 a custom integration
carries them itself, in custom_components/<domain>/brand/ (icon.png 256, icon@2x.png 512, logo.png and logo@2x.png
256 and 512 tall, dark_ variants), PNG with transparency, trimmed; they are served at
/api/brands/integration/sportsdb_tracker/<image>. The icon is a scoreboard: a white board with a 2:1 scoreline on a
pitch-green rounded square, a slim clock bar above it. No TheSportsDB or Home Assistant marks are used.

    python brand/make_brand.py        -> custom_components/sportsdb_tracker/brand/*.png
"""
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "custom_components", "sportsdb_tracker", "brand")
GREEN = (14, 116, 70, 255)
INK = (15, 23, 41, 255)
WHITE = (255, 255, 255, 255)
BOLD = r"C:\Windows\Fonts\segoeuib.ttf"
SCALE = 4                                  # drawn large, then shrunk for smooth edges


def icon(size):
    s = size * SCALE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=s * 0.22, fill=GREEN)
    pad = s * 0.13
    d.rounded_rectangle([pad, s * 0.17, s - pad, s * 0.24], radius=s * 0.035, fill=(255, 255, 255, 210))   # the clock bar
    d.ellipse([s * 0.47, s * 0.185, s * 0.53, s * 0.225], fill=GREEN)                                      # its colon
    d.rounded_rectangle([pad, s * 0.31, s - pad, s * 0.80], radius=s * 0.07, fill=WHITE)                   # the board
    font = ImageFont.truetype(BOLD, int(s * 0.36))
    for text, cx in (("2", s * 0.33), ("1", s * 0.67)):
        box = d.textbbox((0, 0), text, font=font, anchor="ls")
        d.text((cx - (box[2] - box[0]) / 2 - box[0], s * 0.555 + (box[3] - box[1]) / 2 - box[3]), text, font=font, fill=INK, anchor="ls")
    for cy in (s * 0.50, s * 0.61):
        d.ellipse([s * 0.485, cy - s * 0.02, s * 0.515, cy + s * 0.02], fill=GREEN)
    return img.resize((size, size), Image.LANCZOS)


def logo(height, dark=False):
    h = height * SCALE
    mark = icon(height).resize((h, h), Image.LANCZOS)
    font = ImageFont.truetype(BOLD, int(h * 0.44))
    text = "Team Scores"
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    box = probe.textbbox((0, 0), text, font=font, anchor="ls")
    tw = box[2] - box[0]
    gap = int(h * 0.22)
    img = Image.new("RGBA", (h + gap + tw + int(h * 0.02), h), (0, 0, 0, 0))
    img.paste(mark, (0, 0), mark)
    d = ImageDraw.Draw(img)
    d.text((h + gap - box[0], h * 0.5 + (box[3] - box[1]) / 2 - box[3]), text, font=font, fill=WHITE if dark else INK, anchor="ls")
    img = img.crop(img.getbbox())
    return img.resize((round(img.width / SCALE), round(img.height / SCALE)), Image.LANCZOS)


def main():
    out = lambda name: os.path.join(HERE, name)  # noqa: E731
    icon(256).save(out("icon.png"))
    icon(512).save(out("icon@2x.png"))
    logo(256).save(out("logo.png"))
    logo(512).save(out("logo@2x.png"))
    logo(256, dark=True).save(out("dark_logo.png"))
    logo(512, dark=True).save(out("dark_logo@2x.png"))
    for name in ("icon.png", "icon@2x.png", "logo.png", "logo@2x.png", "dark_logo.png", "dark_logo@2x.png"):
        im = Image.open(out(name))
        print("%-16s %dx%d %s" % (name, im.width, im.height, im.mode))


if __name__ == "__main__":
    main()
