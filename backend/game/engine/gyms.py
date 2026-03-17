"""
Helpers de dados e montagem de batalhas de ginasio.
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

from .cards import load_pokemon_by_name, load_playable_pokemon_by_name

_DATA_PATH = Path(__file__).resolve().parent.parent / 'data' / 'gym_leaders.json'


@lru_cache(maxsize=1)
def load_gym_registry() -> dict[str, dict]:
    payload = json.loads(_DATA_PATH.read_text(encoding='utf-8'))
    gyms = payload.get('gyms') or []
    registry: dict[str, dict] = {}
    for gym in gyms:
        gym_copy = copy.deepcopy(gym)
        gym_copy.setdefault('leader_team', [])
        registry[gym_copy['id']] = gym_copy
    return registry


def list_gym_definitions() -> list[dict]:
    return [copy.deepcopy(gym) for gym in load_gym_registry().values()]


def get_gym_definition(*, gym_id: str | None = None, tile_id: int | None = None) -> dict | None:
    registry = load_gym_registry()
    if gym_id:
        gym = registry.get(gym_id)
        return copy.deepcopy(gym) if gym else None

    if tile_id is None:
        return None

    for gym in registry.values():
        if int(gym.get('tile_id', -1)) == int(tile_id):
            return copy.deepcopy(gym)
    return None


def _build_leader_pokemon(entry: dict, team_index: int) -> dict:
    pokemon_name = entry.get('name') or f'Pokemon {team_index + 1}'
    card = load_playable_pokemon_by_name(pokemon_name) or load_pokemon_by_name(pokemon_name)
    pokemon = copy.deepcopy(card) if card else {
        'id': f'gym-{team_index}-{pokemon_name.lower().replace(" ", "-")}',
        'name': pokemon_name,
        'types': [str(poke_type).title() for poke_type in entry.get('types', [])],
        'battle_points': int(entry.get('battle_points', 1) or 1),
        'master_points': 0,
        'ability': 'none',
        'ability_type': 'none',
        'battle_effect': None,
        'image_path': None,
    }
    pokemon['battle_points'] = int(entry.get('battle_points', pokemon.get('battle_points', 1)) or 1)
    pokemon['types'] = [str(poke_type).title() for poke_type in (entry.get('types') or pokemon.get('types') or [])]
    pokemon['gym_team_index'] = team_index
    pokemon['battle_slot_key'] = f'leader:{team_index}'
    pokemon['knocked_out'] = False
    return pokemon


def build_gym_leader_team(gym_definition: dict) -> list[dict]:
    team = gym_definition.get('leader_team') or []
    return [_build_leader_pokemon(entry, index) for index, entry in enumerate(team)]
