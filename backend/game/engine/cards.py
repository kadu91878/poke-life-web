"""
Gerenciamento dos baralhos reais de Pokémon, Evento e Vitória.
"""
from __future__ import annotations

import copy
import json
import random
import re
from functools import lru_cache
from pathlib import Path

from .inventory import add_item, remove_item, sync_player_inventory
from .pokemon_abilities import adjust_primary_ability_charges

_DATA_DIR = Path(__file__).resolve().parent.parent / 'data'
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_CARD_METADATA_PATH = _PROJECT_ROOT / 'backend' / 'cards_metadata.json'

_CARD_PUBLIC_PATHS = {
    'event': '/assets/cards/events',
    'victory': '/assets/cards/victory',
}
_POKEMON_PUBLIC_PATH = '/assets/pokemon'

_NAME_ALIASES = {
    'farfetchd': 'farfetch d',
    'm fossil': 'mysterious fossil',
    'm fossil.': 'mysterious fossil',
    'nidoranf': 'nidoran female',
    'nidoranm': 'nidoran male',
    'diglet': 'diglett',
    'sellder': 'shellder',
}

_NEGATIVE_EVENT_EFFECTS = frozenset({
    'lose_pokeball', 'lose_full_restore', 'lose_master_points',
    'move_backward', 'teleport_start',
})

_AMBIGUOUS_MARKET_REWARDS = frozenset({'wind item icon', 'boy icon item'})
_FOSSIL_ALIASES = frozenset({'m. fossil', 'm fossil', 'mysterious fossil'})


def _public_card_image(pile: str, reference_image: str | None) -> str | None:
    if not reference_image:
        return None
    base = _CARD_PUBLIC_PATHS.get(pile)
    if not base:
        return None
    return f'{base}/{reference_image}'


@lru_cache(maxsize=1)
def load_cards_metadata() -> list[dict]:
    try:
        data = json.loads(_CARD_METADATA_PATH.read_text(encoding='utf-8'))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    cards = data.get('cards', []) if isinstance(data, dict) else []
    return [card for card in cards if isinstance(card, dict)]


@lru_cache(maxsize=1)
def load_cards_metadata_index() -> dict[str, dict]:
    index: dict[str, dict] = {}
    for card in load_cards_metadata():
        for key in _metadata_lookup_keys(card):
            index[key] = copy.deepcopy(card)
    return index


def _normalize_pokemon_name(name: str) -> str:
    normalized = str(name or '').strip().lower()
    normalized = normalized.replace('♀', ' female').replace('♂', ' male')
    normalized = normalized.replace('_', ' ').replace('-', ' ')
    normalized = normalized.replace("'", ' ').replace('.', ' ').replace("`", ' ')
    normalized = re.sub(r'\s+', ' ', normalized)
    normalized = normalized.strip()
    return _NAME_ALIASES.get(normalized, normalized)


def _metadata_lookup_keys(card: dict) -> set[str]:
    keys: set[str] = set()
    for raw in (
        card.get('real_name'),
        card.get('current_name'),
        card.get('id'),
    ):
        normalized = _normalize_pokemon_name(str(raw or ''))
        if normalized:
            keys.add(normalized)
    for raw in card.get('aliases') or []:
        normalized = _normalize_pokemon_name(str(raw or ''))
        if normalized:
            keys.add(normalized)
    return keys


def _coerce_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _runtime_image_path(card: dict) -> str | None:
    if 'image_path' in card:
        explicit = card.get('image_path')
        if isinstance(explicit, str) and explicit.startswith('/assets/'):
            return explicit
        return None
    reference_image = card.get('reference_image')
    if not reference_image:
        return None
    return f'{_POKEMON_PUBLIC_PATH}/{reference_image}'


