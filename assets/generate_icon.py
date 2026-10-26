"""Generate Voice Typer's polished app and tray icons with Pillow."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent
SCALE = 4
SIZE = 256 * SCALE


def rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((8, 8, size - 8, size - 8), radius=radius, fill=255)
    return mask


def base_icon() -> Image.Image:
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gradient = Image.new("RGBA", (SIZE, SIZE))
    pixels = gradient.load()
    top = (39, 52, 137)
    bottom = (6, 182, 212)
    for y in range(SIZE):
        ratio = y / (SIZE - 1)
        for x in range(SIZE):
            horizontal = x / (SIZE - 1) * 0.22
            mix = min(1.0, ratio * 0.78 + horizontal)
            pixels[x, y] = tuple(int(top[c] * (1 - mix) + bottom[c] * mix) for c in range(3)) + (255,)
    image.paste(gradient, (0, 0), rounded_mask(SIZE, 60 * SCALE))

    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse((72 * SCALE, 25 * SCALE, 188 * SCALE, 190 * SCALE), fill=(125, 211, 252, 90))
    glow = glow.filter(ImageFilter.GaussianBlur(22 * SCALE))
    image.alpha_composite(glow)
    draw = ImageDraw.Draw(image)

    # A crisp microphone with an open voice waveform on each side.
    shadow = (15, 23, 42, 65)
    white = (248, 250, 252, 255)
    cyan = (165, 243, 252, 255)
    draw.rounded_rectangle((94 * SCALE, 45 * SCALE, 166 * SCALE, 157 * SCALE), radius=36 * SCALE, fill=shadow)
    draw.rounded_rectangle((90 * SCALE, 39 * SCALE, 162 * SCALE, 151 * SCALE), radius=36 * SCALE, fill=white)
    draw.rounded_rectangle((105 * SCALE, 55 * SCALE, 147 * SCALE, 62 * SCALE), radius=3 * SCALE, fill=(191, 219, 254, 255))
    draw.rounded_rectangle((105 * SCALE, 72 * SCALE, 147 * SCALE, 79 * SCALE), radius=3 * SCALE, fill=(191, 219, 254, 255))
    draw.arc((65 * SCALE, 86 * SCALE, 187 * SCALE, 194 * SCALE), start=0, end=180, fill=white, width=13 * SCALE)
    draw.line((126 * SCALE, 190 * SCALE, 126 * SCALE, 219 * SCALE), fill=white, width=13 * SCALE)
    draw.rounded_rectangle((91 * SCALE, 213 * SCALE, 161 * SCALE, 225 * SCALE), radius=6 * SCALE, fill=white)
    draw.arc((45 * SCALE, 75 * SCALE, 79 * SCALE, 151 * SCALE), start=105, end=255, fill=cyan, width=7 * SCALE)
    draw.arc((173 * SCALE, 75 * SCALE, 207 * SCALE, 151 * SCALE), start=-75, end=75, fill=cyan, width=7 * SCALE)
    return image.resize((256, 256), Image.Resampling.LANCZOS)


icon = base_icon()
icon.save(ROOT / "voice_typer.png")

listening = icon.copy()
draw = ImageDraw.Draw(listening)
draw.ellipse((174, 174, 238, 238), fill=(248, 250, 252, 255))
draw.ellipse((182, 182, 230, 230), fill=(34, 197, 94, 255))
draw.ellipse((191, 188, 207, 204), fill=(187, 247, 208, 220))
listening.save(ROOT / "voice_typer_listening.png")

icon.save(
    ROOT / "voice_typer.ico",
    format="ICO",
    sizes=[(16, 16), (20, 20), (24, 24), (32, 32), (40, 40), (48, 48), (64, 64), (128, 128), (256, 256)],
)
print(f"Generated icons in {ROOT}")
