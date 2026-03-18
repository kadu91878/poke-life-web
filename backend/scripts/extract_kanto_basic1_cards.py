#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]
SOURCE_SHEET = ROOT / "backend" / "assets" / "raw" / "Kanto" / "Kanto Pokémon" / "Basic 1 (x8).png"
PUBLIC_ASSET_DIR = ROOT / "frontend" / "public" / "assets" / "pokemon"

CARD_WIDTH = 245
CARD_HEIGHT = 341
GRID_COLUMNS = 4
GRID_ROWS = 2

# Ordem confirmada a partir do sheet bruto Basic 1 (x8), lido em row-major.
CARD_NAMES = [
    "Pidgey",
    "Pidgeotto",
    "Pidgeot",
    "Paras",
    "Weedle",
    "Kakuna",
    "Beedrill",
    "Parasect",
]


def slugify(name: str) -> str:
    return (
        name.lower()
        .replace("♀", "_female")
        .replace("♂", "_male")
        .replace(".", "")
        .replace("'", "")
        .replace(" ", "_")
    )


def main() -> int:
    sheet = Image.open(SOURCE_SHEET)
    expected_size = (CARD_WIDTH * GRID_COLUMNS, CARD_HEIGHT * GRID_ROWS)
    if sheet.size != expected_size:
        raise SystemExit(f"Unexpected sheet size {sheet.size}; expected {expected_size}")

    PUBLIC_ASSET_DIR.mkdir(parents=True, exist_ok=True)

    for index, card_name in enumerate(CARD_NAMES):
        row, col = divmod(index, GRID_COLUMNS)
        left = col * CARD_WIDTH
        upper = row * CARD_HEIGHT
        right = left + CARD_WIDTH
        lower = upper + CARD_HEIGHT
        crop = sheet.crop((left, upper, right, lower))
        output_path = PUBLIC_ASSET_DIR / f"{slugify(card_name)}.png"
        crop.save(output_path)
        print(f"{card_name}: {output_path} [{left}, {upper}, {right}, {lower}]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