def _metadata_to_pokemon(card: dict) -> dict:
    raw_name = card.get('real_name') or card.get('current_name') or card.get('id') or 'Unknown'
    printed_power = card.get('power')
    runtime_battle_points = printed_power if printed_power is not None else card.get('engine_battle_points')
    return {
        'id': card.get('id') or raw_name.lower().replace(' ', '_'),
        'pokedex_id': card.get('engine_pokedex_id'),
        'name': raw_name,
        'types': [str(poke_type).title() for poke_type in (card.get('engine_types') or card.get('types') or [])],
        'battle_points': max(1, _coerce_int(runtime_battle_points, 1)),
        'master_points': max(0, _coerce_int(card.get('points'), 0)),
        'ability': card.get('engine_ability_name') or card.get('ability') or 'none',
        'ability_description': card.get('ability_description', ''),
        'ability_type': card.get('ability_type', 'passive') or 'passive',
        'evolves_to': card.get('evolves_to') or None,
        'evolution_method': card.get('evolution_method'),
        'is_starter': bool(card.get('is_initial')),
        'is_legendary': bool(card.get('engine_is_legendary') or card.get('is_legendary')),
        'is_baby': bool(card.get('engine_is_baby') or card.get('is_baby')),
        'rarity': card.get('engine_rarity') or card.get('rarity') or ('legendary' if card.get('engine_is_legendary') else 'unknown'),
        'battle_effect': card.get('engine_battle_effect') or card.get('battle_effect'),
        'ability_charges': card.get('charges'),
        'ability_charges_total': card.get('charges'),
        'can_battle': printed_power is not None or card.get('engine_battle_points') is not None,
        'printed_power': printed_power,
        'reference_image': card.get('reference_image'),
        'image_path': _runtime_image_path(card),
        'source_image_path': card.get('source_image_path'),
        'pokeball_slots': max(1, _coerce_int(card.get('engine_pokeball_slots', card.get('pokeball_slots', 1)), 1)),
    }


@lru_cache(maxsize=1)
def load_pokemon_cards() -> list[dict]:
    cards = [_metadata_to_pokemon(card) for card in load_cards_metadata()]
    for card in cards:
        card.setdefault('pokeball_slots', 1)
    return cards


@lru_cache(maxsize=1)
def load_pokemon_card_index() -> dict[str, dict]:
    index: dict[str, dict] = {}
    for card in load_pokemon_cards():
        lookup_keys = {
            _normalize_pokemon_name(card.get('name', '')),
            _normalize_pokemon_name(str(card.get('id', ''))),
        }
        pokedex_id = card.get('pokedex_id')
        if pokedex_id is not None:
            lookup_keys.add(str(pokedex_id))
        for key in lookup_keys:
            if key:
                index[key] = copy.deepcopy(card)
    return index


def load_pokemon_by_id(pokemon_id) -> dict | None:
    normalized = _normalize_pokemon_name(str(pokemon_id or ''))
    card = load_pokemon_card_index().get(normalized)
    return copy.deepcopy(card) if card else None


def has_pokemon_metadata(name: str) -> bool:
    normalized = _normalize_pokemon_name(name)
    return normalized in load_cards_metadata_index()


def load_playable_pokemon_by_name(name: str) -> dict | None:
    normalized = _normalize_pokemon_name(name)
    base = load_pokemon_card_index().get(normalized)
    if base:
        return copy.deepcopy(base)
    return None


def load_pokemon_by_name(name: str, *, allow_metadata_fallback: bool = True) -> dict | None:
    del allow_metadata_fallback
    return load_playable_pokemon_by_name(name)


def list_debug_pokemon_defs() -> list[dict]:
    catalog = []
    for card in sorted(load_pokemon_cards(), key=lambda entry: str(entry.get('name') or '').lower()):
        catalog.append({
            'id': card.get('id'),
            'name': card.get('name'),
            'types': copy.deepcopy(card.get('types') or []),
            'battle_points': card.get('battle_points'),
            'master_points': card.get('master_points'),
            'slot_cost': card.get('pokeball_slots', 1),
            'is_legendary': bool(card.get('is_legendary')),
            'image_path': card.get('image_path'),
        })
    return catalog


def get_supported_pokemon_details(pokemon_or_name: str | dict | None) -> dict:
    if isinstance(pokemon_or_name, dict):
        pokemon_name = pokemon_or_name.get('name') or pokemon_or_name.get('id')
    else:
        pokemon_name = pokemon_or_name

    playable = None
    if isinstance(pokemon_or_name, dict):
        playable = canonicalize_runtime_pokemon(pokemon_or_name)
    elif pokemon_name:
        playable = load_playable_pokemon_by_name(pokemon_name)
    metadata_exists = has_pokemon_metadata(str(pokemon_name or ''))
    return {
        'pokemon_name': pokemon_name,
        'metadata_exists': metadata_exists,
        'playable_exists': playable is not None,
        'supported': playable is not None,
    }


