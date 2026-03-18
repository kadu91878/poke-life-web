#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / 'backend'
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from game.engine.cards import load_pokemon_cards  # noqa: E402


def main() -> int:
    output_path = ROOT / 'backend' / 'game' / 'data' / 'pokemon.json'
    cards = load_pokemon_cards()
    output_path.write_text(json.dumps(cards, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'synced {len(cards)} cards -> {output_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
