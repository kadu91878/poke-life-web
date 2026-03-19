"""
Regras compartilhadas de inventário e capacidade do jogador.
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

from .pokemon_abilities import sync_pokemon_ability_state

ITEM_CAPACITY = 8

ITEM_DEFS = {
    'full_restore': {
        'key': 'full_restore',
        'name': 'Full Restore',
        'image_path': '/assets/items/full_restore.png',
        'category': 'healing',
        'effect': 'heal_one_pokemon_outside_battle',
        'implemented': True,
        'notes': 'O projeto já usa Full Restore como recurso de captura em lendários; o efeito de cura visual não tem modelo completo de HP no estado atual.',
    },
    'bill': {
        'key': 'bill',
        'name': 'Bill',
        'image_path': '/assets/items/bill.png',
        'category': 'utility',
        'effect': 'increase_move_dice_by_2',
        'implemented': True,
    },
    'gust_of_wind': {
        'key': 'gust_of_wind',
        'name': 'Gust of Wind',
        'image_path': '/assets/items/gust_of_wind.png',
        'category': 'battle',
        'effect': 'choose_opponent_pokemon_in_duel',
        'implemented': True,
    },
    'pluspower': {
        'key': 'pluspower',
        'name': 'PlusPower',
        'image_path': '/assets/items/pluspower.png',
        'category': 'battle',
        'effect': 'grant_plus_2_battle_points_for_one_battle',
        'implemented': True,
    },
    'prof_oak': {
        'key': 'prof_oak',
        'name': 'Prof. Oak',
        'image_path': '/assets/items/prof_oak.png',
        'category': 'utility',
        'effect': 'decrease_move_dice_by_1_min_zero',
        'implemented': True,
    },
    'miracle_stone': {
        'key': 'miracle_stone',
        'name': 'Miracle Stone',
        'image_path': '/assets/items/miracle_stone.png',
        'category': 'utility',
        'effect': 'evolve_one_pokemon_with_current_game_data',
        'implemented': True,
        'notes': 'Implementação conservadora: usa apenas a cadeia evolves_to já presente nos dados atuais.',
    },
    'gold_nugget': {
        'key': 'gold_nugget',
        'name': 'Gold Nugget',
        'image_path': '/assets/items/master_points_nugget.png',
        'category': 'reward',
        'effect': 'special_tile_reward',
        'implemented': True,
        'notes': 'Usado como prêmio do Game Corner; compartilha o ícone disponível do nugget no projeto.',
    },
    'master_ball': {
        'key': 'master_ball',
        'name': 'Master Ball',
        'image_path': '/assets/items/master_ball.png',
        'category': 'reward',
        'effect': 'special_tile_reward',
        'implemented': True,
        'notes': 'Usado como prêmio máximo do Game Corner.',
    },
    'defender': {
        'key': 'defender',
        'name': 'Defender',
        'image_path': None,
        'category': 'battle',
        'effect': 'unimplemented',
        'implemented': False,
        'notes': 'Carta visualmente identificada, mas sem resolução segura implementada ainda.',
    },
    'master_points_nugget': {
        'key': 'master_points_nugget',
        'name': 'Master Points Nugget',
        'image_path': '/assets/items/master_points_nugget.png',
        'category': 'unknown',
        'effect': 'unimplemented',
        'implemented': False,
        'notes': 'Carta visualmente identificada, mas sem regra operacional explícita no material analisado.',
    },
}

DEBUG_ITEM_KEYS = [
    'bill',
    'full_restore',
    'gust_of_wind',
    'pluspower',
    'prof_oak',
    'miracle_stone',
    'gold_nugget',
    'master_ball',
    'master_points_nugget',
]

PROJECT_ROOT = Path(__file__).resolve().parents[3]
INITIAL_ITEMS_RULES_PATH = PROJECT_ROOT / 'initial_items_from_rules.json'


def get_item_def(item_key: str) -> dict:
    return copy.deepcopy(ITEM_DEFS.get(item_key, {}))


def list_debug_item_defs() -> list[dict]:
    return [get_item_def(key) for key in DEBUG_ITEM_KEYS if key in ITEM_DEFS]


@lru_cache(maxsize=1)
def load_initial_item_rules() -> dict:
    try:
        return json.loads(INITIAL_ITEMS_RULES_PATH.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return {'starting_items': []}


def get_starting_resource_defaults() -> dict:
    defaults = {
        'pokeballs': 6,
        'full_restores': 0,
        'items': [],
    }
    rules = load_initial_item_rules()
    for item in rules.get('starting_items', []):
        item_name = item.get('item_name')
        quantity = max(0, int(item.get('quantity', 0) or 0))
        if item_name == 'pokeball':
            defaults['pokeballs'] = quantity
            continue
        if item_name == 'full_restore':
            defaults['full_restores'] = quantity
        if item_name in ITEM_DEFS and quantity > 0:
            defaults['items'].append({
                'key': item_name,
                'name': ITEM_DEFS[item_name]['name'],
                'quantity': quantity,
                'image_path': ITEM_DEFS[item_name].get('image_path'),
                'category': ITEM_DEFS[item_name].get('category'),
                'effect': ITEM_DEFS[item_name].get('effect'),
                'implemented': ITEM_DEFS[item_name].get('implemented', False),
                'notes': ITEM_DEFS[item_name].get('notes'),
            })
    return defaults


def normalize_items(items, full_restores: int = 0) -> list[dict]:
    """
    Normaliza inventário legado para uma lista de stacks.
    """
    normalized: dict[str, dict] = {}

    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            key = item.get('key')
            if not key:
                continue
            normalized[key] = {
                'key': key,
                'name': item.get('name') or ITEM_DEFS.get(key, {}).get('name') or key,
                'quantity': max(0, int(item.get('quantity', 0))),
                'image_path': item.get('image_path') or ITEM_DEFS.get(key, {}).get('image_path'),
                'category': item.get('category') or ITEM_DEFS.get(key, {}).get('category'),
                'effect': item.get('effect') or ITEM_DEFS.get(key, {}).get('effect'),
                'implemented': item.get('implemented', ITEM_DEFS.get(key, {}).get('implemented', False)),
                'notes': item.get('notes') or ITEM_DEFS.get(key, {}).get('notes'),
            }
    elif isinstance(items, dict):
        for key, quantity in items.items():
            if key == 'pokeballs':
                continue
            legacy_key = 'full_restore' if key == 'full_restores' else key
            normalized[legacy_key] = {
                'key': legacy_key,
                'name': ITEM_DEFS.get(legacy_key, {}).get('name') or legacy_key,
                'quantity': max(0, int(quantity or 0)),
                'image_path': ITEM_DEFS.get(legacy_key, {}).get('image_path'),
                'category': ITEM_DEFS.get(legacy_key, {}).get('category'),
                'effect': ITEM_DEFS.get(legacy_key, {}).get('effect'),
                'implemented': ITEM_DEFS.get(legacy_key, {}).get('implemented', False),
                'notes': ITEM_DEFS.get(legacy_key, {}).get('notes'),
            }

    if full_restores and normalized.get('full_restore', {}).get('quantity', 0) == 0:
        normalized['full_restore'] = {
            'key': 'full_restore',
            'name': ITEM_DEFS['full_restore']['name'],
            'quantity': max(0, int(full_restores)),
            'image_path': ITEM_DEFS['full_restore']['image_path'],
            'category': ITEM_DEFS['full_restore']['category'],
            'effect': ITEM_DEFS['full_restore']['effect'],
            'implemented': ITEM_DEFS['full_restore']['implemented'],
            'notes': ITEM_DEFS['full_restore'].get('notes'),
        }

    return [item for item in normalized.values() if item['quantity'] > 0]


def _ensure_normalized_item_list(player: dict) -> list[dict]:
    player['items'] = normalize_items(player.get('items'), player.get('full_restores', 0))
    return player['items']


def pokemon_slot_cost(pokemon: dict | None) -> int:
    if not pokemon:
        return 0
    return max(1, int(pokemon.get('pokeball_slots', 1)))


def team_slot_usage(player: dict) -> int:
    usage = sum(pokemon_slot_cost(pokemon) for pokemon in player.get('pokemon', []))
    usage += pokemon_slot_cost(player.get('starter_pokemon'))
    return usage


def total_item_count(player: dict) -> int:
    return sum(max(0, int(item.get('quantity', 0))) for item in _ensure_normalized_item_list(player))


def get_item_quantity(player: dict, item_key: str) -> int:
    for item in _ensure_normalized_item_list(player):
        if item.get('key') == item_key:
            return max(0, int(item.get('quantity', 0)))
    return 0


def add_item(player: dict, item_key: str, quantity: int = 1, name: str | None = None) -> None:
    if quantity <= 0:
        return

    for item in _ensure_normalized_item_list(player):
        if item.get('key') == item_key:
            current_quantity = max(0, int(item.get('quantity', 0)))
            if item_key == 'full_restore':
                current_quantity = max(current_quantity, int(player.get('full_restores', 0)))
            item['quantity'] = current_quantity + quantity
            sync_player_inventory(player)
            return

    player.setdefault('items', []).append({
        'key': item_key,
        'name': name or ITEM_DEFS.get(item_key, {}).get('name') or item_key,
        'quantity': quantity,
        'image_path': ITEM_DEFS.get(item_key, {}).get('image_path'),
        'category': ITEM_DEFS.get(item_key, {}).get('category'),
        'effect': ITEM_DEFS.get(item_key, {}).get('effect'),
        'implemented': ITEM_DEFS.get(item_key, {}).get('implemented', False),
        'notes': ITEM_DEFS.get(item_key, {}).get('notes'),
    })
    sync_player_inventory(player)


def remove_item(player: dict, item_key: str, quantity: int = 1) -> bool:
    if quantity <= 0:
        return False

    removed = False
    next_items = []
    for item in _ensure_normalized_item_list(player):
        if item.get('key') != item_key:
            next_items.append(item)
            continue

        current_quantity = max(0, int(item.get('quantity', 0)))
        if item_key == 'full_restore':
            current_quantity = max(current_quantity, int(player.get('full_restores', 0)))
        new_quantity = max(0, current_quantity - quantity)
        removed = current_quantity > 0
        if new_quantity > 0:
            next_items.append({**item, 'quantity': new_quantity})

    player['items'] = next_items
    sync_player_inventory(player)
    return removed


def sync_player_inventory(player: dict) -> dict:
    player['items'] = normalize_items(player.get('items'), player.get('full_restores', 0))
    player['item_capacity'] = ITEM_CAPACITY
    player['item_count'] = total_item_count(player)
    player['full_restores'] = get_item_quantity(player, 'full_restore')
    player['pokeball_slots_used'] = team_slot_usage(player)
    player['pokeball_slots_free'] = max(0, int(player.get('pokeballs', 0)))
    player['pokeball_capacity'] = player['pokeball_slots_used'] + player['pokeball_slots_free']

    pokemon_inventory = []
    if player.get('starter_pokemon'):
        sync_pokemon_ability_state(player['starter_pokemon'])
        pokemon_inventory.append({
            **copy.deepcopy(player['starter_pokemon']),
            'is_starter_slot': True,
            'slot_key': 'starter',
            'slot_cost': pokemon_slot_cost(player['starter_pokemon']),
        })
    for index, pokemon in enumerate(player.get('pokemon', [])):
        sync_pokemon_ability_state(pokemon)
        pokemon_inventory.append({
            **copy.deepcopy(pokemon),
            'is_starter_slot': False,
            'slot_key': f'pokemon:{index}',
            'slot_cost': pokemon_slot_cost(pokemon),
        })
    player['pokemon_inventory'] = pokemon_inventory
    return player