_RUNTIME_MUTABLE_FIELDS = {
    'ability_charges',
    'ability_runtime',
    'ability_used',
    'battle_slot_key',
    'capture_context',
    'capture_sequence',
    'acquisition_origin',
    'gym_team_index',
    'is_starter_slot',
    'knocked_out',
    'pluspower_applied',
    'slot_cost',
}


def canonicalize_runtime_pokemon(pokemon: dict | None) -> dict | None:
    if not isinstance(pokemon, dict):
        return None

    base = None
    if pokemon.get('name'):
        base = load_playable_pokemon_by_name(pokemon['name'])
    if base is None and pokemon.get('id') is not None:
        base = load_pokemon_by_id(pokemon['id'])
    if base is None:
        return None

    canonical = copy.deepcopy(base)
    for key, value in pokemon.items():
        if key not in canonical or key in _RUNTIME_MUTABLE_FIELDS:
            canonical[key] = copy.deepcopy(value)
    return canonical


def ensure_supported_inventory_pokemon(pokemon: dict | None) -> tuple[dict | None, dict]:
    support = get_supported_pokemon_details(pokemon)
    if not support['supported'] or not isinstance(pokemon, dict):
        return None, support
    canonical = canonicalize_runtime_pokemon(pokemon)
    if canonical is None:
        return None, support
    return canonical, support


def resolve_supported_pokemon_reward(name: str) -> tuple[dict | None, dict]:
    support = get_supported_pokemon_details(name)
    pokemon = load_playable_pokemon_by_name(name) if support['supported'] else None
    return pokemon, support


def get_starters() -> list:
    cards = load_pokemon_cards()
    return [copy.deepcopy(p) for p in cards if p.get('is_starter')]


def build_pokemon_deck(exclude_starters: bool = True) -> list:
    cards = load_pokemon_cards()
    if exclude_starters:
        cards = [p for p in cards if not p.get('is_starter')]
    deck = [copy.deepcopy(card) for card in cards]
    random.shuffle(deck)
    return deck


def _load_card_collection(path: Path, list_key: str, pile: str) -> list[dict]:
    data = json.loads(path.read_text(encoding='utf-8'))
    cards = data.get(list_key, []) if isinstance(data, dict) else []
    normalized: list[dict] = []
    for card in cards:
        if card.get('category') == 'background':
            continue
        entry = copy.deepcopy(card)
        entry['pile'] = pile
        entry['image_path'] = _public_card_image(pile, entry.get('reference_image'))
        normalized.append(entry)
    return normalized


def load_event_cards() -> list:
    return _load_card_collection(_DATA_DIR / 'event_pile_metadata.json', 'events', 'event')


def load_victory_cards() -> list:
    return _load_card_collection(_DATA_DIR / 'victory_pile_metadata.json', 'victories', 'victory')


def build_event_deck() -> list:
    deck = load_event_cards()
    random.shuffle(deck)
    return deck


def build_victory_deck() -> list:
    deck = load_victory_cards()
    random.shuffle(deck)
    return deck


def draw_card(deck: list, discard: list) -> tuple[dict | None, list, list]:
    """
    Compra uma carta do topo do baralho.
    Se o baralho estiver vazio, recicla o descarte.
    Retorna (carta, novo_deck, novo_descarte).
    """
    if not deck:
        if not discard:
            return None, [], []
        deck = list(discard)
        random.shuffle(deck)
        discard = []

    card = deck.pop(0)
    return card, deck, discard


def append_to_discard(discard: list, card: dict | None) -> list:
    next_discard = list(discard)
    if card:
        next_discard.append(copy.deepcopy(card))
    return next_discard


def reveal_card(state: dict, player_id: str, card: dict, deck_type: str, *, resolved: bool = False) -> dict:
    players = state.get('players', [])
    player = next((p for p in players if p['id'] == player_id), None)
    state['revealed_card'] = {
        'deck_type': deck_type,
        'card': copy.deepcopy(card),
        'player_id': player_id,
        'player_name': player.get('name') if player else '',
        'resolved': resolved,
    }
    return state


def clear_revealed_card(state: dict) -> dict:
    state['revealed_card'] = None
    return state


