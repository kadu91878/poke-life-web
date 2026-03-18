#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / 'backend'
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from game.engine.cards import load_pokemon_cards  # noqa: E402
from game.engine.gyms import list_gym_definitions, build_gym_leader_team  # noqa: E402


ALIASES = {
    'farfetchd': 'farfetch d',
    'm fossil': 'mysterious fossil',
    'm fossil.': 'mysterious fossil',
    'nidoranf': 'nidoran female',
    'nidoranm': 'nidoran male',
    'diglet': 'diglett',
    'sellder': 'shellder',
}


def normalize_name(value: str | None) -> str:
    normalized = str(value or '').strip().lower()
    normalized = normalized.replace('♀', ' female').replace('♂', ' male')
    normalized = normalized.replace('_', ' ').replace('-', ' ')
    normalized = normalized.replace("'", ' ').replace('.', ' ').replace('`', ' ')
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    return ALIASES.get(normalized, normalized)


def build_metadata_index(cards: list[dict]) -> set[str]:
    keys: set[str] = set()
    for card in cards:
        for raw in (card.get('real_name'), card.get('current_name'), card.get('id')):
            normalized = normalize_name(raw)
            if normalized:
                keys.add(normalized)
        for raw in card.get('aliases') or []:
            normalized = normalize_name(raw)
            if normalized:
                keys.add(normalized)
    return keys


def main() -> int:
    metadata_path = ROOT / 'backend' / 'cards_metadata.json'
    compatibility_path = ROOT / 'backend' / 'game' / 'data' / 'pokemon.json'
    board_path = ROOT / 'backend' / 'game' / 'data' / 'board.json'
    public_image_root = ROOT / 'frontend' / 'public' / 'assets' / 'pokemon'

    metadata_cards = json.loads(metadata_path.read_text(encoding='utf-8'))['cards']
    compatibility_cards = json.loads(compatibility_path.read_text(encoding='utf-8'))
    runtime_cards = load_pokemon_cards()

    metadata_keys = build_metadata_index(metadata_cards)
    metadata_names = {card['real_name'] for card in metadata_cards}
    runtime_names = {card['name'] for card in runtime_cards}
    compatibility_names = {card['name'] for card in compatibility_cards}

    missing_public_images = sorted(
        card['real_name']
        for card in metadata_cards
        if card.get('reference_image') and not (public_image_root / card['reference_image']).exists()
    )
    missing_runtime_images = sorted(card['real_name'] for card in metadata_cards if not card.get('image_path'))
    missing_evolution_targets = sorted(
        (card['real_name'], card['evolves_to'])
        for card in metadata_cards
        if card.get('evolves_to') and card['evolves_to'] not in metadata_names
    )

    board = json.loads(board_path.read_text(encoding='utf-8'))
    missing_board_refs: list[tuple[str, str]] = []
    for tile in board.get('tiles', []):
        for encounter in (tile.get('data') or {}).get('encounters', []):
            pokemon_name = encounter.get('pokemon_name')
            if pokemon_name and normalize_name(pokemon_name) not in metadata_keys:
                missing_board_refs.append((tile.get('name', '?'), pokemon_name))

    missing_gym_refs: list[tuple[str, str]] = []
    gym_cards_without_images: list[tuple[str, list[str]]] = []
    for gym in list_gym_definitions():
        team = build_gym_leader_team(gym)
        missing_names = [pokemon['name'] for pokemon in team if normalize_name(pokemon['name']) not in metadata_keys]
        if missing_names:
            missing_gym_refs.extend((gym['leader_name'], pokemon_name) for pokemon_name in missing_names)
        missing_images = [pokemon['name'] for pokemon in team if not pokemon.get('image_path')]
        if missing_images:
            gym_cards_without_images.append((gym['leader_name'], missing_images))

    report = {
        'cards_metadata_count': len(metadata_cards),
        'runtime_count': len(runtime_cards),
        'compatibility_snapshot_count': len(compatibility_cards),
        'runtime_matches_metadata_names': runtime_names == metadata_names,
        'compatibility_matches_runtime_names': compatibility_names == runtime_names,
        'missing_public_images': missing_public_images,
        'missing_runtime_images': missing_runtime_images,
        'missing_evolution_targets': missing_evolution_targets,
        'missing_board_refs': missing_board_refs,
        'missing_gym_refs': missing_gym_refs,
        'gym_cards_without_images': gym_cards_without_images,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
