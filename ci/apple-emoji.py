import argparse
import json
import re
import struct
from pathlib import Path
from PIL import Image

parser = argparse.ArgumentParser()
parser.add_argument("--tdesktop", type=Path, default=Path(__file__).resolve().parents[2] / "tdesktop")
parser.add_argument("--assets", type=Path, required=True)
args = parser.parse_args()
source = (args.tdesktop / "out/Telegram/lib_ui/gen/emoji.cpp").read_text()
units = [int(x, 16) for x in re.findall(r"0x([0-9a-f]+)", source.split("const ushort IdData[] = {", 1)[1].split("};", 1)[0])]
rows = re.findall(r"\{ uint32\((\d+)\), uint32\((\d+)\), uint32\((\d+)\), uint32\((\d+)\) \}", source.split("const DataStruct Data[] = {", 1)[1].split("};", 1)[0])
def normalized(value):
    return tuple(int(x, 16) for x in value.split("-") if int(x, 16) != 0xfe0f)
files = {normalized(p.stem): p for p in args.assets.glob("*.png")}
folder = args.tdesktop / "Telegram/Resources/emoji"
sprites = [Image.open(folder / f"emoji_{i + 1}.webp").convert("RGBA") for i in range((len(rows) + 511) // 512)]
offset = 0
missing = []
for i, (_, size, _, _) in enumerate(rows):
    size = int(size)
    text = struct.pack("<" + "H" * size, *units[offset:offset + size]).decode("utf-16-le")
    offset += size
    key = "-".join(f"{ord(c):x}" for c in text)
    image_path = files.get(normalized(key))
    if image_path is None:
        missing.append(key)
        continue
    image = Image.open(image_path).convert("RGBA").resize((72, 72), Image.Resampling.LANCZOS)
    sprites[i // 512].paste(image, ((i % 32) * 72, ((i % 512) // 32) * 72))
for i, sprite in enumerate(sprites):
    sprite.save(folder / f"emoji_{i + 1}.webp", lossless=True, method=6)
print(json.dumps({"replaced": len(rows) - len(missing), "upstream_fallback": missing}, indent=2))