def _parse_rolls(text: str) -> list[int]:
    text = (text or '').strip()
    if not text:
        return []
    if '/' in text:
        start, end = [int(part) for part in text.split('/', 1)]
        return list(range(start, end + 1))
    values: list[int] = []
    for part in text.split(','):
        part = part.strip()
        if part.isdigit():
            values.append(int(part))
    return values


def _wild_pokemon_title_name(card: dict) -> str:
    title = (card.get('title') or '').strip()
    if title.lower().startswith('wild pokémon '):
        title = title[len('Wild Pokémon '):]
    elif title.lower().startswith('wild pokemon '):
        title = title[len('Wild Pokemon '):]
    return title.strip()


def _resolve_single_wild_capture_card(card: dict) -> dict:
    description = card.get('description', '')
    title_name = _wild_pokemon_title_name(card)

    if '♂' in description and '♀' in description:
        roll = random.randint(1, 6)
        if roll in _parse_rolls('3,4'):
            return {'success': True, 'pokemon_name': 'Nidoran Male', 'rolls': [roll]}
        if roll in _parse_rolls('1,2'):
            return {'success': True, 'pokemon_name': 'Nidoran Female', 'rolls': [roll]}
        return {'success': False, 'rolls': [roll]}

    roll_match = re.search(r'capture this pokémon!\s*([0-9,/\s]+)', description, re.IGNORECASE)
    if not roll_match:
        roll_match = re.search(r'capture this pokemon!\s*([0-9,/\s]+)', description, re.IGNORECASE)
    allowed = _parse_rolls(roll_match.group(1)) if roll_match else []

    roll = random.randint(1, 6)
    return {
        'success': roll in allowed,
        'pokemon_name': title_name,
        'rolls': [roll],
    }


def parse_single_wild_capture_card(card: dict, rolls: list[int]) -> dict:
    description = card.get('description', '')
    title_name = _wild_pokemon_title_name(card)
    if not rolls:
        return {'success': False, 'rolls': []}

    first_roll = int(rolls[0])
    if '♂' in description and '♀' in description:
        if first_roll in _parse_rolls('3,4'):
            return {'success': True, 'pokemon_name': 'Nidoran Male', 'rolls': [first_roll]}
        if first_roll in _parse_rolls('1,2'):
            return {'success': True, 'pokemon_name': 'Nidoran Female', 'rolls': [first_roll]}
        return {'success': False, 'rolls': [first_roll]}

    roll_match = re.search(r'capture this pokémon!\s*([0-9,/\s]+)', description, re.IGNORECASE)
    if not roll_match:
        roll_match = re.search(r'capture this pokemon!\s*([0-9,/\s]+)', description, re.IGNORECASE)
    allowed = _parse_rolls(roll_match.group(1)) if roll_match else []
    return {
        'success': first_roll in allowed,
        'pokemon_name': title_name,
        'rolls': [first_roll],
        'allowed_rolls': allowed,
    }


def _resolve_choice_pack_card(card: dict) -> dict:
    description = card.get('description', '')
    first_roll = random.randint(1, 6)
    rolls = [first_roll]

    for match in re.finditer(r'If the first roll is\s+([0-9])\,\s*roll again:\s*([^.]*)\.', description, re.IGNORECASE):
        trigger = int(match.group(1))
        if first_roll != trigger:
            continue

        second_roll = random.randint(1, 6)
        rolls.append(second_roll)
        branch = match.group(2)
        for option in re.finditer(r'([0-9,/]+)\s*=\s*([^;]+)', branch):
            if second_roll in _parse_rolls(option.group(1)):
                pokemon_name = option.group(2).strip()
                if pokemon_name.lower() in _FOSSIL_ALIASES:
                    return {'success': False, 'unsupported_reward': pokemon_name, 'rolls': rolls}
                return {'success': True, 'pokemon_name': pokemon_name, 'rolls': rolls}
        return {'success': False, 'rolls': rolls}

    return {'success': False, 'rolls': rolls}


