"""
Gerenciamento do tabuleiro: tiles, movimentação e efeitos.
"""
import json
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent / 'data'


def load_board() -> dict:
    with open(_DATA_DIR / 'board.json', encoding='utf-8') as f:
        return json.load(f)


def get_tile(board_data: dict, position: int) -> dict:
    tiles = board_data.get('tiles', [])
    if 0 <= position < len(tiles):
        return tiles[position]
    return tiles[-1]  # última casa (Pokemon League)


def get_total_tiles(board_data: dict) -> int:
    return len(board_data.get('tiles', []))


def calculate_new_position(current_position: int, dice_roll: int, board_data: dict) -> int:
    total = get_total_tiles(board_data)
    new_pos = current_position + dice_roll
    # Não ultrapassa a última casa
    return max(0, min(new_pos, total - 1))


def get_positions_between(start_position: int, end_position: int) -> list[int]:
    if end_position == start_position:
        return []
    step = 1 if end_position > start_position else -1
    return list(range(start_position + step, end_position + step, step))


def get_path_positions(current_position: int, dice_roll: int, board_data: dict) -> list[int]:
    final_position = calculate_new_position(current_position, dice_roll, board_data)
    return get_positions_between(current_position, final_position)


def get_tile_effect(tile: dict) -> dict:
    """
    Retorna o efeito que deve ser executado ao cair na casa.
    Tipos de efeito:
      - grass:   jogador pode capturar Pokémon
      - event:   compra carta de evento
      - duel:    pode desafiar outro jogador
      - gym:     batalha automática contra líder
      - city:    efeito especial (descanso, loja, etc.)
      - special: efeito único descrito na casa
      - league:  fase final (Elite Four)
      - start:   sem efeito
    """
    tile_type = tile.get('type', 'grass')
    return {
        'type': tile_type,
        'name': tile.get('name', ''),
        'description': tile.get('description', ''),
        'data': tile.get('data', {}),
    }


def get_gym_tiles(board_data: dict) -> list:
    return [t for t in board_data.get('tiles', []) if t.get('type') == 'gym']


def find_previous_pokemon_center_tile(board_data: dict, before_position: int) -> dict | None:
    for position in range(max(0, before_position - 1), -1, -1):
        tile = get_tile(board_data, position)
        data = tile.get('data', {})
        if tile.get('type') == 'city' and data.get('city_kind') == 'pokemon_center':
            return tile
    return None


def get_tile_by_name(board_data: dict, name: str) -> dict | None:
    for tile in board_data.get('tiles', []):
        if tile.get('name') == name:
            return tile
    return None