def parse_choice_pack_card(card: dict, rolls: list[int]) -> dict:
    description = card.get('description', '')
    if not rolls:
        return {'success': False, 'rolls': []}

    first_roll = int(rolls[0])
    used_rolls = [first_roll]

    for match in re.finditer(r'If the first roll is\s+([0-9])\,\s*roll again:\s*([^.]*)\.', description, re.IGNORECASE):
        trigger = int(match.group(1))
        if first_roll != trigger:
            continue

        if len(rolls) < 2:
            return {'success': False, 'rolls': used_rolls, 'requires_additional_roll': True}

        second_roll = int(rolls[1])
        used_rolls.append(second_roll)
        branch = match.group(2)
        for option in re.finditer(r'([0-9,/]+)\s*=\s*([^;]+)', branch):
            if second_roll in _parse_rolls(option.group(1)):
                pokemon_name = option.group(2).strip()
                if pokemon_name.lower() in _FOSSIL_ALIASES:
                    return {'success': False, 'unsupported_reward': pokemon_name, 'rolls': used_rolls}
                return {'success': True, 'pokemon_name': pokemon_name, 'rolls': used_rolls}
        return {'success': False, 'rolls': used_rolls}

    return {'success': False, 'rolls': used_rolls}


def resolve_wild_pokemon_card(card: dict) -> dict:
    category = card.get('category')
    if category == 'wild_pokemon_choice':
        return _resolve_choice_pack_card(card)
    return _resolve_single_wild_capture_card(card)


def resolve_wild_pokemon_card_from_rolls(card: dict, rolls: list[int]) -> dict:
    category = card.get('category')
    if category == 'wild_pokemon_choice':
        return parse_choice_pack_card(card, rolls)
    return parse_single_wild_capture_card(card, rolls)


def parse_gift_pokemon_choice_options(card: dict) -> tuple[list[dict], list[str]]:
    description = card.get('description', '')
    text = description.split('!', 1)[-1] if '!' in description else description
    raw_options = [part.strip().strip('.') for part in text.split(',') if part.strip()]
    options: list[dict] = []
    unsupported: list[str] = []
    for name in raw_options:
        pokemon, support = resolve_supported_pokemon_reward(name)
        if not support['supported']:
            unsupported.append(name)
            continue
        options.append({
            'id': support['pokemon_name'],
            'label': pokemon['name'],
            'pokemon_name': pokemon['name'],
        })
    return options, unsupported


def build_trainer_battle_context(card: dict) -> dict:
    description = (card.get('description') or '').lower()
    trainer_name = (card.get('title') or 'Trainer').replace('Trainer ', '').strip()

    reward_plan = {
        'victory_cards': 0,
        'master_points': 0,
        'extra_turn': False,
        'recharge_ability_charge': False,
        'repeat_battle': False,
        'max_battles': 1,
    }
    if 'two victory cards' in description or '2 victory cards' in description:
        reward_plan['victory_cards'] = 2
    elif 'draw a victory card' in description or 'draw one victory card' in description:
        reward_plan['victory_cards'] = 1

    if '20 master points' in description:
        reward_plan['master_points'] = 20
    elif '10 master points' in description:
        reward_plan['master_points'] = 10

    reward_plan['extra_turn'] = 'additional turn' in description or 'extra turn' in description
    reward_plan['recharge_ability_charge'] = 'recharge one ability charge' in description
    if 'battle him again' in description:
        reward_plan['repeat_battle'] = True
        reward_plan['max_battles'] = 4 if 'four times' in description else 2

    return {
        'trainer_name': trainer_name,
        'trainer_bp': 3,
        'reward_plan': reward_plan,
        'card_title': card.get('title', 'Trainer Battle'),
        'card_category': card.get('category'),
        'card_description': card.get('description', ''),
    }


def parse_market_reward(card: dict) -> dict:
    description = card.get('description', '')
    roll = random.randint(1, 6)

    mapping: list[tuple[list[int], str]] = []
    for dice, reward in re.findall(r'([0-9,/]+)\s*=\s*([^,.]+)', description):
        mapping.append((_parse_rolls(dice), reward.strip()))

    reward_name = None
    for rolls, candidate in mapping:
        if roll in rolls:
            reward_name = candidate
            break

    normalized = (reward_name or '').strip()
    if normalized.lower() == 'pokéball' or normalized.lower() == 'pokeball':
        return {'type': 'gain_pokeball', 'amount': 1, 'rolls': [roll]}
    if normalized.lower() == 'bill':
        return {'type': 'gain_item', 'item_key': 'bill', 'amount': 1, 'rolls': [roll]}
    if normalized.lower() == 'pluspower':
        return {'type': 'gain_item', 'item_key': 'pluspower', 'amount': 1, 'rolls': [roll]}
    if normalized.lower() == 'master points nugget':
        return {'type': 'gain_item', 'item_key': 'master_points_nugget', 'amount': 1, 'rolls': [roll]}
    if normalized.lower() == 'miracle stone':
        return {'type': 'gain_item', 'item_key': 'miracle_stone', 'amount': 1, 'rolls': [roll]}
    if normalized.lower() == 'defender':
        return {'type': 'gain_item', 'item_key': 'defender', 'amount': 1, 'rolls': [roll]}
    if normalized.lower() in _AMBIGUOUS_MARKET_REWARDS:
        return {'type': 'unsupported_reward', 'reward_name': normalized, 'rolls': [roll]}
    return {'type': 'unsupported_reward', 'reward_name': normalized or 'unknown', 'rolls': [roll]}


def parse_victory_item_reward(card: dict, state: dict, player_id: str) -> list[dict]:
    description = card.get('description', '')
    rewards: list[dict] = []

    if 'more Pokéballs than you' in description or 'more Pokeballs than you' in description:
        players = [p for p in state.get('players', []) if p.get('id') != player_id and p.get('is_active', True)]
        me = next((p for p in state.get('players', []) if p['id'] == player_id), None)
        if me and any((p.get('pokeballs', 0) > me.get('pokeballs', 0)) for p in players):
            rewards.append({'type': 'gain_pokeball', 'amount': 1})
        else:
            rewards.append({'type': 'gain_item', 'item_key': 'miracle_stone', 'amount': 1})
        return rewards

    item_map = {
        'full restore': 'full_restore',
        'gust of wind': 'gust_of_wind',
        'pluspower': 'pluspower',
        'defender': 'defender',
        'bill': 'bill',
        'prof. oak': 'prof_oak',
    }
    for text, key in item_map.items():
        if text in description.lower():
            rewards.append({'type': 'gain_item', 'item_key': key, 'amount': 1})
    return rewards


def parse_master_points(description: str) -> int | None:
    match = re.search(r'(\d+)\s+Master Points', description, re.IGNORECASE)
    return int(match.group(1)) if match else None


def apply_simple_reward(state: dict, player: dict, reward: dict) -> None:
    reward_type = reward.get('type')
    if reward_type == 'gain_pokeball':
        player['pokeballs'] += int(reward.get('amount', 1) or 1)
        sync_player_inventory(player)
        return
    if reward_type == 'gain_item':
        add_item(player, reward.get('item_key', ''), int(reward.get('amount', 1) or 1))
        sync_player_inventory(player)
        return
    if reward_type == 'gain_master_points':
        player['master_points'] += int(reward.get('amount', 0) or 0)
        sync_player_inventory(player)


def event_card_effect_type(card: dict) -> str:
    category = card.get('category')
    if category == 'event':
        description = (card.get('description') or '').lower()
        if 'skip your next turn' in description:
            return 'skip_next_turn'
        if 'run three tiles back' in description:
            return 'move_backward_trigger'
        if 'throw away an item' in description:
            return 'all_discard_item'
        if 'loses a charge' in description:
            return 'lose_ability_charge'
        if 'knocking out 2 of your pokémon' in description or 'knocking out 2 of your pokemon' in description:
            return 'knock_out_two_pokemon'
    if category == 'team_rocket':
        description = (card.get('description') or '').lower()
        if 'steal two of your items' in description:
            return 'steal_two_items'
        if 'steal 20 of your master points' in description:
            return 'steal_master_points'
        if 'run five tiles forward' in description:
            return 'move_forward_trigger'
    return category or 'none'


def is_negative_event_card(card: dict) -> bool:
    effect_type = event_card_effect_type(card)
    return effect_type in _NEGATIVE_EVENT_EFFECTS or effect_type in {
        'skip_next_turn', 'move_backward_trigger', 'steal_two_items', 'steal_master_points',
        'lose_ability_charge', 'knock_out_two_pokemon',
    }


def apply_event_effect(state: dict, player_id: str, card: dict) -> tuple[dict, dict]:
    """
    Aplica o efeito de uma carta de evento já revelada.
    Retorna (state, result_dict) com metadados de resolução.
    """
    player = next((p for p in state['players'] if p['id'] == player_id), None)
    if not player:
        return state, {'status': 'ignored', 'reason': 'player_not_found'}

    category = card.get('category')
    result: dict = {'category': category, 'status': 'applied'}

    if category == 'wild_pokemon':
        pokemon_name = _wild_pokemon_title_name(card)
        pokemon, support = resolve_supported_pokemon_reward(pokemon_name)
        result.update(support)
        result['effect'] = 'capture_attempt'
        if support['supported']:
            result['status'] = 'pending'
            result['capture_action'] = {
                'mode': 'known_pokemon',
                'pokemon_name': pokemon['name'],
                'capture_context': 'event_card',
                'allowed_rolls': parse_single_wild_capture_card(card, [1]).get('allowed_rolls', []),
                'source_card_id': card.get('id'),
                'source_card_title': card.get('title'),
            }
        else:
            result['status'] = 'partial'
        return state, result

    if category == 'market':
        reward = parse_market_reward(card)
        result.update(reward)
        if reward['type'] == 'unsupported_reward':
            result['status'] = 'partial'
            return state, result
        apply_simple_reward(state, player, reward)
        return state, result

    if category == 'special_event':
        title = (card.get('title') or '').lower()
        if title == 'breeder':
            result['effect'] = 'gift_pokemon_from_area'
            return state, result
        if title == 'teleporter':
            result['status'] = 'pending'
            result['effect'] = 'teleporter_choice'
            return state, result
        if title == 'mr. fuji':
            result['status'] = 'pending'
            result['effect'] = 'mr_fuji_choice'
            return state, result
        if title == 'pokécenter' or title == 'pokecenter':
            # "Heal as many Pokémon as you like" → restaura 1 Full Restore por Pokémon que o jogador possui
            all_pokemon = list(player.get('pokemon', []))
            if player.get('starter_pokemon'):
                all_pokemon.append(player['starter_pokemon'])
            healed = max(1, len(all_pokemon))
            add_item(player, 'full_restore', healed)
            sync_player_inventory(player)
            result['effect'] = 'pokecenter_heal'
            result['full_restores_given'] = healed
            return state, result
        if title == "oak's assistant":
            result['status'] = 'pending'
            result['effect'] = 'oak_assistant_choice'
            return state, result
        return state, result

    if category == 'event':
        effect_type = event_card_effect_type(card)
        result['effect'] = effect_type
        if effect_type == 'skip_next_turn':
            player['skip_turns'] = int(player.get('skip_turns', 0) or 0) + 1
            sync_player_inventory(player)
            return state, result
        if effect_type == 'move_backward_trigger':
            result['spaces'] = 3
            return state, result
        if effect_type == 'all_discard_item':
            players = [p for p in state['players'] if p.get('is_active', True)]
            affected = []
            for target in players:
                items = target.get('items', [])
                if not items:
                    continue
                item = sorted(items, key=lambda x: x.get('key', ''))[0]
                remove_item(target, item.get('key', ''), 1)
                affected.append(target['id'])
            result['affected_players'] = affected
            return state, result
        if effect_type == 'lose_ability_charge':
            all_pokemon = list(player.get('pokemon', []))
            if player.get('starter_pokemon'):
                all_pokemon.append(player['starter_pokemon'])
            affected = []
            for p in all_pokemon:
                previous = p.get('ability_charges')
                remaining = adjust_primary_ability_charges(p, -1)
                if remaining is not None and remaining != previous:
                    affected.append(p['name'])
                    break  # apenas 1 Pokémon perde a carga
            result['affected_pokemon'] = affected
            return state, result
        if effect_type == 'knock_out_two_pokemon':
            # Remove até 2 Pokémon da coleção (não o starter)
            pool = list(player.get('pokemon', []))
            removed = []
            for _ in range(2):
                if pool:
                    p = pool.pop(0)
                    removed.append(p.get('name', '?'))
            player['pokemon'] = pool
            sync_player_inventory(player)
            result['removed_pokemon'] = removed
            return state, result
        return state, result

    if category == 'team_rocket':
        effect_type = event_card_effect_type(card)
        roll = random.randint(1, 6)
        result['effect'] = effect_type
        result['rolls'] = [roll]
        if effect_type == 'steal_two_items':
            if roll <= 3:
                removed = 0
                for item in sorted(player.get('items', []), key=lambda x: x.get('key', '')):
                    if removed >= 2:
                        break
                    quantity = min(2 - removed, int(item.get('quantity', 0) or 0))
                    if quantity <= 0:
                        continue
                    remove_item(player, item['key'], quantity)
                    removed += quantity
                result['removed_items'] = removed
            return state, result
        if effect_type == 'steal_master_points':
            if roll <= 3:
                player['master_points'] = max(0, int(player.get('master_points', 0)) - 20)
            sync_player_inventory(player)
            return state, result
        if effect_type == 'move_forward_trigger':
            result['spaces'] = 5
            return state, result
        return state, result

    if category == 'trainer_battle':
        result['effect'] = 'trainer_battle'
        result['status'] = 'pending'
        result['trainer_battle_context'] = build_trainer_battle_context(card)
        return state, result

    return state, result


def apply_victory_effect(state: dict, player_id: str, card: dict) -> tuple[dict, dict]:
    player = next((p for p in state['players'] if p['id'] == player_id), None)
    if not player:
        return state, {'status': 'ignored', 'reason': 'player_not_found'}

    category = card.get('category')
    result: dict = {'category': category, 'status': 'applied'}
    description = card.get('description', '')

    if category == 'master_points':
        amount = parse_master_points(description) or 0
        player['master_points'] += amount
        sync_player_inventory(player)
        result['amount'] = amount
        return state, result

    if category == 'item_reward':
        rewards = parse_victory_item_reward(card, state, player_id)
        result['rewards'] = rewards
        for reward in rewards:
            apply_simple_reward(state, player, reward)
        return state, result

    if category == 'gift_pokemon':
        name_match = re.search(r'receive(?:\s+as many\s+)?\s+a?\s*([A-Za-z .\'-]+)!', description, re.IGNORECASE)
        if name_match:
            pokemon_name = name_match.group(1).strip()
            if pokemon_name.lower() == 'many magikarp as you want':
                pokemon_name = 'Magikarp'
            pokemon, support = resolve_supported_pokemon_reward(pokemon_name)
            result.update(support)
            if support['supported']:
                result['effect'] = 'capture_attempt'
                result['status'] = 'pending'
                result['capture_action'] = {
                    'mode': 'known_pokemon',
                    'pokemon_name': pokemon['name'],
                    'capture_context': 'victory_gift',
                    'allowed_rolls': [],
                    'source_card_id': card.get('id'),
                    'source_card_title': card.get('title'),
                }
            else:
                result['status'] = 'partial'
        return state, result

    if category == 'wild_pokemon':
        pokemon_name = _wild_pokemon_title_name(card)
        pokemon, support = resolve_supported_pokemon_reward(pokemon_name)
        result.update(support)
        result['effect'] = 'capture_attempt'
        if support['supported']:
            result['status'] = 'pending'
            result['capture_action'] = {
                'mode': 'known_pokemon',
                'pokemon_name': pokemon['name'],
                'capture_context': 'victory_wild',
                'allowed_rolls': parse_single_wild_capture_card(card, [1]).get('allowed_rolls', []),
                'source_card_id': card.get('id'),
                'source_card_title': card.get('title'),
            }
        else:
            result['status'] = 'partial'
        return state, result

    if category == 'wild_pokemon_choice':
        result['effect'] = 'capture_attempt'
        result['status'] = 'pending'
        result['capture_action'] = {
            'mode': 'choice_pack',
            'capture_context': 'victory_wild',
            'source_card_id': card.get('id'),
            'source_card_title': card.get('title'),
            'card': copy.deepcopy(card),
        }
        return state, result

    if category == 'gift_pokemon_choice':
        options, unsupported = parse_gift_pokemon_choice_options(card)
        result['effect'] = 'gift_pokemon_choice'
        result['options'] = options
        result['unsupported_options'] = unsupported
        result['status'] = 'pending' if options else 'partial'
        return state, result

    if category == 'trainer_battle':
        result['effect'] = 'trainer_battle'
        result['status'] = 'pending'
        result['trainer_battle_context'] = build_trainer_battle_context(card)
        return state, result

    if category == 'draw_event_cards':
        result['effect'] = 'draw_event_cards'
        result['draw_count'] = 3
        return state, result

    if category == 'draw_victory_cards':
        result['effect'] = 'draw_victory_cards'
        result['draw_count'] = 3
        return state, result

    if category == 'special_reward':
        result['status'] = 'partial'
        result['effect'] = 'special_reward_not_implemented'
        return state, result

    return state, result
