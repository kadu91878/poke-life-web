"""
Gerenciador central do estado do jogo.

Estrutura do game_state (JSON):
{
  "status": "waiting | playing | finished",
  "players": [ { id, name, color, is_host, position, pokeballs,
                  full_restores, starter_pokemon, pokemon,
                  badges, master_points, has_reached_league,
                  is_active, is_connected } ],
  "decks": {
    "pokemon_deck":    [...],
    "pokemon_discard": [...],
    "event_deck":      [...],
    "event_discard":   [...]
  },
  "board": { tiles: [...] },
  "turn": {
    "round":            int,
    "current_player_id": str,
    "phase": "select_starter | roll | action | battle | event | item_choice | release_pokemon | gym | league | end",
    "dice_result":      int | null,
    "last_roll":        dict | null,
    "roll_history":     [dict],
    "current_tile":     dict | null,
    "battle":           dict | null,
    "pending_event":    dict | null,
    "pending_pokemon":  dict | null,
    "pending_safari":   list | null,
    "starters_chosen":  [player_ids],
    "extra_turn":       bool,
    "compound_eyes_active": bool,
    "seafoam_legendary": bool,
    "capture_context":  str | null,  # 'safari' | 'mt_moon' | 'cinnabar' | 'seafoam' | 'power_plant' | 'mystery_cave' | 'bicycle_bridge' | null
  },
  "log": [ { round, player, message, timestamp } ]
}
"""
import copy
import random
from datetime import datetime, timezone

from .board import (
    load_board,
    calculate_new_position,
    get_positions_between,
    get_path_positions,
    get_tile,
    get_tile_effect,
)
from .cards import (
    append_to_discard,
    apply_event_effect,
    apply_victory_effect,
    build_event_deck,
    build_pokemon_deck,
    build_victory_deck,
    clear_revealed_card,
    draw_card,
    ensure_supported_inventory_pokemon,
    event_card_effect_type,
    get_starters,
    is_negative_event_card,
    load_pokemon_by_id,
    load_pokemon_by_name,
    load_playable_pokemon_by_name,
    load_cards_metadata_index,
    parse_gift_pokemon_choice_options,
    reveal_card,
    resolve_supported_pokemon_reward,
    resolve_wild_pokemon_card_from_rolls,
)
from .inventory import (
    ITEM_CAPACITY,
    add_item,
    get_starting_resource_defaults,
    get_item_quantity,
    get_item_def,
    list_debug_item_defs,
    pokemon_slot_cost,
    remove_item,
    sync_player_inventory,
    team_slot_usage,
    total_item_count,
)
from .gyms import build_gym_leader_team, get_gym_definition
from .mechanics import (
    can_evolve,
    resolve_duel,
    resolve_elite_four,
    roll_battle_dice,
    roll_capture_dice,
    roll_game_corner_dice,
    roll_movement_dice,
    roll_market_dice,
    roll_team_rocket_dice,
)
from .pokemon_abilities import (
    adjust_primary_ability_charges,
    annotate_state_ability_snapshots,
    build_move_roll_prompt_options,
    get_static_ability_definitions,
    mark_primary_ability_used,
    reset_player_ability_runtime,
    sync_pokemon_ability_state,
)

# Habilidades que se reiniciam a cada turno (demais são uma vez por partida)
_PER_TURN_ABILITIES = frozenset({'compound_eyes', 'run_away', 'psychic', 'solar_beam'})

# Efeitos de evento considerados negativos para Run Away
_NEGATIVE_EVENT_EFFECTS = frozenset({
    'lose_pokeball', 'lose_full_restore', 'lose_master_points',
    'move_backward', 'teleport_start',
})

# IDs dos Pokémon fósseis (Mt. Moon)
_FOSSIL_POKEMON_NAMES = ['Omanyte', 'Kabuto']
_MYSTERY_CAVE_POKEMON_NAMES = ['Gastly', 'Gastly', 'Haunter', 'Gengar', 'Ditto']
_MAX_ROLL_HISTORY = 50
_DEBUG_TEST_PLAYER_ID = '__debug_test_player__'
_DEBUG_TEST_PLAYER_NAME = 'Player de teste'
_HOST_TOOLS_LOG_PREFIX = '[HOST TOOLS]'
_DEBUG_TEST_PLAYER_COLOR = '#f59f00'
_SPECIAL_METHOD_EVOLUTION_NAMES = frozenset({
    'dratini',
    'eevee',
    'magikarp',
    'mankey',
    'slowpoke',
    'tyrogue',
})
_SPECIAL_METHOD_EVOLUTION_PHRASES = (
    'only evolve through battle',
    'cannot evolve mankey any other way',
    'if the outcome of your move dice is ever 6',
    'if you release another pokémon',
    'if you release another pokemon',
    'will evolve when you add another pokémon to your team',
    'will evolve when you add another pokemon to your team',
    'when evolving eevee',
    'when evolving slowpoke',
    'when evolving tyrogue',
)
_GAME_CORNER_PRIZES = (
    {'key': 'bill', 'label': 'Bill'},
    {'key': 'full_restore', 'label': 'Full Restore'},
    {'key': 'miracle_stone', 'label': 'Miracle Stone'},
    {'key': 'gold_nugget', 'label': 'Gold Nugget'},
    {'key': 'pokeball', 'label': 'Poké Ball'},
    {'key': 'master_ball', 'label': 'Master Ball'},
)
_POKEMART_PRIMARY_REWARDS = {
    1: {'key': 'gust_of_wind', 'label': 'Gust of Wind'},
    2: {'key': 'bill', 'label': 'Bill'},
    3: {'key': 'full_restore', 'label': 'Full Restore'},
    4: {'key': 'full_restore', 'label': 'Full Restore'},
    5: {'key': 'miracle_stone', 'label': 'Miracle Stone'},
}
_POKEMART_REROLL_REWARD = {'key': 'pokeball', 'label': 'Poké Ball'}
_POKEMART_JACKPOT_REWARD = {'key': 'master_ball', 'label': 'Master Ball'}
_ROLL_CONTEXT_LABELS = {
    'movement': 'movimento',
    'grass': 'grama',
    'safari': 'Safari Zone',
    'mt_moon': 'Mt. Moon',
    'power_plant': 'Usina Elétrica',
    'victory_wild': 'Victory Card',
    'victory_gift': 'Victory Card',
    'duel': 'duelo',
    'gym': 'ginásio',
    'team_rocket_tile': 'tile Equipe Rocket',
    'pokemart_tile': 'Poké-Mart',
    'game_corner': 'Game Corner',
}
_CARD_EFFECT_LOG_LABELS = {
    'trainer_battle': 'batalha de treinador',
    'capture_attempt': 'tentativa de captura',
    'gift_pokemon_choice': 'escolha de presente',
}
_FORCED_STOP_LOG_LABELS = {
    'team_rocket': 'Equipe Rocket',
    'teleporter': 'Teleporter',
    'gym': 'ginásio',
}


# ── Helpers internos ────────────────────────────────────────────────────────

def _log(state: dict, player_name: str, message: str):
    state.setdefault('log', []).append({
        'round': state.get('turn', {}).get('round', 0),
        'player': player_name,
        'message': message,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    })
    # Mantém apenas os últimos 100 logs
    state['log'] = state['log'][-100:]


def _log_warning(state: dict, player_name: str, message: str) -> None:
    _log(state, player_name, f'Aviso: {message}')


def _format_roll_context(context: str | None) -> str | None:
    if not context:
        return None
    return _ROLL_CONTEXT_LABELS.get(context, str(context).replace('_', ' '))


def _format_rolls_for_log(rolls: list[int] | tuple[int, ...] | None) -> str:
    values = [int(roll) for roll in (rolls or [])]
    return f"[{', '.join(str(roll) for roll in values)}]" if values else '[]'


def _describe_card_for_log(card: dict | None) -> str:
    card = card or {}
    title = card.get('title', 'Carta')
    category = card.get('category')
    return f'{title} [{category}]' if category else title


def _describe_card_result_for_log(result: dict | None) -> str:
    result = result or {}
    effect = result.get('effect')
    if effect in _CARD_EFFECT_LOG_LABELS:
        return _CARD_EFFECT_LOG_LABELS[effect]
    category = result.get('category')
    if category == 'draw_event_cards':
        count = int(result.get('draw_count', 0) or 0)
        return f'comprar {count} carta(s) de evento'
    if category == 'draw_victory_cards':
        count = int(result.get('draw_count', 0) or 0)
        return f'comprar {count} carta(s) de vitória'
    return 'efeito imediato resolvido'


def _describe_capture_cost_for_log(*, capture_cost: int, use_full_restore: bool, use_master_ball: bool) -> str:
    if use_master_ball:
        return 'Recurso usado: Master Ball'
    if use_full_restore:
        return 'Recurso usado: 1 Full Restore'
    if capture_cost <= 0:
        return 'Sem gasto de Pokébola'
    return f'Custo: {capture_cost} Pokébola(s)'


def _log_movement_resolution(
    state: dict,
    *,
    player_name: str,
    start_position: int,
    dice_result: int,
    natural_destination: int,
    resolved_destination: int,
    tile_name: str,
    forced_stop_kind: str | None,
) -> None:
    if forced_stop_kind:
        stop_label = _FORCED_STOP_LOG_LABELS.get(forced_stop_kind, forced_stop_kind)
        _log(
            state,
            player_name,
            f"Movimento: {start_position} -> {resolved_destination} com {dice_result}. "
            f"Parada forçada em {stop_label} na casa {tile_name} "
            f"(destino natural: {natural_destination}).",
        )
        return

    _log(
        state,
        player_name,
        f"Movimento: {start_position} -> {resolved_destination} com {dice_result}. Destino: {tile_name}.",
    )


def _build_roll_log_message(roll_entry: dict) -> tuple[str, str]:
    player_name = roll_entry.get('player_name') or 'Sistema'
    roll_type = roll_entry.get('roll_type', 'desconhecido')
    raw_result = roll_entry.get('raw_result')
    final_result = roll_entry.get('final_result')
    modifier = roll_entry.get('modifier')
    modifier_reason = roll_entry.get('modifier_reason')
    context_label = _format_roll_context(roll_entry.get('context'))

    message = f"Rolou dado de {roll_type}"
    if context_label and context_label.lower() != str(roll_type).lower():
        message += f" em {context_label}"
    message += f": {raw_result}"
    if modifier and raw_result != final_result:
        if modifier_reason:
            message += f", modificado para {final_result} por {modifier_reason}"
        else:
            message += f", modificado para {final_result}"
    else:
        message += f", resultado final: {final_result}"
    return player_name, message


def _record_roll(
    state: dict,
    *,
    roll_type: str,
    player_id: str | None,
    player_name: str,
    raw_result: int,
    final_result: int | None = None,
    modifier: dict | None = None,
    modifier_reason: str | None = None,
    context: str | None = None,
    metadata: dict | None = None,
    emit_log: bool = True,
) -> dict:
    final_value = raw_result if final_result is None else final_result
    roll_entry = {
        'roll_type': roll_type,
        'player_id': player_id,
        'player_name': player_name,
        'raw_result': int(raw_result),
        'final_result': int(final_value),
        'modifier': modifier,
        'modifier_reason': modifier_reason,
        'context': context,
        'metadata': metadata or {},
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
    state['turn'].setdefault('roll_history', []).append(roll_entry)
    state['turn']['roll_history'] = state['turn']['roll_history'][-_MAX_ROLL_HISTORY:]
    state['turn']['last_roll'] = roll_entry
    if emit_log:
        player_for_log, message = _build_roll_log_message(roll_entry)
        _log(state, player_for_log, message)
    return roll_entry


def host_tools_enabled(state: dict) -> bool:
    return bool((((state or {}).get('debug_visual') or {}).get('host_tools') or {}).get('enabled'))


def _get_host_tools_state(state: dict) -> dict:
    debug_visual = state.setdefault('debug_visual', {})
    host_tools = debug_visual.get('host_tools')
    if not isinstance(host_tools, dict):
        host_tools = {}
    return host_tools


def _set_host_tools_state(state: dict, host_tools: dict) -> dict:
    debug_visual = copy.deepcopy(state.get('debug_visual') or {})
    debug_visual['host_tools'] = copy.deepcopy(host_tools)
    state['debug_visual'] = debug_visual
    return state


def _clear_host_tools_pending_tile(state: dict, *, player_id: str | None = None) -> dict:
    host_tools = copy.deepcopy(_get_host_tools_state(state))
    pending = host_tools.get('pending_tile_trigger')
    if player_id is None or not isinstance(pending, dict) or pending.get('player_id') == player_id:
        host_tools['pending_tile_trigger'] = None
    return _set_host_tools_state(state, host_tools)


def _set_host_tools_pending_tile(state: dict, *, player_id: str, position: int, steps: int) -> dict:
    host_tools = copy.deepcopy(_get_host_tools_state(state))
    host_tools['pending_tile_trigger'] = {
        'player_id': player_id,
        'position': int(position),
        'steps': int(steps),
    }
    return _set_host_tools_state(state, host_tools)


def _require_host_tools_enabled(state: dict) -> str | None:
    if not host_tools_enabled(state):
        return 'O modo Host Tools está desabilitado'
    return None


def _apply_debug_pokemon_grant(state: dict, player: dict, pokemon_name: str, *, log_prefix: str) -> tuple[dict | None, str | dict]:
    pokemon_name = (pokemon_name or '').strip()
    if not pokemon_name:
        return None, 'pokemon_name é obrigatório'

    pokemon = load_pokemon_by_name(pokemon_name)
    if not pokemon:
        return None, f'Pokémon "{pokemon_name}" não foi encontrado no dataset atual'

    pokemon = _init_pokemon(pokemon)
    pokemon['types'] = [str(poke_type).title() for poke_type in pokemon.get('types', [])]
    pokemon['knocked_out'] = False
    _apply_pokemon_acquisition_metadata(
        pokemon,
        acquisition_origin='debug',
        capture_context='debug_add',
    )

    player.setdefault('pokemon', []).append(pokemon)
    player['pokeballs'] = max(0, int(player.get('pokeballs', 0)) - pokemon_slot_cost(pokemon))
    sync_player_inventory(player)

    _log(state, player['name'], f"{log_prefix} Adicionou {pokemon['name']} ao time.")
    return state, {
        'success': True,
        'pokemon': copy.deepcopy(pokemon),
        'slot_cost': pokemon_slot_cost(pokemon),
        'remaining_pokeball_slots': int(player.get('pokeballs', 0)),
    }


def _apply_pokemon_movement_roll_modifiers(
    state: dict,
    player: dict,
    raw_roll: int,
    current_final_roll: int,
) -> tuple[int, dict | None]:
    """
    Hook reservado para futuras habilidades que alteram o dado de movimento.
    No estado atual nao aplica nenhuma habilidade, apenas preserva o ponto de extensao.
    """
    _ = state, player, raw_roll
    return current_final_roll, None


def apply_movement_roll_modifiers(state: dict, player_id: str, raw_roll: int) -> tuple[dict, dict]:
    state = copy.deepcopy(state)
    player = _get_player(state, player_id)
    final_roll = int(raw_roll)
    modifier = None
    modifier_reason = None

    item_modifier = state.get('turn', {}).get('roll_item_modifier') or {}
    if item_modifier.get('player_id') == player_id:
        final_roll = max(0, final_roll + int(item_modifier.get('amount', 0)))
        item_key = item_modifier.get('item_key')
        item_name = get_item_def(item_key).get('name') or item_key
        modifier = {
            'source': 'item',
            'item_key': item_key,
            'amount': int(item_modifier.get('amount', 0)),
        }
        modifier_reason = item_name
        state['turn']['roll_item_modifier'] = None

    if player:
        final_roll, pokemon_modifier = _apply_pokemon_movement_roll_modifiers(
            state,
            player,
            int(raw_roll),
            final_roll,
        )
        if pokemon_modifier:
            modifier = pokemon_modifier
            modifier_reason = pokemon_modifier.get('source_name') or pokemon_modifier.get('source')

    return state, {
        'raw_result': int(raw_roll),
        'final_result': int(final_roll),
        'modifier': modifier,
        'modifier_reason': modifier_reason,
    }


def resolve_movement_roll(state: dict, player_id: str, raw_roll: int) -> tuple[dict, dict]:
    state, resolved = apply_movement_roll_modifiers(state, player_id, raw_roll)
    player = _get_player(state, player_id)
    player_name = player['name'] if player else 'Sistema'
    roll_entry = _record_roll(
        state,
        roll_type='movimento',
        player_id=player_id,
        player_name=player_name,
        raw_result=resolved['raw_result'],
        final_result=resolved['final_result'],
        modifier=resolved.get('modifier'),
        modifier_reason=resolved.get('modifier_reason'),
        context='movement',
    )
    return state, roll_entry


def perform_movement_roll(state: dict, player_id: str) -> tuple[dict, dict]:
    raw_roll = roll_movement_dice()
    state, roll_entry = resolve_movement_roll(state, player_id, raw_roll)
    _queue_move_roll_ability_decision(
        state,
        player_id,
        int(roll_entry['final_result']),
        raw_roll=int(roll_entry['raw_result']),
    )
    return state, roll_entry


def roll_capture_for_attempt(state: dict, player_id: str, capture_context: str | None) -> tuple[dict, dict]:
    state = copy.deepcopy(state)
    player = _get_player(state, player_id)
    player_name = player['name'] if player else 'Sistema'
    raw_roll = roll_capture_dice()
    roll_entry = _record_roll(
        state,
        roll_type='captura',
        player_id=player_id,
        player_name=player_name,
        raw_result=raw_roll,
        final_result=raw_roll,
        context=capture_context,
    )
    return state, roll_entry


def _record_battle_roll(state: dict, actor_name: str, raw_roll: int, final_roll: int, context: str) -> dict:
    return _record_roll(
        state,
        roll_type='batalha',
        player_id=None,
        player_name=actor_name,
        raw_result=raw_roll,
        final_result=final_roll,
        modifier={'source': 'battle_effect'} if raw_roll != final_roll else None,
        modifier_reason='efeito de batalha' if raw_roll != final_roll else None,
        context=context,
        emit_log=False,
    )


def _format_battle_roll_summary(raw_roll: int | None, final_roll: int | None) -> str:
    if raw_roll is None and final_roll is None:
        return 'não rolou'
    if final_roll is None or raw_roll == final_roll:
        return f'rolou {final_roll}'
    return f'rolou {raw_roll} e o dado terminou em {final_roll}'


def _log_battle_result_summary(
    state: dict,
    *,
    log_player: str,
    challenger_name: str,
    defender_name: str,
    challenger_pokemon_name: str,
    defender_pokemon_name: str,
    challenger_raw_roll: int | None,
    defender_raw_roll: int | None,
    challenger_final_roll: int | None,
    defender_final_roll: int | None,
    challenger_bp: int,
    defender_bp: int,
    challenger_bonus: int,
    defender_bonus: int,
    challenger_score: int,
    defender_score: int,
    winner_message: str,
) -> None:
    _log(state, log_player, f"{challenger_name} {_format_battle_roll_summary(challenger_raw_roll, challenger_final_roll)} com {challenger_pokemon_name}.")
    _log(state, log_player, f"{defender_name} {_format_battle_roll_summary(defender_raw_roll, defender_final_roll)} com {defender_pokemon_name}.")
    _log(
        state,
        log_player,
        "Resultado final — "
        f"{challenger_name}: {challenger_final_roll} x ({challenger_bp} + {challenger_bonus}) = {challenger_score} | "
        f"{defender_name}: {defender_final_roll} x ({defender_bp} + {defender_bonus}) = {defender_score}.",
    )
    _log(state, log_player, winner_message)


def _prepare_tied_battle_reroll(
    state: dict,
    battle: dict,
    *,
    log_player: str,
    message: str,
    result_payload: dict,
) -> tuple[dict, dict]:
    battle['challenger_roll'] = None
    battle['defender_roll'] = None
    battle['sub_phase'] = 'rolling'
    battle['choice_stage'] = 'complete'
    state['turn']['battle'] = battle
    state['turn']['phase'] = 'battle'
    _log(state, log_player, message)
    return state, {
        **result_payload,
        'winner_id': None,
        'loser_id': None,
        'winner_name': None,
        'loser_name': None,
        'winner_pokemon': None,
        'loser_pokemon': None,
        'battle_finished': False,
        'continues': True,
        'reroll_required': True,
        'tied_round': True,
    }


def _get_debug_test_player(state: dict) -> dict | None:
    debug_visual = state.get('debug_visual') or {}
    session = debug_visual.get('session_state')
    if not isinstance(session, dict):
        return None
    return next(
        (player for player in session.get('players', []) if player.get('id') == _DEBUG_TEST_PLAYER_ID or player.get('is_test_player')),
        None,
    )


def _get_player(state: dict, player_id: str) -> dict | None:
    player = next((p for p in state.get('players', []) if p['id'] == player_id), None)
    if player:
        return player
    if player_id == _DEBUG_TEST_PLAYER_ID:
        return _get_debug_test_player(state)
    return None


def _get_active_players(state: dict) -> list:
    return [p for p in state.get('players', []) if p.get('is_active', True)]


def _get_player_to_left(state: dict, player_id: str) -> dict | None:
    """Retorna o jogador à esquerda (índice anterior) na ordem de turno."""
    active = _get_active_players(state)
    for idx, p in enumerate(active):
        if p['id'] == player_id:
            return active[(idx - 1) % len(active)] if len(active) > 1 else None
    return None


def _init_pokemon(pokemon: dict) -> dict:
    """Inicializa campos de rastreamento de habilidade em um Pokémon."""
    pokemon = copy.deepcopy(pokemon)
    pokemon.setdefault('ability_used', False)
    pokemon.setdefault('pokeball_slots', 1)
    return sync_pokemon_ability_state(pokemon)


def _sync_player(state: dict, player_id: str) -> dict | None:
    player = _get_player(state, player_id)
    if player:
        sync_player_inventory(player)
    return player


def _ensure_player_capture_counter(player: dict) -> int:
    highest_sequence = 0
    for pokemon in player.get('pokemon', []):
        try:
            sequence = int(pokemon.get('capture_sequence'))
        except (TypeError, ValueError):
            sequence = None
        if sequence is not None:
            highest_sequence = max(highest_sequence, sequence)
    try:
        current_counter = int(player.get('capture_sequence_counter', 0) or 0)
    except (TypeError, ValueError):
        current_counter = 0
    player['capture_sequence_counter'] = max(current_counter, highest_sequence)
    return int(player['capture_sequence_counter'])


def _apply_pokemon_acquisition_metadata(
    pokemon: dict,
    *,
    acquisition_origin: str,
    capture_sequence: int | None = None,
    capture_context: str | None = None,
) -> dict:
    if not isinstance(pokemon, dict):
        return pokemon
    pokemon['acquisition_origin'] = acquisition_origin
    pokemon['capture_sequence'] = None if capture_sequence is None else int(capture_sequence)
    if capture_context is None:
        pokemon.setdefault('capture_context', None)
    else:
        pokemon['capture_context'] = capture_context
    return pokemon


def _ensure_player_pokemon_acquisition_metadata(player: dict) -> None:
    starter = player.get('starter_pokemon')
    if isinstance(starter, dict):
        _apply_pokemon_acquisition_metadata(starter, acquisition_origin='starter')

    counter = _ensure_player_capture_counter(player)
    for pokemon in player.get('pokemon', []):
        origin = pokemon.get('acquisition_origin')
        if origin == 'captured':
            try:
                sequence = int(pokemon.get('capture_sequence'))
            except (TypeError, ValueError):
                sequence = None
            if sequence is None:
                counter += 1
                _apply_pokemon_acquisition_metadata(
                    pokemon,
                    acquisition_origin='captured',
                    capture_sequence=counter,
                    capture_context=pokemon.get('capture_context'),
                )
            continue
        if origin:
            _apply_pokemon_acquisition_metadata(
                pokemon,
                acquisition_origin=origin,
                capture_sequence=pokemon.get('capture_sequence'),
                capture_context=pokemon.get('capture_context'),
            )
            continue

        # Estados antigos não tinham metadado de captura. Preservamos a ordem
        # do time como melhor aproximação da ordem real de captura.
        counter += 1
        _apply_pokemon_acquisition_metadata(
            pokemon,
            acquisition_origin='captured',
            capture_sequence=counter,
            capture_context=pokemon.get('capture_context'),
        )

    player['capture_sequence_counter'] = counter


def _next_capture_sequence(player: dict) -> int:
    _ensure_player_pokemon_acquisition_metadata(player)
    next_sequence = int(player.get('capture_sequence_counter', 0) or 0) + 1
    player['capture_sequence_counter'] = next_sequence
    return next_sequence


def _copy_pokemon_acquisition_metadata(source: dict, target: dict) -> dict:
    return _apply_pokemon_acquisition_metadata(
        target,
        acquisition_origin=source.get('acquisition_origin', 'captured'),
        capture_sequence=source.get('capture_sequence'),
        capture_context=source.get('capture_context'),
    )


def _is_captured_team_pokemon(pokemon: dict | None) -> bool:
    return bool(pokemon) and pokemon.get('acquisition_origin') == 'captured'


def _get_last_captured_team_pokemon_index(player: dict) -> int | None:
    _ensure_player_pokemon_acquisition_metadata(player)
    candidates: list[tuple[int, int]] = []
    for index, pokemon in enumerate(player.get('pokemon', [])):
        if not _is_captured_team_pokemon(pokemon):
            continue
        try:
            sequence = int(pokemon.get('capture_sequence'))
        except (TypeError, ValueError):
            sequence = -1
        candidates.append((sequence, index))
    if not candidates:
        return None
    candidates.sort()
    return candidates[-1][1]


def _remove_last_captured_team_pokemon(player: dict) -> dict | None:
    index = _get_last_captured_team_pokemon_index(player)
    if index is None:
        return None
    removed = player['pokemon'].pop(index)
    player['pokeballs'] = max(0, int(player.get('pokeballs', 0) or 0) + pokemon_slot_cost(removed))
    sync_player_inventory(player)
    return removed


def _iter_player_battle_slots(player: dict, *, include_knocked_out: bool = True) -> list[tuple[str, dict]]:
    slots: list[tuple[str, dict]] = []
    for index, pokemon in enumerate(player.get('pokemon', [])):
        if not include_knocked_out and pokemon.get('knocked_out'):
            continue
        slots.append((f'pokemon:{index}', pokemon))
    starter = player.get('starter_pokemon')
    if starter and (include_knocked_out or not starter.get('knocked_out')):
        slots.append(('starter', starter))
    return slots


def _build_player_battle_pool(player: dict, *, include_knocked_out: bool = True) -> list[dict]:
    pool: list[dict] = []
    for slot_key, pokemon in _iter_player_battle_slots(player, include_knocked_out=include_knocked_out):
        candidate = copy.deepcopy(pokemon)
        candidate['battle_slot_key'] = slot_key
        candidate['types'] = [str(poke_type).title() for poke_type in candidate.get('types', [])]
        candidate.setdefault('knocked_out', False)
        pool.append(candidate)
    return pool


def _resolve_battle_pool_choice(
    pool: list[dict],
    *,
    pokemon_index: int | None = None,
    pokemon_slot_key: str | None = None,
) -> tuple[dict | None, int | None]:
    normalized_slot_key = (pokemon_slot_key or '').strip()
    if normalized_slot_key:
        for index, pokemon in enumerate(pool):
            if pokemon.get('battle_slot_key') == normalized_slot_key:
                return copy.deepcopy(pokemon), index
        return None, None

    if not pool or pokemon_index is None:
        return None, None

    resolved_index = max(0, min(int(pokemon_index), len(pool) - 1))
    return copy.deepcopy(pool[resolved_index]), resolved_index


def _get_player_pokemon_slot(player: dict, slot_key: str | None) -> dict | None:
    if not slot_key:
        return None
    if slot_key == 'starter':
        starter = player.get('starter_pokemon')
        return starter if isinstance(starter, dict) else None
    if not slot_key.startswith('pokemon:'):
        return None
    try:
        index = int(slot_key.split(':', 1)[1])
    except (TypeError, ValueError):
        return None
    pokemon = player.get('pokemon', [])
    if 0 <= index < len(pokemon):
        return pokemon[index]
    return None


def _set_player_pokemon_slot(player: dict, slot_key: str | None, pokemon: dict | None) -> dict | None:
    if not slot_key:
        return None
    sanitized = copy.deepcopy(pokemon) if isinstance(pokemon, dict) else None
    if isinstance(sanitized, dict):
        for transient_key in ('slot_key', 'battle_slot_key', 'is_starter_slot', 'slot_cost'):
            sanitized.pop(transient_key, None)
    if slot_key == 'starter':
        player['starter_pokemon'] = sanitized
        return sanitized
    if not slot_key.startswith('pokemon:'):
        return None
    try:
        index = int(slot_key.split(':', 1)[1])
    except (TypeError, ValueError):
        return None
    pokemon_list = player.get('pokemon', [])
    if 0 <= index < len(pokemon_list):
        pokemon_list[index] = sanitized
        return sanitized
    return None


def _build_trade_slot_label(player: dict, slot_key: str) -> str:
    pokemon = _get_player_pokemon_slot(player, slot_key)
    if not pokemon:
        return slot_key
    label = pokemon.get('name', slot_key)
    if slot_key == 'starter':
        label = f'{label} (Starter)'
    if pokemon.get('knocked_out'):
        label = f'{label} [KO]'
    return label


def _build_trade_options_for_player(player: dict) -> list[dict]:
    options: list[dict] = []
    for slot_key, pokemon in _iter_player_battle_slots(player, include_knocked_out=True):
        options.append({
            'id': slot_key,
            'slot_key': slot_key,
            'label': f"Trocar {_build_trade_slot_label(player, slot_key)}",
            'pokemon_name': pokemon.get('name', slot_key),
            'pokemon': copy.deepcopy(pokemon),
        })
    options.append({'id': 'decline', 'label': 'Recusar'})
    return options


def _get_trade_eligible_target_ids(state: dict, player_id: str) -> list[str]:
    player = _get_player(state, player_id)
    if not player:
        return []

    reachable_positions = {int(player.get('position', 0) or 0)}
    movement = state.get('turn', {}).get('movement_context') or {}
    try:
        start_position = int(movement.get('start_position'))
        end_position = int(movement.get('resolved_destination'))
    except (TypeError, ValueError):
        start_position = None
        end_position = None
    if start_position is not None and end_position is not None:
        reachable_positions.update(get_positions_between(start_position, end_position))

    eligible_ids: list[str] = []
    for target in state.get('players', []):
        if target.get('id') == player_id:
            continue
        if not target.get('is_active', True):
            continue
        if not target.get('is_connected', True) and not target.get('is_cpu', False):
            continue
        try:
            target_position = int(target.get('position', 0) or 0)
        except (TypeError, ValueError):
            continue
        if target_position in reachable_positions:
            eligible_ids.append(target['id'])
    return eligible_ids


def _update_last_movement_roll(
    state: dict,
    *,
    final_result: int,
    modifier: dict | None = None,
    modifier_reason: str | None = None,
) -> None:
    payload = {
        'final_result': int(final_result),
        'modifier': copy.deepcopy(modifier),
        'modifier_reason': modifier_reason,
    }
    history = state.get('turn', {}).get('roll_history') or []
    for roll_entry in reversed(history):
        if roll_entry.get('context') == 'movement':
            roll_entry.update(payload)
            break

    last_roll = state.get('turn', {}).get('last_roll')
    if isinstance(last_roll, dict) and last_roll.get('context') == 'movement':
        last_roll.update(payload)


def _queue_move_roll_ability_decision(
    state: dict,
    player_id: str,
    current_roll: int,
    *,
    raw_roll: int | None = None,
) -> bool:
    player = _get_player(state, player_id)
    if not player:
        return False

    flattened_options: list[dict] = []
    for slot_key, pokemon in _iter_player_battle_slots(player, include_knocked_out=False):
        sync_pokemon_ability_state(pokemon)
        option_defs = build_move_roll_prompt_options(pokemon, int(current_roll))
        for index, option in enumerate(option_defs):
            flattened_options.append({
                'id': f'ability:{slot_key}:{option["ability_id"]}:{option["effect_kind"]}:{index}',
                'label': f'{pokemon.get("name", "Pokémon")}: {option["ability_name"]} ({option["label_suffix"]})',
                'slot_key': slot_key,
                'pokemon_name': pokemon.get('name'),
                'ability_id': option['ability_id'],
                'ability_name': option['ability_name'],
                'effect_kind': option['effect_kind'],
                'resolution': copy.deepcopy(option.get('resolution') or {}),
                'charges_remaining': option.get('charges_remaining'),
                'charges_total': option.get('charges_total'),
            })

    if not flattened_options:
        return False

    turn = state['turn']
    decision_id = (
        f"move-roll:{player_id}:{turn.get('round', 1)}:"
        f"{len(turn.get('roll_history') or [])}:{int(current_roll)}"
    )
    flattened_options.append({
        'id': 'skip',
        'label': 'Não usar habilidade',
        'effect_kind': 'skip',
    })
    _set_pending_action(state, {
        'type': 'ability_decision',
        'decision_kind': 'move_roll',
        'decision_id': decision_id,
        'player_id': player_id,
        'prompt': f'Você rolou {int(current_roll)}. Deseja usar uma habilidade opcional antes de mover?',
        'raw_roll': int(raw_roll if raw_roll is not None else current_roll),
        'current_roll': int(current_roll),
        'options': flattened_options,
        'allowed_actions': ['resolve_pending_action'],
    })
    return True


def _resolve_move_roll_ability_decision(
    state: dict,
    player_id: str,
    pending_action: dict,
    chosen: dict,
) -> tuple[dict | None, str | dict]:
    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'

    current_roll = int(pending_action.get('current_roll') or pending_action.get('raw_roll') or 0)
    raw_roll = int(pending_action.get('raw_roll') or current_roll)

    if chosen.get('id') == 'skip':
        _clear_pending_action(state)
        state = process_move(state, player_id, current_roll)
        return state, {
            'type': 'ability_decision',
            'decision_kind': 'move_roll',
            'used': False,
            'final_roll': current_roll,
        }

    slot_key = chosen.get('slot_key')
    pokemon = _get_player_pokemon_slot(player, slot_key)
    if not pokemon:
        return None, 'Pokémon da habilidade não encontrado'

    sync_pokemon_ability_state(pokemon)
    ability = next(
        (
            item for item in (pokemon.get('abilities') or [])
            if item.get('id') == chosen.get('ability_id')
        ),
        None,
    )
    if not ability:
        return None, 'Habilidade não encontrada neste Pokémon'
    if ability.get('has_charges') and int(ability.get('charges_remaining') or 0) <= 0:
        return None, 'Esta habilidade não possui cargas restantes'
    if (ability.get('runtime') or {}).get('used_this_turn'):
        return None, 'Esta habilidade já foi usada neste turno'

    pokemon_name = pokemon.get('name', 'Pokémon')
    ability_name = ability.get('name') or 'Habilidade'
    effect_kind = chosen.get('effect_kind')
    resolution = copy.deepcopy(chosen.get('resolution') or {})
    consume_charge = ability.get('charges_total') is not None
    next_roll = current_roll

    if resolution.get('mode') == 'reroll':
        state, reroll_entry = resolve_movement_roll(state, player_id, roll_movement_dice())
        next_roll = int(reroll_entry['final_result'])
        _log(
            state,
            player['name'],
            f'Usou {ability_name} de {pokemon_name} para rerrolar o dado de movimento ({current_roll} -> {next_roll}).',
        )
    elif resolution.get('mode') == 'set':
        try:
            next_roll = int(resolution.get('result'))
        except (TypeError, ValueError):
            return None, 'Resultado inválido para a habilidade'
        if next_roll == current_roll:
            return None, 'Esta habilidade não altera o resultado atual do dado'
        _log(
            state,
            player['name'],
            f'Usou {ability_name} de {pokemon_name} para alterar o dado de movimento ({current_roll} -> {next_roll}).',
        )
    else:
        return None, 'Resolução de habilidade ainda não suportada'

    mark_primary_ability_used(
        pokemon,
        scope='turn',
        consume_charge=consume_charge,
        decision_id=pending_action.get('decision_id'),
    )
    _update_last_movement_roll(
        state,
        final_result=next_roll,
        modifier={
            'source': 'pokemon_ability',
            'effect_kind': effect_kind,
            'source_name': f'{pokemon_name}: {ability_name}',
        },
        modifier_reason=f'{pokemon_name}: {ability_name}',
    )
    _clear_pending_action(state)

    if _queue_move_roll_ability_decision(state, player_id, next_roll, raw_roll=raw_roll):
        return state, {
            'type': 'ability_decision',
            'decision_kind': 'move_roll',
            'used': True,
            'pokemon': pokemon_name,
            'ability_name': ability_name,
            'effect_kind': effect_kind,
            'final_roll': next_roll,
            'awaiting_follow_up': True,
        }

    state = process_move(state, player_id, next_roll)
    return state, {
        'type': 'ability_decision',
        'decision_kind': 'move_roll',
        'used': True,
        'pokemon': pokemon_name,
        'ability_name': ability_name,
        'effect_kind': effect_kind,
        'final_roll': next_roll,
    }


def _queue_capture_choice_decision(
    state: dict,
    player_id: str,
    use_full_restore: bool,
    *,
    pending_capture_action: dict,
    slot_key: str,
    pokemon: dict,
    ability: dict,
) -> tuple[dict, dict]:
    """Fila uma decisão de capture_choice antes do dado de captura ser rolado."""
    pokemon_name = pokemon.get('name', 'Pokémon')
    ability_name = ability.get('name') or 'Habilidade'
    options = [
        {'id': str(val), 'label': f'Escolher {val}', 'value': val}
        for val in range(1, 7)
    ]
    options.append({'id': 'skip', 'label': 'Não usar habilidade', 'value': None})
    _set_pending_action(state, {
        'type': 'capture_choice_decision',
        'player_id': player_id,
        'slot_key': slot_key,
        'pokemon_name': pokemon_name,
        'ability_id': ability.get('id', 'primary'),
        'ability_name': ability_name,
        'has_charges': bool(ability.get('has_charges')),
        'use_full_restore': use_full_restore,
        'original_capture_action': copy.deepcopy(pending_capture_action),
        'prompt': f'{pokemon_name} pode usar {ability_name}. Escolha o resultado do dado de captura:',
        'options': options,
        'allowed_actions': ['resolve_pending_action'],
    })
    return state, {
        'success': False,
        'requires_ability_decision': True,
        'decision_type': 'capture_choice',
        'pokemon_name': pokemon_name,
        'ability_name': ability_name,
    }


def _queue_capture_reroll_decision(
    state: dict,
    player_id: str,
    use_full_restore: bool,
    *,
    pending_capture_action: dict,
    capture_roll: dict,
    slot_key: str,
    pokemon: dict,
    ability: dict,
) -> tuple[dict, dict]:
    """Fila uma decisão de capture_reroll após o dado de captura ser rolado."""
    pokemon_name = pokemon.get('name', 'Pokémon')
    ability_name = ability.get('name') or 'Habilidade'
    current_roll = int(capture_roll['raw_result'])
    _set_pending_action(state, {
        'type': 'capture_reroll_decision',
        'player_id': player_id,
        'slot_key': slot_key,
        'pokemon_name': pokemon_name,
        'ability_id': ability.get('id', 'primary'),
        'ability_name': ability_name,
        'has_charges': bool(ability.get('has_charges')),
        'use_full_restore': use_full_restore,
        'original_capture_action': copy.deepcopy(pending_capture_action),
        'current_roll': current_roll,
        'capture_roll_result': copy.deepcopy(capture_roll),
        'prompt': f'Você rolou {current_roll}. {pokemon_name} pode usar {ability_name} para rerrolar:',
        'options': [
            {'id': 'reroll', 'label': f'Rerrolar ({pokemon_name}: {ability_name})'},
            {'id': 'keep', 'label': f'Manter resultado atual ({current_roll})'},
        ],
        'allowed_actions': ['resolve_pending_action'],
    })
    return state, {
        'success': False,
        'requires_ability_decision': True,
        'decision_type': 'capture_reroll',
        'pokemon_name': pokemon_name,
        'ability_name': ability_name,
        'current_roll': current_roll,
    }


def _resolve_capture_choice_decision(
    state: dict,
    player_id: str,
    pending_action: dict,
    chosen: dict,
) -> tuple[dict | None, str | dict]:
    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'

    original_action = copy.deepcopy(pending_action.get('original_capture_action') or {})
    original_action['capture_choice_used'] = True
    use_full_restore = bool(pending_action.get('use_full_restore'))
    chosen_value = chosen.get('value')

    if chosen.get('id') == 'skip' or chosen_value is None:
        _set_pending_action(state, original_action)
        return roll_capture_attempt(state, player_id, use_full_restore)

    slot_key = pending_action.get('slot_key')
    pokemon = _get_player_pokemon_slot(player, slot_key)
    if pokemon:
        sync_pokemon_ability_state(pokemon)
        mark_primary_ability_used(pokemon, scope='turn', consume_charge=bool(pending_action.get('has_charges')))

    _set_pending_action(state, original_action)
    ability_name = pending_action.get('ability_name', 'Habilidade')
    pokemon_name = pending_action.get('pokemon_name', 'Pokémon')
    _log(state, player['name'], f'Usou {ability_name} de {pokemon_name} para escolher {chosen_value} no dado de captura.')
    return roll_capture_attempt(state, player_id, use_full_restore, ability_chosen_roll=int(chosen_value))


def _resolve_capture_reroll_decision(
    state: dict,
    player_id: str,
    pending_action: dict,
    chosen: dict,
) -> tuple[dict | None, str | dict]:
    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'

    original_action = copy.deepcopy(pending_action.get('original_capture_action') or {})
    original_action['capture_reroll_used'] = True
    use_full_restore = bool(pending_action.get('use_full_restore'))
    current_roll = int(pending_action.get('current_roll') or 0)
    ability_name = pending_action.get('ability_name', 'Habilidade')
    pokemon_name = pending_action.get('pokemon_name', 'Pokémon')

    if chosen.get('id') == 'keep':
        _set_pending_action(state, original_action)
        _log(state, player['name'], f'Manteve o resultado {current_roll} no dado de captura.')
        return roll_capture_attempt(state, player_id, use_full_restore, ability_chosen_roll=current_roll)

    # "reroll"
    slot_key = pending_action.get('slot_key')
    pokemon = _get_player_pokemon_slot(player, slot_key)
    if pokemon:
        sync_pokemon_ability_state(pokemon)
        mark_primary_ability_used(pokemon, scope='turn', consume_charge=bool(pending_action.get('has_charges')))

    _set_pending_action(state, original_action)
    _log(state, player['name'], f'Usou {ability_name} de {pokemon_name} para rerrolar o dado de captura (anterior: {current_roll}).')
    return roll_capture_attempt(state, player_id, use_full_restore)


def _resolve_heal_other_choice(
    state: dict,
    player_id: str,
    pending_action: dict,
    chosen: dict,
) -> tuple[dict | None, str | dict]:
    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'

    target_slot_key = chosen.get('slot_key') or chosen.get('id')
    target_poke = _get_player_pokemon_slot(player, target_slot_key)
    if not target_poke:
        return None, 'Pokémon alvo não encontrado'
    if not target_poke.get('knocked_out'):
        return None, 'Este Pokémon não está desmaiado'

    healer_slot_key = pending_action.get('healer_slot_key')
    healer = _get_player_pokemon_slot(player, healer_slot_key)
    ability_name = pending_action.get('ability_name', 'Habilidade')
    healer_name = pending_action.get('healer_name', 'Pokémon')
    target_name = target_poke.get('name', target_slot_key)

    _heal_player_pokemon_slots(player, [target_slot_key])
    if healer:
        sync_pokemon_ability_state(healer)
        mark_primary_ability_used(healer, scope='turn', consume_charge=False)
    sync_player_inventory(player)
    _clear_pending_action(state)
    _log(state, player['name'], f'Usou {ability_name} de {healer_name} para curar {target_name}.')
    return state, {
        'type': 'heal_other_choice',
        'healer': healer_name,
        'healed': target_name,
        'slot_key': target_slot_key,
    }


def _queue_battle_reroll_decision(
    state: dict,
    player_id: str,
    *,
    roll: int,
    is_challenger: bool,
    slot_key: str,
    pokemon: dict,
    ability: dict,
) -> tuple[dict, dict]:
    """Fila uma decisão de battle_reroll após o dado de batalha ser rolado."""
    pokemon_name = pokemon.get('name', 'Pokémon')
    ability_name = ability.get('name') or 'Habilidade'
    _set_pending_action(state, {
        'type': 'battle_reroll_decision',
        'player_id': player_id,
        'slot_key': slot_key,
        'pokemon_name': pokemon_name,
        'ability_id': ability.get('id', 'primary'),
        'ability_name': ability_name,
        'has_charges': bool(ability.get('has_charges')),
        'original_roll': roll,
        'is_challenger': is_challenger,
        'prompt': f'Você rolou {roll}. {pokemon_name} pode usar {ability_name} para rerrolar o dado de batalha:',
        'options': [
            {'id': 'reroll', 'label': f'Rerrolar ({pokemon_name}: {ability_name})'},
            {'id': 'keep', 'label': f'Manter resultado atual ({roll})'},
        ],
        'allowed_actions': ['resolve_pending_action'],
    })
    return state, {
        'success': False,
        'requires_ability_decision': True,
        'decision_type': 'battle_reroll',
        'pokemon_name': pokemon_name,
        'ability_name': ability_name,
        'current_roll': roll,
    }


def _resolve_battle_reroll_decision(
    state: dict,
    player_id: str,
    pending_action: dict,
    chosen: dict,
) -> tuple[dict | None, str | dict]:
    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'

    battle = state['turn'].get('battle')
    if not battle:
        return None, 'Nenhuma batalha ativa'

    original_roll = int(pending_action.get('original_roll') or 0)
    is_challenger = bool(pending_action.get('is_challenger'))
    mode = battle.get('mode', 'player')
    ability_name = pending_action.get('ability_name', 'Habilidade')
    pokemon_name = pending_action.get('pokemon_name', 'Pokémon')
    _clear_pending_action(state)

    if chosen.get('id') == 'keep':
        _log(state, player['name'], f'Manteve o resultado {original_roll} no dado de batalha.')
    else:
        # 'reroll': mark used, consume charge, do fresh roll
        slot_key = pending_action.get('slot_key')
        poke = _get_player_pokemon_slot(player, slot_key)
        if poke:
            sync_pokemon_ability_state(poke)
            mark_primary_ability_used(poke, scope='battle', consume_charge=bool(pending_action.get('has_charges')))

        new_roll = roll_battle_dice()
        _log(state, player['name'], f'Usou {ability_name} de {pokemon_name} para rerrolar o dado de batalha ({original_roll} → {new_roll}).')
        if is_challenger:
            battle['challenger_roll'] = new_roll
        else:
            battle['defender_roll'] = new_roll

    if mode == 'trainer':
        return _resolve_trainer_battle(state)
    if mode in ('gym', 'league'):
        return _resolve_gym_battle(state)
    # PvP: resolve only when both have rolled
    if battle.get('challenger_roll') is not None and battle.get('defender_roll') is not None:
        return _resolve_duel(state)
    return state, None


def _queue_battle_bp_swap_decision(
    state: dict,
    player_id: str,
    *,
    slot_key: str,
    pokemon: dict,
    ability: dict,
    is_challenger: bool,
) -> tuple[dict, dict]:
    """Fila uma decisão pré-rolagem para trocar Battle Points com o oponente."""
    battle = state['turn'].get('battle') or {}
    own_choice = battle.get('challenger_choice' if is_challenger else 'defender_choice') or {}
    opponent_choice = battle.get('defender_choice' if is_challenger else 'challenger_choice') or {}
    pokemon_name = pokemon.get('name', 'Pokémon')
    ability_name = ability.get('name') or 'Habilidade'
    own_bp = int(own_choice.get('battle_points') or pokemon.get('battle_points') or 1)
    opponent_bp = int(opponent_choice.get('battle_points') or 1)

    _set_pending_action(state, {
        'type': 'battle_bp_swap_decision',
        'player_id': player_id,
        'slot_key': slot_key,
        'pokemon_name': pokemon_name,
        'ability_id': ability.get('id', 'primary'),
        'ability_name': ability_name,
        'has_charges': bool(ability.get('has_charges')),
        'is_challenger': is_challenger,
        'prompt': (
            f'{pokemon_name} pode usar {ability_name} para trocar os Battle Points '
            f'({own_bp} ↔ {opponent_bp}) antes da rolagem.'
        ),
        'options': [
            {'id': 'swap', 'label': f'Trocar BP ({own_bp} ↔ {opponent_bp})'},
            {'id': 'skip', 'label': 'Não usar habilidade'},
        ],
        'allowed_actions': ['resolve_pending_action'],
    })
    return state, {
        'success': False,
        'requires_ability_decision': True,
        'decision_type': 'battle_bp_swap',
        'pokemon_name': pokemon_name,
        'ability_name': ability_name,
    }


def _log_battle_ready_to_roll(state: dict, battle: dict) -> None:
    mode = battle.get('mode', 'player')
    if mode == 'trainer':
        challenger = _get_player(state, battle.get('challenger_id'))
        if challenger:
            _log(state, 'Duelo', f"{challenger['name']} vai enfrentar {battle.get('defender_name', 'Trainer')}. Role o dado de batalha!")
        return

    if mode in ('gym', 'league'):
        label = 'Liga' if mode == 'league' else 'Ginásio'
        defender_choice = battle.get('defender_choice') or {}
        _log(
            state,
            label,
            f"{battle.get('defender_name', 'Líder')} está com {defender_choice.get('name', 'seu Pokémon')} em campo. Role o dado de batalha!",
        )
        return

    challenger = _get_player(state, battle.get('challenger_id'))
    defender = _get_player(state, battle.get('defender_id'))
    challenger_choice = battle.get('challenger_choice') or {}
    defender_choice = battle.get('defender_choice') or {}
    if challenger and defender:
        _log(
            state,
            'Duelo',
            f"Ambos escolheram: {challenger['name']} com {challenger_choice.get('name', '?')} e {defender['name']} com {defender_choice.get('name', '?')}.",
        )
        _log(state, 'Duelo', 'Cada jogador deve rolar seu dado de batalha.')


def _queue_pre_roll_battle_ability_decision(state: dict) -> bool:
    battle = state['turn'].get('battle') or {}
    if battle.get('sub_phase') != 'rolling':
        return False

    resolved_slots = {str(item) for item in (battle.get('bp_swap_resolved_slots') or []) if str(item).strip()}
    candidates = [
        (battle.get('challenger_id'), battle.get('challenger_choice') or {}, True),
    ]
    if battle.get('mode') == 'player':
        candidates.append((battle.get('defender_id'), battle.get('defender_choice') or {}, False))

    for participant_id, battle_choice, is_challenger in candidates:
        if not participant_id or not battle_choice:
            continue
        player = _get_player(state, participant_id)
        if not player:
            continue
        ability_match = _find_available_battle_bp_swap_ability(player, battle_choice)
        if not ability_match:
            continue
        slot_key, pokemon, ability = ability_match
        if slot_key in resolved_slots:
            continue
        _queue_battle_bp_swap_decision(
            state,
            participant_id,
            slot_key=slot_key,
            pokemon=pokemon,
            ability=ability,
            is_challenger=is_challenger,
        )
        return True

    return False


def _resolve_battle_bp_swap_decision(
    state: dict,
    player_id: str,
    pending_action: dict,
    chosen: dict,
) -> tuple[dict | None, str | dict]:
    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'

    battle = state['turn'].get('battle')
    if not battle:
        return None, 'Nenhuma batalha ativa'

    slot_key = str(pending_action.get('slot_key') or '').strip()
    resolved_slots = [str(item) for item in (battle.get('bp_swap_resolved_slots') or []) if str(item).strip()]
    if slot_key and slot_key not in resolved_slots:
        resolved_slots.append(slot_key)
    battle['bp_swap_resolved_slots'] = resolved_slots

    pokemon_name = pending_action.get('pokemon_name', 'Pokémon')
    ability_name = pending_action.get('ability_name', 'Habilidade')
    is_challenger = bool(pending_action.get('is_challenger'))
    own_key = 'challenger_choice' if is_challenger else 'defender_choice'
    opponent_key = 'defender_choice' if is_challenger else 'challenger_choice'
    own_choice = battle.get(own_key)
    opponent_choice = battle.get(opponent_key)
    if not own_choice or not opponent_choice:
        return None, 'A batalha não possui Pokémon suficientes para trocar Battle Points'

    _clear_pending_action(state)

    used = False
    if chosen.get('id') == 'swap':
        poke = _get_player_pokemon_slot(player, slot_key)
        if poke:
            sync_pokemon_ability_state(poke)
            mark_primary_ability_used(poke, scope='battle', consume_charge=bool(pending_action.get('has_charges')))

        own_bp = int(own_choice.get('battle_points') or 1)
        opponent_bp = int(opponent_choice.get('battle_points') or 1)
        own_choice['battle_points'], opponent_choice['battle_points'] = opponent_bp, own_bp
        _log(
            state,
            player['name'],
            f'Usou {ability_name} de {pokemon_name} para trocar os Battle Points ({own_bp} ↔ {opponent_bp}).',
        )
        used = True
    else:
        _log(state, player['name'], f'Decidiu não usar {ability_name} de {pokemon_name} nesta batalha.')

    if _queue_pre_roll_battle_ability_decision(state):
        return state, {
            'type': 'battle_bp_swap_decision',
            'used': used,
            'awaiting_follow_up': True,
        }

    _log_battle_ready_to_roll(state, battle)
    return state, {
        'type': 'battle_bp_swap_decision',
        'used': used,
    }


def _resolve_abra_transfer_offer(
    state: dict,
    player_id: str,
    pending_action: dict,
    chosen: dict,
) -> tuple[dict | None, str | dict]:
    proposer_id = pending_action.get('proposer_id')
    if proposer_id is not None:
        proposer = _get_player(state, proposer_id)
        target = _get_player(state, player_id)
        if not proposer or not target:
            return None, 'Jogador não encontrado'

        offered_slot_key = str(pending_action.get('offered_slot_key') or '').strip()
        offered_snapshot = pending_action.get('offered_pokemon') or {}
        offered_name = offered_snapshot.get('name', offered_slot_key or 'Pokémon')

        _clear_pending_action(state)

        if chosen.get('id') == 'decline':
            _log(
                state,
                target.get('name', 'Jogador'),
                f"Recusou a troca proposta por {proposer.get('name', 'Jogador')} ({offered_name}).",
            )
            return state, {
                'type': 'trade_proposal',
                'accepted': False,
                'proposer_id': proposer_id,
                'target_player_id': player_id,
                'offered_pokemon': offered_name,
            }

        requested_slot_key = str(chosen.get('slot_key') or chosen.get('id') or '').strip()
        offered_live = _get_player_pokemon_slot(proposer, offered_slot_key)
        requested_live = _get_player_pokemon_slot(target, requested_slot_key)
        if not offered_live or not requested_live:
            return None, 'Um dos Pokémon da troca não está mais disponível'

        proposer_free_slots = int(proposer.get('pokeballs', 0) or 0) + pokemon_slot_cost(offered_live) - pokemon_slot_cost(requested_live)
        target_free_slots = int(target.get('pokeballs', 0) or 0) + pokemon_slot_cost(requested_live) - pokemon_slot_cost(offered_live)
        if proposer_free_slots < 0 or target_free_slots < 0:
            return None, 'A troca deixou um dos jogadores sem slots suficientes'

        requested_name = requested_live.get('name', requested_slot_key or 'Pokémon')
        proposer_incoming = copy.deepcopy(requested_live)
        target_incoming = copy.deepcopy(offered_live)
        _set_player_pokemon_slot(proposer, offered_slot_key, proposer_incoming)
        _set_player_pokemon_slot(target, requested_slot_key, target_incoming)
        proposer['pokeballs'] = proposer_free_slots
        target['pokeballs'] = target_free_slots
        sync_player_inventory(proposer)
        sync_player_inventory(target)

        _log(
            state,
            proposer.get('name', 'Jogador'),
            f"Trocou {offered_name} com {target.get('name', 'Jogador')} por {requested_name}.",
        )
        return state, {
            'type': 'trade_proposal',
            'accepted': True,
            'proposer_id': proposer_id,
            'target_player_id': player_id,
            'proposer_name': proposer.get('name', 'Jogador'),
            'target_name': target.get('name', 'Jogador'),
            'offered_pokemon': offered_name,
            'requested_pokemon': requested_name,
        }

    offer = pending_action.get('offer') or {}
    from_player_id = offer.get('from_player_id')
    loser_slot = offer.get('loser_slot')
    abra_snapshot = offer.get('pokemon') or {}

    _clear_pending_action(state)
    # Remove this offer from the global list regardless of choice
    state['abra_transfer_offers'] = [
        o for o in (state.get('abra_transfer_offers') or [])
        if not (o.get('from_player_id') == from_player_id and o.get('to_player_id') == player_id)
    ]

    to_player = _get_player(state, player_id)
    if not to_player:
        return None, 'Jogador não encontrado'

    if chosen.get('id') == 'decline':
        _log(state, to_player['name'], 'Recusou a oferta do Abra.')
        return state, {'type': 'abra_transfer_offer', 'accepted': False}

    from_player = _get_player(state, from_player_id)
    if not from_player:
        return None, 'Jogador de origem inválido'

    # Remove Abra from loser's team
    if loser_slot:
        _remove_player_pokemon_slot(from_player, loser_slot)
        sync_player_inventory(from_player)

    # Add Abra to accepting player WITHOUT spending a pokéball
    abra = copy.deepcopy(abra_snapshot)
    abra['knocked_out'] = False
    abra.pop('battle_slot_key', None)
    to_player.setdefault('pokemon', []).append(abra)
    sync_player_inventory(to_player)

    _log(state, to_player['name'], 'Adicionou Abra ao time (sem gastar Pokébola)!')
    _log(state, from_player['name'], f"Abra foi transferido para {to_player['name']}.")

    return state, {'type': 'abra_transfer_offer', 'accepted': True, 'pokemon': 'Abra'}


def _queue_abra_transfer_offer_if_pending(state: dict, player_id: str) -> bool:
    """Se existe oferta de Abra pendente para este jogador, cria pending_action. Retorna True se enfileirou."""
    abra_offers = state.get('abra_transfer_offers') or []
    my_offer = next((o for o in abra_offers if o.get('to_player_id') == player_id), None)
    if not my_offer:
        return False
    from_player = _get_player(state, my_offer.get('from_player_id'))
    from_name = from_player['name'] if from_player else 'outro jogador'
    state['turn']['pending_action'] = {
        'type': 'abra_transfer_offer',
        'player_id': player_id,
        'offer': my_offer,
        'prompt': f"Abra de {from_name} perdeu a batalha! Você quer adicioná-lo ao seu time (sem gastar Pokébola)?",
        'options': [
            {'id': 'accept', 'label': 'Aceitar Abra'},
            {'id': 'decline', 'label': 'Recusar'},
        ],
    }
    return True


def _remove_player_pokemon_slot(player: dict, slot_key: str | None) -> dict | None:
    if not slot_key:
        return None
    if slot_key == 'starter':
        starter = player.get('starter_pokemon')
        if not isinstance(starter, dict):
            return None
        player['starter_pokemon'] = None
        return starter
    if not slot_key.startswith('pokemon:'):
        return None
    try:
        index = int(slot_key.split(':', 1)[1])
    except (TypeError, ValueError):
        return None
    pokemon = player.get('pokemon', [])
    if 0 <= index < len(pokemon):
        return pokemon.pop(index)
    return None


def _set_pokemon_knocked_out(player: dict, slot_key: str | None, knocked_out: bool = True) -> dict | None:
    pokemon = _get_player_pokemon_slot(player, slot_key)
    if pokemon is not None:
        pokemon['knocked_out'] = knocked_out
    return pokemon


def _heal_player_pokemon_slots(player: dict, slot_keys: list[str] | None = None) -> list[str]:
    healed: list[str] = []
    requested = set(slot_keys or [slot_key for slot_key, _ in _iter_player_battle_slots(player, include_knocked_out=True)])
    for slot_key, pokemon in _iter_player_battle_slots(player, include_knocked_out=True):
        if slot_key not in requested or not pokemon.get('knocked_out'):
            continue
        pokemon['knocked_out'] = False
        healed.append(slot_key)
    return healed


def _count_knocked_out_pokemon(player: dict) -> int:
    return sum(1 for _, pokemon in _iter_player_battle_slots(player, include_knocked_out=True) if pokemon.get('knocked_out'))


def _build_gym_slot_label(player: dict, slot_key: str) -> str:
    pokemon = _get_player_pokemon_slot(player, slot_key)
    return pokemon.get('name', slot_key) if pokemon else slot_key


def _build_release_pokemon_options(player: dict) -> list[dict]:
    options: list[dict] = []
    for slot_key, pokemon in _iter_player_battle_slots(player, include_knocked_out=True):
        if not pokemon:
            continue
        label = pokemon.get('name', slot_key)
        if slot_key == 'starter':
            label = f'{label} (Starter)'
        if pokemon.get('knocked_out'):
            label = f'{label} [KO]'
        options.append({
            'id': slot_key,
            'slot_key': slot_key,
            'label': label,
            'pokemon_name': pokemon.get('name', slot_key),
            'slot_cost': pokemon_slot_cost(pokemon),
            'is_starter_slot': slot_key == 'starter',
            'knocked_out': bool(pokemon.get('knocked_out')),
        })
    return options


def _is_current_turn_player(state: dict, player_id: str) -> bool:
    return state.get('turn', {}).get('current_player_id') == player_id


def _is_pokemon_center_tile(tile: dict | None) -> bool:
    if not isinstance(tile, dict):
        return False
    return tile.get('type') == 'city' and (tile.get('data') or {}).get('city_kind') == 'pokemon_center'


def _is_team_rocket_tile(tile: dict | None) -> bool:
    if not isinstance(tile, dict):
        return False
    return tile.get('type') == 'special' and (tile.get('data') or {}).get('special_effect') == 'team_rocket'


def _is_start_tile(tile: dict | None) -> bool:
    if not isinstance(tile, dict):
        return False
    if tile.get('type') == 'start':
        return True
    try:
        return int(tile.get('id', -1)) == 0
    except (TypeError, ValueError):
        return False


def _is_safe_heal_tile(tile: dict | None) -> bool:
    return _is_pokemon_center_tile(tile) or _is_start_tile(tile)


def _get_pokemon_center_tile(board_data: dict, tile_id: int | None) -> dict | None:
    if tile_id is None:
        return None
    try:
        position = int(tile_id)
    except (TypeError, ValueError):
        return None
    tiles = board_data.get('tiles') or []
    if not (0 <= position < len(tiles)):
        return None
    tile = get_tile(board_data, position)
    return tile if _is_pokemon_center_tile(tile) else None


def _get_safe_heal_tile(board_data: dict, tile_id: int | None) -> dict | None:
    if tile_id is None:
        return None
    try:
        position = int(tile_id)
    except (TypeError, ValueError):
        return None
    tile = get_tile(board_data, position)
    return tile if _is_safe_heal_tile(tile) else None


def _get_pokecenters_on_path(board_data: dict, start_position: int, end_position: int) -> list[dict]:
    centers: list[dict] = []
    for position in get_positions_between(int(start_position), int(end_position)):
        tile = get_tile(board_data, position)
        if _is_pokemon_center_tile(tile):
            centers.append(tile)
    return centers


def _set_last_pokemon_center(player: dict, tile: dict, visit_kind: str) -> dict | None:
    if not player or not _is_pokemon_center_tile(tile):
        return None
    record = {
        'tile_id': int(tile.get('id', player.get('position', 0) or 0)),
        'tile_name': tile.get('name', 'Pokemon Center'),
        'visit_kind': visit_kind,
    }
    player['last_pokemon_center'] = record
    return record


def _clear_deferred_pokecenter_heal(player: dict) -> None:
    if player is not None:
        player['deferred_pokecenter_heal'] = None


def _store_deferred_pokecenter_heal(
    player: dict,
    center_tile: dict,
    *,
    heal_limit: int,
    source: str,
) -> None:
    if not player or not _is_pokemon_center_tile(center_tile) or heal_limit <= 0:
        return
    player['deferred_pokecenter_heal'] = {
        'tile_id': int(center_tile.get('id', player.get('position', 0) or 0)),
        'tile_name': center_tile.get('name', 'Pokemon Center'),
        'heal_limit': int(heal_limit),
        'source': source,
    }


def _get_last_pokemon_center_tile(state: dict, player: dict) -> dict | None:
    last_center = player.get('last_pokemon_center') or {}
    return _get_pokemon_center_tile(state.get('board', {}), last_center.get('tile_id'))


def _update_pokecenter_progress(state: dict, player_id: str, start_position: int, end_position: int) -> list[dict]:
    player = _get_player(state, player_id)
    if not player:
        return []
    center_tiles = _get_pokecenters_on_path(state.get('board', {}), start_position, end_position)
    final_position = int(end_position)
    for center_tile in center_tiles:
        visit_kind = 'stopped' if int(center_tile.get('id', -1)) == final_position else 'passed'
        _set_last_pokemon_center(player, center_tile, visit_kind)
    return center_tiles


def _get_special_tile_state(state: dict) -> dict:
    special_tile_state = state.setdefault('special_tile_state', {})
    special_tile_state.setdefault('bill_teleport_used_by', None)
    special_tile_state.setdefault('bicycle_bridge_first_player_id', None)
    special_tile_state.setdefault('mr_fuji_first_player_id', None)
    return special_tile_state


def _get_player_special_tile_flags(player: dict | None) -> dict:
    if not player:
        return {}
    flags = player.setdefault('special_tile_flags', {})
    flags.setdefault('celadon_dept_store_bonus_claimed', False)
    return flags


def _is_celadon_dept_store_tile(tile: dict | None) -> bool:
    if not isinstance(tile, dict):
        return False
    return tile.get('type') == 'special' and (tile.get('data') or {}).get('special_effect') == 'celadon_dept_store'


def _is_teleporter_tile(tile: dict | None) -> bool:
    if not isinstance(tile, dict):
        return False
    return tile.get('type') == 'special' and (tile.get('data') or {}).get('special_effect') == 'teleporter'


def _grant_celadon_dept_store_reach_bonus(state: dict, player_id: str, tile: dict) -> bool:
    player = _get_player(state, player_id)
    if not player or not _is_celadon_dept_store_tile(tile):
        return False

    flags = _get_player_special_tile_flags(player)
    if flags.get('celadon_dept_store_bonus_claimed'):
        return False

    flags['celadon_dept_store_bonus_claimed'] = True
    player['pokeballs'] += 1
    sync_player_inventory(player)
    _log(state, player['name'], f"Alcançou {tile.get('name', 'Celadon Dept. Store')} pela primeira vez e recebeu 1 Pokébola.")
    return True


def _apply_path_reach_effects(state: dict, player_id: str, start_position: int, end_position: int) -> None:
    board_data = state.get('board', {})
    for position in get_positions_between(int(start_position), int(end_position)):
        tile = get_tile(board_data, position)
        _grant_celadon_dept_store_reach_bonus(state, player_id, tile)


def _find_market_card_in_piles(deck: list[dict], discard: list[dict]) -> tuple[dict | None, list[dict], list[dict]]:
    next_deck = list(deck or [])
    for index, card in enumerate(next_deck):
        if card.get('category') == 'market':
            chosen = copy.deepcopy(next_deck.pop(index))
            return chosen, next_deck, list(discard or [])
    return None, list(deck or []), list(discard or [])


def _queue_market_event(state: dict, player_id: str, *, source: str, source_tile: dict | None = None) -> dict:
    player = _get_player(state, player_id)
    if not player:
        return state

    card, new_deck, new_discard = _find_market_card_in_piles(
        state.get('decks', {}).get('event_deck', []),
        state.get('decks', {}).get('event_discard', []),
    )
    state['decks']['event_deck'] = new_deck
    state['decks']['event_discard'] = new_discard

    if not card:
        _log(state, player['name'], f"Não havia carta de PokéMarket disponível para resolver em {source_tile.get('name', source) if source_tile else source}.")
        state['turn']['phase'] = 'end'
        return end_turn(state)

    state['turn']['pending_event'] = card
    state['turn']['phase'] = 'event'
    reveal_card(state, player_id, card, 'event')
    source_name = source_tile.get('name') if isinstance(source_tile, dict) else source
    _log(state, player['name'], f"Chegou em {source_name}. O tile funciona como PokéMarket.")
    return state


def _build_pokemart_roll_prompt(source_name: str, phase: str, rolls: list[int] | None = None) -> str:
    resolved_rolls = [int(roll) for roll in (rolls or [])]
    if phase == 'reroll':
        first_roll = resolved_rolls[0] if resolved_rolls else 6
        return (
            f"Primeira rolagem em {source_name}: {first_roll}. "
            "Role novamente o dado do Poké-Mart para definir entre Poké Ball e Master Ball."
        )
    return f"Você caiu em {source_name}. Role o dado do Poké-Mart para descobrir qual item vai receber."


def _queue_pokemart_roll_action(
    state: dict,
    player_id: str,
    *,
    tile_id: int | str | None,
    source_name: str,
    phase: str = 'initial_roll',
    rolls: list[int] | None = None,
) -> dict:
    resolved_rolls = [int(roll) for roll in (rolls or [])]
    button_label = 'Rerrolar dado do Poké-Mart' if phase == 'reroll' else 'Rolar dado do Poké-Mart'
    _set_pending_action(state, {
        'type': 'pokemart_roll',
        'player_id': player_id,
        'tile_id': tile_id,
        'source_name': source_name,
        'pending_pokemart_roll': True,
        'pokemart_phase': phase,
        'rolls': resolved_rolls,
        'prompt': _build_pokemart_roll_prompt(source_name, phase, resolved_rolls),
        'options': [{'id': 'roll', 'label': button_label}],
        'allowed_actions': ['resolve_pending_action'],
    })
    state['turn']['phase'] = 'action'
    return state


def _resolve_pokemart_tile(state: dict, player_id: str, tile: dict) -> dict:
    player = _get_player(state, player_id)
    if not player:
        return state

    source_name = tile.get('name', 'Poké-Mart')
    _log(state, player['name'], f"Caiu em {source_name}. Aguardando rolagem explícita do dado do Poké-Mart.")
    return _queue_pokemart_roll_action(
        state,
        player_id,
        tile_id=tile.get('id'),
        source_name=source_name,
        phase='initial_roll',
    )


def _resolve_pokemart_roll_action(state: dict, player_id: str, pending_action: dict) -> tuple[dict, dict]:
    player = _get_player(state, player_id)
    if not player:
        return state, {
            'success': False,
            'type': 'pokemart_roll',
            'error': 'Jogador não encontrado',
        }

    source_name = pending_action.get('source_name', 'Poké-Mart')
    phase = pending_action.get('pokemart_phase', 'initial_roll')
    prior_rolls = [int(roll) for roll in (pending_action.get('rolls') or [])]
    roll = roll_market_dice()
    metadata = {
        'tile_id': pending_action.get('tile_id'),
        'stage': 'reroll' if phase == 'reroll' else 'initial',
    }
    if prior_rolls:
        metadata['prior_rolls'] = prior_rolls
        metadata['initial_roll'] = prior_rolls[0]
    _record_roll(
        state,
        roll_type='poké-mart',
        player_id=player_id,
        player_name=player['name'],
        raw_result=roll,
        final_result=roll,
        context='pokemart_tile',
        metadata=metadata,
    )
    current_rolls = prior_rolls + [roll]

    if phase != 'reroll':
        reward = _POKEMART_PRIMARY_REWARDS.get(roll)
        if reward is None:
            _log(
                state,
                player['name'],
                f"Rolou 6 em {source_name}. O Poké-Mart agora aguarda uma segunda rolagem explícita para definir o prêmio.",
            )
            state = _queue_pokemart_roll_action(
                state,
                player_id,
                tile_id=pending_action.get('tile_id'),
                source_name=source_name,
                phase='reroll',
                rolls=current_rolls,
            )
            return state, {
                'success': True,
                'type': 'pokemart_roll',
                'source_name': source_name,
                'pokemart_phase': 'reroll',
                'roll': roll,
                'rolls': current_rolls,
                'requires_additional_roll': True,
            }

        _clear_pending_action(state)
        _log(state, player['name'], f"Rolou {roll} em {source_name} e ganhou {reward['label']}.")
        state = _grant_special_tile_reward(state, player_id, reward['key'], source=source_name)
        state = _resume_pending_effects_or_finish_turn(state, player_id, end_turn_when_done=True)
        return state, {
            'success': True,
            'type': 'pokemart_roll',
            'source_name': source_name,
            'pokemart_phase': phase,
            'roll': roll,
            'rolls': current_rolls,
            'reward_key': reward['key'],
            'reward_label': reward['label'],
        }

    reward = _POKEMART_REROLL_REWARD if roll <= 5 else _POKEMART_JACKPOT_REWARD
    _clear_pending_action(state)
    _log(state, player['name'], f"No reroll de {source_name}, tirou {roll} e ganhou {reward['label']}.")
    state = _grant_special_tile_reward(state, player_id, reward['key'], source=source_name)
    state = _resume_pending_effects_or_finish_turn(state, player_id, end_turn_when_done=True)
    return state, {
        'success': True,
        'type': 'pokemart_roll',
        'source_name': source_name,
        'pokemart_phase': phase,
        'roll': roll,
        'rolls': current_rolls,
        'reward_key': reward['key'],
        'reward_label': reward['label'],
    }


def _queue_game_corner_action(state: dict, player_id: str, *, current_prize_index: int = -1, stage: str | None = None) -> dict:
    next_prize_index = max(0, min(current_prize_index + 1, len(_GAME_CORNER_PRIZES) - 1))
    next_prize = _GAME_CORNER_PRIZES[next_prize_index]
    stage = stage or ('roll' if current_prize_index < 0 else 'decision')
    prompt = (
        f"Role o dado para tentar alcançar {next_prize['label']}. Tirando 1 ou 2 você perde tudo."
        if stage == 'roll'
        else f"Você alcançou { _GAME_CORNER_PRIZES[current_prize_index]['label'] }. Quer parar ou tentar {next_prize['label']}?"
    )
    options = (
        [{'id': 'roll', 'label': f"Rolar em busca de {next_prize['label']}"}]
        if stage == 'roll'
        else [
            {'id': 'stop', 'label': f"Parar e ficar com {_GAME_CORNER_PRIZES[current_prize_index]['label']}"},
            {'id': 'continue', 'label': f"Tentar {next_prize['label']}"},
        ]
    )
    _set_pending_action(state, {
        'type': 'game_corner',
        'player_id': player_id,
        'prompt': prompt,
        'options': options,
        'current_prize_index': current_prize_index,
        'allowed_actions': ['resolve_pending_action'],
    })
    state['turn']['phase'] = 'action'
    return state


def _queue_bill_teleport_choice(state: dict, player_id: str, *, source_tile: dict | None = None) -> dict:
    player = _get_player(state, player_id)
    if not player:
        return state

    options = [
        {'id': other['id'], 'label': f"Teleportar para {other['name']}", 'target_player_id': other['id']}
        for other in state.get('players', [])
        if other.get('is_active', True) and other['id'] != player_id
    ]
    options.append({'id': 'stay', 'label': 'Não teleportar'})
    _set_pending_action(state, {
        'type': 'bill_teleport',
        'player_id': player_id,
        'prompt': f"Bill pode te teleportar a partir de {source_tile.get('name', 'seu tile atual')}. Você quer usar isso agora?",
        'options': options,
        'source_tile_id': source_tile.get('id') if source_tile else None,
        'allowed_actions': ['resolve_pending_action'],
    })
    state['turn']['phase'] = 'action'
    return state


def _queue_miracle_stone_tile_action(state: dict, player_id: str, tile: dict, candidate_slots: list[str]) -> dict:
    player = _get_player(state, player_id)
    if not player:
        return state

    options = [
        {
            'id': slot_key,
            'label': _build_gym_slot_label(player, slot_key),
            'slot_key': slot_key,
        }
        for slot_key in candidate_slots
    ]
    options.append({'id': 'skip', 'label': 'Não evoluir agora'})
    _set_pending_action(state, {
        'type': 'miracle_stone_tile',
        'player_id': player_id,
        'prompt': f"Escolha 1 Pokémon elegível para evoluir instantaneamente em {tile.get('name', 'Miracle Stone')}.",
        'options': options,
        'tile_id': tile.get('id'),
        'allowed_actions': ['resolve_pending_action'],
    })
    state['turn']['phase'] = 'action'
    return state


def _queue_teleporter_manual_roll_action(state: dict, player_id: str, *, source_tile: dict | None = None) -> dict:
    location_suffix = f" em {source_tile.get('name')}" if source_tile else ''
    _set_pending_action(state, {
        'type': 'teleporter_manual_roll',
        'player_id': player_id,
        'prompt': f"O teleporter te concedeu um turno extra. Escolha o resultado do dado de movimento{location_suffix}.",
        'options': [
            {'id': f'roll-{value}', 'label': f'Mover {value} casa(s)', 'dice_result': value}
            for value in range(1, 7)
        ],
        'allowed_actions': ['resolve_pending_action'],
    })
    state['turn']['phase'] = 'roll'
    return state


def _queue_pending_effect(state: dict, effect: dict) -> None:
    state.setdefault('turn', {}).setdefault('pending_effects', []).append(copy.deepcopy(effect))


def _pop_pending_effect(state: dict) -> dict | None:
    pending_effects = state.setdefault('turn', {}).setdefault('pending_effects', [])
    if not pending_effects:
        return None
    return pending_effects.pop(0)


def _apply_pending_effect(state: dict, player_id: str, effect: dict) -> dict:
    kind = (effect or {}).get('kind')
    if kind == 'award_victory_cards':
        return _award_victory_cards(state, player_id, int(effect.get('count', 0) or 0), source=effect.get('source', 'special_tile'))
    if kind == 'draw_event_cards':
        return _draw_event_cards(state, player_id, int(effect.get('count', 0) or 0), source=effect.get('source', 'special_tile'))
    if kind == 'bill_teleport_choice':
        tile = get_tile(state.get('board', {}), int(effect.get('tile_id', -1))) if effect.get('tile_id') is not None else None
        return _queue_bill_teleport_choice(state, player_id, source_tile=tile)
    return state


def _resume_pending_effects_or_finish_turn(state: dict, player_id: str, *, end_turn_when_done: bool) -> dict:
    while True:
        if turn_has_blocking_interaction(state.get('turn')):
            return state
        effect = _pop_pending_effect(state)
        if not effect:
            break
        state = _apply_pending_effect(state, player_id, effect)

    if end_turn_when_done and not turn_has_blocking_interaction(state.get('turn')):
        state['turn']['phase'] = 'end'
        return end_turn(state)
    return state


def _build_pokecenter_heal_prompt(center_name: str, heal_limit: int, visit_kind: str) -> str:
    heal_text = '1 Pokémon nocauteado' if int(heal_limit) == 1 else f"até {int(heal_limit)} Pokémon nocauteados"
    if visit_kind == 'passed':
        return f"Você passou por {center_name}. Escolha {heal_text} para curar."
    if visit_kind == 'returned':
        return f"Você retornou para {center_name}. Escolha {heal_text} para curar."
    if visit_kind == 'remained':
        return f"Você já está em {center_name}. Escolha {heal_text} para curar."
    return f"Você parou em {center_name}. Escolha {heal_text} para curar."


def _queue_pokecenter_heal_action(
    state: dict,
    player_id: str,
    *,
    center_tile: dict,
    heal_limit: int,
    visit_kind: str,
    healed_slots: list[str] | None = None,
    completion: dict | None = None,
) -> bool:
    player = _get_player(state, player_id)
    if not player or not _is_safe_heal_tile(center_tile) or heal_limit <= 0:
        return False

    healed_slots = list(healed_slots or [])
    knockouts = [
        slot_key
        for slot_key, pokemon in _iter_player_battle_slots(player, include_knocked_out=True)
        if pokemon.get('knocked_out')
    ]
    healable_slots = [slot_key for slot_key in knockouts if slot_key not in healed_slots]
    if not healable_slots:
        return False

    options = [
        {'id': slot_key, 'label': f"Curar {_build_gym_slot_label(player, slot_key)}", 'slot_key': slot_key}
        for slot_key in healable_slots
    ]
    options.append({'id': 'finish', 'label': 'Concluir cura'})
    tile_name = center_tile.get('name', 'Pokemon Center')
    _set_pending_action(state, {
        'type': 'pokecenter_heal',
        'player_id': player_id,
        'center_tile_id': int(center_tile.get('id', player.get('position', 0) or 0)),
        'center_tile_name': tile_name,
        'visit_kind': visit_kind,
        'remaining_heals': int(heal_limit),
        'healed_slots': healed_slots,
        'completion': copy.deepcopy(completion) if completion else {'kind': 'resume_turn'},
        'prompt': _build_pokecenter_heal_prompt(tile_name, int(heal_limit), visit_kind),
        'options': options,
        'allowed_actions': ['resolve_pending_action'],
    })
    state['turn']['phase'] = 'action'
    return True


def _complete_pokecenter_heal_action(state: dict, player_id: str, pending_action: dict) -> dict:
    player = _get_player(state, player_id)
    completion = copy.deepcopy(pending_action.get('completion') or {})
    completion_kind = completion.get('kind')
    safe_tile = _get_safe_heal_tile(state.get('board', {}), pending_action.get('center_tile_id'))

    if completion_kind == 'resolve_tile_effect':
        tile = copy.deepcopy(completion.get('tile') or {})
        if not tile:
            return state
        effect = copy.deepcopy(completion.get('effect') or get_tile_effect(tile))
        state['turn']['current_tile'] = tile
        return _resolve_tile_effect(state, player_id, tile, effect)

    if completion_kind == 'finish_pokecenter_stop':
        center_tile = _get_pokemon_center_tile(state.get('board', {}), pending_action.get('center_tile_id'))
        if player and completion.get('grant_full_restore', True):
            add_item(player, 'full_restore', 1)
            _log(
                state,
                player['name'],
                f"Concluiu a parada em {pending_action.get('center_tile_name', 'Pokemon Center')} e recuperou 1 Full Restore.",
            )
        if center_tile:
            state['turn']['current_tile'] = center_tile
        if not _queue_item_choice(state, player_id, f"Parou em {pending_action.get('center_tile_name', 'Pokemon Center')}"):
            state['turn']['phase'] = 'end'
            state = end_turn(state)
        return state

    if completion_kind == 'end_turn':
        if safe_tile:
            state['turn']['current_tile'] = safe_tile
        state['turn']['phase'] = 'end'
        return end_turn(state)

    if safe_tile:
        state['turn']['current_tile'] = safe_tile
    state['turn']['phase'] = 'roll'
    return state


def _activate_deferred_pokecenter_heal_for_current_player(state: dict) -> bool:
    player_id = state.get('turn', {}).get('current_player_id')
    player = _get_player(state, player_id) if player_id else None
    if not player:
        return False

    deferred = copy.deepcopy(player.get('deferred_pokecenter_heal') or {})
    if not deferred:
        return False

    _clear_deferred_pokecenter_heal(player)
    center_tile = _get_pokemon_center_tile(state.get('board', {}), deferred.get('tile_id'))
    if not center_tile:
        return False

    queued = _queue_pokecenter_heal_action(
        state,
        player_id,
        center_tile=center_tile,
        heal_limit=int(deferred.get('heal_limit', 3) or 3),
        visit_kind='returned',
        completion={'kind': 'resume_turn'},
    )
    if queued:
        _log(
            state,
            player['name'],
            f"Começou o turno em {center_tile.get('name', 'Pokemon Center')} e pode curar seus Pokémon nocauteados antes de rolar.",
        )
    return queued


def _handle_pokecenter_pass_through(
    state: dict,
    player_id: str,
    *,
    start_position: int,
    end_position: int,
    final_tile: dict,
    final_effect: dict,
) -> bool:
    player = _get_player(state, player_id)
    if not player:
        return False

    _apply_path_reach_effects(state, player_id, start_position, end_position)
    center_tiles = _update_pokecenter_progress(state, player_id, start_position, end_position)
    if not center_tiles or _is_pokemon_center_tile(final_tile) or not _is_current_turn_player(state, player_id):
        return False

    if _count_knocked_out_pokemon(player) <= 0:
        return False

    last_center = center_tiles[-1]
    queued = _queue_pokecenter_heal_action(
        state,
        player_id,
        center_tile=last_center,
        heal_limit=1,
        visit_kind='passed',
        completion={
            'kind': 'resolve_tile_effect',
            'tile': copy.deepcopy(final_tile),
            'effect': copy.deepcopy(final_effect),
        },
    )
    if queued:
        _log(
            state,
            player['name'],
            f"Passou por {last_center.get('name', 'Pokemon Center')} e pode curar 1 Pokémon nocauteado antes de continuar.",
        )
    return queued


def _return_player_to_last_pokecenter_or_start(state: dict, player_id: str, *, source: str) -> dict:
    player = _get_player(state, player_id)
    if not player:
        return {
            'returned_to_tile_id': 0,
            'returned_to_tile_name': 'Pallet Town',
            'returned_to_center': False,
            'stayed_on_safe_tile': False,
            'turn_ended': False,
            'return_source': source,
        }

    board_data = state.get('board', {})
    current_tile = get_tile(board_data, player.get('position', 0))
    current_position = int(player.get('position', 0) or 0)
    stayed_on_safe_tile = _is_safe_heal_tile(current_tile)
    center_tile = None if stayed_on_safe_tile else _get_last_pokemon_center_tile(state, player)

    if stayed_on_safe_tile:
        destination_tile = current_tile or get_tile(board_data, current_position)
    elif center_tile:
        destination_tile = center_tile
        player['position'] = int(center_tile.get('id', 0) or 0)
        _set_last_pokemon_center(player, center_tile, 'returned')
    else:
        destination_tile = get_tile(board_data, 0)
        player['position'] = 0

    _clear_deferred_pokecenter_heal(player)
    if stayed_on_safe_tile and _is_pokemon_center_tile(destination_tile):
        _set_last_pokemon_center(player, destination_tile, 'stopped')

    sync_player_inventory(player)
    if _is_current_turn_player(state, player_id):
        state['turn']['current_tile'] = destination_tile

    destination_name = destination_tile.get('name', 'Pallet Town') if destination_tile else 'Pallet Town'
    movement_label = f"permaneceu em {destination_name}" if stayed_on_safe_tile else f"voltou para {destination_name}"
    _log(state, player['name'], f"Ficou sem Pokémon utilizáveis após {source} e {movement_label}.")
    return {
        'returned_to_tile_id': int(destination_tile.get('id', 0) if destination_tile else 0),
        'returned_to_tile_name': destination_name,
        'returned_to_center': bool(center_tile),
        'stayed_on_safe_tile': stayed_on_safe_tile,
        'turn_ended': False,
        'return_source': source,
    }


def _handle_total_knockout_recovery(state: dict, player_id: str, *, source: str) -> tuple[dict, dict]:
    player = _get_player(state, player_id)
    return_data = _return_player_to_last_pokecenter_or_start(state, player_id, source=source)
    if not player:
        state['turn']['phase'] = 'end'
        return end_turn(state), return_data

    destination_tile = _get_safe_heal_tile(state.get('board', {}), return_data.get('returned_to_tile_id'))
    visit_kind = 'remained' if return_data.get('stayed_on_safe_tile') else 'returned'
    queued = False
    if destination_tile:
        queued = _queue_pokecenter_heal_action(
            state,
            player_id,
            center_tile=destination_tile,
            heal_limit=1,
            visit_kind=visit_kind,
            completion={'kind': 'end_turn'},
        )

    return_data['recovery_pending'] = queued
    if queued:
        place_label = 'nesse ponto seguro' if _is_start_tile(destination_tile) else destination_tile.get('name', 'Pokemon Center')
        _log(state, player['name'], f"Pode curar 1 Pokémon nocauteado em {place_label} antes do turno passar.")
        return state, return_data

    state['turn']['phase'] = 'end'
    return_data['turn_ended'] = True
    return end_turn(state), return_data


def _queue_item_choice(state: dict, player_id: str, reason: str) -> bool:
    player = _sync_player(state, player_id)
    if not player:
        return False

    overflow = max(0, total_item_count(player) - ITEM_CAPACITY)
    if overflow <= 0:
        state['turn']['pending_item_choice'] = None
        return False

    state['turn']['phase'] = 'item_choice'
    state['turn']['pending_item_choice'] = {
        'player_id': player_id,
        'reason': reason,
        'discard_count': overflow,
    }
    return True


def _set_pending_action(state: dict, action: dict | None) -> None:
    state['turn']['pending_action'] = copy.deepcopy(action) if action else None


def _clear_pending_action(state: dict) -> None:
    state['turn']['pending_action'] = None


def _clear_pending_capture(state: dict) -> None:
    state['turn']['pending_release_choice'] = None


def _queue_release_pokemon_choice(
    state: dict,
    player_id: str,
    *,
    resolution_type: str,
    pokemon: dict,
    capture_cost: int | None = None,
    use_full_restore: bool = False,
    use_master_ball: bool = False,
    capture_roll: dict | None = None,
    reward_source: str | None = None,
    capture_context: str | None = None,
) -> tuple[dict | None, str | dict]:
    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'

    options = _build_release_pokemon_options(player)
    if not options:
        return None, 'Você não possui Pokémon na party para libertar'

    incoming_name = pokemon.get('name', 'o novo Pokémon')
    if resolution_type == 'reward':
        prompt = f"Sua party está sem espaço. Escolha um Pokémon para libertar e receber {incoming_name}, ou cancele."
    else:
        prompt = f"Sua party está sem espaço. Escolha um Pokémon para libertar e capturar {incoming_name}, ou cancele."

    state['turn']['phase'] = 'release_pokemon'
    state['turn']['pending_release_choice'] = {
        'player_id': player_id,
        'resolution_type': resolution_type,
        'capture_cost': None if capture_cost is None else int(capture_cost),
        'use_full_restore': bool(use_full_restore),
        'use_master_ball': bool(use_master_ball),
        'pokemon': copy.deepcopy(pokemon),
        'capture_roll': copy.deepcopy(capture_roll),
        'reward_source': reward_source,
        'capture_context': capture_context,
        'prompt': prompt,
        'allow_cancel': True,
        'options': options,
    }
    _clear_pending_action(state)
    return state, {
        'requires_release': True,
        'pokemon': copy.deepcopy(pokemon),
        'capture_cost': None if capture_cost is None else int(capture_cost),
        'capture_roll': copy.deepcopy(capture_roll),
        'use_master_ball': bool(use_master_ball),
        'options': copy.deepcopy(options),
        'resolution_type': resolution_type,
    }


def turn_has_blocking_interaction(turn: dict | None) -> bool:
    turn = turn or {}
    return bool(
        turn.get('phase') == 'battle'
        or turn.get('battle')
        or turn.get('pending_action')
        or turn.get('pending_event')
        or turn.get('pending_pokemon')
        or turn.get('pending_item_choice')
        or turn.get('pending_release_choice')
    )


def _log_unsupported_pokemon(state: dict, player_name: str, support: dict, source: str) -> None:
    pokemon_name = support.get('pokemon_name') or 'Pokémon desconhecido'
    reasons = []
    if not support.get('metadata_exists'):
        reasons.append('sem metadata válida em cards_metadata.json')
    if not support.get('playable_exists'):
        reasons.append('sem carta jogável no dataset')
    reason_text = ', '.join(reasons) if reasons else 'não suportado'
    _log_warning(state, player_name, f"{pokemon_name} foi ignorado ({source}) — {reason_text}")


def _coerce_inventory_pokemon(
    pokemon: dict | None,
    *,
    source: str,
    player_name: str,
    state: dict,
) -> tuple[dict | None, dict]:
    supported_pokemon, support = ensure_supported_inventory_pokemon(pokemon)
    if supported_pokemon:
        return supported_pokemon, support
    _log_unsupported_pokemon(state, player_name, support, source)
    return None, support


def _resolve_encounters_from_rolls(encounters: list[dict], rolls: list[int]) -> dict:
    if not rolls:
        return {'success': False, 'rolls': []}

    first_roll = int(rolls[0])
    used_rolls = [first_roll]
    matching = [enc for enc in encounters if first_roll in enc.get('roll', [])]
    if not matching:
        return {'success': False, 'rolls': used_rolls}

    reroll_matches = [enc for enc in matching if enc.get('reroll')]
    if reroll_matches:
        if len(rolls) < 2:
            return {'success': False, 'rolls': used_rolls, 'requires_additional_roll': True}
        second_roll = int(rolls[1])
        used_rolls.append(second_roll)
        for encounter in reroll_matches:
            if second_roll in (encounter.get('reroll') or []):
                return {
                    'success': True,
                    'rolls': used_rolls,
                    'pokemon_name': encounter.get('pokemon_name'),
                    'pokemon_id': encounter.get('pokemon_id'),
                    'encounter': encounter,
                }
        return {'success': False, 'rolls': used_rolls}

    chosen = matching[0]
    return {
        'success': True,
        'rolls': used_rolls,
        'pokemon_name': chosen.get('pokemon_name'),
        'pokemon_id': chosen.get('pokemon_id'),
        'encounter': chosen,
    }


def _queue_board_encounter(state: dict, player_id: str, tile: dict, capture_context: str) -> dict:
    player = _get_player(state, player_id)
    encounters = tile.get('data', {}).get('encounters', [])
    if not encounters:
        return state

    _queue_capture_attempt(
        state,
        player_id,
        pokemon=None,
        capture_context=capture_context,
        source='tile_encounter',
        allowed_rolls=None,
        encounters=encounters,
        encounter_source=tile.get('name'),
        prompt=f"Você caiu em {tile.get('name', 'um tile de captura')}. Role o dado de captura para descobrir o encontro.",
    )
    if player:
        _log(state, player['name'], f"Caiu em {tile['name']} e precisa rolar o dado de captura para descobrir o encontro.")
    return state


def _build_capture_attempt_prompt(
    *,
    pokemon: dict | None,
    encounter_source: str | None,
    source: str,
    capture_rolls: list[int] | None = None,
    requires_additional_roll: bool = False,
    master_ball_in_use: bool = False,
) -> str:
    if requires_additional_roll:
        latest = capture_rolls[-1] if capture_rolls else '?'
        if encounter_source:
            if master_ball_in_use:
                return (
                    f"Você rolou {latest} no dado de captura em {encounter_source} usando a Master Ball. "
                    "A próxima rolagem será normal. Role novamente para concluir o encontro."
                )
            return f"Você rolou {latest} no dado de captura em {encounter_source}. Role novamente para concluir o encontro."
        if pokemon:
            if master_ball_in_use:
                return (
                    f"Você rolou {latest} no dado de captura para {pokemon.get('name', 'o Pokémon')} usando a Master Ball. "
                    "A próxima rolagem será normal. Role novamente para concluir a captura."
                )
            return f"Você rolou {latest} no dado de captura para {pokemon.get('name', 'o Pokémon')}. Role novamente para concluir a captura."
        if master_ball_in_use:
            return f"Você rolou {latest} no dado de captura usando a Master Ball. A próxima rolagem será normal. Role novamente para concluir a captura."
        return f"Você rolou {latest} no dado de captura. Role novamente para concluir a captura."
    if encounter_source:
        return f"Você caiu em {encounter_source}. Role o dado de captura para descobrir o encontro."
    if pokemon:
        return f"Role o dado de captura para tentar capturar {pokemon.get('name', 'o Pokémon')}."
    if source == 'event_card':
        return 'Role o dado de captura para resolver a captura da carta de evento.'
    if source == 'victory_card':
        return 'Role o dado de captura para resolver a captura da carta de vitória.'
    return 'Role o dado de captura para resolver esta tentativa.'


def _queue_capture_attempt(
    state: dict,
    player_id: str,
    *,
    pokemon: dict | None,
    capture_context: str,
    source: str,
    allowed_rolls: list[int] | None = None,
    source_card: dict | None = None,
    resolver_card: dict | None = None,
    encounters: list[dict] | None = None,
    encounter_source: str | None = None,
    capture_rolls: list[int] | None = None,
    requires_additional_roll: bool = False,
    master_ball_in_use: bool = False,
    prompt: str | None = None,
) -> dict:
    state['turn']['phase'] = 'action'
    state['turn']['capture_context'] = capture_context
    state['turn']['pending_pokemon'] = copy.deepcopy(pokemon) if pokemon else None
    resolved_rolls = [int(roll) for roll in (capture_rolls or [])]
    _set_pending_action(state, {
        'type': 'capture_attempt',
        'player_id': player_id,
        'source': source,
        'capture_context': capture_context,
        'pokemon_name': pokemon.get('name') if pokemon else None,
        'allowed_rolls': list(allowed_rolls or []),
        'source_card': copy.deepcopy(source_card) if source_card else None,
        'resolver_card': copy.deepcopy(resolver_card) if resolver_card else None,
        'encounters': copy.deepcopy(encounters) if encounters else None,
        'encounter_source': encounter_source,
        'capture_rolls': resolved_rolls,
        'requires_additional_roll': bool(requires_additional_roll),
        'master_ball_in_use': bool(master_ball_in_use),
        'prompt': prompt or _build_capture_attempt_prompt(
            pokemon=pokemon,
            encounter_source=encounter_source,
            source=source,
            capture_rolls=resolved_rolls,
            requires_additional_roll=requires_additional_roll,
            master_ball_in_use=master_ball_in_use,
        ),
        'allowed_actions': ['roll_capture_dice', 'skip_action'],
    })
    return state


def _queue_reward_choice(state: dict, player_id: str, *, source: str, card: dict, options: list[dict], prompt: str) -> dict:
    state['turn']['phase'] = 'event' if source == 'event_card' else 'action'
    _set_pending_action(state, {
        'type': 'reward_choice',
        'player_id': player_id,
        'source': source,
        'prompt': prompt,
        'card': copy.deepcopy(card),
        'options': copy.deepcopy(options),
        'allowed_actions': ['resolve_pending_action'],
    })
    return state


def _grant_reward_pokemon(
    state: dict,
    player_id: str,
    pokemon: dict,
    *,
    source: str,
) -> tuple[dict, dict | str]:
    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'

    supported_pokemon, support = _coerce_inventory_pokemon(
        pokemon,
        source=source,
        player_name=player['name'],
        state=state,
    )
    if not supported_pokemon:
        return None, f"Pokémon sem suporte para inventário: {support.get('pokemon_name') or 'desconhecido'}"
    pokemon = supported_pokemon

    required_slots = pokemon_slot_cost(pokemon)
    if player['pokeballs'] < required_slots:
        return _queue_release_pokemon_choice(
            state,
            player_id,
            resolution_type='reward',
            pokemon=pokemon,
            capture_cost=required_slots,
            reward_source=source,
            capture_context=source,
        )

    finalized, result = _finalize_capture(
        state,
        player_id,
        pokemon,
        capture_cost=required_slots,
        use_full_restore=False,
        acquisition_origin='reward',
        capture_context=source,
    )
    if finalized is None:
        return None, result
    _clear_pending_action(finalized)
    finalized['turn']['capture_context'] = None
    _log(finalized, player['name'], f"Recebeu {pokemon['name']} como recompensa")
    return finalized, {
        **result,
        'granted': True,
        'source': source,
    }


def _award_victory_cards(state: dict, player_id: str, count: int, source: str) -> dict:
    player = _get_player(state, player_id)
    if not player or count <= 0:
        return state

    for _ in range(count):
        card, new_deck, new_discard = draw_card(
            state['decks']['victory_deck'],
            state['decks']['victory_discard'],
        )
        state['decks']['victory_deck'] = new_deck
        state['decks']['victory_discard'] = new_discard
        if not card:
            break

        reveal_card(state, player_id, card, 'victory')
        state.setdefault('consumed', {}).setdefault('victory', []).append(card.get('id'))
        state, result = apply_victory_effect(state, player_id, card)
        state['decks']['victory_discard'] = append_to_discard(state['decks']['victory_discard'], card)
        _log(
            state,
            player['name'],
            f"Carta de vitória revelada em {source}: {_describe_card_for_log(card)} -> {_describe_card_result_for_log(result)}.",
        )

        if result.get('effect') == 'trainer_battle':
            trainer_context = result.get('trainer_battle_context') or {}
            state = _start_trainer_battle(state, player_id, trainer_context, source='victory_card')
            return state

        if result.get('effect') == 'capture_attempt':
            capture_action = result.get('capture_action') or {}
            pokemon_name = capture_action.get('pokemon_name')
            if pokemon_name:
                pokemon = load_playable_pokemon_by_name(pokemon_name)
                if pokemon:
                    if capture_action.get('loop_capture'):
                        state['turn']['loop_capture_pokemon_name'] = pokemon['name']
                    state = _queue_capture_attempt(
                        state,
                        player_id,
                        pokemon=pokemon,
                        capture_context=capture_action.get('capture_context', 'victory_wild'),
                        source='victory_card',
                        allowed_rolls=capture_action.get('allowed_rolls'),
                        source_card=card,
                    )
                    return state
            else:
                state['turn']['phase'] = 'action'
                _set_pending_action(state, {
                    'type': 'capture_attempt',
                    'player_id': player_id,
                    'source': 'victory_card',
                    'capture_context': capture_action.get('capture_context', 'victory_wild'),
                    'allowed_actions': ['roll_capture_dice', 'skip_action'],
                    'resolver_card': copy.deepcopy(capture_action.get('card') or card),
                    'source_card': copy.deepcopy(card),
                })
                return state

        if result.get('effect') == 'gift_pokemon_choice':
            options = result.get('options') or []
            if options:
                state = _queue_reward_choice(
                    state,
                    player_id,
                    source='victory_card',
                    card=card,
                    options=options,
                    prompt='Escolha um dos Pokémon de presente',
                )
            if result.get('unsupported_options'):
                player = _get_player(state, player_id)
                if player:
                    _log_warning(state, player['name'], f"opções indisponíveis ignoradas: {', '.join(result['unsupported_options'])}")
            if options:
                return state

        if state['turn'].get('phase') == 'battle' or state['turn'].get('pending_action'):
            return state

        if result.get('category') == 'draw_event_cards':
            state = _draw_event_cards(state, player_id, int(result.get('draw_count', 0) or 0), source='victory_card')
        elif result.get('category') == 'draw_victory_cards':
            # Evita recursão explosiva; cada carta extra segue a mesma resolução autoritativa.
            state = _award_victory_cards(state, player_id, int(result.get('draw_count', 0) or 0), source='extra_victory')

    return state


def _draw_event_cards(state: dict, player_id: str, count: int, source: str) -> dict:
    player = _get_player(state, player_id)
    if not player or count <= 0:
        return state

    for _ in range(count):
        card, new_deck, new_discard = draw_card(
            state['decks']['event_deck'],
            state['decks']['event_discard'],
        )
        state['decks']['event_deck'] = new_deck
        state['decks']['event_discard'] = new_discard
        if not card:
            break

        reveal_card(state, player_id, card, 'event', resolved=True)
        state.setdefault('consumed', {}).setdefault('events', []).append(card.get('id'))
        state, result = apply_event_effect(state, player_id, card)
        state['decks']['event_discard'] = append_to_discard(state['decks']['event_discard'], card)
        _log(
            state,
            player['name'],
            f"Carta de evento revelada em {source}: {_describe_card_for_log(card)} -> {_describe_card_result_for_log(result)}.",
        )

        effect_type = event_card_effect_type(card)
        if state['turn'].get('pending_action') or state['turn'].get('pending_event') or state['turn'].get('pending_pokemon') or state['turn'].get('phase') == 'battle':
            return state
        if effect_type == 'move_backward_trigger':
            player['position'] = max(0, player['position'] - int(result.get('spaces', 3)))
            tile = get_tile(state['board'], player['position'])
            state['turn']['current_tile'] = tile
            state = _resolve_tile_effect(state, player_id, tile, get_tile_effect(tile))
        elif effect_type == 'move_forward_trigger':
            player['position'] = calculate_new_position(player['position'], int(result.get('spaces', 5)), state['board'])
            tile = get_tile(state['board'], player['position'])
            state['turn']['current_tile'] = tile
            state = _resolve_tile_effect(state, player_id, tile, get_tile_effect(tile))

    return state


def _finalize_capture(
    state: dict,
    player_id: str,
    pokemon: dict,
    capture_cost: int,
    use_full_restore: bool = False,
    *,
    acquisition_origin: str = 'captured',
    capture_context: str | None = None,
    use_master_ball: bool = False,
) -> tuple[dict | None, str | dict]:
    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'

    if use_full_restore:
        if get_item_quantity(player, 'full_restore') <= 0:
            return None, 'Sem Full Restores! Use Pokébolas ou pule.'
        remove_item(player, 'full_restore', 1)

    if capture_cost > 0 and not use_master_ball:
        if player['pokeballs'] < capture_cost:
            return None, 'Sem Pokébolas livres suficientes para armazenar este Pokémon'
        player['pokeballs'] -= capture_cost

    pokemon_copy = _init_pokemon(pokemon)
    if acquisition_origin == 'captured':
        _apply_pokemon_acquisition_metadata(
            pokemon_copy,
            acquisition_origin='captured',
            capture_sequence=_next_capture_sequence(player),
            capture_context=capture_context,
        )
    else:
        _apply_pokemon_acquisition_metadata(
            pokemon_copy,
            acquisition_origin=acquisition_origin,
            capture_sequence=None,
            capture_context=capture_context,
        )
    player['pokemon'].append(pokemon_copy)
    _award_team_bonus_mp(state, player, pokemon_copy)
    _trigger_special_add_to_team_evolutions(
        state,
        player_id,
        newly_added_slot_key=f"pokemon:{len(player['pokemon']) - 1}",
        added_pokemon_name=pokemon_copy.get('name'),
    )
    sync_player_inventory(player)

    state['turn']['pending_pokemon'] = None
    _clear_pending_capture(state)

    return state, {
        'pokemon': pokemon,
        'pokeballs_left': player['pokeballs'],
        'pokeball_slots_used': team_slot_usage(player),
        'pokeball_capacity': player['pokeball_capacity'],
    }


def _find_pokemon_with_ability(player: dict, ability_action: str) -> dict | None:
    """Encontra o Pokémon do jogador com a habilidade pelo nome normalizado."""
    all_pokemon = list(player.get('pokemon', []))
    if player.get('starter_pokemon'):
        all_pokemon.append(player['starter_pokemon'])
    for p in all_pokemon:
        normalized = p.get('ability', '').lower().replace(' ', '_')
        if normalized == ability_action:
            return p
    return None


def _ability_supports_effect(ability: dict | None, effect_kind: str) -> bool:
    if not isinstance(ability, dict):
        return False
    return any(
        effect.get('effect_kind') == effect_kind and effect.get('implemented') is True
        for effect in (ability.get('effects') or [])
    )


def _find_available_capture_ability(
    player: dict,
    effect_kind: str,
) -> tuple[str, dict, dict] | None:
    """Encontra o primeiro Pokémon disponível com a habilidade de captura do tipo effect_kind.

    Retorna (slot_key, pokemon, ability_snapshot) ou None.
    """
    for slot_key, pokemon in _iter_player_battle_slots(player, include_knocked_out=False):
        sync_pokemon_ability_state(pokemon)
        for ability in (pokemon.get('abilities') or []):
            if not _ability_supports_effect(ability, effect_kind):
                continue
            runtime = ability.get('runtime') or {}
            if runtime.get('used_this_turn'):
                continue
            if ability.get('has_charges') and int(ability.get('charges_remaining') or 0) <= 0:
                continue
            return slot_key, pokemon, ability
    return None


def _find_available_battle_reroll_ability(
    player: dict,
    battle_choice: dict,
) -> tuple[str, dict, dict] | None:
    """Encontra a habilidade battle_reroll no Pokémon atualmente em batalha.

    Checa used_this_battle (não used_this_turn).
    Retorna (slot_key, pokemon, ability_snapshot) ou None.
    """
    slot_key = battle_choice.get('battle_slot_key')
    if not slot_key:
        return None
    pokemon = _get_player_pokemon_slot(player, slot_key)
    if not pokemon:
        return None
    sync_pokemon_ability_state(pokemon)
    for ability in (pokemon.get('abilities') or []):
        if not _ability_supports_effect(ability, 'battle_reroll'):
            continue
        runtime = ability.get('runtime') or {}
        if runtime.get('used_this_battle'):
            continue
        if ability.get('has_charges') and int(ability.get('charges_remaining') or 0) <= 0:
            continue
        return slot_key, pokemon, ability
    return None


def _find_available_battle_bp_swap_ability(
    player: dict,
    battle_choice: dict,
) -> tuple[str, dict, dict] | None:
    """Encontra a habilidade de trocar Battle Points no Pokémon atualmente em batalha."""
    slot_key = battle_choice.get('battle_slot_key')
    if not slot_key:
        return None
    pokemon = _get_player_pokemon_slot(player, slot_key)
    if not pokemon:
        return None
    sync_pokemon_ability_state(pokemon)
    for ability in (pokemon.get('abilities') or []):
        if not _ability_supports_effect(ability, 'battle_bp_swap'):
            continue
        runtime = ability.get('runtime') or {}
        if runtime.get('used_this_battle'):
            continue
        if ability.get('has_charges') and int(ability.get('charges_remaining') or 0) <= 0:
            continue
        return slot_key, pokemon, ability
    return None


def _compute_team_bonus_bp(player: dict, chosen: dict) -> int:
    """Retorna bônus de BP de habilidade team_bonus (ex.: múltiplos Beedrill).

    Idempotente: calculado em runtime a partir do estado atual da equipe; não
    é persistido no pokemon, portanto não há risco de duplicação em save/load.
    """
    sync_pokemon_ability_state(chosen)
    chosen_slot_key = chosen.get('battle_slot_key', '')
    for ability in (chosen.get('abilities') or []):
        for effect in (ability.get('effects') or []):
            if effect.get('effect_kind') != 'team_bonus' or not effect.get('implemented'):
                continue
            params = effect.get('params') or {}
            bonus_per_ally = int(params.get('bonus_bp_per_ally') or 0)
            ally_name = params.get('ally_name') or chosen.get('name', '')
            if not bonus_per_ally or not ally_name:
                continue
            ally_name_lc = ally_name.lower()
            count = sum(
                1
                for slot_key, p in _iter_player_battle_slots(player, include_knocked_out=True)
                if (p.get('name') or '').lower() == ally_name_lc and slot_key != chosen_slot_key
            )
            return count * bonus_per_ally
    return 0


def _award_team_bonus_mp(state: dict, player: dict, pokemon: dict) -> None:
    """Concede MP extra de habilidade team_bonus ao adicionar pokemon à equipe.

    Deve ser chamado DEPOIS de appended ao player['pokemon'], para que o contador
    inclua o novo pokemon e `other_count = total - 1` seja correto.
    Idempotente por design: só é chamado uma vez, no momento de aquisição.
    """
    for definition in get_static_ability_definitions(pokemon):
        for effect in (definition.get('effects') or []):
            if effect.get('effect_kind') != 'team_bonus' or not effect.get('implemented'):
                continue
            params = effect.get('params') or {}
            bonus_per_ally = int(params.get('bonus_mp_per_ally') or 0)
            ally_name = params.get('ally_name') or pokemon.get('name', '')
            if not bonus_per_ally or not ally_name:
                continue
            ally_name_lc = ally_name.lower()
            total_count = sum(
                1
                for _, p in _iter_player_battle_slots(player, include_knocked_out=True)
                if (p.get('name') or '').lower() == ally_name_lc
            )
            other_count = total_count - 1  # exclui o recém-adicionado
            if other_count > 0:
                bonus_mp = other_count * bonus_per_ally
                player['bonus_points'] = player.get('bonus_points', 0) + bonus_mp
                player['bonus_master_points'] = player.get('bonus_master_points', 0) + bonus_mp
                _log(
                    state,
                    player['name'],
                    f"Bônus de equipe ({pokemon.get('name', '')}): +{bonus_mp} MP "
                    f"({other_count} aliado(s) com o mesmo nome na equipe)",
                )
            return


def _trigger_special_add_to_team_evolutions(
    state: dict,
    player_id: str,
    *,
    newly_added_slot_key: str | None = None,
    added_pokemon_name: str | None = None,
) -> list[dict]:
    """Resolve evoluções disparadas ao adicionar outro Pokémon ao time."""
    player = _get_player(state, player_id)
    if not player:
        return []

    candidates: list[tuple[str, dict]] = []
    starter = player.get('starter_pokemon')
    if isinstance(starter, dict):
        candidates.append(('starter', starter))
    for index, team_pokemon in enumerate(player.get('pokemon') or []):
        candidates.append((f'pokemon:{index}', team_pokemon))

    evolved: list[dict] = []
    for slot_key, candidate in candidates:
        if slot_key == newly_added_slot_key:
            continue
        if candidate.get('evolution_method') != 'special_add_to_team':
            continue
        if not can_evolve(candidate) or candidate.get('is_baby', False):
            continue

        original_name = candidate.get('name', '?')
        candidate_for_evolution = copy.deepcopy(candidate)
        candidate_for_evolution['battle_slot_key'] = slot_key
        evolved_pokemon = _try_evolve(state, player_id, candidate_for_evolution, heal_on_evolve=False)
        if not evolved_pokemon:
            continue

        evolved.append({
            'slot_key': slot_key,
            'from': original_name,
            'to': evolved_pokemon.get('name'),
        })
        trigger_name = added_pokemon_name or 'outro Pokémon'
        _log(
            state,
            player['name'],
            f"{original_name} evoluiu para {evolved_pokemon['name']} ao adicionar {trigger_name} ao time.",
        )

    return evolved


def _ordered_active_player_ids(state: dict) -> list[str]:
    active_ids = [p['id'] for p in _get_active_players(state)]
    if not active_ids:
        return []

    ordered_ids = [pid for pid in (state.get('turn_order') or []) if pid in active_ids]
    ordered_ids.extend(pid for pid in active_ids if pid not in ordered_ids)
    return ordered_ids


def _next_player_id(state: dict) -> str:
    ids = _ordered_active_player_ids(state)
    if not ids:
        return ''
    current_id = state['turn']['current_player_id']
    try:
        idx = ids.index(current_id)
        return ids[(idx + 1) % len(ids)]
    except ValueError:
        return ids[0]


def _build_debug_visual_player() -> tuple[dict | None, str | None]:
    starting_defaults = get_starting_resource_defaults()
    starter, support = resolve_supported_pokemon_reward('Pichu')
    if not starter:
        return None, (
            f"Pichu não está disponível para o player de teste "
            f"(metadata={support.get('metadata_exists')}, playable={support.get('playable_exists')})"
        )

    player = {
        'id': _DEBUG_TEST_PLAYER_ID,
        'name': _DEBUG_TEST_PLAYER_NAME,
        'color': _DEBUG_TEST_PLAYER_COLOR,
        'is_host': False,
        'is_active': True,
        'is_connected': True,
        'is_test_player': True,
        'position': 0,
        'pokeballs': starting_defaults['pokeballs'],
        'full_restores': starting_defaults['full_restores'],
        'starter_slot_applied': False,
        'starter_pokemon': None,
        'pokemon': [],
        'capture_sequence_counter': 0,
        'last_pokemon_center': None,
        'deferred_pokecenter_heal': None,
        'special_tile_flags': {
            'celadon_dept_store_bonus_claimed': False,
        },
        'items': copy.deepcopy(starting_defaults['items']),
        'badges': [],
        'master_points': 0,
        'bonus_points': 0,
        'league_bonus': 0,
        'has_reached_league': False,
        'skip_turns': 0,
    }

    player['starter_pokemon'] = _apply_pokemon_acquisition_metadata(
        _init_pokemon(starter),
        acquisition_origin='starter',
    )
    player['pokeballs'] = max(0, player['pokeballs'] - pokemon_slot_cost(player['starter_pokemon']))
    player['starter_slot_applied'] = True
    sync_player_inventory(player)
    return player, None


def _build_debug_visual_session() -> tuple[dict | None, str | None]:
    player, error = _build_debug_visual_player()
    if not player:
        return None, error

    board_data = load_board()
    current_tile = get_tile(board_data, player['position'])
    session = {
        'status': 'playing',
        'players': [player],
        'turn_order': [player['id']],
        'board': board_data,
        'decks': {
            'pokemon_deck': build_pokemon_deck(exclude_starters=True),
            'pokemon_discard': [],
            'event_deck': build_event_deck(),
            'event_discard': [],
            'victory_deck': build_victory_deck(),
            'victory_discard': [],
        },
        'consumed': {
            'events': [],
            'pokemon': [],
            'victory': [],
        },
        'special_tile_state': {
            'bill_teleport_used_by': None,
            'bicycle_bridge_first_player_id': None,
            'mr_fuji_first_player_id': None,
        },
        'revealed_card': None,
        'revealed_card_history': [],
        'log': [],
        'turn': {
            'round': 1,
            'current_player_id': player['id'],
            'phase': 'roll',
            'dice_result': None,
            'last_roll': None,
            'roll_history': [],
            'current_tile': current_tile,
            'battle': None,
            'pending_action': None,
            'pending_event': None,
            'pending_pokemon': None,
            'pending_item_choice': None,
            'pending_release_choice': None,
            'pending_reward_choice': None,
            'pending_effects': [],
            'pending_safari': None,
            'starters_chosen': [player['id']],
            'extra_turn': False,
            'capture_context': None,
            'roll_item_modifier': None,
        },
    }
    _log(session, 'Sistema', 'Player de teste visual habilitado.')
    return session, None


def _get_debug_visual_session(state: dict) -> dict | None:
    debug_visual = state.get('debug_visual') or {}
    session = debug_visual.get('session_state')
    if not debug_visual.get('enabled') or not isinstance(session, dict):
        return None
    return session


def _store_debug_visual_session(state: dict, session: dict | None, *, enabled: bool) -> dict:
    debug_visual = state.get('debug_visual') or {}
    state['debug_visual'] = {
        'enabled': enabled,
        'session_state': copy.deepcopy(session) if session else None,
        'shared_battle_resume_state': copy.deepcopy(debug_visual.get('shared_battle_resume_state'))
        if isinstance(debug_visual.get('shared_battle_resume_state'), dict)
        else None,
    }
    return state


def _reset_debug_visual_session_for_free_actions(session: dict) -> dict:
    session = copy.deepcopy(session)
    player = _get_player(session, _DEBUG_TEST_PLAYER_ID)
    turn = session.setdefault('turn', {})
    turn['current_player_id'] = _DEBUG_TEST_PLAYER_ID
    turn['phase'] = 'roll'
    turn['dice_result'] = None
    turn['battle'] = None
    turn['pending_action'] = None
    turn['pending_event'] = None
    turn['pending_pokemon'] = None
    turn['pending_item_choice'] = None
    turn['pending_release_choice'] = None
    turn['pending_reward_choice'] = None
    turn['pending_effects'] = []
    turn['pending_safari'] = None
    turn['capture_context'] = None
    turn['roll_item_modifier'] = None
    turn.pop('encounter_rolls', None)
    turn.pop('encounter_source', None)
    turn.pop('battle_result', None)
    turn.pop('league_results', None)
    turn.pop('compound_eyes_active', None)
    turn.pop('seafoam_legendary', None)
    turn.pop('movement_context', None)
    turn.pop('extra_turn_source', None)
    turn.pop('extra_turn_tile_id', None)
    turn['current_tile'] = get_tile(session.get('board', {}), player.get('position', 0) if player else 0)
    session['revealed_card'] = None
    return session


_DEBUG_SHARED_BATTLE_SOURCE = 'debug_test_player'


def _snapshot_debug_shared_battle_state(state: dict) -> dict:
    return {
        'players': copy.deepcopy(state.get('players', [])),
        'turn': copy.deepcopy(state.get('turn', {})),
        'decks': copy.deepcopy(state.get('decks', {})),
        'consumed': copy.deepcopy(state.get('consumed', {})),
        'revealed_card': copy.deepcopy(state.get('revealed_card')),
        'revealed_card_history': copy.deepcopy(state.get('revealed_card_history', [])),
    }


def _set_debug_shared_battle_resume_state(state: dict, snapshot: dict | None) -> dict:
    debug_visual = copy.deepcopy(state.get('debug_visual') or {})
    debug_visual['shared_battle_resume_state'] = copy.deepcopy(snapshot) if isinstance(snapshot, dict) else None
    state['debug_visual'] = debug_visual
    return state


def _restore_debug_shared_battle_state(state: dict) -> dict:
    debug_visual = state.get('debug_visual') or {}
    snapshot = debug_visual.get('shared_battle_resume_state')
    if not isinstance(snapshot, dict):
        return state

    state['players'] = copy.deepcopy(snapshot.get('players', []))
    state['turn'] = copy.deepcopy(snapshot.get('turn', {}))
    state['decks'] = copy.deepcopy(snapshot.get('decks', {}))
    state['consumed'] = copy.deepcopy(snapshot.get('consumed', {}))
    state['revealed_card'] = copy.deepcopy(snapshot.get('revealed_card'))
    state['revealed_card_history'] = copy.deepcopy(snapshot.get('revealed_card_history', []))
    return _set_debug_shared_battle_resume_state(state, None)


# ── Inicialização ────────────────────────────────────────────────────────────

def initialize_game(state: dict) -> dict:
    """
    Transita de 'waiting' para 'playing'.
    Embaralha baralhos, prepara turno inicial de escolha de starter.
    """
    state = copy.deepcopy(state)
    board_data = load_board()

    state['status'] = 'playing'
    state['board'] = board_data
    state['league_arrival_count'] = 0
    state['decks'] = {
        'pokemon_deck': build_pokemon_deck(exclude_starters=True),
        'pokemon_discard': [],
        'event_deck': build_event_deck(),
        'event_discard': [],
        'victory_deck': build_victory_deck(),
        'victory_discard': [],
    }
    state['log'] = []
    state['revealed_card'] = None
    state['revealed_card_history'] = []
    active_players = _get_active_players(state)
    state['turn_order'] = [p['id'] for p in active_players]
    random.shuffle(state['turn_order'])
    starting_player_id = state['turn_order'][0] if state['turn_order'] else None
    state['turn'] = {
        'round': 1,
        'current_player_id': starting_player_id,
        'phase': 'select_starter',
        'dice_result': None,
        'last_roll': None,
        'roll_history': [],
        'current_tile': None,
        'battle': None,
        'pending_action': None,
        'pending_event': None,
        'pending_pokemon': None,
        'pending_item_choice': None,
        'pending_release_choice': None,
        'pending_reward_choice': None,
        'pending_safari': None,
        'starters_chosen': [],
        'extra_turn': False,
        'available_starters': get_starters(),
        'capture_context': None,
        'roll_item_modifier': None,
    }

    ordered_names = [
        player.get('name', player_id)
        for player_id in state['turn_order']
        for player in [_get_player(state, player_id)]
        if player
    ]
    if ordered_names:
        _log(
            state,
            'Sistema',
            f"Jogo iniciado! Ordem inicial: {', '.join(ordered_names)}. {ordered_names[0]} escolhe primeiro.",
        )
    else:
        _log(state, 'Sistema', 'Jogo iniciado! Cada jogador deve escolher seu Pokémon inicial.')
    return state


# ── Escolha de Starter ───────────────────────────────────────────────────────

def select_starter(state: dict, player_id: str, starter_id) -> dict | None:
    """
    Seleção sequencial de starter: apenas o jogador com current_player_id pode escolher.
    Após a escolha, current_player_id avança para o próximo. Quando todos escolheram,
    inicia o primeiro turno de rolagem.
    """
    state = copy.deepcopy(state)
    turn = state['turn']

    # Apenas o jogador atual pode selecionar neste momento
    if turn.get('current_player_id') != player_id:
        return None

    if player_id in turn.get('starters_chosen', []):
        return None  # Já escolheu

    available = turn.get('available_starters', [])
    starter_id_normalized = str(starter_id)
    starter = next((s for s in available if str(s.get('id')) == starter_id_normalized), None)
    if not starter:
        return None

    # Rejeita se outro jogador já escolheu este starter
    for p in _get_active_players(state):
        if p['id'] != player_id and p.get('starter_pokemon', {}) and str(p['starter_pokemon'].get('id')) == starter_id_normalized:
            return None

    player = _get_player(state, player_id)
    if not player:
        return None

    player['starter_pokemon'] = _apply_pokemon_acquisition_metadata(
        _init_pokemon(starter),
        acquisition_origin='starter',
    )
    player['pokeballs'] = max(0, player.get('pokeballs', 6) - pokemon_slot_cost(player['starter_pokemon']))
    player['starter_slot_applied'] = True
    sync_player_inventory(player)
    turn['starters_chosen'].append(player_id)
    # Remove o starter escolhido da lista de disponíveis
    turn['available_starters'] = [s for s in available if str(s.get('id')) != starter_id_normalized]

    _log(state, player['name'], f"Escolheu {starter['name']} como Pokémon inicial!")

    # Todos escolheram?
    active_ids = _ordered_active_player_ids(state)
    if set(turn['starters_chosen']) >= set(active_ids):
        turn['phase'] = 'roll'
        turn['current_player_id'] = active_ids[0] if active_ids else None
        turn.pop('available_starters', None)
        first_player = _get_player(state, turn['current_player_id']) if turn.get('current_player_id') else None
        if first_player:
            _log(state, 'Sistema', f"Todos escolheram seus iniciais. Turno de {first_player['name']}!")
    else:
        # Avança para o próximo jogador escolher
        turn['current_player_id'] = _next_player_id(state)
        next_player = _get_player(state, turn['current_player_id'])
        if next_player:
            _log(state, 'Sistema', f"Vez de {next_player['name']} escolher seu inicial.")

    return state


# ── Movimento ────────────────────────────────────────────────────────────────

def _should_force_stop_at_gym(player: dict, gym_definition: dict | None) -> bool:
    if not gym_definition:
        return False
    gym_id = gym_definition.get('id')
    if not gym_id:
        return False
    attempted = set(player.get('gyms_attempted') or [])
    defeated = set(player.get('gyms_defeated') or [])
    return gym_id not in attempted and gym_id not in defeated


def _find_forced_special_stop(
    player: dict,
    start_position: int,
    dice_result: int,
    board_data: dict,
) -> tuple[int | None, dict | None, str | None]:
    for position in get_path_positions(start_position, dice_result, board_data):
        tile = get_tile(board_data, position)
        if tile.get('type') == 'gym':
            gym_definition = get_gym_definition(tile_id=tile.get('id'))
            if _should_force_stop_at_gym(player, gym_definition):
                return position, tile, 'gym'
        if _is_team_rocket_tile(tile):
            return position, tile, 'team_rocket'
        if _is_teleporter_tile(tile):
            return position, tile, 'teleporter'
    return None, None, None


def process_move(state: dict, player_id: str, dice_result: int) -> dict:
    """
    Processa rolagem de dado: move o jogador e resolve o efeito da casa.
    """
    state = copy.deepcopy(state)
    state = _clear_host_tools_pending_tile(state, player_id=player_id)
    player = _get_player(state, player_id)
    board_data = state['board']
    pending_action = state['turn'].get('pending_action') or {}
    if pending_action.get('type') == 'ability_decision' and pending_action.get('player_id') == player_id:
        _clear_pending_action(state)

    old_pos = player['position']
    natural_destination = calculate_new_position(old_pos, dice_result, board_data)
    forced_stop_position, forced_tile, forced_stop_kind = _find_forced_special_stop(player, old_pos, dice_result, board_data)
    new_pos = forced_stop_position if forced_stop_position is not None else natural_destination
    player['position'] = new_pos

    tile = get_tile(board_data, new_pos)
    effect = get_tile_effect(tile)

    state['turn']['dice_result'] = dice_result
    state['turn']['current_tile'] = tile
    state['turn']['movement_context'] = {
        'start_position': int(old_pos),
        'dice_result': int(dice_result),
        'natural_destination': int(natural_destination),
        'resolved_destination': int(new_pos),
        'forced_stop_kind': forced_stop_kind,
    }

    _log_movement_resolution(
        state,
        player_name=player['name'],
        start_position=int(old_pos),
        dice_result=int(dice_result),
        natural_destination=int(natural_destination),
        resolved_destination=int(new_pos),
        tile_name=tile.get('name', '?'),
        forced_stop_kind=forced_stop_kind if forced_tile and forced_tile.get('id') == new_pos else None,
    )

    if _handle_pokecenter_pass_through(
        state,
        player_id,
        start_position=old_pos,
        end_position=new_pos,
        final_tile=tile,
        final_effect=effect,
    ):
        return state

    # Resolve o efeito da casa automaticamente ou aguarda ação do jogador
    return _resolve_tile_effect(state, player_id, tile, effect)


def _resolve_tile_effect(state: dict, player_id: str, tile: dict, effect: dict) -> dict:
    player = _get_player(state, player_id)
    tile_type = effect['type']

    if tile_type == 'grass':
        encounters = tile.get('data', {}).get('encounters', [])
        if encounters:
            state = _queue_board_encounter(state, player_id, tile, tile.get('data', {}).get('terrain', 'grass'))
        else:
            card, new_deck, new_discard = draw_card(
                state['decks']['pokemon_deck'],
                state['decks']['pokemon_discard'],
            )
            state['decks']['pokemon_deck'] = new_deck
            state['decks']['pokemon_discard'] = new_discard
            if card:
                state = _queue_capture_attempt(
                    state,
                    player_id,
                    pokemon=card,
                    capture_context='grass',
                    source='tile_draw',
                )

    elif tile_type == 'event':
        card, new_deck, new_discard = draw_card(
            state['decks']['event_deck'],
            state['decks']['event_discard'],
        )
        state['decks']['event_deck'] = new_deck
        state['decks']['event_discard'] = new_discard

        if card:
            state['turn']['pending_event'] = card
            state['turn']['phase'] = 'event'
            reveal_card(state, player_id, card, 'event')
            _log(
                state,
                player['name'],
                f"Carta de evento revelada no tile {tile.get('name', '?')}: {_describe_card_for_log(card)} — confirme para aplicar.",
            )
        else:
            state['turn']['phase'] = 'end'
            state = end_turn(state)

    elif tile_type == 'duel':
        # Jogador decide se quer desafiar (ou escolhe quem)
        state['turn']['phase'] = 'action'
        state['turn']['capture_context'] = 'duel'

    elif tile_type == 'gym':
        gym_definition = get_gym_definition(tile_id=tile.get('id'))
        if not gym_definition:
            _log(state, player['name'], f"O ginásio em {tile.get('name', '?')} ainda não possui configuração jogável.")
            state['turn']['phase'] = 'end'
            state = end_turn(state)
        elif gym_definition['id'] in set(player.get('gyms_defeated') or []):
            _log(state, player['name'], f"Já conquistou o ginásio {gym_definition['leader_name']}. Seguiu viagem sem nova batalha.")
            state['turn']['phase'] = 'end'
            state = end_turn(state)
        else:
            state = _start_gym_battle(state, player_id, tile, gym_definition)

    elif tile_type == 'city':
        city_kind = tile.get('data', {}).get('city_kind')
        if city_kind == 'pokemon_center':
            _set_last_pokemon_center(player, tile, 'stopped')
            queued = _queue_pokecenter_heal_action(
                state,
                player_id,
                center_tile=tile,
                heal_limit=3,
                visit_kind='stopped',
                completion={'kind': 'finish_pokecenter_stop', 'grant_full_restore': True},
            )
            if queued:
                _log(state, player['name'], f"Parou em {tile['name']} e pode curar até 3 Pokémon nocauteados.")
                return state
        elif city_kind == 'pokemart':
            return _resolve_pokemart_tile(state, player_id, tile)
        # Cidade: recupera 1 Full Restore gratuitamente
        add_item(player, 'full_restore', 1)
        _log(state, player['name'], f"Chegou em {tile['name']} e recuperou 1 Full Restore")
        if not _queue_item_choice(state, player_id, f'Chegou em {tile["name"]}'):
            state['turn']['phase'] = 'end'
            state = end_turn(state)

    elif tile_type == 'special':
        # Efeito especial descrito nos dados da casa
        state = _resolve_special_tile(state, player_id, tile)

    elif tile_type == 'league':
        player['has_reached_league'] = True
        _log(state, player['name'], f"Chegou na Liga Pokémon!")
        state = _resolve_league(state, player_id)

    elif tile_type == 'start':
        # Deu a volta: ganha 1 Pokébola bônus
        player['pokeballs'] += 1
        sync_player_inventory(player)
        _log(state, player['name'], f"Passou pela Pallet Town! +1 Pokébola")
        state['turn']['phase'] = 'end'
        state = end_turn(state)

    return state


def _resolve_team_rocket_tile(state: dict, player_id: str, tile: dict) -> dict:
    player = _get_player(state, player_id)
    if not player:
        return state

    _ensure_player_pokemon_acquisition_metadata(player)
    _log(state, player['name'], f"Caiu no tile da Equipe Rocket em {tile.get('name', 'Team Rocket')}! A Equipe Rocket vai rolar o dado.")
    state['turn']['phase'] = 'action'
    _set_pending_action(state, {
        'type': 'team_rocket_roll',
        'player_id': player_id,
        'tile_id': tile.get('id'),
        'tile_name': tile.get('name', 'Team Rocket'),
        'prompt': 'Role o dado da Equipe Rocket para descobrir se o último Pokémon capturado será roubado.',
        'options': [
            {'id': 'roll', 'label': 'Rolar dado da Equipe Rocket'},
        ],
        'allowed_actions': ['resolve_pending_action'],
    })
    return state


def _resolve_team_rocket_roll_action(
    state: dict,
    player_id: str,
    pending_action: dict,
) -> tuple[dict, dict]:
    player = _get_player(state, player_id)
    if not player:
        return state, {'error': 'Jogador não encontrado'}

    _clear_pending_action(state)
    rocket_roll = roll_team_rocket_dice()
    _record_roll(
        state,
        roll_type='Equipe Rocket',
        player_id=player_id,
        player_name='Equipe Rocket',
        raw_result=rocket_roll,
        final_result=rocket_roll,
        context='team_rocket_tile',
        metadata={
            'tile_id': pending_action.get('tile_id'),
            'target_player_id': player_id,
        },
    )

    result = {
        'success': True,
        'type': 'team_rocket_roll',
        'rocket_roll': rocket_roll,
        'tile_id': pending_action.get('tile_id'),
        'tile_name': pending_action.get('tile_name'),
    }

    if rocket_roll <= 3:
        stolen_pokemon = _remove_last_captured_team_pokemon(player)
        if stolen_pokemon:
            _log(
                state,
                'Equipe Rocket',
                f"Rolou {rocket_roll} e roubou {stolen_pokemon['name']}, o último Pokémon capturado de {player['name']}.",
            )
            result.update({
                'stolen': True,
                'stolen_pokemon': stolen_pokemon['name'],
            })
        else:
            _log(
                state,
                'Equipe Rocket',
                f"Rolou {rocket_roll}, mas {player['name']} não tinha Pokémon capturado elegível para roubo. O inicial e suas evoluções não contam como captura.",
            )
            result['stolen'] = False
    else:
        _log(
            state,
            'Equipe Rocket',
            f"Rolou {rocket_roll}. {player['name']} escapou sem perder nenhum Pokémon capturado.",
        )
        result['stolen'] = False

    state['turn']['phase'] = 'end'
    return end_turn(state), result


def _can_use_miracle_stone_on_pokemon(pokemon: dict | None) -> bool:
    if not pokemon or not can_evolve(pokemon):
        return False

    normalized_name = (pokemon.get('name') or '').strip().lower()
    if normalized_name in _SPECIAL_METHOD_EVOLUTION_NAMES:
        return False

    metadata = load_cards_metadata_index().get(normalized_name) or {}
    combined_text = ' '.join(
        part for part in [
            metadata.get('ability_description', ''),
            metadata.get('notes', ''),
        ]
        if part
    ).lower()
    return not any(phrase in combined_text for phrase in _SPECIAL_METHOD_EVOLUTION_PHRASES)


def _build_miracle_stone_candidate_slots(player: dict) -> list[str]:
    candidate_slots: list[str] = []
    for slot_key, pokemon in _iter_player_battle_slots(player, include_knocked_out=True):
        if _can_use_miracle_stone_on_pokemon(pokemon):
            candidate_slots.append(slot_key)
    return candidate_slots


def _grant_special_tile_reward(state: dict, player_id: str, reward_key: str, *, source: str) -> dict:
    player = _get_player(state, player_id)
    if not player:
        return state

    normalized_key = (reward_key or '').strip().lower()
    if normalized_key == 'pokeball':
        player['pokeballs'] += 1
        sync_player_inventory(player)
        _log(state, player['name'], f"Recebeu 1 Pokébola em {source}.")
        return state

    if normalized_key == 'master_ball':
        player['master_balls'] = max(0, int(player.get('master_balls', 0))) + 1
        sync_player_inventory(player)
        _log(state, player['name'], f"Recebeu Master Ball em {source}.")
        return state

    add_item(player, normalized_key, 1)
    item_def = get_item_def(normalized_key)
    item_name = item_def.get('name') or normalized_key
    _log(state, player['name'], f"Recebeu {item_name} em {source}.")
    _queue_item_choice(state, player_id, f'Recompensa em {source}')
    return state


def _resolve_miracle_stone_tile(state: dict, player_id: str, tile: dict) -> dict:
    player = _get_player(state, player_id)
    if not player:
        return state

    candidate_slots = _build_miracle_stone_candidate_slots(player)
    if not candidate_slots:
        _log(state, player['name'], f"Chegou em {tile.get('name', 'Miracle Stone')}, mas não tinha Pokémon elegível para evolução imediata.")
        state['turn']['phase'] = 'end'
        return end_turn(state)

    _log(state, player['name'], f"Chegou em {tile.get('name', 'Miracle Stone')} e pode evoluir 1 Pokémon elegível instantaneamente.")
    return _queue_miracle_stone_tile_action(state, player_id, tile, candidate_slots)


def _resolve_bill_tile(state: dict, player_id: str, tile: dict) -> dict:
    player = _get_player(state, player_id)
    if not player:
        return state

    special_tile_state = _get_special_tile_state(state)
    reward_key = (tile.get('data') or {}).get('granted_item_key', 'bill')
    state = _grant_special_tile_reward(state, player_id, reward_key, source=tile.get('name', 'Bill'))

    teleport_targets = [
        other for other in state.get('players', [])
        if other.get('is_active', True) and other.get('id') != player_id
    ]
    if special_tile_state.get('bill_teleport_used_by'):
        _log(state, player['name'], 'Bill já teleportou outro jogador nesta partida e não pode repetir o efeito.')
        return _resume_pending_effects_or_finish_turn(state, player_id, end_turn_when_done=True)
    if not teleport_targets:
        _log(state, player['name'], 'Bill não encontrou outro jogador válido para teleportar.')
        return _resume_pending_effects_or_finish_turn(state, player_id, end_turn_when_done=True)

    _queue_pending_effect(state, {'kind': 'bill_teleport_choice', 'tile_id': tile.get('id')})
    return _resume_pending_effects_or_finish_turn(state, player_id, end_turn_when_done=True)


def _resolve_game_corner_reward(state: dict, player_id: str, prize_index: int) -> dict:
    prize = _GAME_CORNER_PRIZES[max(0, min(prize_index, len(_GAME_CORNER_PRIZES) - 1))]
    return _grant_special_tile_reward(state, player_id, prize['key'], source='Game Corner')


def _resolve_bicycle_bridge_tile(state: dict, player_id: str, tile: dict) -> dict:
    player = _get_player(state, player_id)
    if not player:
        return state

    special_tile_state = _get_special_tile_state(state)
    first_bonus_player_id = special_tile_state.get('bicycle_bridge_first_player_id')
    first_bonus_name = (tile.get('data') or {}).get('first_player_bonus_pokemon')

    if not first_bonus_player_id and first_bonus_name:
        special_tile_state['bicycle_bridge_first_player_id'] = player_id
        bonus_pokemon = load_pokemon_by_name(first_bonus_name)
        if bonus_pokemon:
            _queue_pending_effect(state, {'kind': 'award_victory_cards', 'count': int((tile.get('data') or {}).get('victory_cards', 1) or 1), 'source': 'bicycle_bridge'})
            granted_state, result = _grant_reward_pokemon(
                state,
                player_id,
                bonus_pokemon,
                source='bicycle_bridge_bonus',
            )
            if granted_state is None:
                _log(state, player['name'], f"Não foi possível receber {first_bonus_name} na Bicycle Bridge: {result}")
                return _award_victory_cards(state, player_id, int((tile.get('data') or {}).get('victory_cards', 1) or 1), source='bicycle_bridge')
            _log(granted_state, player['name'], f"Foi o primeiro a alcançar {tile.get('name', 'Bicycle Bridge')} e recebeu {first_bonus_name}.")
            return _resume_pending_effects_or_finish_turn(granted_state, player_id, end_turn_when_done=True)

    state = _award_victory_cards(state, player_id, int((tile.get('data') or {}).get('victory_cards', 1) or 1), source='bicycle_bridge')
    if first_bonus_player_id and first_bonus_player_id != player_id:
        _log(state, player['name'], f"O bônus de primeiro jogador em {tile.get('name', 'Bicycle Bridge')} já foi reivindicado.")
    if turn_has_blocking_interaction(state.get('turn')):
        return state
    state['turn']['phase'] = 'end'
    return end_turn(state)


def _resolve_safari_zone_tile(state: dict, player_id: str, tile: dict) -> dict:
    player = _get_player(state, player_id)
    if not player:
        return state

    tile_data = tile.get('data') or {}
    if tile_data.get('is_exit'):
        return_to_tile_id = int(tile_data.get('return_to_tile_id', tile.get('id', 0)) or tile.get('id', 0))
        player['position'] = return_to_tile_id
        state['turn']['current_tile'] = get_tile(state.get('board', {}), return_to_tile_id)
        _log(state, player['name'], f"Chegou ao fim da Safari Zone e voltou para {state['turn']['current_tile'].get('name', 'a House')}.")
        state['turn']['phase'] = 'end'
        return end_turn(state)

    pokemon_name = tile_data.get('displayed_pokemon_name')
    pokemon = load_pokemon_by_name(pokemon_name) if pokemon_name else None
    if not pokemon:
        _log(state, player['name'], f"A Safari Zone mostrou {pokemon_name or 'um Pokémon desconhecido'}, mas ele não possui suporte jogável no estado atual.")
        state['turn']['phase'] = 'end'
        return end_turn(state)

    _log(state, player['name'], f"Entrou em {tile.get('name', 'Safari Zone')} e pode tentar capturar {pokemon['name']}.")
    return _queue_capture_attempt(
        state,
        player_id,
        pokemon=pokemon,
        capture_context='safari',
        source='safari_zone_tile',
    )


def _resolve_mr_fuji_house_tile(state: dict, player_id: str, tile: dict) -> dict:
    player = _get_player(state, player_id)
    if not player:
        return state

    house_name = tile.get('name', "Mr. Fuji's House")
    special_tile_state = _get_special_tile_state(state)
    first_bonus_player_id = special_tile_state.get('mr_fuji_first_player_id')
    first_bonus_name = (tile.get('data') or {}).get('first_player_bonus_pokemon')
    event_cards = int((tile.get('data') or {}).get('event_cards', 2) or 2)

    if not first_bonus_player_id and first_bonus_name:
        special_tile_state['mr_fuji_first_player_id'] = player_id
        bonus_pokemon = load_pokemon_by_name(first_bonus_name)
        if bonus_pokemon:
            _queue_pending_effect(state, {'kind': 'draw_event_cards', 'count': event_cards, 'source': 'mr_fuji_house'})
            granted_state, result = _grant_reward_pokemon(state, player_id, bonus_pokemon, source='mr_fuji_house_bonus')
            if granted_state is None:
                _log(state, player['name'], f"Não foi possível receber {first_bonus_name} em Mr. Fuji's House: {result}")
                state = _draw_event_cards(state, player_id, event_cards, source='mr_fuji_house')
                if turn_has_blocking_interaction(state.get('turn')):
                    return state
                state['turn']['phase'] = 'end'
                return end_turn(state)
            _log(granted_state, player['name'], f"Foi o primeiro a alcançar {house_name} e recebeu {first_bonus_name}.")
            return _resume_pending_effects_or_finish_turn(granted_state, player_id, end_turn_when_done=True)

    state = _draw_event_cards(state, player_id, event_cards, source='mr_fuji_house')
    if first_bonus_player_id and first_bonus_player_id != player_id:
        _log(state, player['name'], f"O bônus de primeiro jogador em {house_name} já foi reivindicado.")
    if turn_has_blocking_interaction(state.get('turn')):
        return state
    state['turn']['phase'] = 'end'
    return end_turn(state)


def _resolve_celadon_dept_store_tile(state: dict, player_id: str, tile: dict) -> dict:
    return _queue_market_event(state, player_id, source='celadon_dept_store', source_tile=tile)


def _resolve_teleporter_tile(state: dict, player_id: str, tile: dict) -> dict:
    player = _get_player(state, player_id)
    if not player:
        return state

    pair_tile_id = (tile.get('data') or {}).get('paired_tile_id')
    pair_tile = get_tile(state.get('board', {}), int(pair_tile_id)) if pair_tile_id is not None else None
    if not pair_tile:
        _log(state, player['name'], f"O teleporter em {tile.get('name', 'Teleporter')} não possui destino configurado.")
        state['turn']['phase'] = 'end'
        return end_turn(state)

    movement_context = state.get('turn', {}).get('movement_context') or {}
    landed_exactly = int(movement_context.get('natural_destination', -1) or -1) == int(tile.get('id', -2) or -2)

    player['position'] = int(pair_tile.get('id', player.get('position', 0) or 0))
    state['turn']['current_tile'] = pair_tile
    _log(state, player['name'], f"Alcançou o teleporter em {tile.get('name', 'Teleporter')} e foi enviado instantaneamente para {pair_tile.get('name', 'o outro teleporter')}.")

    if landed_exactly:
        state['turn']['extra_turn'] = True
        state['turn']['extra_turn_source'] = 'teleporter'
        state['turn']['extra_turn_tile_id'] = int(pair_tile.get('id', 0) or 0)
        _log(state, player['name'], 'Como parou exatamente no teleporter, ganhou um turno extra com escolha manual do dado de movimento.')

    state['turn']['phase'] = 'end'
    return end_turn(state)


def _resolve_special_tile(state: dict, player_id: str, tile: dict) -> dict:
    player = _get_player(state, player_id)
    special = tile.get('data', {}).get('special_effect', 'none')

    if special == 'team_rocket':
        state = _resolve_team_rocket_tile(state, player_id, tile)

    elif special == 'miracle_stone':
        state = _resolve_miracle_stone_tile(state, player_id, tile)

    elif special == 'bill':
        state = _resolve_bill_tile(state, player_id, tile)

    elif special == 'game_corner':
        _log(state, player['name'], f"Entrou no {tile.get('name', 'Game Corner')} e pode apostar por um prêmio.")
        state = _queue_game_corner_action(state, player_id)

    elif special == 'bicycle_bridge':
        state = _resolve_bicycle_bridge_tile(state, player_id, tile)

    elif special == 'safari_zone':
        state = _resolve_safari_zone_tile(state, player_id, tile)

    elif special == 'power_plant':
        # Garante carta de Zapdos (lendário elétrico)
        zapdos = load_pokemon_by_name('Zapdos')
        if zapdos:
            state = _queue_capture_attempt(
                state,
                player_id,
                pokemon=zapdos,
                capture_context='power_plant',
                source='power_plant',
            )
            _log(state, player['name'], 'Encontrou Zapdos na Usina Elétrica! Captura custa 2 Pokébolas.')
        else:
            state['turn']['phase'] = 'end'
            state = end_turn(state)

    elif special == 'ss_anne':
        # Ganha 1 Full Restore + 1 Pokébola
        add_item(player, 'full_restore', 1)
        player['pokeballs'] += 1
        sync_player_inventory(player)
        _log(state, player['name'], 'Embarcou no S.S. Anne! +1 Full Restore, +1 Pokébola')
        if not _queue_item_choice(state, player_id, 'Recebeu item no S.S. Anne'):
            state['turn']['phase'] = 'end'
            state = end_turn(state)

    elif special == 'lavender_town':
        state = _draw_event_cards(state, player_id, 2, source='lavender_town')
        if not state['turn'].get('pending_action') and state['turn'].get('phase') not in ('battle', 'event', 'action'):
            state['turn']['phase'] = 'end'
            state = end_turn(state)

    elif special == 'mt_moon':
        # Caverna de Mt. Moon: encontro com Pokémon fóssil (Omanyte ou Kabuto)
        fossil_name = random.choice(_FOSSIL_POKEMON_NAMES)
        fossil = load_pokemon_by_name(fossil_name)
        if fossil:
            state = _queue_capture_attempt(
                state,
                player_id,
                pokemon=fossil,
                capture_context='mt_moon',
                source='mt_moon',
            )
            _log(state, player['name'],
                 f'Monte Lua: um fóssil de {fossil["name"]} foi encontrado! Pode capturar por 1 Pokébola.')
        else:
            # Fallback: draw from deck
            card, new_deck, new_discard = draw_card(
                state['decks']['pokemon_deck'],
                state['decks']['pokemon_discard'],
            )
            state['decks']['pokemon_deck'] = new_deck
            state['decks']['pokemon_discard'] = new_discard
            if card:
                state = _queue_capture_attempt(
                    state,
                    player_id,
                    pokemon=card,
                    capture_context='mt_moon',
                    source='mt_moon',
                )
                _log(state, player['name'], f'Monte Lua: encontrou {card["name"]}!')
            else:
                state['turn']['phase'] = 'end'
                state = end_turn(state)

    elif special == 'cinnabar_lab':
        # Laboratório de Cinnabar: captura gratuita de um Pokémon revivido
        card, new_deck, new_discard = draw_card(
            state['decks']['pokemon_deck'],
            state['decks']['pokemon_discard'],
        )
        state['decks']['pokemon_deck'] = new_deck
        state['decks']['pokemon_discard'] = new_discard
        if card:
            state['turn']['compound_eyes_active'] = True  # Captura gratuita
            state = _queue_capture_attempt(
                state,
                player_id,
                pokemon=card,
                capture_context='cinnabar',
                source='cinnabar',
            )
            _log(state, player['name'],
                 f'Laboratório de Cinnabar: {card["name"]} foi revivido! Captura GRATUITA!')
        else:
            state['turn']['phase'] = 'end'
            state = end_turn(state)

    elif special == 'seafoam':
        # Ilhas Seafoam: encontro com Articuno (lendário de gelo)
        articuno = load_pokemon_by_name('Articuno')
        if articuno:
            state['turn']['seafoam_legendary'] = True
            state = _queue_capture_attempt(
                state,
                player_id,
                pokemon=articuno,
                capture_context='seafoam',
                source='seafoam',
            )
            _log(state, player['name'],
                 'Articuno apareceu nas Ilhas Seafoam! Custa 2 Pokébolas ou 1 Full Restore.')
        else:
            state['turn']['phase'] = 'end'
            state = end_turn(state)

    elif special == 'mystery_cave':
        # Caverna Misteriosa: encontro com Pokémon Fantasma (Gastly, Haunter, Gengar ou Ditto)
        ghost_name = random.choice(_MYSTERY_CAVE_POKEMON_NAMES)
        ghost = load_pokemon_by_name(ghost_name)
        if ghost:
            state = _queue_capture_attempt(
                state,
                player_id,
                pokemon=ghost,
                capture_context='mystery_cave',
                source='mystery_cave',
            )
            _log(state, player['name'],
                 f'Caverna Misteriosa: um {ghost["name"]} aparece nas sombras! Custa 1 Pokébola.')
        else:
            state['turn']['phase'] = 'end'
            state = end_turn(state)

    elif special == 'mr_fuji_house':
        state = _resolve_mr_fuji_house_tile(state, player_id, tile)

    elif special == 'celadon_dept_store':
        state = _resolve_celadon_dept_store_tile(state, player_id, tile)

    elif special == 'teleporter':
        state = _resolve_teleporter_tile(state, player_id, tile)

    else:
        state['turn']['phase'] = 'end'
        state = end_turn(state)

    return state


def resolve_event(state: dict, player_id: str, use_run_away: bool = False) -> tuple[dict | None, str]:
    """
    Confirma ou foge de um evento pendente.
    use_run_away=True: usa Rattata (Run Away) para ignorar eventos negativos.
    """
    state = copy.deepcopy(state)
    turn = state['turn']

    if turn.get('phase') != 'event':
        return None, 'Não é fase de evento'
    if turn.get('current_player_id') != player_id:
        return None, 'Não é seu turno'

    card = turn.get('pending_event')
    if not card:
        return None, 'Nenhum evento pendente'

    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'

    if use_run_away:
        rattata = _find_pokemon_with_ability(player, 'run_away')
        if not rattata or rattata.get('ability_used'):
            return None, 'Rattata com Run Away não disponível'
        if not is_negative_event_card(card):
            return None, 'Run Away só funciona em eventos negativos'
        rattata['ability_used'] = True
        _log(state, player['name'], f"Usou Run Away! Fugiu do evento: {card.get('title', '?')}")
    else:
        state, result = apply_event_effect(state, player_id, card)
        _log(state, player['name'], f"Evento: {card.get('title', 'Carta de Evento')}")
        effect_type = event_card_effect_type(card)
        if result.get('effect') == 'capture_attempt':
            capture_action = result.get('capture_action') or {}
            pokemon_name = capture_action.get('pokemon_name')
            if pokemon_name:
                pokemon = load_playable_pokemon_by_name(pokemon_name)
                if pokemon:
                    state = _queue_capture_attempt(
                        state,
                        player_id,
                        pokemon=pokemon,
                        capture_context=capture_action.get('capture_context', 'event_card'),
                        source='event_card',
                        allowed_rolls=capture_action.get('allowed_rolls'),
                        source_card=card,
                    )
            else:
                state['turn']['phase'] = 'action'
                _set_pending_action(state, {
                    'type': 'capture_attempt',
                    'player_id': player_id,
                    'source': 'event_card',
                    'capture_context': capture_action.get('capture_context', 'event_card'),
                    'allowed_actions': ['roll_capture_dice', 'skip_action'],
                    'resolver_card': copy.deepcopy(capture_action.get('card') or card),
                    'source_card': copy.deepcopy(card),
                })
        elif result.get('effect') == 'gift_pokemon_choice':
            options = result.get('options') or []
            if options:
                state = _queue_reward_choice(
                    state,
                    player_id,
                    source='victory_card' if card.get('pile') == 'victory' else 'event_card',
                    card=card,
                    options=options,
                    prompt='Escolha um dos Pokémon disponíveis',
                )
            if result.get('unsupported_options'):
                _log_warning(state, player['name'], f"opções indisponíveis ignoradas: {', '.join(result['unsupported_options'])}")
        elif result.get('effect') == 'teleporter_choice':
            options = [
                {'id': p['id'], 'label': p['name'], 'target_player_id': p['id']}
                for p in state.get('players', [])
                if p.get('is_active', True) and p['id'] != player_id
            ]
            state = _queue_reward_choice(state, player_id, source='event_card', card=card, options=options, prompt='Escolha para qual jogador você quer se teleportar')
        elif result.get('effect') == 'mr_fuji_choice':
            options = []
            for index, pokemon in enumerate(player.get('pokemon_inventory', [])):
                options.append({
                    'id': f"mr-fuji-{index}",
                    'label': pokemon['name'],
                    'pokemon_index': index,
                })
            state = _queue_reward_choice(state, player_id, source='event_card', card=card, options=options, prompt='Escolha qual Pokémon entregar ao Mr. Fuji')
        elif result.get('effect') == 'oak_assistant_choice':
            active_players = [p for p in state.get('players', []) if p.get('is_active', True)]
            min_pokeballs = min((p.get('pokeballs', 0) for p in active_players), default=0)
            if player.get('pokeballs', 0) == min_pokeballs and player.get('items'):
                options = [
                    {'id': item['key'], 'label': f"{item['name']} x{item['quantity']}", 'item_key': item['key']}
                    for item in player.get('items', [])
                ]
                state = _queue_reward_choice(state, player_id, source='event_card', card=card, options=options, prompt='Escolha um item para trocar por 1 Pokébola')
            else:
                _log(state, player['name'], "Oak's Assistant não teve efeito: você não é elegível ou não possui itens")
        if result.get('effect') == 'trainer_battle':
            trainer_context = result.get('trainer_battle_context') or {}
            state = _start_trainer_battle(state, player_id, trainer_context, source='event_card')
            turn['pending_event'] = None
            state['decks']['event_discard'] = append_to_discard(state['decks']['event_discard'], card)
            state.setdefault('consumed', {}).setdefault('events', []).append(card.get('id'))
            return state, 'ok'
        if effect_type == 'move_backward_trigger':
            old_position = player['position']
            player['position'] = max(0, player['position'] - int(result.get('spaces', 3)))
            tile = get_tile(state['board'], player['position'])
            state['turn']['current_tile'] = tile
            if _handle_pokecenter_pass_through(
                state,
                player_id,
                start_position=old_position,
                end_position=player['position'],
                final_tile=tile,
                final_effect=get_tile_effect(tile),
            ):
                state['decks']['event_discard'] = append_to_discard(state['decks']['event_discard'], card)
                state.setdefault('consumed', {}).setdefault('events', []).append(card.get('id'))
                state['turn']['pending_event'] = None
                return state, 'ok'
            state = _resolve_tile_effect(state, player_id, tile, get_tile_effect(tile))
        elif effect_type == 'move_forward_trigger':
            old_position = player['position']
            player['position'] = calculate_new_position(player['position'], int(result.get('spaces', 5)), state['board'])
            tile = get_tile(state['board'], player['position'])
            state['turn']['current_tile'] = tile
            if _handle_pokecenter_pass_through(
                state,
                player_id,
                start_position=old_position,
                end_position=player['position'],
                final_tile=tile,
                final_effect=get_tile_effect(tile),
            ):
                state['decks']['event_discard'] = append_to_discard(state['decks']['event_discard'], card)
                state.setdefault('consumed', {}).setdefault('events', []).append(card.get('id'))
                state['turn']['pending_event'] = None
                return state, 'ok'
            state = _resolve_tile_effect(state, player_id, tile, get_tile_effect(tile))
        elif result.get('category') == 'special_event' and result.get('effect') == 'gift_pokemon_from_area':
            tile = state['turn'].get('current_tile') or get_tile(state['board'], player.get('position', 0))
            if tile:
                state = _queue_board_encounter(state, player_id, tile, 'event_card')

    state['decks']['event_discard'] = append_to_discard(state['decks']['event_discard'], card)
    state.setdefault('consumed', {}).setdefault('events', []).append(card.get('id'))
    state['turn']['pending_event'] = None
    if state['turn'].get('pending_action') or state['turn'].get('pending_pokemon') or state['turn'].get('phase') in ('action', 'battle'):
        return state, 'ok'
    if not _queue_item_choice(state, player_id, f"Evento: {card.get('title', 'Carta de Evento')}"):
        state['turn']['phase'] = 'end'
        state = end_turn(state)
    return state, 'ok'


# ── Handlers de habilidades ativas ───────────────────────────────────────────
# Cada handler tem assinatura:
#   _handle_xxx(state, player, pokemon, **kwargs) -> tuple[dict | None, dict | str]
#
# Convenção de retorno:
#   (None, 'mensagem de erro')  — habilidade inválida nas condições atuais
#   (state, result_dict)        — sucesso; state já modificado in-place
#
# Os handlers podem chamar _resolve_tile_effect, end_turn, _log etc.
# definidos posteriormente no módulo (Python resolve nomes em tempo de chamada).

def _handle_movement_replace(state: dict, player: dict, pokemon: dict, steps: int, **kw) -> tuple:
    """Base compartilhada para habilidades que substituem o rolar do dado."""
    turn = state['turn']
    if turn.get('phase') != 'roll':
        return None, 'Use esta habilidade na fase de rolagem (em vez de rolar o dado)'
    board_data = state.get('board', {})
    old_pos = player['position']
    new_pos = calculate_new_position(old_pos, steps, board_data)
    player['position'] = new_pos
    tile = get_tile(board_data, new_pos)
    effect = get_tile_effect(tile)
    turn['dice_result'] = steps
    turn['current_tile'] = tile
    pokemon['ability_used'] = True
    _log(state, player['name'],
         f"Usou {pokemon['ability']}! Avançou {steps} casas para {tile['name']}")
    if _handle_pokecenter_pass_through(
        state,
        player['id'],
        start_position=old_pos,
        end_position=new_pos,
        final_tile=tile,
        final_effect=effect,
    ):
        return state, {}
    state = _resolve_tile_effect(state, player['id'], tile, effect)
    return state, {}


def _handle_hurricane(state: dict, player: dict, pokemon: dict, **kw) -> tuple:
    return _handle_movement_replace(state, player, pokemon, steps=5, **kw)


def _handle_extreme_speed(state: dict, player: dict, pokemon: dict, **kw) -> tuple:
    turn = state['turn']
    if turn.get('phase') != 'action':
        return None, 'Use Extreme Speed após cair em uma casa (fase de ação)'
    board_data = state.get('board', {})
    old_pos = player['position']
    new_pos = calculate_new_position(old_pos, 1, board_data)
    player['position'] = new_pos
    tile = get_tile(board_data, new_pos)
    effect = get_tile_effect(tile)
    turn['pending_pokemon'] = None
    turn['pending_action'] = None
    turn['capture_context'] = None
    turn['current_tile'] = tile
    pokemon['ability_used'] = True
    _log(state, player['name'],
         f"Usou Extreme Speed! Avançou para a próxima casa: {tile['name']}")
    if _handle_pokecenter_pass_through(
        state,
        player['id'],
        start_position=old_pos,
        end_position=new_pos,
        final_tile=tile,
        final_effect=effect,
    ):
        return state, {}
    state = _resolve_tile_effect(state, player['id'], tile, effect)
    return state, {}


def _handle_teleport(state: dict, player: dict, pokemon: dict, **kw) -> tuple:
    turn = state['turn']
    target_position = kw.get('target_position')
    if turn.get('phase') != 'roll':
        return None, 'Use Teleport na fase de rolagem (em vez de rolar o dado)'
    if target_position is None:
        return None, 'Informe a posição alvo para Teleport (target_position)'
    if not (0 <= target_position < player['position']):
        return None, 'Teleport só pode mover para posições já visitadas (0 até posição atual - 1)'
    board_data = state.get('board', {})
    player['position'] = target_position
    tile = get_tile(board_data, target_position)
    effect = get_tile_effect(tile)
    turn['dice_result'] = target_position
    turn['current_tile'] = tile
    pokemon['ability_used'] = True
    _log(state, player['name'],
         f"Usou Teleport! Voltou para casa {target_position}: {tile['name']}")
    state = _resolve_tile_effect(state, player['id'], tile, effect)
    return state, {}


def _handle_water_gun(state: dict, player: dict, pokemon: dict, **kw) -> tuple:
    """Wartortle: rerrola o dado de movimento (em vez do movimento +2 incorreto anterior)."""
    turn = state['turn']
    if turn.get('phase') != 'roll':
        return None, 'Use Water Gun na fase de rolagem (em vez de rolar o dado)'
    from .mechanics import roll_movement_dice
    new_roll = roll_movement_dice()
    return _handle_movement_replace(state, player, pokemon, steps=new_roll, **kw)


def _handle_hydro_pump(state: dict, player: dict, pokemon: dict, **kw) -> tuple:
    """Blastoise: rerrola o dado de movimento (em vez de empurrar oponente — comportamento incorreto anterior)."""
    turn = state['turn']
    if turn.get('phase') != 'roll':
        return None, 'Use Hydro Pump na fase de rolagem (em vez de rolar o dado)'
    from .mechanics import roll_movement_dice
    new_roll = roll_movement_dice()
    return _handle_movement_replace(state, player, pokemon, steps=new_roll, **kw)


def _handle_compound_eyes(state: dict, player: dict, pokemon: dict, **kw) -> tuple:
    turn = state['turn']
    if turn.get('phase') != 'action':
        return None, 'Use Compound Eyes na fase de ação (quando houver Pokémon para capturar)'
    if not turn.get('pending_pokemon'):
        return None, 'Não há Pokémon disponível para capturar agora'
    turn['compound_eyes_active'] = True
    pokemon['ability_used'] = True
    _log(state, player['name'], 'Usou Compound Eyes! Próxima captura não gasta Pokébola')
    return state, {}


def _handle_run_away(state: dict, player: dict, pokemon: dict, **kw) -> tuple:
    turn = state['turn']
    if turn.get('phase') != 'event':
        return None, 'Use Run Away quando uma carta de evento negativa aparecer'
    card = turn.get('pending_event', {})
    if not card or not is_negative_event_card(card):
        return None, 'Run Away só funciona em eventos negativos'
    turn['pending_event'] = None
    pokemon['ability_used'] = True
    _log(state, player['name'],
         f"Usou Run Away! Fugiu do evento: {card.get('title', '?')}")
    turn['phase'] = 'end'
    state = end_turn(state)
    return state, {}


def _handle_psychic(state: dict, player: dict, pokemon: dict, **kw) -> tuple:
    """Alakazam: teletransporta para a casa de outro jogador (em vez de rolar o dado)."""
    turn = state['turn']
    target_id = kw.get('target_id')
    if turn.get('phase') != 'roll':
        return None, 'Use Psychic na fase de rolagem (em vez de rolar o dado)'
    if not target_id:
        return None, 'Informe o jogador alvo para Psychic (target_id)'
    target = _get_player(state, target_id)
    if not target or not target.get('is_active') or target_id == player['id']:
        return None, 'Alvo inválido'
    board_data = state.get('board', {})
    old_pos = player['position']
    target_pos = target['position']
    player['position'] = target_pos
    tile = get_tile(board_data, target_pos)
    effect = get_tile_effect(tile)
    turn['dice_result'] = target_pos
    turn['current_tile'] = tile
    pokemon['ability_used'] = True
    _log(state, player['name'],
         f"Usou Psychic! Teletransportou para a posição de {target['name']}: {tile['name']}")
    if _handle_pokecenter_pass_through(
        state,
        player['id'],
        start_position=old_pos,
        end_position=target_pos,
        final_tile=tile,
        final_effect=effect,
    ):
        return state, {}
    state = _resolve_tile_effect(state, player['id'], tile, effect)
    return state, {'target_id': target_id, 'new_position': target_pos}


def _handle_psybeam(state: dict, player: dict, pokemon: dict, **kw) -> tuple:
    """Kadabra: teletransporta para a casa de evento mais próxima atrás (em vez de rolar o dado)."""
    turn = state['turn']
    if turn.get('phase') != 'roll':
        return None, 'Use Psybeam na fase de rolagem (em vez de rolar o dado)'
    board_data = state.get('board', {})
    current_pos = player['position']
    target_pos = None
    for pos in range(current_pos - 1, -1, -1):
        candidate = get_tile(board_data, pos)
        if candidate.get('type') == 'event':
            target_pos = pos
            break
    if target_pos is None:
        return None, 'Não há casa de evento atrás da sua posição atual'
    old_pos = current_pos
    player['position'] = target_pos
    tile = get_tile(board_data, target_pos)
    effect = get_tile_effect(tile)
    turn['dice_result'] = target_pos
    turn['current_tile'] = tile
    pokemon['ability_used'] = True
    _log(state, player['name'],
         f"Usou Psybeam! Voltou para a casa de evento mais próxima: {tile['name']} (posição {target_pos})")
    state = _resolve_tile_effect(state, player['id'], tile, effect)
    return state, {'target_position': target_pos}


def _handle_move_1(state: dict, player: dict, pokemon: dict, **kw) -> tuple:
    """Mew: move exatamente 1 casa em vez de rolar o dado."""
    return _handle_movement_replace(state, player, pokemon, steps=1, **kw)


def _handle_move_2(state: dict, player: dict, pokemon: dict, **kw) -> tuple:
    """Jolteon: move exatamente 2 casas em vez de rolar o dado."""
    return _handle_movement_replace(state, player, pokemon, steps=2, **kw)


def _handle_move_3(state: dict, player: dict, pokemon: dict, **kw) -> tuple:
    """Pichu / Pikachu / Raichu: move exatamente 3 casas em vez de rolar o dado."""
    return _handle_movement_replace(state, player, pokemon, steps=3, **kw)


def _handle_torrent(state: dict, player: dict, pokemon: dict, **kw) -> tuple:
    """Squirtle: rerrola o dado de movimento."""
    turn = state['turn']
    if turn.get('phase') != 'roll':
        return None, 'Use Torrent na fase de rolagem (em vez de rolar o dado)'
    from .mechanics import roll_movement_dice
    new_roll = roll_movement_dice()
    return _handle_movement_replace(state, player, pokemon, steps=new_roll, **kw)


# ── Dispatch de habilidades ativas ────────────────────────────────────────────
# Para adicionar uma nova habilidade: crie _handle_xxx acima e registre aqui.
_ACTIVE_ABILITY_HANDLERS: dict[str, callable] = {
    'hurricane':      _handle_hurricane,
    'extreme_speed':  _handle_extreme_speed,
    'flash_fire':     _handle_extreme_speed,   # Growlithe: mesma lógica do Extreme Speed
    'teleport':       _handle_teleport,
    'water_gun':      _handle_water_gun,
    'hydro_pump':     _handle_hydro_pump,
    'compound_eyes':  _handle_compound_eyes,
    'run_away':       _handle_run_away,
    'psychic':        _handle_psychic,
    'psybeam':        _handle_psybeam,
    'static':         _handle_move_3,
    'thunder':        _handle_move_3,
    'move_3':         _handle_move_3,          # Pichu: ability slug 'Move 3'
    'torrent':        _handle_torrent,
    'volt_absorb':    _handle_move_2,          # Jolteon: mover 2 casas
    'synchronize':    _handle_move_1,          # Mew: mover 1 casa
}


# ── Habilidades ativas ────────────────────────────────────────────────────────

def use_ability(state: dict, player_id: str, ability_action: str,
                target_id: str | None = None,
                target_position: int | None = None) -> tuple[dict | None, dict | str]:
    """
    Ativa uma habilidade ativa de um Pokémon do jogador.
    Retorna (novo_estado, resultado_info) ou (None, mensagem_de_erro).

    Para adicionar novas habilidades: crie _handle_xxx e registre em _ACTIVE_ABILITY_HANDLERS.
    """
    state = copy.deepcopy(state)
    turn = state['turn']

    if turn.get('current_player_id') != player_id:
        return None, 'Não é seu turno'

    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'

    pokemon = _find_pokemon_with_ability(player, ability_action)
    if not pokemon:
        return None, f'Você não tem um Pokémon com a habilidade "{ability_action}"'
    if pokemon.get('ability_used'):
        return None, 'Habilidade já utilizada'

    handler = _ACTIVE_ABILITY_HANDLERS.get(ability_action)
    if not handler:
        return None, f'Habilidade "{ability_action}" ainda não implementada no engine'

    result = handler(state, player, pokemon,
                     target_id=target_id, target_position=target_position)

    if result[0] is None:
        return result  # propagate error

    state, extra = result
    base_result = {'type': 'ability_used', 'ability': ability_action, 'player_id': player_id}
    base_result.update(extra)
    return state, base_result


def use_pokemon_ability(
    state: dict,
    player_id: str,
    *,
    slot_key: str | None,
    ability_id: str | None = None,
    action_id: str | None = None,
) -> tuple[dict | None, dict | str]:
    state = copy.deepcopy(state)
    turn = state.get('turn') or {}

    if turn.get('current_player_id') != player_id:
        return None, 'Não é seu turno'

    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'

    annotate_state_ability_snapshots(state)
    pokemon = _get_player_pokemon_slot(player, slot_key)
    if not pokemon:
        return None, 'Pokémon inválido para ativar habilidade'

    selected_ability_id = (ability_id or 'primary').strip() or 'primary'
    selected_action_id = (action_id or '').strip()
    if not selected_action_id:
        return None, 'Ação de habilidade inválida'

    ability = next(
        (
            item for item in (pokemon.get('abilities') or [])
            if item.get('id') == selected_ability_id
        ),
        None,
    )
    if not ability:
        return None, 'Habilidade não encontrada'

    action = next(
        (
            item for item in (ability.get('actions') or [])
            if item.get('action_id') == selected_action_id
        ),
        None,
    )
    if not action:
        return None, 'Ação de habilidade não encontrada'
    if not action.get('supported'):
        return None, 'Esta ação de habilidade ainda não possui handler seguro'
    if not action.get('can_activate_now'):
        return None, action.get('disabled_reason') or 'Esta habilidade não pode ser usada agora'

    pokemon_name = pokemon.get('name', 'Pokémon')
    ability_name = ability.get('name') or 'Habilidade'
    effect_kind = action.get('effect_kind')
    consume_charge = ability.get('charges_total') is not None

    if effect_kind == 'fixed_move':
        steps = int((action.get('params') or {}).get('steps') or 0)
        if steps <= 0:
            return None, 'Movimento fixo inválido'
        mark_primary_ability_used(pokemon, scope='turn', consume_charge=consume_charge)
        _log(state, player['name'], f'Usou {ability_name} de {pokemon_name} para mover {steps} casa(s) sem rolar o dado.')
        state = process_move(state, player_id, steps)
        return state, {
            'type': 'manual_pokemon_ability',
            'pokemon': pokemon_name,
            'ability_name': ability_name,
            'effect_kind': effect_kind,
            'steps': steps,
        }

    if effect_kind == 'capture_free_next':
        mark_primary_ability_used(pokemon, scope='turn', consume_charge=consume_charge)
        state['turn']['compound_eyes_active'] = True
        _log(state, player['name'], f'Usou {ability_name} de {pokemon_name}. A próxima captura deste turno não gastará Pokébola.')
        return state, {
            'type': 'manual_pokemon_ability',
            'pokemon': pokemon_name,
            'ability_name': ability_name,
            'effect_kind': effect_kind,
            'capture_free': True,
        }

    if effect_kind == 'heal_other':
        if state['turn'].get('phase') == 'battle':
            return None, 'Não é possível curar outro Pokémon durante uma batalha'
        # Find knocked-out Pokémon excluding the ability user's own slot
        options = []
        for target_slot_key, target_poke in _iter_player_battle_slots(player, include_knocked_out=True):
            if target_slot_key == slot_key:
                continue
            if not target_poke.get('knocked_out'):
                continue
            label = target_poke.get('name', target_slot_key)
            if target_slot_key == 'starter':
                label = f'{label} (Starter)'
            options.append({
                'id': target_slot_key,
                'slot_key': target_slot_key,
                'label': f'Curar {label}',
                'pokemon_name': target_poke.get('name', target_slot_key),
            })
        if not options:
            return None, 'Nenhum Pokémon elegível para curar (nenhum desmaiado)'
        _set_pending_action(state, {
            'type': 'heal_other_choice',
            'player_id': player_id,
            'healer_slot_key': slot_key,
            'healer_name': pokemon_name,
            'ability_name': ability_name,
            'prompt': f'{pokemon_name} pode curar um Pokémon desmaiado:',
            'options': options,
            'allowed_actions': ['resolve_pending_action'],
        })
        return state, {
            'type': 'manual_pokemon_ability',
            'pokemon': pokemon_name,
            'ability_name': ability_name,
            'effect_kind': effect_kind,
            'awaiting_target': True,
        }

    return None, 'Esta ação de habilidade ainda não foi implementada com segurança'


_LEAGUE_MEMBERS = [
    {
        'name': 'Lorelei',
        'team': [
            {'name': 'Dewgong',   'battle_points': 7, 'types': ['Water', 'Ice']},
            {'name': 'Slowbro',   'battle_points': 6, 'types': ['Water', 'Psychic']},
            {'name': 'Lapras',    'battle_points': 5, 'types': ['Water', 'Ice']},
            {'name': 'Cloyster',  'battle_points': 6, 'types': ['Water', 'Ice']},
            {'name': 'Jynx',      'battle_points': 7, 'types': ['Ice', 'Psychic']},
        ],
    },
    {
        'name': 'Bruno',
        'team': [
            {'name': 'Onix',      'battle_points': 6, 'types': ['Rock', 'Ground']},
            {'name': 'Steelix',   'battle_points': 8, 'types': ['Steel', 'Ground']},
            {'name': 'Hitmonchan','battle_points': 7, 'types': ['Fighting']},
            {'name': 'Hitmonlee', 'battle_points': 7, 'types': ['Fighting']},
            {'name': 'Machamp',   'battle_points': 8, 'types': ['Fighting']},
        ],
    },
    {
        'name': 'Agatha',
        'team': [
            {'name': 'Gengar',    'battle_points': 8, 'types': ['Ghost', 'Poison']},
            {'name': 'Gengar',    'battle_points': 8, 'types': ['Ghost', 'Poison']},
            {'name': 'Haunter',   'battle_points': 6, 'types': ['Ghost', 'Poison']},
            {'name': 'Crobat',    'battle_points': 9, 'types': ['Poison', 'Flying']},
            {'name': 'Arbok',     'battle_points': 7, 'types': ['Poison']},
        ],
    },
    {
        'name': 'Lance',
        'team': [
            {'name': 'Dragonite', 'battle_points': 10, 'types': ['Dragon', 'Flying']},
            {'name': 'Dragonite', 'battle_points': 10, 'types': ['Dragon', 'Flying']},
            {'name': 'Dragonair', 'battle_points': 7,  'types': ['Dragon']},
            {'name': 'Aerodactyl','battle_points': 9,  'types': ['Rock', 'Flying']},
            {'name': 'Gyarados',  'battle_points': 9,  'types': ['Water', 'Flying']},
        ],
    },
    {
        'name': 'Gary',
        'team': [
            {'name': 'Pidgeot',   'battle_points': 10, 'types': ['Normal', 'Flying']},
            {'name': 'Alakazam',  'battle_points': 9,  'types': ['Psychic']},
            {'name': 'Rhydon',    'battle_points': 10, 'types': ['Ground', 'Rock']},
            {'name': 'Exeggutor', 'battle_points': 11, 'types': ['Grass', 'Psychic']},
            {'name': 'Arcanine',  'battle_points': 12, 'types': ['Fire']},
        ],
    },
]


def _league_mp_reward(arrival_order: int, member_index: int) -> int:
    """Retorna recompensa de MP por derrotar um membro da Liga Pokémon."""
    is_champion = (member_index == 4)
    if is_champion:
        if arrival_order == 0:
            return 60
        if arrival_order == 1:
            return 40
        return 30
    else:
        if arrival_order == 0:
            return 50
        return 30


def _build_league_member_team(member: dict) -> list[dict]:
    from .gyms import _build_leader_pokemon
    return [_build_leader_pokemon(entry, idx) for idx, entry in enumerate(member['team'])]


def _resolve_league(state: dict, player_id: str) -> dict:
    """Inicia a batalha interativa da Liga Pokémon (Elite Four + Campeão)."""
    player = _get_player(state, player_id)
    if not player:
        return state

    if player.get('league_failed'):
        _log(state, player['name'], 'Você já foi eliminado da Liga Pokémon e não pode reentrar.')
        state['turn']['phase'] = 'end'
        state = end_turn(state)
        return state

    # Rastreia ordem de chegada (0 = primeiro)
    arrival_order = int(state.get('league_arrival_count', 0) or 0)
    state['league_arrival_count'] = arrival_order + 1
    player['league_arrival_order'] = arrival_order

    return _start_league_member_battle(state, player_id, member_index=0, arrival_order=arrival_order)


def _start_league_member_battle(state: dict, player_id: str, member_index: int, arrival_order: int) -> dict:
    """Configura um battle dict para enfrentar o membro member_index da Liga."""
    player = _get_player(state, player_id)
    if not player:
        return state

    reset_player_ability_runtime(player, 'battle')
    member = _LEAGUE_MEMBERS[member_index]
    is_champion = (member_index == len(_LEAGUE_MEMBERS) - 1)
    leader_team = _build_league_member_team(member)

    battle = {
        'mode': 'league',
        'source': 'league_tile',
        'challenger_id': player_id,
        'defender_id': None,
        'gym_id': f'league_{member["name"].lower()}',
        'gym_name': f'Pokémon League — {member["name"]}',
        'gym_tile_id': None,
        'badge_name': None,
        'badge_image_path': None,
        'master_points_reward': 0,
        'defender_name': member['name'],
        'leader_team': leader_team,
        'leader_current_index': 0,
        'defeated_leader_indexes': [],
        'defeated_player_slots': [],
        'pending_evolution_slots': [],
        'challenger_choice': None,
        'defender_choice': None,
        'challenger_roll': None,
        'defender_roll': None,
        'sub_phase': 'choosing',
        'choice_stage': 'challenger',
        'round_number': 1,
        'league_member_index': member_index,
        'league_arrival_order': arrival_order,
        'league_is_champion': is_champion,
    }

    state['turn']['battle'] = battle
    state['turn']['phase'] = 'battle'
    label = 'Campeão' if is_champion else 'Elite Four'
    _log(state, player['name'], f"Enfrenta {member['name']} ({label}) na Pokémon League!")
    return state


def _finalize_league_member_victory(state: dict, battle: dict, result: dict) -> tuple[dict, dict]:
    """Chamado quando o player derrota todos os Pokémon de um membro da Liga."""
    player = _get_player(state, battle['challenger_id'])
    member_index = int(battle.get('league_member_index', 0) or 0)
    arrival_order = int(battle.get('league_arrival_order', 0) or 0)
    member_name = battle.get('defender_name', '')
    is_champion = bool(battle.get('league_is_champion', False))

    mp_reward = _league_mp_reward(arrival_order, member_index)
    if player:
        player['league_bonus'] = player.get('league_bonus', 0) + mp_reward
        player['bonus_master_points'] = player.get('bonus_master_points', 0) + mp_reward
        sync_player_inventory(player)
        _log(state, player['name'], f"Derrotou {member_name} da Liga! +{mp_reward} MP")

    state = _award_victory_cards(state, battle['challenger_id'], 1, source='league')

    next_index = member_index + 1
    if not is_champion and next_index < len(_LEAGUE_MEMBERS):
        state['turn']['battle'] = None
        state = _queue_league_intermission(state, battle['challenger_id'], next_index, arrival_order)
        return state, {
            **result,
            'mode': 'league',
            'gym_victory': False,
            'battle_finished': True,
            'continues': True,
            'league_member_defeated': member_name,
            'next_league_member': _LEAGUE_MEMBERS[next_index]['name'],
            'league_intermission': True,
        }

    # Derrotou o Campeão — fim da Liga
    if player:
        _log(state, player['name'], f"Derrotou o Campeão {member_name}! Pokémon League concluída!")

    state['turn']['battle'] = None
    _check_league_end(state, battle['challenger_id'])
    return state, {
        **result,
        'mode': 'league',
        'gym_victory': True,
        'battle_finished': True,
        'continues': False,
        'league_completed': True,
    }


def _finalize_league_member_loss(state: dict, battle: dict, result: dict) -> tuple[dict, dict]:
    """Chamado quando o player perde para um membro da Liga."""
    player = _get_player(state, battle['challenger_id'])
    member_name = battle.get('defender_name', '')
    if player:
        player['league_failed'] = True
        _log(state, player['name'], f"Perdeu para {member_name}. Eliminado da Liga Pokémon — não pode reentrar.")

    state['turn']['battle'] = None
    _check_league_end(state, battle['challenger_id'])
    return state, {
        **result,
        'mode': 'league',
        'gym_victory': False,
        'battle_finished': True,
        'continues': False,
        'league_failed': True,
    }


def _queue_league_intermission(state: dict, player_id: str, next_member_index: int, arrival_order: int) -> dict:
    """Pausa entre membros da Liga para que o player use itens antes da próxima batalha."""
    player = _get_player(state, player_id)
    next_member = _LEAGUE_MEMBERS[next_member_index]
    state['turn']['phase'] = 'league_intermission'
    _set_pending_action(state, {
        'type': 'league_intermission',
        'player_id': player_id,
        'next_member_index': next_member_index,
        'arrival_order': arrival_order,
        'next_member_name': next_member['name'],
        'allowed_actions': ['confirm_league_intermission', 'use_item'],
    })
    if player:
        _log(state, player['name'], f"Preparação antes de enfrentar {next_member['name']}. Use itens se necessário e confirme quando estiver pronto.")
    return state


def confirm_league_intermission(state: dict, player_id: str) -> tuple[dict | None, str | dict]:
    """Confirma fim da preparação e inicia a próxima batalha da Liga."""
    state = copy.deepcopy(state)
    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'

    pending_action = state['turn'].get('pending_action') or {}
    if pending_action.get('type') != 'league_intermission':
        return None, 'Não há preparação de Liga pendente'
    if pending_action.get('player_id') != player_id:
        return None, 'Esta preparação não pertence a você'

    next_member_index = int(pending_action.get('next_member_index', 0))
    arrival_order = int(pending_action.get('arrival_order', 0))

    _clear_pending_action(state)
    state = _start_league_member_battle(state, player_id, member_index=next_member_index, arrival_order=arrival_order)
    return state, {
        'success': True,
        'type': 'league_intermission_confirmed',
        'next_member_index': next_member_index,
    }


def _check_league_end(state: dict, player_id: str) -> None:
    """Verifica se o jogo deve encerrar (todos chegaram na liga) e avança o turno."""
    active = _get_active_players(state)
    all_done = all(p.get('has_reached_league') for p in active)
    if all_done:
        state.update(_finish_game(state))
    else:
        state['turn']['phase'] = 'end'
        state_ref = end_turn(state)
        state.update(state_ref)


def _finish_game(state: dict) -> dict:
    """Finaliza o jogo e calcula ranking."""
    from .mechanics import calculate_final_scores
    active = _get_active_players(state)
    scores = calculate_final_scores(active)
    state['status'] = 'finished'
    state['final_scores'] = scores
    _log(state, 'Sistema',
         f"Jogo finalizado! Campeão: {scores[0]['player_name']} com {scores[0]['total']} MP")
    return state


# ── Captura de Pokémon ───────────────────────────────────────────────────────

def _resolve_successful_capture(
    state: dict,
    player_id: str,
    pokemon: dict,
    *,
    capture_context: str,
    capture_cost: int,
    use_full_restore: bool,
    use_master_ball: bool,
    capture_roll: dict,
) -> tuple[dict | None, str | dict]:
    if state['turn'].get('compound_eyes_active'):
        state['turn'].pop('compound_eyes_active', None)
    if state['turn'].get('seafoam_legendary') or capture_context == 'power_plant':
        state['turn'].pop('seafoam_legendary', None)

    state, result = _finalize_capture(
        state,
        player_id,
        pokemon,
        capture_cost=capture_cost,
        use_full_restore=use_full_restore,
        acquisition_origin='captured',
        capture_context=capture_context,
        use_master_ball=use_master_ball,
    )
    if state is None:
        return None, result

    player = _get_player(state, player_id)
    master_ball_consumed = False
    if use_master_ball:
        if not remove_item(player, 'master_ball', 1):
            return None, 'Sem Master Ball disponível para concluir esta captura'
        master_ball_consumed = True
        _log(state, player['name'], 'A Master Ball foi consumida porque a captura foi concluída com sucesso.')
    _log(
        state,
        player['name'],
        f"Capturou {pokemon['name']} com dados {_format_rolls_for_log(capture_roll.get('all_rolls'))}. "
        f"{_describe_capture_cost_for_log(capture_cost=capture_cost, use_full_restore=use_full_restore, use_master_ball=use_master_ball)}. "
        f"+{pokemon.get('master_points', 0)} MP.",
    )
    _clear_pending_action(state)

    safari_reserve = state['turn'].get('pending_safari') or []
    if safari_reserve and capture_context == 'safari':
        next_card = safari_reserve[0]
        remaining = safari_reserve[1:]
        state['turn']['pending_safari'] = remaining
        _queue_capture_attempt(
            state,
            player_id,
            pokemon=next_card,
            capture_context='safari',
            source='safari_zone',
        )
        return state, {
            **result,
            'safari_next': True,
            'capture_roll': capture_roll,
            'used_master_ball': use_master_ball,
            'master_ball_consumed': master_ball_consumed,
        }

    loop_pokemon_name = state['turn'].get('loop_capture_pokemon_name')
    if loop_pokemon_name:
        loop_player = _get_player(state, player_id)
        if loop_player and loop_player.get('pokeballs', 0) > 0:
            loop_pokemon = load_playable_pokemon_by_name(loop_pokemon_name)
            if loop_pokemon:
                _queue_capture_attempt(
                    state,
                    player_id,
                    pokemon=loop_pokemon,
                    capture_context='victory_gift',
                    source='victory_card',
                )
                return state, {
                    **result,
                    'capture_roll': capture_roll,
                    'used_master_ball': use_master_ball,
                    'master_ball_consumed': master_ball_consumed,
                    'loop_capture': True,
                }
        state['turn'].pop('loop_capture_pokemon_name', None)

    state['turn']['pending_safari'] = None
    state['turn']['capture_context'] = None
    state = end_turn(state)
    return state, {
        **result,
        'capture_roll': capture_roll,
        'used_master_ball': use_master_ball,
        'master_ball_consumed': master_ball_consumed,
    }


def _resolve_failed_capture(state: dict, player_id: str, capture_roll: dict, reason: str) -> tuple[dict, dict]:
    player = _get_player(state, player_id)
    pokemon = state['turn'].get('pending_pokemon')
    pending_action = state['turn'].get('pending_action') or {}
    used_master_ball = bool(pending_action.get('master_ball_in_use'))
    roll_summary = _format_rolls_for_log(capture_roll.get('all_rolls') or [capture_roll.get('raw_result')])
    if player:
        if pokemon:
            _log(state, player['name'], f"Falhou na captura de {pokemon['name']} com dados {roll_summary}: {reason}")
        elif pending_action.get('encounter_source'):
            _log(state, player['name'], f"Falhou ao resolver o encontro em {pending_action['encounter_source']} com dados {roll_summary}: {reason}")
        else:
            _log(state, player['name'], f"Falhou ao resolver a captura com dados {roll_summary}: {reason}")
        if used_master_ball:
            _log(state, player['name'], 'A Master Ball não foi consumida porque a captura não foi concluída.')

    state['turn']['pending_pokemon'] = None
    _clear_pending_action(state)
    state['turn'].pop('compound_eyes_active', None)
    state['turn'].pop('seafoam_legendary', None)

    safari_reserve = state['turn'].get('pending_safari') or []
    if safari_reserve and state['turn'].get('capture_context') == 'safari':
        next_card = safari_reserve[0]
        remaining = safari_reserve[1:]
        state['turn']['pending_safari'] = remaining
        _queue_capture_attempt(
            state,
            player_id,
            pokemon=next_card,
            capture_context='safari',
            source='safari_zone',
        )
        return state, {
            'success': False,
            'capture_roll': capture_roll,
            'safari_next': True,
            'used_master_ball': used_master_ball,
            'master_ball_preserved': used_master_ball,
        }

    state['turn']['pending_safari'] = None
    state['turn']['capture_context'] = None
    state = end_turn(state)
    return state, {
        'success': False,
        'capture_roll': capture_roll,
        'used_master_ball': used_master_ball,
        'master_ball_preserved': used_master_ball,
    }


def roll_capture_attempt(
    state: dict,
    player_id: str,
    use_full_restore: bool = False,
    *,
    use_master_ball: bool = False,
    chosen_capture_roll: int | None = None,
    ability_chosen_roll: int | None = None,
) -> tuple[dict | None, str | dict]:
    state = copy.deepcopy(state)
    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'

    pending_action = state['turn'].get('pending_action') or {}
    if pending_action.get('type') != 'capture_attempt':
        return None, 'Não há tentativa de captura pendente'
    if pending_action.get('player_id') != player_id:
        return None, 'Esta captura pendente não pertence a você'

    capture_context = state['turn'].get('capture_context', pending_action.get('capture_context', 'grass'))
    pokemon = state['turn'].get('pending_pokemon')
    resolver_card = pending_action.get('resolver_card')
    encounters = pending_action.get('encounters') or []
    prior_rolls = [int(roll) for roll in (pending_action.get('capture_rolls') or [])]
    master_ball_in_use = bool(pending_action.get('master_ball_in_use'))
    using_master_ball_now = bool(use_master_ball)

    if use_full_restore and using_master_ball_now:
        return None, 'Escolha entre Full Restore ou Master Ball para esta captura'
    if using_master_ball_now and prior_rolls:
        return None, 'A Master Ball só pode controlar a primeira rolagem da captura'
    if using_master_ball_now and master_ball_in_use:
        return None, 'Esta captura já está usando uma Master Ball'

    # capture_choice: antes de rolar, primeira rolagem, sem master ball, sem context lendário
    if (
        not prior_rolls
        and not using_master_ball_now
        and ability_chosen_roll is None
        and not pending_action.get('capture_choice_used')
    ):
        is_legendary_ctx = state['turn'].get('seafoam_legendary') or capture_context == 'power_plant'
        if not is_legendary_ctx:
            cap_choice = _find_available_capture_ability(player, 'capture_choice')
            if cap_choice:
                slot_key, cap_pokemon, cap_ability = cap_choice
                return _queue_capture_choice_decision(
                    state, player_id, use_full_restore,
                    pending_capture_action=pending_action,
                    slot_key=slot_key,
                    pokemon=cap_pokemon,
                    ability=cap_ability,
                )

    if using_master_ball_now:
        if get_item_quantity(player, 'master_ball') <= 0:
            return None, 'Sem Master Ball disponível'
        try:
            forced_roll = int(chosen_capture_roll)
        except (TypeError, ValueError):
            return None, 'Escolha um valor válido de 1 a 6 para a Master Ball'
        if not 1 <= forced_roll <= 6:
            return None, 'Escolha um valor válido de 1 a 6 para a Master Ball'
        capture_roll = _record_roll(
            state,
            roll_type='captura',
            player_id=player_id,
            player_name=player['name'],
            raw_result=forced_roll,
            final_result=forced_roll,
            context=capture_context,
            metadata={'forced_by': 'master_ball'},
        )
        _log(state, player['name'], f"Usou a Master Ball e escolheu {forced_roll} para o dado de captura.")
    elif ability_chosen_roll is not None:
        # Rolagem determinada por habilidade (capture_choice) ou resultado mantido (capture_reroll keep)
        forced = int(ability_chosen_roll)
        capture_roll = _record_roll(
            state,
            roll_type='captura',
            player_id=player_id,
            player_name=player['name'],
            raw_result=forced,
            final_result=forced,
            context=capture_context,
            metadata={'forced_by': 'ability'},
        )
    else:
        state, capture_roll = roll_capture_for_attempt(state, player_id, capture_context)

    # capture_reroll: após rolar, sem master ball, sem rolagem forçada por habilidade
    if (
        not using_master_ball_now
        and ability_chosen_roll is None
        and not pending_action.get('capture_reroll_used')
    ):
        cap_reroll = _find_available_capture_ability(player, 'capture_reroll')
        if cap_reroll:
            slot_key, cap_pokemon, cap_ability = cap_reroll
            return _queue_capture_reroll_decision(
                state, player_id, use_full_restore,
                pending_capture_action=pending_action,
                capture_roll=capture_roll,
                slot_key=slot_key,
                pokemon=cap_pokemon,
                ability=cap_ability,
            )

    current_rolls = prior_rolls + [int(capture_roll['raw_result'])]
    capture_roll_result = copy.deepcopy(capture_roll)
    capture_roll_result['all_rolls'] = current_rolls
    allowed_rolls = pending_action.get('allowed_rolls') or []
    if using_master_ball_now:
        pending_action = copy.deepcopy(pending_action)
        pending_action['master_ball_in_use'] = True
        _set_pending_action(state, pending_action)

    resolution = None
    success = not allowed_rolls or int(capture_roll['raw_result']) in allowed_rolls

    if encounters:
        resolution = _resolve_encounters_from_rolls(encounters, current_rolls)
    elif resolver_card:
        resolution = resolve_wild_pokemon_card_from_rolls(resolver_card, current_rolls)

    if resolution and resolution.get('requires_additional_roll'):
        updated_action = copy.deepcopy(state['turn'].get('pending_action') or pending_action)
        updated_action['capture_rolls'] = current_rolls
        updated_action['requires_additional_roll'] = True
        updated_action['master_ball_in_use'] = master_ball_in_use or using_master_ball_now
        updated_action['prompt'] = _build_capture_attempt_prompt(
            pokemon=pokemon,
            encounter_source=updated_action.get('encounter_source'),
            source=updated_action.get('source', 'capture_attempt'),
            capture_rolls=current_rolls,
            requires_additional_roll=True,
            master_ball_in_use=updated_action['master_ball_in_use'],
        )
        _set_pending_action(state, updated_action)
        state['turn']['pending_pokemon'] = copy.deepcopy(pokemon) if pokemon else None
        if updated_action['master_ball_in_use']:
            _log(state, player['name'], f"A Master Ball controlou a primeira rolagem. A próxima rolagem será normal. Dados atuais: {current_rolls}.")
        else:
            _log(state, player['name'], f"A captura exige nova rolagem. Dados atuais: {current_rolls}.")
        return state, {
            'success': False,
            'requires_additional_roll': True,
            'capture_roll': capture_roll_result,
            'capture_rolls': current_rolls,
            'used_master_ball': updated_action['master_ball_in_use'],
            'master_ball_consumed': False,
        }

    if resolution:
        success = bool(resolution.get('success'))
        resolved_name = resolution.get('pokemon_name')
        resolved_id = resolution.get('pokemon_id')
        if resolved_name:
            pokemon = load_playable_pokemon_by_name(resolved_name)
        if not pokemon and resolved_id is not None:
            pokemon = load_pokemon_by_id(resolved_id)
        if resolution.get('unsupported_reward') or (success and not pokemon):
            unsupported = resolution.get('unsupported_reward') or resolved_name or resolved_id or 'Pokémon desconhecido'
            _log_warning(state, player['name'], f"recompensa ignorada por falta de suporte jogável: {unsupported}")
            return _resolve_failed_capture(state, player_id, capture_roll_result, 'Pokémon sem suporte jogável')

    if resolution and not success and not allowed_rolls:
        return _resolve_failed_capture(
            state,
            player_id,
            capture_roll_result,
            f'dados de captura {current_rolls} não correspondem a um encontro válido',
        )

    if not pokemon and pending_action.get('pokemon_name'):
        pokemon = load_playable_pokemon_by_name(pending_action['pokemon_name'])

    if not pokemon:
        return None, 'Nenhum Pokémon disponível para esta captura'

    supported_pokemon, support = _coerce_inventory_pokemon(
        pokemon,
        source=f'captura:{capture_context}',
        player_name=player['name'],
        state=state,
    )
    if not supported_pokemon:
        return _resolve_failed_capture(state, player_id, capture_roll_result, 'Pokémon sem suporte para inventário')
    pokemon = supported_pokemon
    state['turn']['pending_pokemon'] = copy.deepcopy(pokemon)

    compound_eyes_active = state['turn'].get('compound_eyes_active')
    seafoam_legendary = state['turn'].get('seafoam_legendary')
    is_legendary = seafoam_legendary or capture_context == 'power_plant'
    slot_cost = pokemon_slot_cost(pokemon)
    capture_cost = slot_cost

    if master_ball_in_use or using_master_ball_now:
        capture_cost = slot_cost
    elif compound_eyes_active:
        capture_cost = 0
    elif is_legendary and not use_full_restore:
        capture_cost = max(2, slot_cost)
    elif use_full_restore:
        capture_cost = 0

    if use_full_restore and get_item_quantity(player, 'full_restore') <= 0:
        return None, 'Sem Full Restores! Use Pokébolas ou pule.'

    if not success:
        expected = ', '.join(str(value) for value in allowed_rolls) if allowed_rolls else 'resultado válido'
        return _resolve_failed_capture(state, player_id, capture_roll_result, f'dado {capture_roll["raw_result"]} não atende a regra ({expected})')

    using_mb = master_ball_in_use or using_master_ball_now
    effective_pokeballs = player['pokeballs']
    if using_mb:
        effective_pokeballs += max(0, int(player.get('master_balls', 0)))
    if effective_pokeballs < capture_cost:
        return _queue_release_pokemon_choice(
            state,
            player_id,
            resolution_type='capture',
            pokemon=pokemon,
            capture_cost=capture_cost,
            use_full_restore=use_full_restore,
            use_master_ball=using_mb,
            capture_roll=capture_roll_result,
            capture_context=capture_context,
        )

    return _resolve_successful_capture(
        state,
        player_id,
        pokemon,
        capture_context=capture_context,
        capture_cost=capture_cost,
        use_full_restore=use_full_restore,
        use_master_ball=using_mb,
        capture_roll=capture_roll_result,
    )

def capture_pokemon(state: dict, player_id: str,
                    use_full_restore: bool = False) -> tuple[dict | None, str | dict]:
    """
    Tenta capturar o Pokémon disponível na casa atual.
    - Grama/Normal: custa 1 Pokébola
    - Safari Zone: custa 1 Pokébola (sequencial)
    - Cinnabar Lab: gratuito (compound_eyes_active)
    - Mt. Moon: custa 1 Pokébola
    - Power Plant / Seafoam (lendários): custa 2 Pokébolas OU 1 Full Restore
    Retorna (novo_estado, resultado) ou (None, erro).
    """
    return roll_capture_attempt(state, player_id, use_full_restore=use_full_restore)


def discard_item(state: dict, player_id: str, item_key: str) -> tuple[dict | None, str]:
    state = copy.deepcopy(state)
    turn = state['turn']
    choice = turn.get('pending_item_choice') or {}

    if turn.get('phase') != 'item_choice':
        return None, 'Não há descarte de item pendente'
    if choice.get('player_id') != player_id:
        return None, 'Este descarte não pertence a você'

    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'
    if not remove_item(player, item_key, 1):
        return None, 'Item inválido para descarte'

    item_name = get_item_def(item_key).get('name', item_key)
    remaining_items = total_item_count(player)
    reason = choice.get('reason') or 'descarte obrigatório'
    if remaining_items > ITEM_CAPACITY:
        overflow = remaining_items - ITEM_CAPACITY
        _log(
            state,
            player['name'],
            f"Descartou 1 {item_name} ({reason}). Inventário: {remaining_items}/{ITEM_CAPACITY}; ainda faltam {overflow} descarte(s).",
        )
        turn['pending_item_choice']['discard_count'] = overflow
        return state, 'ok'

    _log(
        state,
        player['name'],
        f"Descartou 1 {item_name} ({reason}). Inventário: {remaining_items}/{ITEM_CAPACITY}.",
    )
    turn['pending_item_choice'] = None
    lass_queue = turn.get('lass_discard_queue') or []
    if lass_queue:
        next_id = lass_queue[0]
        turn['lass_discard_queue'] = lass_queue[1:]
        turn['phase'] = 'item_choice'
        turn['pending_item_choice'] = {
            'player_id': next_id,
            'reason': 'Event Lass: descarte obrigatório',
            'discard_count': 1,
            'is_lass': True,
        }
        return state, 'ok'
    turn.pop('lass_discard_queue', None)
    state = _resume_pending_effects_or_finish_turn(state, player_id, end_turn_when_done=True)
    return state, 'ok'


def release_pokemon_for_capture(
    state: dict,
    player_id: str,
    pokemon_index: int | None = None,
    pokemon_slot_key: str | None = None,
) -> tuple[dict | None, str | dict]:
    state = copy.deepcopy(state)
    turn = state['turn']
    pending = turn.get('pending_release_choice') or {}

    if turn.get('phase') != 'release_pokemon':
        return None, 'Não há captura pendente aguardando liberação'
    if pending.get('player_id') != player_id:
        return None, 'Esta captura pendente não pertence a você'

    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'

    options = pending.get('options') or _build_release_pokemon_options(player)
    if not options:
        return None, 'Você não possui Pokémon na party para libertar'

    resolved_slot_key = (pokemon_slot_key or '').strip()
    if not resolved_slot_key:
        if pokemon_index is None:
            return None, 'Escolha um Pokémon para libertar'
        try:
            resolved_index = int(pokemon_index)
        except (TypeError, ValueError):
            return None, 'Pokémon inválido para liberação'
        if not (0 <= resolved_index < len(options)):
            return None, 'Pokémon inválido para liberação'
        resolved_slot_key = str(options[resolved_index].get('slot_key') or options[resolved_index].get('id') or '').strip()

    if not any(str(option.get('slot_key') or option.get('id') or '').strip() == resolved_slot_key for option in options):
        return None, 'Pokémon inválido para liberação'

    released = _remove_player_pokemon_slot(player, resolved_slot_key)
    if not released:
        return None, 'Pokémon inválido para liberação'
    player['pokeballs'] += pokemon_slot_cost(released)
    sync_player_inventory(player)
    _log(state, player['name'], f"Liberou {released['name']} para abrir espaço")

    resolution_type = pending.get('resolution_type', 'capture')
    capture_cost = int(pending.get('capture_cost', 1 if resolution_type == 'capture' else pokemon_slot_cost(pending.get('pokemon'))))
    use_master_ball = bool(pending.get('use_master_ball'))
    effective_pokeballs_after_release = player['pokeballs']
    if use_master_ball:
        effective_pokeballs_after_release += max(0, int(player.get('master_balls', 0)))
    if effective_pokeballs_after_release < capture_cost:
        turn['pending_release_choice']['options'] = _build_release_pokemon_options(player)
        return state, {
            'released_pokemon': released,
            'requires_release': True,
            'pokeballs_left': player['pokeballs'],
            'capture_roll': pending.get('capture_roll'),
            'use_master_ball': use_master_ball,
        }

    pokemon = pending.get('pokemon')
    use_full_restore = bool(pending.get('use_full_restore'))
    state['turn'].pop('pending_release_choice', None)
    state['turn']['phase'] = 'action'
    if resolution_type == 'reward':
        finalized, result = _grant_reward_pokemon(
            state,
            player_id,
            pokemon,
            source=pending.get('reward_source', 'reward'),
        )
        if finalized is None:
            return None, result
        _log(finalized, player['name'], f"Recebeu {pokemon['name']} após liberar espaço")
        finalized = _resume_pending_effects_or_finish_turn(finalized, player_id, end_turn_when_done=True)
        return finalized, {**result, 'released_pokemon': released}

    finalized, result = _resolve_successful_capture(
        state,
        player_id,
        pokemon,
        capture_context=pending.get('capture_context') or state['turn'].get('capture_context', 'grass'),
        capture_cost=capture_cost,
        use_full_restore=use_full_restore,
        use_master_ball=use_master_ball,
        capture_roll=pending.get('capture_roll'),
    )
    if finalized is None:
        return None, result

    safari_reserve = finalized['turn'].get('pending_safari') or []
    capture_context = finalized['turn'].get('capture_context', 'grass')
    if safari_reserve and capture_context == 'safari':
        return finalized, {
            **result,
            'released_pokemon': released,
            'safari_next': True,
            'capture_roll': pending.get('capture_roll'),
        }
    return finalized, {**result, 'released_pokemon': released, 'capture_roll': pending.get('capture_roll')}


def skip_action(state: dict, player_id: str) -> dict:
    """
    Pula a ação atual (não capturar / não duelar).
    Trata fila do Safari Zone: avança para o próximo Pokémon se houver.
    """
    state = copy.deepcopy(state)
    turn = state['turn']
    player = _get_player(state, player_id)
    pending_action = turn.get('pending_action') or {}

    pending_release_choice = turn.get('pending_release_choice') or {}
    if turn.get('phase') == 'release_pokemon' and pending_release_choice.get('player_id') == player_id:
        incoming = pending_release_choice.get('pokemon') or turn.get('pending_pokemon') or {}
        incoming_name = incoming.get('name', 'o Pokémon pendente')
        use_master_ball = bool(pending_release_choice.get('use_master_ball'))
        _clear_pending_capture(state)
        turn.pop('compound_eyes_active', None)
        turn.pop('seafoam_legendary', None)

        if pending_release_choice.get('resolution_type') == 'reward':
            turn['pending_pokemon'] = None
            turn['capture_context'] = None
            turn['phase'] = 'action'
            if player:
                _log(state, player['name'], f"Cancelou a troca e recusou {incoming_name}")
            return _resume_pending_effects_or_finish_turn(state, player_id, end_turn_when_done=True)

        if player:
            _log(state, player['name'], f"Cancelou a captura de {incoming_name}")
            if use_master_ball:
                _log(state, player['name'], 'A Master Ball foi preservada porque a captura foi cancelada.')
        turn['phase'] = 'action'

    # Limpa Pokémon atual
    if player and pending_action.get('type') == 'capture_attempt' and pending_action.get('master_ball_in_use'):
        _log(state, player['name'], 'A Master Ball foi preservada porque a captura foi cancelada.')
    turn['pending_pokemon'] = None
    _clear_pending_action(state)
    turn.pop('compound_eyes_active', None)
    turn.pop('seafoam_legendary', None)

    # Safari Zone: avança para próximo Pokémon da fila
    safari_reserve = turn.get('pending_safari') or []
    capture_context = turn.get('capture_context', '')
    if safari_reserve and capture_context == 'safari':
        next_card = safari_reserve[0]
        remaining = safari_reserve[1:]
        turn['pending_safari'] = remaining
        _queue_capture_attempt(
            state,
            player_id,
            pokemon=next_card,
            capture_context='safari',
            source='safari_zone',
        )
        # Mantém fase de ação para próxima captura opcional
        return state

    # Limpa estados e encerra turno
    turn['pending_safari'] = None
    turn['capture_context'] = None
    return end_turn(state)


def resolve_pending_action(state: dict, player_id: str, option_id: str) -> tuple[dict | None, str | dict]:
    state = copy.deepcopy(state)
    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'

    pending_action = state['turn'].get('pending_action') or {}
    pending_type = pending_action.get('type')
    if pending_type not in (
        'ability_decision',
        'team_rocket_roll',
        'pokemart_roll',
        'reward_choice',
        'gym_heal',
        'pokecenter_heal',
        'miracle_stone_tile',
        'bill_teleport',
        'game_corner',
        'teleporter_manual_roll',
        'capture_choice_decision',
        'capture_reroll_decision',
        'battle_reroll_decision',
        'battle_bp_swap_decision',
        'heal_other_choice',
        'trade_proposal',
        'abra_transfer_offer',
    ):
        return None, 'Nenhuma escolha pendente'
    if pending_action.get('player_id') != player_id:
        return None, 'Esta escolha não pertence a você'

    options = pending_action.get('options') or []
    chosen = next((option for option in options if str(option.get('id')) == str(option_id)), None)
    if not chosen:
        return None, 'Opção inválida'

    if pending_type == 'ability_decision':
        if pending_action.get('decision_kind') == 'move_roll':
            return _resolve_move_roll_ability_decision(state, player_id, pending_action, chosen)
        return None, 'Tipo de decisão de habilidade ainda não suportado'

    if pending_type == 'capture_choice_decision':
        return _resolve_capture_choice_decision(state, player_id, pending_action, chosen)

    if pending_type == 'capture_reroll_decision':
        return _resolve_capture_reroll_decision(state, player_id, pending_action, chosen)

    if pending_type == 'battle_reroll_decision':
        return _resolve_battle_reroll_decision(state, player_id, pending_action, chosen)

    if pending_type == 'battle_bp_swap_decision':
        return _resolve_battle_bp_swap_decision(state, player_id, pending_action, chosen)

    if pending_type == 'heal_other_choice':
        return _resolve_heal_other_choice(state, player_id, pending_action, chosen)

    if pending_type == 'trade_proposal':
        return _resolve_abra_transfer_offer(state, player_id, pending_action, chosen)

    if pending_type == 'abra_transfer_offer':
        return _resolve_abra_transfer_offer(state, player_id, pending_action, chosen)

    if pending_type == 'team_rocket_roll':
        return _resolve_team_rocket_roll_action(state, player_id, pending_action)

    if pending_type == 'pokemart_roll':
        return _resolve_pokemart_roll_action(state, player_id, pending_action)

    prompt = pending_action.get('prompt') or 'Escolha pendente'
    _log(state, player['name'], f"{prompt}: {chosen.get('label', option_id)}")

    if pending_type == 'miracle_stone_tile':
        _clear_pending_action(state)
        if chosen.get('id') == 'skip':
            return _resume_pending_effects_or_finish_turn(state, player_id, end_turn_when_done=True), {
                'success': True,
                'type': 'miracle_stone_tile',
                'skipped': True,
            }

        slot_key = chosen.get('slot_key') or chosen.get('id')
        pokemon = _get_player_pokemon_slot(player, slot_key)
        if not _can_use_miracle_stone_on_pokemon(pokemon):
            return None, 'Este Pokémon não pode evoluir com a Miracle Stone'

        evolving = copy.deepcopy(pokemon)
        evolving['battle_slot_key'] = slot_key
        evolved = _try_evolve(state, player_id, evolving)
        if not evolved:
            return None, 'Não foi possível evoluir este Pokémon'
        _log(state, player['name'], f"{pokemon['name']} evoluiu instantaneamente para {evolved['name']} em uma Miracle Stone.")
        return _resume_pending_effects_or_finish_turn(state, player_id, end_turn_when_done=True), {
            'success': True,
            'type': 'miracle_stone_tile',
            'pokemon': pokemon['name'],
            'evolved_to': evolved['name'],
        }

    if pending_type == 'bill_teleport':
        _clear_pending_action(state)
        if chosen.get('id') == 'stay':
            _log(state, player['name'], 'Decidiu não usar o teleporte especial do Bill.')
            return _resume_pending_effects_or_finish_turn(state, player_id, end_turn_when_done=True), {
                'success': True,
                'type': 'bill_teleport',
                'teleported': False,
            }

        target = _get_player(state, chosen.get('target_player_id'))
        if not target:
            return None, 'Alvo inválido'

        player['position'] = int(target.get('position', player.get('position', 0)) or 0)
        state['turn']['current_tile'] = get_tile(state['board'], player['position'])
        _get_special_tile_state(state)['bill_teleport_used_by'] = player_id
        _log(state, player['name'], f"Bill teleportou {player['name']} para a posição de {target['name']} em {state['turn']['current_tile'].get('name', 'outra casa')}.")
        return _resume_pending_effects_or_finish_turn(state, player_id, end_turn_when_done=True), {
            'success': True,
            'type': 'bill_teleport',
            'teleported': True,
            'target_player_id': target['id'],
            'tile_id': player['position'],
        }

    if pending_type == 'game_corner':
        _clear_pending_action(state)
        raw_prize_index = pending_action.get('current_prize_index', -1)
        current_prize_index = int(raw_prize_index if raw_prize_index is not None else -1)

        if chosen.get('id') == 'continue':
            state = _queue_game_corner_action(state, player_id, current_prize_index=current_prize_index, stage='roll')
            return state, {
                'success': True,
                'type': 'game_corner',
                'continued': True,
                'current_prize_index': current_prize_index,
            }

        if chosen.get('id') == 'stop':
            state = _resolve_game_corner_reward(state, player_id, current_prize_index)
            state = _resume_pending_effects_or_finish_turn(state, player_id, end_turn_when_done=True)
            return state, {
                'success': True,
                'type': 'game_corner',
                'stopped': True,
                'prize_key': _GAME_CORNER_PRIZES[current_prize_index]['key'],
            }

        if chosen.get('id') != 'roll':
            return None, 'Opção inválida do Game Corner'

        roll = roll_game_corner_dice()
        _record_roll(
            state,
            roll_type='Game Corner',
            player_id=player_id,
            player_name=player['name'],
            raw_result=roll,
            final_result=roll,
            context='game_corner',
            metadata={'current_prize_index': current_prize_index},
        )
        if roll <= 2:
            _log(state, player['name'], f"Rolou {roll} no Game Corner e perdeu tudo.")
            state = _resume_pending_effects_or_finish_turn(state, player_id, end_turn_when_done=True)
            return state, {
                'success': False,
                'type': 'game_corner',
                'roll': roll,
                'lost_all': True,
            }

        reached_index = min(current_prize_index + 1, len(_GAME_CORNER_PRIZES) - 1)
        reached_prize = _GAME_CORNER_PRIZES[reached_index]
        _log(state, player['name'], f"Rolou {roll} no Game Corner e alcançou {reached_prize['label']}.")
        if reached_index >= len(_GAME_CORNER_PRIZES) - 1:
            state = _resolve_game_corner_reward(state, player_id, reached_index)
            state = _resume_pending_effects_or_finish_turn(state, player_id, end_turn_when_done=True)
            return state, {
                'success': True,
                'type': 'game_corner',
                'roll': roll,
                'prize_key': reached_prize['key'],
                'final_prize': True,
            }

        state = _queue_game_corner_action(state, player_id, current_prize_index=reached_index)
        return state, {
            'success': True,
            'type': 'game_corner',
            'roll': roll,
            'current_prize_index': reached_index,
            'prize_key': reached_prize['key'],
        }

    if pending_type == 'teleporter_manual_roll':
        _clear_pending_action(state)
        chosen_roll = chosen.get('dice_result')
        try:
            dice_result = int(chosen_roll)
        except (TypeError, ValueError):
            return None, 'Valor de dado inválido'
        if not 1 <= dice_result <= 6:
            return None, 'O dado do teleporter deve ficar entre 1 e 6'
        _log(state, player['name'], f"Escolheu manualmente o resultado {dice_result} para o turno extra do teleporter.")
        state = process_move(state, player_id, dice_result)
        return state, {
            'success': True,
            'type': 'teleporter_manual_roll',
            'dice_result': dice_result,
        }

    if pending_type == 'pokecenter_heal':
        _clear_pending_action(state)
        remaining_heals = int(pending_action.get('remaining_heals', 0) or 0)
        healed_slots = list(pending_action.get('healed_slots') or [])
        center_tile = _get_pokemon_center_tile(state.get('board', {}), pending_action.get('center_tile_id'))
        visit_kind = pending_action.get('visit_kind', 'stopped')

        if chosen.get('id') != 'finish':
            slot_key = chosen.get('slot_key') or chosen.get('id')
            healed_now = _heal_player_pokemon_slots(player, [slot_key])
            if not healed_now:
                return None, 'Este Pokémon não precisa de cura'
            healed_slots.extend(healed_now)
            remaining_heals = max(0, remaining_heals - len(healed_now))
            healed_names = ', '.join(_build_gym_slot_label(player, healed_key) for healed_key in healed_now)
            _log(state, player['name'], f"Curou {healed_names} no PokéCenter.")

        if chosen.get('id') == 'finish' or remaining_heals <= 0 or not center_tile:
            state = _complete_pokecenter_heal_action(state, player_id, pending_action)
            return state, {
                'success': True,
                'type': 'pokecenter_heal',
                'visit_kind': visit_kind,
                'healed_slots': healed_slots,
                'remaining_heals': remaining_heals,
            }

        queued = _queue_pokecenter_heal_action(
            state,
            player_id,
            center_tile=center_tile,
            heal_limit=remaining_heals,
            visit_kind=visit_kind,
            healed_slots=healed_slots,
            completion=pending_action.get('completion'),
        )
        if not queued:
            state = _complete_pokecenter_heal_action(state, player_id, pending_action)
        return state, {
            'success': True,
            'type': 'pokecenter_heal',
            'visit_kind': visit_kind,
            'healed_slots': healed_slots,
            'remaining_heals': remaining_heals,
        }

    if pending_type == 'gym_heal':
        _clear_pending_action(state)
        remaining_heals = int(pending_action.get('remaining_heals', 0) or 0)
        healed_slots = list(pending_action.get('healed_slots') or [])
        candidate_slots = list(pending_action.get('candidate_slots') or [])
        gym_id = pending_action.get('gym_id')
        leader_name = pending_action.get('leader_name', 'Lider')

        if chosen.get('id') != 'finish':
            slot_key = chosen.get('slot_key') or chosen.get('id')
            healed_now = _heal_player_pokemon_slots(player, [slot_key])
            if not healed_now:
                return None, 'Este Pokémon não precisa de cura'
            healed_slots.extend(healed_now)
            remaining_heals = max(0, remaining_heals - len(healed_now))
            healed_names = ', '.join(_build_gym_slot_label(player, healed_key) for healed_key in healed_now)
            _log(state, player['name'], f"Curou {healed_names} após vencer {leader_name}.")

        if chosen.get('id') == 'finish' or remaining_heals <= 0:
            if pending_action.get('award_victory_card', True):
                state = _award_victory_cards(state, player_id, 1, source='gym')
            if not state['turn'].get('battle') and not state['turn'].get('pending_action'):
                state['turn']['phase'] = 'end'
                state = end_turn(state)
            return state, {
                'success': True,
                'type': 'gym_heal',
                'healed_slots': healed_slots,
                'remaining_heals': remaining_heals,
            }

        state = _queue_gym_heal_action(
            state,
            player_id,
            gym_id=gym_id,
            leader_name=leader_name,
            remaining_heals=remaining_heals,
            healed_slots=healed_slots,
            candidate_slots=candidate_slots,
        )
        if not state['turn'].get('pending_action') and pending_action.get('award_victory_card', True):
            state = _award_victory_cards(state, player_id, 1, source='gym')
            if not state['turn'].get('battle') and not state['turn'].get('pending_action'):
                state['turn']['phase'] = 'end'
                state = end_turn(state)
        return state, {
            'success': True,
            'type': 'gym_heal',
            'healed_slots': healed_slots,
            'remaining_heals': remaining_heals,
        }

    card = pending_action.get('card') or {}
    source = pending_action.get('source', 'event_card')
    _clear_pending_action(state)

    if 'recharge_slot_key' in chosen:
        recharged = _restore_primary_ability_charge_for_slot(player, chosen['recharge_slot_key'])
        if not recharged:
            return None, 'Este Pokémon não pode recuperar carga agora'
        _log(state, player['name'], f"Recuperou 1 carga de habilidade para {recharged['pokemon_name']}.")
        state = end_turn(state)
        return state, {
            'success': True,
            'type': 'reward_choice',
            'reward': 'ability_charge',
            'pokemon': recharged['pokemon_name'],
            'charges_remaining': recharged['charges_remaining'],
            'charges_total': recharged['charges_total'],
        }

    if 'pokemon_name' in chosen:
        pokemon, support = resolve_supported_pokemon_reward(chosen['pokemon_name'])
        if not support['supported'] or not pokemon:
            _log_warning(state, player['name'], f"recompensa ignorada por falta de suporte jogável: {chosen['pokemon_name']}")
            state = end_turn(state)
            return state, {'success': False, 'unsupported_pokemon': chosen['pokemon_name']}
        result_state, result = _grant_reward_pokemon(state, player_id, pokemon, source=source)
        if result_state is None:
            return None, result
        if result_state['turn'].get('phase') != 'release_pokemon':
            result_state = end_turn(result_state)
        return result_state, {'success': True, 'pokemon': pokemon, 'source': source}

    if 'target_player_id' in chosen:
        target = _get_player(state, chosen['target_player_id'])
        if not target:
            return None, 'Alvo inválido'
        player['position'] = target['position']
        tile = get_tile(state['board'], player['position'])
        state['turn']['current_tile'] = tile
        _log(state, player['name'], f"Teleportou para {target['name']} em {tile['name']}")
        state = _resolve_tile_effect(state, player_id, tile, get_tile_effect(tile))
        return state, {'success': True, 'target_player_id': target['id']}

    if 'pokemon_index' in chosen:
        pool = list(player.get('pokemon_inventory', []))
        index = int(chosen['pokemon_index'])
        if not (0 <= index < len(pool)):
            return None, 'Pokémon inválido'
        selected = pool[index]
        value = int(selected.get('master_points', 0) or 0)
        rounded = int(round(value / 20.0) * 10) if value else 0
        if selected.get('is_starter_slot'):
            player['starter_pokemon'] = None
        else:
            non_starter = [p for p in player.get('pokemon_inventory', []) if not p.get('is_starter_slot')]
            normalized_index = max(0, min(index - (1 if player.get('starter_pokemon') else 0), len(player.get('pokemon', [])) - 1))
            if player.get('pokemon') and non_starter:
                player['pokemon'].pop(normalized_index)
        player['pokeballs'] += pokemon_slot_cost(selected)
        player['bonus_points'] = player.get('bonus_points', 0) + rounded
        player['bonus_master_points'] = player.get('bonus_master_points', 0) + rounded
        sync_player_inventory(player)
        _log(state, player['name'], f"Entregou {selected['name']} ao Mr. Fuji e recebeu {rounded} Master Points")
        state = end_turn(state)
        return state, {'success': True, 'master_points': rounded}

    if 'item_key' in chosen:
        if not remove_item(player, chosen['item_key'], 1):
            return None, 'Item inválido para troca'
        player['pokeballs'] += 1
        sync_player_inventory(player)
        _log(state, player['name'], f"Trocou 1 {chosen['item_key']} por 1 Pokébola com Oak's Assistant")
        state = end_turn(state)
        return state, {'success': True, 'item_key': chosen['item_key']}

    return None, 'Tipo de escolha pendente sem suporte'


def trigger_current_tile_effect(state: dict, player_id: str, *, source: str = 'debug') -> tuple[dict | None, str | dict]:
    state = copy.deepcopy(state)
    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'
    if state.get('status') != 'playing':
        return None, 'A partida ainda não está em andamento'
    turn = state.get('turn', {})
    if turn.get('current_player_id') != player_id:
        return None, 'Não é seu turno'
    if turn_has_blocking_interaction(turn):
        return None, 'Não é possível executar o tile atual durante uma interação pendente'
    tile = get_tile(state.get('board', {}), player.get('position', 0))
    if not tile:
        return None, 'Tile atual inválido'
    state['turn']['current_tile'] = tile
    _log(state, player['name'], f"[DEBUG] Executou o efeito do tile atual: {tile.get('name', '?')}")
    state = _resolve_tile_effect(state, player_id, tile, get_tile_effect(tile))
    return state, {'success': True, 'tile_id': tile.get('id'), 'tile_name': tile.get('name'), 'source': source}


def set_host_tools_enabled(state: dict, enabled: bool) -> tuple[dict | None, str | dict]:
    state = copy.deepcopy(state)
    host_tools = copy.deepcopy(_get_host_tools_state(state))
    host_tools['enabled'] = bool(enabled)
    if not enabled:
        host_tools['pending_tile_trigger'] = None
    state = _set_host_tools_state(state, host_tools)
    return state, {'enabled': bool(enabled)}


def debug_move_host(state: dict, player_id: str, steps: int) -> tuple[dict | None, str | dict]:
    state = copy.deepcopy(state)
    error = _require_host_tools_enabled(state)
    if error:
        return None, error

    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'
    if state.get('status') != 'playing':
        return None, 'A partida ainda não está em andamento'
    if state.get('turn', {}).get('current_player_id') != player_id:
        return None, 'Não é seu turno'
    if turn_has_blocking_interaction(state.get('turn')):
        return None, 'Não é possível mover com Host Tools durante uma interação pendente'

    steps = int(steps or 0)
    if steps == 0:
        return None, 'O movimento de Host Tools exige um inteiro diferente de zero'

    old_position = int(player.get('position', 0))
    new_position = calculate_new_position(old_position, steps, state.get('board', {}))
    tile = get_tile(state.get('board', {}), new_position)

    player['position'] = new_position
    state['turn']['dice_result'] = steps
    state['turn']['current_tile'] = tile
    state['turn']['movement_context'] = {
        'start_position': old_position,
        'dice_result': steps,
        'natural_destination': int(new_position),
        'resolved_destination': int(new_position),
        'forced_stop_kind': 'host_tools_debug_move',
    }
    _record_roll(
        state,
        roll_type='movimento',
        player_id=player_id,
        player_name=player['name'],
        raw_result=steps,
        final_result=steps,
        context='host_tools_debug_move',
    )
    state = _set_host_tools_pending_tile(state, player_id=player_id, position=new_position, steps=steps)
    _log(
        state,
        player['name'],
        f"{_HOST_TOOLS_LOG_PREFIX} Moveu {steps:+d} casa(s) para {tile.get('name', '?')} sem disparar o tile automaticamente.",
    )
    return state, {
        'success': True,
        'steps': steps,
        'position': new_position,
        'tile_id': tile.get('id'),
        'tile_name': tile.get('name'),
        'tile_pending': True,
    }


def debug_trigger_host_current_tile(state: dict, player_id: str) -> tuple[dict | None, str | dict]:
    state = copy.deepcopy(state)
    error = _require_host_tools_enabled(state)
    if error:
        return None, error

    pending = ((_get_host_tools_state(state) or {}).get('pending_tile_trigger'))
    if not isinstance(pending, dict) or pending.get('player_id') != player_id:
        return None, 'Não há tile pendente para Host Tools neste turno'

    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'
    if int(player.get('position', 0)) != int(pending.get('position', 0)):
        state = _clear_host_tools_pending_tile(state, player_id=player_id)
        return None, 'O tile pendente não corresponde mais à posição atual do host'

    state = _clear_host_tools_pending_tile(state, player_id=player_id)
    new_state, result = trigger_current_tile_effect(state, player_id, source='host_tools')
    if new_state is None:
        return None, result
    return new_state, result


# ── Duelo ────────────────────────────────────────────────────────────────────


def _mark_gym_progress(player: dict, progress_key: str, gym_id: str) -> None:
    values = player.setdefault(progress_key, [])
    if gym_id not in values:
        values.append(gym_id)


def _prepare_gym_leader_choice(battle: dict) -> dict | None:
    team = battle.get('leader_team') or []
    defeated_indexes = set(battle.get('defeated_leader_indexes') or [])
    available_indexes = [index for index in range(len(team)) if index not in defeated_indexes]
    if not available_indexes:
        battle['leader_current_index'] = None
        battle['defender_choice'] = None
        return None

    current_index = battle.get('leader_current_index')
    if current_index not in available_indexes:
        current_index = available_indexes[0]

    battle['leader_current_index'] = current_index
    battle['defender_choice'] = copy.deepcopy(team[current_index])
    return battle['defender_choice']


def _queue_gym_heal_action(
    state: dict,
    player_id: str,
    *,
    gym_id: str,
    leader_name: str,
    remaining_heals: int,
    healed_slots: list[str],
    candidate_slots: list[str],
) -> dict:
    player = _get_player(state, player_id)
    if not player:
        return state

    healable_slots = []
    for slot_key in candidate_slots:
        pokemon = _get_player_pokemon_slot(player, slot_key)
        if not pokemon or not pokemon.get('knocked_out') or slot_key in healed_slots:
            continue
        healable_slots.append(slot_key)

    if remaining_heals <= 0 or not healable_slots:
        _clear_pending_action(state)
        state['turn']['phase'] = 'gym'
        state['turn']['battle'] = None
        return state

    options = [
        {'id': slot_key, 'label': f"Curar {_build_gym_slot_label(player, slot_key)}", 'slot_key': slot_key}
        for slot_key in healable_slots
    ]
    options.append({'id': 'finish', 'label': 'Concluir cura'})
    _set_pending_action(state, {
        'type': 'gym_heal',
        'player_id': player_id,
        'gym_id': gym_id,
        'leader_name': leader_name,
        'remaining_heals': remaining_heals,
        'healed_slots': list(healed_slots),
        'candidate_slots': list(candidate_slots),
        'award_victory_card': True,
        'prompt': f"Voce venceu {leader_name}! Escolha ate {remaining_heals} Pokemon para curar.",
        'options': options,
        'allowed_actions': ['resolve_pending_action'],
    })
    state['turn']['phase'] = 'gym'
    state['turn']['battle'] = None
    return state


def _apply_deferred_gym_evolutions(state: dict, player_id: str, slot_keys: list[str], leader_name: str) -> list[dict]:
    player = _get_player(state, player_id)
    if not player:
        return []

    evolved: list[dict] = []
    seen: set[str] = set()
    for slot_key in slot_keys:
        if slot_key in seen:
            continue
        seen.add(slot_key)
        pokemon = _get_player_pokemon_slot(player, slot_key)
        if not pokemon or not can_evolve(pokemon) or pokemon.get('is_baby', False):
            continue
        original_name = pokemon.get('name', '?')
        pokemon_for_evolution = copy.deepcopy(pokemon)
        pokemon_for_evolution['battle_slot_key'] = slot_key
        evolved_pokemon = _try_evolve(state, player_id, pokemon_for_evolution, heal_on_evolve=True)
        if not evolved_pokemon:
            continue
        evolved.append({
            'slot_key': slot_key,
            'from': original_name,
            'to': evolved_pokemon['name'],
        })
        _log(state, player['name'], f"{original_name} evoluiu para {evolved_pokemon['name']} apos a batalha de ginasio contra {leader_name}!")
    return evolved


def _finalize_gym_victory(state: dict, battle: dict, result: dict) -> tuple[dict, dict]:
    player = _get_player(state, battle['challenger_id'])
    gym_id = battle['gym_id']
    badge_name = battle.get('badge_name')
    leader_name = battle.get('defender_name', 'Lider')
    rewards: list[dict] = []

    if player:
        _mark_gym_progress(player, 'gyms_defeated', gym_id)
        existing_badge_names = [b['name'] if isinstance(b, dict) else b for b in player.get('badges', [])]
        if badge_name and badge_name not in existing_badge_names:
            player['badges'].append({'name': badge_name, 'image_path': battle.get('badge_image_path')})
            rewards.append({'type': 'badge', 'badge': badge_name, 'image_path': battle.get('badge_image_path')})

        master_points_reward = int(battle.get('master_points_reward', 20) or 20)
        if master_points_reward > 0:
            player['bonus_master_points'] = player.get('bonus_master_points', 0) + master_points_reward
            sync_player_inventory(player)
            rewards.append({'type': 'master_points', 'amount': master_points_reward})

    rewards.append({'type': 'victory_card', 'count': 1})
    evolved = _apply_deferred_gym_evolutions(
        state,
        battle['challenger_id'],
        battle.get('pending_evolution_slots') or [],
        leader_name,
    )

    _log(state, player['name'], f"Venceu o ginasio de {leader_name}!")
    if badge_name:
        _log(state, player['name'], f"Recebeu a insiginia {badge_name}.")
    if any(reward['type'] == 'master_points' for reward in rewards):
        _log(state, player['name'], f"Ganhou {battle.get('master_points_reward', 20)} Master Points pela vitoria no ginasio.")

    state['turn']['battle'] = None
    candidate_slots = list(battle.get('defeated_player_slots') or [])
    state = _queue_gym_heal_action(
        state,
        battle['challenger_id'],
        gym_id=gym_id,
        leader_name=leader_name,
        remaining_heals=3,
        healed_slots=[],
        candidate_slots=candidate_slots,
    )

    if not state['turn'].get('pending_action'):
        state = _award_victory_cards(state, battle['challenger_id'], 1, source='gym')
        if not state['turn'].get('battle') and not state['turn'].get('pending_action'):
            state['turn']['phase'] = 'end'
            state = end_turn(state)

    return state, {
        **result,
        'mode': 'gym',
        'gym_id': gym_id,
        'gym_name': battle.get('gym_name'),
        'leader_name': leader_name,
        'badge': badge_name,
        'badge_image_path': battle.get('badge_image_path'),
        'winner_id': battle['challenger_id'],
        'loser_id': None,
        'winner_name': player['name'],
        'loser_name': leader_name,
        'winner_pokemon': result.get('winner_pokemon') or (battle.get('challenger_choice') or {}).get('name'),
        'loser_pokemon': result.get('loser_pokemon') or (battle.get('defender_choice') or {}).get('name'),
        'gym_victory': True,
        'battle_finished': True,
        'continues': False,
        'rewards': rewards,
        'evolved': evolved,
        'healing_pending': bool(state['turn'].get('pending_action')),
    }


def _finalize_gym_loss(state: dict, battle: dict, result: dict) -> tuple[dict, dict]:
    player = _get_player(state, battle['challenger_id'])
    leader_name = battle.get('defender_name', 'Lider')
    gym_id = battle['gym_id']

    evolved = _apply_deferred_gym_evolutions(
        state,
        battle['challenger_id'],
        battle.get('pending_evolution_slots') or [],
        leader_name,
    )

    sync_player_inventory(player)

    state['turn']['battle'] = None
    state['turn']['pending_action'] = None
    state['turn']['phase'] = 'end'

    _log(state, leader_name, f"{player['name']} perdeu o desafio do ginasio.")
    return_data = {
        'returned_to_tile_id': None,
        'returned_to_tile_name': None,
        'stayed_on_safe_tile': False,
        'recovery_pending': False,
        'turn_ended': False,
    }
    if not _build_player_battle_pool(player, include_knocked_out=False):
        state, return_data = _handle_total_knockout_recovery(
            state,
            battle['challenger_id'],
            source=f"perder o desafio do ginásio contra {leader_name}",
        )
    else:
        state['turn']['current_tile'] = get_tile(state.get('board', {}), player.get('position', 0))
        state = end_turn(state)
    return state, {
        **result,
        'mode': 'gym',
        'gym_id': gym_id,
        'gym_name': battle.get('gym_name'),
        'leader_name': leader_name,
        'winner_id': None,
        'loser_id': battle['challenger_id'],
        'winner_name': leader_name,
        'loser_name': player['name'],
        'winner_pokemon': battle['defender_choice']['name'],
        'loser_pokemon': battle['challenger_choice']['name'] if battle.get('challenger_choice') else None,
        'gym_victory': False,
        'battle_finished': True,
        'continues': False,
        'returned_to_tile_id': return_data.get('returned_to_tile_id'),
        'returned_to_tile_name': return_data.get('returned_to_tile_name'),
        'stayed_on_safe_tile': return_data.get('stayed_on_safe_tile', False),
        'recovery_pending': return_data.get('recovery_pending', False),
        'evolved': evolved,
    }


def _start_gym_battle(state: dict, player_id: str, tile: dict, gym_definition: dict) -> dict:
    player = _get_player(state, player_id)
    if not player:
        return state

    reset_player_ability_runtime(player, 'battle')

    gym_id = gym_definition['id']
    _mark_gym_progress(player, 'gyms_attempted', gym_id)
    leader_team = build_gym_leader_team(gym_definition)

    battle = {
        'mode': 'gym',
        'source': 'gym_tile',
        'challenger_id': player_id,
        'defender_id': None,
        'gym_id': gym_id,
        'gym_name': gym_definition.get('gym_name', tile.get('name')),
        'gym_tile_id': tile.get('id'),
        'badge_name': gym_definition.get('badge_name'),
        'badge_image_path': gym_definition.get('badge_image_path'),
        'master_points_reward': int(gym_definition.get('master_points_reward', 20) or 20),
        'defender_name': gym_definition.get('leader_name', 'Lider'),
        'leader_team': leader_team,
        'leader_current_index': 0,
        'defeated_leader_indexes': [],
        'defeated_player_slots': [],
        'pending_evolution_slots': [],
        'challenger_choice': None,
        'defender_choice': None,
        'challenger_roll': None,
        'defender_roll': None,
        'sub_phase': 'choosing',
        'choice_stage': 'challenger',
        'round_number': 1,
    }
    _prepare_gym_leader_choice(battle)
    state['turn']['phase'] = 'battle'
    state['turn']['battle'] = battle
    _log(state, player['name'], f"Parou no ginasio {battle['gym_name']} e vai enfrentar {battle['defender_name']}!")
    if battle.get('defender_choice'):
        _log(state, battle['defender_name'], f"Enviou {battle['defender_choice']['name']} para o desafio do ginasio.")

    if not _build_player_battle_pool(player, include_knocked_out=False):
        _log(state, player['name'], 'Nao possui Pokemon disponiveis para o desafio do ginasio.')
        state, _ = _finalize_gym_loss(state, battle, {
            'challenger_roll': None,
            'defender_roll': None,
            'challenger_score': 0,
            'defender_score': 0,
            'challenger_wins': False,
            'reason': 'Sem Pokemon disponiveis',
        })
    return state


def _resolve_gym_battle(state: dict) -> tuple[dict, dict]:
    battle = copy.deepcopy(state['turn']['battle'])
    player = _get_player(state, battle['challenger_id'])
    leader_name = battle.get('defender_name', 'Lider')
    challenger_choice = battle['challenger_choice']
    defender_choice = battle['defender_choice']

    challenger_raw_roll = battle.get('challenger_roll') if battle.get('challenger_roll') is not None else roll_battle_dice()
    defender_raw_roll = battle.get('defender_roll') if battle.get('defender_roll') is not None else roll_battle_dice()
    battle['challenger_roll'] = challenger_raw_roll
    battle['defender_roll'] = defender_raw_roll

    result = resolve_duel(
        challenger_choice,
        defender_choice,
        challenger_roll=challenger_raw_roll,
        defender_roll=defender_raw_roll,
        battle_roll_fn=roll_battle_dice,
    )
    _record_battle_roll(state, player['name'], challenger_raw_roll, result['challenger_roll'], f"gym:{battle['gym_id']}")
    _record_battle_roll(state, leader_name, defender_raw_roll, result['defender_roll'], f"gym:{battle['gym_id']}")

    challenger_bonus = result.get('challenger_type_bonus', 0)
    defender_bonus = result.get('defender_type_bonus', 0)
    challenger_bp = challenger_choice.get('battle_points', 1)
    defender_bp = defender_choice.get('battle_points', 1)
    battle_tied = bool(result.get('is_tie'))

    _log(state, 'Ginasio', f"{player['name']} escolheu {challenger_choice['name']} (BP {challenger_bp})")
    _log(state, 'Ginasio', f"{leader_name} usou {defender_choice['name']} (BP {defender_bp})")
    if challenger_bonus:
        _log(state, 'Ginasio', f"{challenger_choice['name']} recebeu +{challenger_bonus} por vantagem de tipo")
    if defender_bonus:
        _log(state, 'Ginasio', f"{defender_choice['name']} recebeu +{defender_bonus} por vantagem de tipo")
    _log_battle_result_summary(
        state,
        log_player='Ginasio',
        challenger_name=player['name'],
        defender_name=leader_name,
        challenger_pokemon_name=challenger_choice['name'],
        defender_pokemon_name=defender_choice['name'],
        challenger_raw_roll=challenger_raw_roll,
        defender_raw_roll=defender_raw_roll,
        challenger_final_roll=result['challenger_roll'],
        defender_final_roll=result['defender_roll'],
        challenger_bp=challenger_bp,
        defender_bp=defender_bp,
        challenger_bonus=challenger_bonus,
        defender_bonus=defender_bonus,
        challenger_score=result['challenger_score'],
        defender_score=result['defender_score'],
        winner_message='Empate no round do ginásio. Role novamente.'
        if battle_tied
        else f"{player['name'] if result['challenger_wins'] else leader_name} venceu o round.",
    )

    current_slot = challenger_choice.get('battle_slot_key')
    current_leader_index = int(battle.get('leader_current_index', 0) or 0)
    result_payload = {
        **result,
        'gym_id': battle['gym_id'],
        'gym_name': battle.get('gym_name'),
        'leader_name': leader_name,
        'badge': battle.get('badge_name'),
        'challenger_name': player['name'],
        'defender_name': leader_name,
        'current_leader_pokemon': defender_choice['name'],
        'player_pokemon': challenger_choice['name'],
    }

    if battle_tied:
        return _prepare_tied_battle_reroll(
            state,
            battle,
            log_player='Ginasio',
            message=f"{challenger_choice['name']} e {defender_choice['name']} empataram. O round continua com nova rolagem.",
            result_payload={
                **result_payload,
                'mode': 'gym',
                'leader_name': leader_name,
                'challenger_name': player['name'],
                'defender_name': leader_name,
            },
        )

    if result['challenger_wins']:
        if current_slot and can_evolve(challenger_choice) and not challenger_choice.get('is_baby', False):
            pending = battle.setdefault('pending_evolution_slots', [])
            if current_slot not in pending:
                pending.append(current_slot)
        if current_leader_index not in battle['defeated_leader_indexes']:
            battle['defeated_leader_indexes'].append(current_leader_index)
        _log(state, player['name'], f"{challenger_choice['name']} derrotou {defender_choice['name']} no ginasio!")

        refreshed_choice = copy.deepcopy(_get_player_pokemon_slot(player, current_slot)) if current_slot else None
        if refreshed_choice:
            refreshed_choice['battle_slot_key'] = current_slot
        battle['challenger_choice'] = refreshed_choice
        battle['challenger_roll'] = None
        battle['defender_roll'] = None
        next_choice = _prepare_gym_leader_choice(battle)

        if next_choice:
            battle['sub_phase'] = 'rolling'
            battle['choice_stage'] = 'complete'
            battle['round_number'] = int(battle.get('round_number', 1) or 1) + 1
            state['turn']['battle'] = battle
            state['turn']['phase'] = 'battle'
            _log(state, leader_name, f"Enviou {next_choice['name']} para continuar a batalha de ginasio.")
            return state, {
                **result_payload,
                'mode': 'gym',
                'winner_id': player['id'],
                'loser_id': None,
                'winner_name': player['name'],
                'loser_name': leader_name,
                'winner_pokemon': challenger_choice['name'],
                'loser_pokemon': defender_choice['name'],
                'battle_finished': False,
                'continues': True,
                'needs_new_choice': False,
                'next_leader_pokemon': next_choice['name'],
            }

        state['turn']['battle'] = battle
        if battle.get('mode') == 'league':
            return _finalize_league_member_victory(state, battle, result_payload)
        return _finalize_gym_victory(state, battle, result_payload)

    if current_slot and current_slot not in battle['defeated_player_slots']:
        battle['defeated_player_slots'].append(current_slot)
    _set_pokemon_knocked_out(player, current_slot, True)
    sync_player_inventory(player)
    _log(state, leader_name, f"{defender_choice['name']} derrotou {challenger_choice['name']}!")

    available_pool = _build_player_battle_pool(player, include_knocked_out=False)
    if available_pool:
        battle['challenger_choice'] = None
        battle['challenger_roll'] = None
        battle['defender_roll'] = None
        battle['sub_phase'] = 'choosing'
        battle['choice_stage'] = 'challenger'
        battle['round_number'] = int(battle.get('round_number', 1) or 1) + 1
        state['turn']['battle'] = battle
        state['turn']['phase'] = 'battle'
        _log(state, player['name'], f"Escolha outro Pokemon para continuar contra {defender_choice['name']}.")
        return state, {
            **result_payload,
            'mode': 'gym',
            'winner_id': None,
            'loser_id': player['id'],
            'winner_name': leader_name,
            'loser_name': player['name'],
            'winner_pokemon': defender_choice['name'],
            'loser_pokemon': challenger_choice['name'],
            'battle_finished': False,
            'continues': True,
            'needs_new_choice': True,
        }

    state['turn']['battle'] = battle
    if battle.get('mode') == 'league':
        return _finalize_league_member_loss(state, battle, result_payload)
    return _finalize_gym_loss(state, battle, result_payload)


def _build_trainer_opponent_card(battle: dict) -> dict:
    return {
        'id': f"trainer-{battle.get('defender_name', 'trainer').lower().replace(' ', '-')}",
        'name': battle.get('defender_name', 'Trainer'),
        'types': [],
        'battle_points': int(battle.get('defender_bp', 3) or 3),
        'master_points': 0,
        'ability': 'none',
        'ability_type': 'none',
        'battle_effect': None,
    }


def _start_trainer_battle(state: dict, player_id: str, trainer_context: dict, source: str) -> dict:
    player = _get_player(state, player_id)
    if not player:
        return state

    reset_player_ability_runtime(player, 'battle')

    state['turn']['phase'] = 'battle'
    state['turn']['battle'] = {
        'mode': 'trainer',
        'source': source,
        'challenger_id': player_id,
        'defender_id': None,
        'defender_name': trainer_context.get('trainer_name', 'Trainer'),
        'defender_bp': int(trainer_context.get('trainer_bp', 3) or 3),
        'challenger_choice': None,
        'defender_choice': _build_trainer_opponent_card({
            'defender_name': trainer_context.get('trainer_name', 'Trainer'),
            'defender_bp': trainer_context.get('trainer_bp', 3),
        }),
        'challenger_roll': None,
        'defender_roll': None,
        'sub_phase': 'choosing',
        'choice_stage': 'challenger',
        'reward_plan': copy.deepcopy(trainer_context.get('reward_plan') or {}),
        'source_card_title': trainer_context.get('card_title', 'Trainer Battle'),
        'source_card_category': trainer_context.get('card_category'),
        'remaining_rounds': int((trainer_context.get('reward_plan') or {}).get('max_battles', 1) or 1),
        'pending_evolution_slots': [],
    }
    clear_revealed_card(state)
    _log(state, player['name'], f"Iniciou batalha de treinador contra {state['turn']['battle']['defender_name']} ({source})")
    return state


def _build_recharge_ability_reward_options(player: dict) -> list[dict]:
    options: list[dict] = []
    for slot_key, pokemon in _iter_player_battle_slots(player, include_knocked_out=True):
        sync_pokemon_ability_state(pokemon)
        ability = next(iter(pokemon.get('abilities') or []), None)
        if not isinstance(ability, dict) or ability.get('charges_total') is None:
            continue
        charges_total = int(ability.get('charges_total') or 0)
        charges_remaining = int(ability.get('charges_remaining') or 0)
        if charges_remaining >= charges_total:
            continue
        label = pokemon.get('name', slot_key)
        if slot_key == 'starter':
            label = f'{label} (Starter)'
        options.append({
            'id': f'recharge:{slot_key}',
            'label': f'Recarregar {label} ({charges_remaining}/{charges_total})',
            'recharge_slot_key': slot_key,
            'recharge_pokemon_name': pokemon.get('name', slot_key),
        })
    return options


def _restore_primary_ability_charge_for_slot(player: dict, slot_key: str) -> dict | None:
    pokemon = _get_player_pokemon_slot(player, slot_key)
    if not pokemon:
        return None

    sync_pokemon_ability_state(pokemon)
    ability = next(iter(pokemon.get('abilities') or []), None)
    if not isinstance(ability, dict) or ability.get('charges_total') is None:
        return None

    charges_total = int(ability.get('charges_total') or 0)
    charges_before = int(ability.get('charges_remaining') or 0)
    if charges_before >= charges_total:
        return None

    charges_after = adjust_primary_ability_charges(pokemon, 1)
    if charges_after is None or charges_after <= charges_before:
        return None

    return {
        'pokemon_name': pokemon.get('name', slot_key),
        'charges_remaining': charges_after,
        'charges_total': charges_total,
    }


def _apply_trainer_battle_rewards(state: dict, player_id: str, battle: dict) -> list[dict]:
    player = _get_player(state, player_id)
    if not player:
        return []

    rewards: list[dict] = []
    reward_plan = battle.get('reward_plan') or {}

    victory_cards = int(reward_plan.get('victory_cards', 0) or 0)
    if victory_cards > 0:
        state = _award_victory_cards(state, player_id, victory_cards, source='trainer_battle')
        rewards.append({'type': 'victory_card', 'count': victory_cards})

    master_points = int(reward_plan.get('master_points', 0) or 0)
    if master_points > 0:
        player['bonus_points'] = player.get('bonus_points', 0) + master_points
        player['bonus_master_points'] = player.get('bonus_master_points', 0) + master_points
        sync_player_inventory(player)
        rewards.append({'type': 'master_points', 'amount': master_points})

    if reward_plan.get('extra_turn'):
        state['turn']['extra_turn'] = True
        rewards.append({'type': 'extra_turn'})

    if reward_plan.get('recharge_ability_charge'):
        options = _build_recharge_ability_reward_options(player)
        if len(options) == 1:
            recharged = _restore_primary_ability_charge_for_slot(player, options[0]['recharge_slot_key'])
            if recharged:
                rewards.append({'type': 'ability_charge', 'pokemon': recharged['pokemon_name']})
        elif len(options) > 1:
            _queue_reward_choice(
                state,
                player_id,
                source='trainer_battle',
                card={'title': battle.get('source_card_title', 'Trainer Reward')},
                options=options,
                prompt='Escolha um Pokémon para recuperar 1 carga de habilidade.',
            )
            _log(state, player['name'], 'Pode recuperar 1 carga de habilidade de um dos seus Pokémon.')

    return rewards


def _apply_deferred_trainer_evolutions(state: dict, player_id: str, slot_keys: list[str], defender_name: str) -> list[dict]:
    player = _get_player(state, player_id)
    if not player:
        return []

    evolved: list[dict] = []
    seen: set[str] = set()
    for slot_key in slot_keys:
        if slot_key in seen:
            continue
        seen.add(slot_key)
        pokemon = _get_player_pokemon_slot(player, slot_key)
        if not pokemon or not can_evolve(pokemon) or pokemon.get('is_baby', False):
            continue
        original_name = pokemon.get('name', '?')
        pokemon_for_evolution = copy.deepcopy(pokemon)
        pokemon_for_evolution['battle_slot_key'] = slot_key
        evolved_pokemon = _try_evolve(state, player_id, pokemon_for_evolution, heal_on_evolve=True)
        if not evolved_pokemon:
            continue
        evolved.append({
            'slot_key': slot_key,
            'from': original_name,
            'to': evolved_pokemon['name'],
        })
        _log(state, player['name'], f"{original_name} evoluiu para {evolved_pokemon['name']} e foi curado automaticamente após a batalha contra {defender_name}!")
    return evolved


def _resolve_trainer_battle(state: dict) -> tuple[dict, dict]:
    battle = copy.deepcopy(state['turn']['battle'])
    player = _get_player(state, battle['challenger_id'])
    trainer_card = copy.deepcopy(battle.get('defender_choice') or _build_trainer_opponent_card(battle))
    player_pokemon = battle['challenger_choice']
    player_raw_roll = int(battle.get('challenger_roll'))
    trainer_raw_roll = int(battle.get('defender_roll'))

    result = resolve_duel(
        player_pokemon,
        trainer_card,
        challenger_roll=player_raw_roll,
        defender_roll=trainer_raw_roll,
        battle_roll_fn=roll_battle_dice,
    )
    _record_battle_roll(state, player['name'], player_raw_roll, result['challenger_roll'], 'trainer')
    _record_battle_roll(state, battle['defender_name'], trainer_raw_roll, result['defender_roll'], 'trainer')

    player_bonus = result.get('challenger_type_bonus', 0)
    trainer_bonus = result.get('defender_type_bonus', 0)
    player_bp = player_pokemon.get('battle_points', 1)
    trainer_bp = trainer_card.get('battle_points', 1)
    battle_tied = bool(result.get('is_tie'))
    player_wins = bool(result['challenger_wins'])

    _log(state, 'Duelo', f"{player['name']} escolheu {player_pokemon['name']} (BP {player_bp})")
    _log(state, 'Duelo', f"{battle['defender_name']} usou {trainer_card['name']} (BP {trainer_bp})")
    if player_bonus:
        _log(state, 'Duelo', f"{player_pokemon['name']} recebeu +{player_bonus} por vantagem de tipo")
    if trainer_bonus:
        _log(state, 'Duelo', f"{trainer_card['name']} recebeu +{trainer_bonus} por vantagem de tipo")
    _log_battle_result_summary(
        state,
        log_player='Duelo',
        challenger_name=player['name'],
        defender_name=battle['defender_name'],
        challenger_pokemon_name=player_pokemon['name'],
        defender_pokemon_name=trainer_card['name'],
        challenger_raw_roll=player_raw_roll,
        defender_raw_roll=trainer_raw_roll,
        challenger_final_roll=result['challenger_roll'],
        defender_final_roll=result['defender_roll'],
        challenger_bp=player_bp,
        defender_bp=trainer_bp,
        challenger_bonus=player_bonus,
        defender_bonus=trainer_bonus,
        challenger_score=result['challenger_score'],
        defender_score=result['defender_score'],
        winner_message='Empate na batalha de treinador. Role novamente.'
        if battle_tied
        else f"{player['name'] if player_wins else battle['defender_name']} venceu a batalha.",
    )

    rewards: list[dict] = []
    continues = False
    evolved: list[dict] = []
    return_data = {
        'returned_to_tile_id': None,
        'returned_to_tile_name': None,
        'stayed_on_safe_tile': False,
        'recovery_pending': False,
        'turn_ended': False,
    }
    current_slot = player_pokemon.get('battle_slot_key')

    if battle_tied:
        return _prepare_tied_battle_reroll(
            state,
            battle,
            log_player='Duelo',
            message=f"{player_pokemon['name']} e {trainer_card['name']} empataram. A batalha continua com nova rolagem.",
            result_payload={
                **result,
                'mode': 'trainer',
                'challenger_name': player['name'],
                'defender_name': battle['defender_name'],
            },
        )

    if player_wins:
        if current_slot and can_evolve(player_pokemon) and not player_pokemon.get('is_baby', False):
            pending = battle.setdefault('pending_evolution_slots', [])
            if current_slot not in pending:
                pending.append(current_slot)
        rewards = _apply_trainer_battle_rewards(state, player['id'], battle)
        follow_up_battle = state['turn'].get('phase') == 'battle' and (state['turn'].get('battle') or {}).get('source') == 'victory_card'
        if battle.get('reward_plan', {}).get('repeat_battle') and int(battle.get('remaining_rounds', 1) or 1) > 1:
            next_battle = copy.deepcopy(battle)
            next_battle['challenger_choice'] = None
            next_battle['challenger_roll'] = None
            next_battle['defender_roll'] = None
            next_battle['sub_phase'] = 'choosing'
            next_battle['choice_stage'] = 'challenger'
            next_battle['remaining_rounds'] = int(next_battle.get('remaining_rounds', 1) or 1) - 1
            state['turn']['battle'] = next_battle
            state['turn']['phase'] = 'battle'
            continues = True
            _log(state, 'Duelo', f"{player['name']} venceu e pode batalhar novamente contra {battle['defender_name']}")
        elif follow_up_battle:
            evolved = _apply_deferred_trainer_evolutions(
                state,
                player['id'],
                battle.get('pending_evolution_slots') or [],
                battle['defender_name'],
            )
            continues = True
            _log(state, 'Duelo', f"{player['name']} venceu a batalha contra {battle['defender_name']} e iniciou uma nova batalha de recompensa")
        else:
            state['turn']['battle'] = None
            state['turn']['phase'] = 'end'
            evolved = _apply_deferred_trainer_evolutions(
                state,
                player['id'],
                battle.get('pending_evolution_slots') or [],
                battle['defender_name'],
            )
            reward_summary = ', '.join(
                f"{reward['count']} carta(s) de vitória" if reward['type'] == 'victory_card'
                else f"{reward['amount']} Master Points" if reward['type'] == 'master_points'
                else 'um turno extra' if reward['type'] == 'extra_turn'
                else f"1 carga para {reward['pokemon']}" if reward['type'] == 'ability_charge'
                else reward['type']
                for reward in rewards
            )
            _log(state, 'Duelo', f"{player['name']} venceu a batalha contra {battle['defender_name']}" + (f" e recebeu {reward_summary}" if reward_summary else ''))
            if not state['turn'].get('pending_action'):
                state = end_turn(state)
    else:
        if current_slot:
            knocked_out = _set_pokemon_knocked_out(player, current_slot, True)
            if knocked_out is not None:
                sync_player_inventory(player)
                _log(state, player['name'], f"{player_pokemon['name']} ficou nocauteado e não pode ser usado até ser curado.")
        state['turn']['battle'] = None
        state['turn']['phase'] = 'end'
        evolved = _apply_deferred_trainer_evolutions(
            state,
            player['id'],
            battle.get('pending_evolution_slots') or [],
            battle['defender_name'],
        )
        if not _build_player_battle_pool(player, include_knocked_out=False):
            state, return_data = _handle_total_knockout_recovery(
                state,
                player['id'],
                source=f"perder a batalha contra {battle['defender_name']}",
            )
        _log(state, 'Duelo', f"{battle['defender_name']} venceu a batalha contra {player['name']}")
        if not (return_data.get('recovery_pending') or return_data.get('turn_ended')):
            state = end_turn(state)

    return state, {
        **result,
        'winner_id': player['id'] if player_wins else None,
        'loser_id': None if player_wins else player['id'],
        'challenger_name': player['name'],
        'defender_name': battle['defender_name'],
        'winner_name': player['name'] if player_wins else battle['defender_name'],
        'loser_name': battle['defender_name'] if player_wins else player['name'],
        'winner_pokemon': player_pokemon['name'] if player_wins else trainer_card['name'],
        'loser_pokemon': trainer_card['name'] if player_wins else player_pokemon['name'],
        'mode': 'trainer',
        'rewards': rewards,
        'continues': continues,
        'evolved': evolved,
        'knocked_out_pokemon': None if player_wins else player_pokemon['name'],
        'returned_to_tile_id': return_data.get('returned_to_tile_id'),
        'returned_to_tile_name': return_data.get('returned_to_tile_name'),
        'stayed_on_safe_tile': return_data.get('stayed_on_safe_tile', False),
        'recovery_pending': return_data.get('recovery_pending', False),
    }

def propose_trade(
    state: dict,
    proposer_id: str,
    target_id: str,
    offered_slot_key: str | None,
    requested_slot_key: str | None = None,
) -> tuple[dict | None, str | dict]:
    state = copy.deepcopy(state)
    turn = state.get('turn', {})
    proposer = _get_player(state, proposer_id)
    target = _get_player(state, target_id)

    if not proposer or not target:
        return None, 'Jogador não encontrado'
    if turn.get('current_player_id') != proposer_id:
        return None, 'Não é seu turno'
    if turn.get('phase') != 'action':
        return None, 'Trocas só podem ser propostas na fase de ação'
    if turn_has_blocking_interaction(turn):
        return None, 'Não é possível trocar durante uma interação pendente'
    if target_id not in _get_trade_eligible_target_ids(state, proposer_id):
        return None, 'Este jogador não está disponível para troca agora'

    offered_key = str(offered_slot_key or '').strip()
    offered_pokemon = _get_player_pokemon_slot(proposer, offered_key)
    if not offered_pokemon:
        return None, 'Escolha um Pokémon seu para oferecer na troca'

    offered_name = offered_pokemon.get('name', offered_key)
    _set_pending_action(state, {
        'type': 'trade_proposal',
        'player_id': target_id,
        'allowed_actions': ['resolve_pending_action'],
        'proposer_id': proposer_id,
        'proposer_name': proposer.get('name', 'Jogador'),
        'target_player_id': target_id,
        'target_name': target.get('name', 'Jogador'),
        'offered_slot_key': offered_key,
        'offered_pokemon': copy.deepcopy(offered_pokemon),
        'prompt': (
            f"{proposer.get('name', 'Jogador')} oferece {offered_name}. "
            "Escolha qual dos seus Pokémon entrar na troca ou recuse."
        ),
        'options': _build_trade_options_for_player(target),
    })
    _log(
        state,
        proposer.get('name', 'Jogador'),
        f"Propôs uma troca para {target.get('name', 'Jogador')} oferecendo {offered_name}.",
    )
    return state, {
        'type': 'trade_proposal',
        'success': True,
        'proposer_id': proposer_id,
        'target_player_id': target_id,
        'proposer_name': proposer.get('name', 'Jogador'),
        'target_name': target.get('name', 'Jogador'),
        'offered_pokemon': offered_name,
        'preferred_requested_slot_key': str(requested_slot_key or '').strip() or None,
    }


def start_duel(state: dict, challenger_id: str, defender_id: str) -> dict | None:
    """Inicia um duelo entre dois jogadores."""
    state = copy.deepcopy(state)

    challenger = _get_player(state, challenger_id)
    defender = _get_player(state, defender_id)

    if not challenger or not defender:
        return None
    if not defender.get('is_active'):
        return None

    # Verifica se ambos têm Pokémon
    challenger_pool = _build_player_battle_pool(challenger, include_knocked_out=False)
    defender_pool = _build_player_battle_pool(defender, include_knocked_out=False)

    if not challenger_pool or not defender_pool:
        return None

    reset_player_ability_runtime(challenger, 'battle')
    reset_player_ability_runtime(defender, 'battle')

    state['turn']['phase'] = 'battle'
    state['turn']['battle'] = {
        'mode': 'player',
        'challenger_id': challenger_id,
        'defender_id': defender_id,
        'challenger_choice': None,
        'defender_choice': None,
        'challenger_roll': None,
        'defender_roll': None,
        'sub_phase': 'choosing',
        'choice_stage': 'defender',
    }

    _log(state, challenger['name'], f"Desafiou {defender['name']} para um duelo!")
    return state


def register_battle_choice(
    state: dict,
    player_id: str,
    pokemon_index: int | None = None,
    pokemon_slot_key: str | None = None,
) -> tuple[dict, dict | None]:
    """
    Registra a escolha de Pokémon de um jogador no duelo.
    Quando ambos escolheram, avança para sub_phase='rolling' (rolagem individual).
    """
    state = copy.deepcopy(state)
    battle = state['turn'].get('battle')
    if not battle:
        return state, {'error': 'Nenhuma batalha ativa'}

    current_sub = battle.get('sub_phase', 'choosing')
    if current_sub != 'choosing':
        return state, {'error': 'A batalha não está aceitando escolhas agora'}

    player = _get_player(state, player_id)
    if not player:
        return state, {'error': 'Jogador não encontrado'}

    is_challenger = battle['challenger_id'] == player_id
    is_defender = battle['defender_id'] == player_id
    mode = battle.get('mode', 'player')
    is_solo_battle = mode in ('trainer', 'gym')
    if not is_challenger and not is_defender:
        return state, {'error': 'Você não participa desta batalha'}

    if is_challenger and battle.get('challenger_choice'):
        return state, {'ignored': True}
    if is_defender and battle.get('defender_choice') and mode == 'player':
        return state, {'ignored': True}

    choice_stage = battle.get('choice_stage', 'defender')
    if mode == 'player':
        if choice_stage == 'defender' and not is_defender:
            return state, {'error': 'O jogador desafiado deve escolher primeiro'}
        if choice_stage == 'challenger' and not is_challenger:
            return state, {'error': 'Agora é a vez do desafiante escolher'}
    elif is_solo_battle and not is_challenger:
        return state, {'error': 'Somente o jogador ativo escolhe nesta batalha'}

    pool = _build_player_battle_pool(player, include_knocked_out=False)
    if not pool:
        return state, {'error': 'Você não possui Pokémon disponíveis'}

    chosen, resolved_index = _resolve_battle_pool_choice(
        pool,
        pokemon_index=pokemon_index,
        pokemon_slot_key=pokemon_slot_key,
    )
    if not chosen:
        return state, {'error': 'Pokémon inválido'}
    resolved_slot_key = chosen.get('battle_slot_key')

    pending_pluspower = battle.get('pluspower_pending') or {}
    pluspower_matches = False
    if pending_pluspower.get('player_id') == player_id:
        pending_slot_key = (pending_pluspower.get('pokemon_slot_key') or '').strip()
        if pending_slot_key:
            pluspower_matches = pending_slot_key == resolved_slot_key
        else:
            pluspower_matches = pending_pluspower.get('pokemon_index') == resolved_index
    if pluspower_matches:
        chosen['battle_points'] = chosen.get('battle_points', 0) + 2
        chosen['pluspower_applied'] = True

    team_bp_bonus = _compute_team_bonus_bp(player, chosen)
    if team_bp_bonus > 0:
        chosen['battle_points'] = chosen.get('battle_points', 0) + team_bp_bonus
        chosen['team_bonus_bp'] = team_bp_bonus

    if is_challenger:
        battle['challenger_choice'] = chosen
    else:
        battle['defender_choice'] = chosen

    if pending_pluspower.get('player_id') == player_id:
        battle['pluspower_pending'] = None

    # Apply defender debuff: player used Defender → opponent's chosen pokemon loses 2 BP
    defender_pending = battle.get('defender_pending') or {}
    if defender_pending.get('player_id') == player_id:
        if is_challenger and battle.get('defender_choice'):
            battle['defender_choice']['battle_points'] = max(1, (battle['defender_choice'].get('battle_points') or 1) - 2)
            battle['defender_choice']['defender_debuffed'] = True
        elif not is_challenger and battle.get('challenger_choice'):
            battle['challenger_choice']['battle_points'] = max(1, (battle['challenger_choice'].get('battle_points') or 1) - 2)
            battle['challenger_choice']['defender_debuffed'] = True
        else:
            battle['defender_active'] = True
        battle['defender_pending'] = None

    _log(state, player['name'], f"Escolheu {chosen['name']} (BP {chosen.get('battle_points', 1)})")

    if mode == 'trainer':
        battle['sub_phase'] = 'rolling'
        battle['choice_stage'] = 'complete'
        if _queue_pre_roll_battle_ability_decision(state):
            return state, None
        _log_battle_ready_to_roll(state, battle)
        return state, None

    if mode in ('gym', 'league'):
        if not battle.get('defender_choice'):
            defender_choice = _prepare_gym_leader_choice(battle)
            if not defender_choice:
                return state, {'error': 'O líder do ginásio não possui mais Pokémon disponíveis'}
            # Apply pending defender debuff to leader's newly chosen pokemon
            if battle.get('defender_active'):
                battle['defender_choice']['battle_points'] = max(1, (battle['defender_choice'].get('battle_points') or 1) - 2)
                battle['defender_choice']['defender_debuffed'] = True
                battle.pop('defender_active', None)
        battle['sub_phase'] = 'rolling'
        battle['choice_stage'] = 'complete'
        if _queue_pre_roll_battle_ability_decision(state):
            return state, None
        _log_battle_ready_to_roll(state, battle)
        return state, None

    if battle.get('defender_choice') and not battle.get('challenger_choice'):
        battle['choice_stage'] = 'challenger'
        challenger = _get_player(state, battle['challenger_id'])
        _log(state, 'Duelo', f"{battle['defender_choice']['name']} já está em campo. {challenger['name']} escolhe agora.")
        return state, None

    if battle['challenger_choice'] and battle['defender_choice']:
        battle['sub_phase'] = 'rolling'
        battle['choice_stage'] = 'complete'
        if _queue_pre_roll_battle_ability_decision(state):
            return state, None
        _log_battle_ready_to_roll(state, battle)

    return state, None


def register_battle_roll(state: dict, player_id: str) -> tuple[dict, dict | None]:
    """
    Registra a rolagem de dado de batalha de um jogador.
    Quando ambos rolaram, resolve o duelo.
    """
    state = copy.deepcopy(state)
    battle = state['turn'].get('battle')
    if not battle:
        return state, {'error': 'Nenhuma batalha ativa'}

    if battle.get('sub_phase') != 'rolling':
        return state, {'error': 'A batalha ainda não está na fase de rolagem'}

    is_challenger = battle['challenger_id'] == player_id
    is_defender = battle['defender_id'] == player_id
    mode = battle.get('mode', 'player')

    if mode == 'trainer':
        if not is_challenger:
            return state, {'error': 'Somente o jogador ativo rola nesta batalha de treinador'}
    elif mode in ('gym', 'league'):
        if not is_challenger:
            return state, {'error': 'Somente o desafiante rola nesta batalha de ginásio'}
    elif not is_challenger and not is_defender:
        return state, {'error': 'Você não participa desta batalha'}

    if is_challenger and battle.get('challenger_roll') is not None:
        return state, {'ignored': True}
    if is_defender and battle.get('defender_roll') is not None:
        return state, {'ignored': True}

    roll = roll_battle_dice()
    player = _get_player(state, player_id)

    if is_challenger:
        battle['challenger_roll'] = roll
    else:
        battle['defender_roll'] = roll

    # battle_reroll: offer reroll to the rolling player (challenger only in trainer/gym)
    battle_choice = battle.get('challenger_choice' if is_challenger else 'defender_choice') or {}
    br = _find_available_battle_reroll_ability(player, battle_choice)
    if br:
        slot_key, br_pokemon, br_ability = br
        if mode == 'trainer':
            trainer_roll = roll_battle_dice()
            battle['defender_roll'] = trainer_roll
        elif mode in ('gym', 'league'):
            leader_roll = roll_battle_dice()
            battle['defender_roll'] = leader_roll
        return _queue_battle_reroll_decision(
            state, player_id,
            roll=roll,
            is_challenger=is_challenger,
            slot_key=slot_key,
            pokemon=br_pokemon,
            ability=br_ability,
        )

    if mode == 'trainer':
        trainer_roll = roll_battle_dice()
        battle['defender_roll'] = trainer_roll
        return _resolve_trainer_battle(state)
    if mode in ('gym', 'league'):
        leader_roll = roll_battle_dice()
        battle['defender_roll'] = leader_roll
        return _resolve_gym_battle(state)

    if battle.get('challenger_roll') is not None and battle.get('defender_roll') is not None:
        return _resolve_duel(state)

    return state, None


def _has_ability(player: dict, ability_name: str) -> bool:
    """Verifica se qualquer Pokémon do jogador (starter incluso) tem a habilidade passiva."""
    all_pokemon = list(player.get('pokemon', []))
    if player.get('starter_pokemon'):
        all_pokemon.append(player['starter_pokemon'])
    return any(p.get('ability') == ability_name for p in all_pokemon)


def _apply_post_battle_effects(
    state: dict,
    winner: dict,
    loser: dict,
    winner_pokemon: dict,
    loser_pokemon: dict,
) -> None:
    """
    Aplica efeitos pós-batalha com base no battle_effect do Pokémon vencedor.
    Modifica winner/loser in-place (state já é cópia profunda).

    Efeitos do VENCEDOR:
      poison_sting / shadow_ball / flame_body  → perdedor perde 1 FR
      super_fang                                → vencedor rouba 1 Pokébola do perdedor
      curse                                     → perdedor perde 5 MP extras
      shed_skin                                 → vencedor recupera 1 FR
      wing_attack                               → vencedor avança 1 casa extra
      hyper_voice                               → perdedor recua 2 casas (bloqueado por Rock Head)
      dynamic_punch                             → perdedor perde 1 item (pendente: sistema de itens)

    Passivos verificados:
      Water Veil  (qualquer Pokémon do perdedor) → imune a perder FR por batalha
      Rock Head   (qualquer Pokémon do perdedor) → imune a recuar por efeitos de batalha
    """
    winner_effect = winner_pokemon.get('battle_effect')
    board_data = state.get('board', {})

    # ── Passivos de proteção do perdedor ─────────────────────────────────────
    loser_immune_fr       = _has_ability(loser, 'Water Veil')
    loser_immune_pushback = _has_ability(loser, 'Rock Head')

    # ── Efeitos que custam Full Restore ao perdedor ──────────────────────────
    if winner_effect in ('poison_sting', 'shadow_ball', 'flame_body'):
        if not loser_immune_fr:
            remove_item(loser, 'full_restore', 1)
            _log(state, winner['name'],
                 f"{winner_pokemon['name']}: {loser['name']} perdeu 1 Full Restore!")
        else:
            _log(state, winner['name'],
                 f"{winner_pokemon['name']}: {loser['name']} é imune (Water Veil)!")

    # ── Super Fang: rouba Pokébola ───────────────────────────────────────────
    elif winner_effect == 'super_fang':
        if loser['pokeballs'] > 0:
            loser['pokeballs'] -= 1
            winner['pokeballs'] += 1
            sync_player_inventory(loser)
            sync_player_inventory(winner)
            _log(state, winner['name'],
                 f"Super Fang: {winner['name']} roubou 1 Pokébola de {loser['name']}!")

    # ── Curse: perdedor perde 5 MP extras ───────────────────────────────────
    elif winner_effect == 'curse':
        loser['bonus_points'] = loser.get('bonus_points', 0) - 5
        loser['bonus_master_points'] = loser.get('bonus_master_points', 0) - 5
        sync_player_inventory(loser)
        _log(state, winner['name'],
             f"Curse: {loser['name']} perdeu 5 Master Points extras!")

    # ── Shed Skin: vencedor recupera 1 FR ───────────────────────────────────
    elif winner_effect == 'shed_skin':
        add_item(winner, 'full_restore', 1)
        _log(state, winner['name'], "Shed Skin: recuperou 1 Full Restore!")

    # ── Wing Attack: vencedor avança 1 casa ─────────────────────────────────
    elif winner_effect == 'wing_attack':
        old_pos = winner['position']
        new_pos = calculate_new_position(old_pos, 1, board_data)
        winner['position'] = new_pos
        _update_pokecenter_progress(state, winner['id'], old_pos, new_pos)
        _log(state, winner['name'],
             f"Wing Attack: {winner['name']} avançou 1 casa extra (posição {new_pos})!")

    # ── Hyper Voice: perdedor recua 2 casas ─────────────────────────────────
    elif winner_effect == 'hyper_voice':
        if not loser_immune_pushback:
            old_pos = loser['position']
            loser['position'] = max(0, loser['position'] - 2)
            _update_pokecenter_progress(state, loser['id'], old_pos, loser['position'])
            _log(state, winner['name'],
                 f"Hyper Voice: {loser['name']} recuou 2 casas (posição {loser['position']})!")
        else:
            _log(state, winner['name'],
                 f"Hyper Voice: {loser['name']} é imune ao recuo (Rock Head)!")

    # ── Dynamic Punch: perdedor perde 1 item ────────────────────────────────
    # Pendente: sistema de itens (ItemCard) não implementado ainda
    elif winner_effect == 'dynamic_punch':
        _log(state, winner['name'],
             f"Dynamic Punch: {loser['name']} perdeu 1 item! (sistema de itens pendente)")


def _resolve_duel(state: dict) -> tuple[dict, dict]:
    battle = state['turn']['battle']
    battle_source = battle.get('source')
    challenger = _get_player(state, battle['challenger_id'])
    defender = _get_player(state, battle['defender_id'])

    # Usa os dados já rolados pelos jogadores (sub_phase='rolling')
    # Fallback para roll automático caso _resolve_duel seja chamado sem rolls salvos
    challenger_raw_roll = battle.get('challenger_roll') if battle.get('challenger_roll') is not None else roll_battle_dice()
    defender_raw_roll = battle.get('defender_roll') if battle.get('defender_roll') is not None else roll_battle_dice()

    ch_pokemon = battle['challenger_choice']
    def_pokemon = battle['defender_choice']

    result = resolve_duel(
        ch_pokemon,
        def_pokemon,
        challenger_roll=challenger_raw_roll,
        defender_roll=defender_raw_roll,
        battle_roll_fn=roll_battle_dice,
    )
    _record_battle_roll(state, challenger['name'], challenger_raw_roll, result['challenger_roll'], 'duel')
    _record_battle_roll(state, defender['name'], defender_raw_roll, result['defender_roll'], 'duel')

    ch_type_bonus = result.get('challenger_type_bonus', 0)
    def_type_bonus = result.get('defender_type_bonus', 0)
    challenger_bp = ch_pokemon.get('battle_points', 1)
    defender_bp = def_pokemon.get('battle_points', 1)
    battle_tied = bool(result.get('is_tie'))

    _log(state, 'Duelo', f"{challenger['name']} escolheu {ch_pokemon['name']} (BP {challenger_bp})")
    _log(state, 'Duelo', f"{defender['name']} escolheu {def_pokemon['name']} (BP {defender_bp})")
    if ch_type_bonus:
        _log(state, 'Duelo', f"{ch_pokemon['name']} recebeu +{ch_type_bonus} por vantagem de tipo")
    if def_type_bonus:
        _log(state, 'Duelo', f"{def_pokemon['name']} recebeu +{def_type_bonus} por vantagem de tipo")
    _log_battle_result_summary(
        state,
        log_player='Duelo',
        challenger_name=challenger['name'],
        defender_name=defender['name'],
        challenger_pokemon_name=ch_pokemon['name'],
        defender_pokemon_name=def_pokemon['name'],
        challenger_raw_roll=challenger_raw_roll,
        defender_raw_roll=defender_raw_roll,
        challenger_final_roll=result['challenger_roll'],
        defender_final_roll=result['defender_roll'],
        challenger_bp=challenger_bp,
        defender_bp=defender_bp,
        challenger_bonus=ch_type_bonus,
        defender_bonus=def_type_bonus,
        challenger_score=result['challenger_score'],
        defender_score=result['defender_score'],
        winner_message='Empate na batalha. Ambos devem rolar novamente.'
        if battle_tied
        else f"{challenger['name'] if result['challenger_wins'] else defender['name']} venceu a batalha.",
    )

    if battle_tied:
        return _prepare_tied_battle_reroll(
            state,
            battle,
            log_player='Duelo',
            message=f"{ch_pokemon['name']} e {def_pokemon['name']} empataram. A batalha continua com nova rolagem.",
            result_payload={
                **result,
                'mode': 'player',
                'challenger_name': challenger['name'],
                'defender_name': defender['name'],
            },
        )

    winner = challenger if result['challenger_wins'] else defender
    loser = defender if result['challenger_wins'] else challenger
    winner_pokemon = ch_pokemon if result['challenger_wins'] else def_pokemon
    loser_pokemon = def_pokemon if result['challenger_wins'] else ch_pokemon
    loser_slot = loser_pokemon.get('battle_slot_key')

    if loser_slot:
        knocked_out = _set_pokemon_knocked_out(loser, loser_slot, True)
        if knocked_out is not None:
            sync_player_inventory(loser)
            _log(state, loser['name'], f"{loser_pokemon['name']} ficou nocauteado e não pode ser usado até ser curado.")

    winner['bonus_points'] = winner.get('bonus_points', 0) + 5
    winner['bonus_master_points'] = winner.get('bonus_master_points', 0) + 5
    sync_player_inventory(winner)
    _log(state, winner['name'], f"Venceu o duelo! +5 Master Points")

    state['turn']['battle'] = None
    state['turn']['phase'] = 'end'
    state = _award_victory_cards(state, winner['id'], 1, source='duel')

    _apply_post_battle_effects(state, winner, loser, winner_pokemon, loser_pokemon)
    # Enforce item capacity after battle effects (e.g. shed_skin adds FR)
    _queue_item_choice(state, winner['id'], 'Efeito de batalha')

    evolved = None
    if can_evolve(winner_pokemon):
        is_baby = winner_pokemon.get('is_baby', False)
        if not is_baby:
            evolved = _try_evolve(state, winner['id'], winner_pokemon, heal_on_evolve=True)
            if evolved:
                _log(state, winner['name'], f"{winner_pokemon['name']} evoluiu para {evolved['name']} e foi curado automaticamente após a batalha!")

    return_data = {
        'returned_to_tile_id': None,
        'returned_to_tile_name': None,
        'stayed_on_safe_tile': False,
        'recovery_pending': False,
        'turn_ended': False,
    }
    if not _build_player_battle_pool(loser, include_knocked_out=False):
        state, return_data = _handle_total_knockout_recovery(
            state,
            loser['id'],
            source=f"perder o duelo contra {winner['name']}",
        )

    # Abra passivo: se Abra foi o Pokémon derrotado, oferecer ao jogador à esquerda
    if loser_pokemon.get('name') == 'Abra':
        left_player = _get_player_to_left(state, loser['id'])
        if left_player and left_player['id'] != loser['id']:
            state.setdefault('abra_transfer_offers', []).append({
                'from_player_id': loser['id'],
                'to_player_id': left_player['id'],
                'pokemon': copy.deepcopy(loser_pokemon),
                'loser_slot': loser_slot,
            })
            _log(state, loser['name'],
                 f"Abra perdeu a batalha! {left_player['name']} poderá adicionar Abra ao time no próximo turno.")

    reward_summary = 'comprou uma carta de vitória'
    _log(state, 'Duelo', f"{winner['name']} venceu a batalha e {reward_summary}")

    battle_result = {
        **result,
        'mode': 'player',
        'challenger_name': challenger['name'],
        'defender_name': defender['name'],
        'winner_id': winner['id'],
        'loser_id': loser['id'],
        'winner_name': winner['name'],
        'loser_name': loser['name'],
        'evolved': evolved,
        'winner_pokemon': winner_pokemon['name'],
        'loser_pokemon': loser_pokemon['name'],
        'pluspower_used': bool(winner_pokemon.get('pluspower_applied') or loser_pokemon.get('pluspower_applied')),
        'knocked_out_pokemon': loser_pokemon['name'],
        'returned_to_tile_id': return_data.get('returned_to_tile_id'),
        'returned_to_tile_name': return_data.get('returned_to_tile_name'),
        'stayed_on_safe_tile': return_data.get('stayed_on_safe_tile', False),
        'recovery_pending': return_data.get('recovery_pending', False),
    }

    if battle_source == _DEBUG_SHARED_BATTLE_SOURCE:
        state = _restore_debug_shared_battle_state(state)
        return state, battle_result

    if state['turn'].get('phase') != 'battle' and not (return_data.get('recovery_pending') or return_data.get('turn_ended')):
        state = end_turn(state)
    return state, battle_result


def _try_evolve(state: dict, player_id: str, pokemon: dict, *, heal_on_evolve: bool = False) -> dict | None:
    """Tenta evoluir um Pokémon, atualizando a coleção do jogador."""
    evolves_to_name = pokemon.get('evolves_to')
    if not evolves_to_name:
        return None

    evolved = load_pokemon_by_name(evolves_to_name)
    if not evolved:
        return None

    player = _get_player(state, player_id)
    supported_evolution, support = ensure_supported_inventory_pokemon(evolved)
    if not supported_evolution:
        if player:
            _log_unsupported_pokemon(state, player['name'], support, f"evolução de {pokemon.get('name', '?')}")
        return None
    evolved = supported_evolution
    # Verifica se é o starter
    slot_key = pokemon.get('battle_slot_key')
    if slot_key:
        slot_target = _get_player_pokemon_slot(player, slot_key)
        if slot_target is not None:
            evolved_copy = copy.deepcopy(evolved)
            evolved_copy['knocked_out'] = False if heal_on_evolve else pokemon.get('knocked_out', False)
            _copy_pokemon_acquisition_metadata(slot_target, evolved_copy)
            if slot_key == 'starter':
                player['starter_pokemon'] = evolved_copy
                sync_player_inventory(player)
                return evolved
            else:
                try:
                    index = int(slot_key.split(':', 1)[1])
                except (TypeError, ValueError):
                    index = None
                if index is not None and 0 <= index < len(player.get('pokemon', [])):
                    player['pokemon'][index] = evolved_copy
                    sync_player_inventory(player)
                    return evolved

    starter = player.get('starter_pokemon') if player else None
    if isinstance(starter, dict) and starter.get('id') == pokemon['id']:
        evolved_copy = copy.deepcopy(evolved)
        evolved_copy['knocked_out'] = False if heal_on_evolve else pokemon.get('knocked_out', False)
        _copy_pokemon_acquisition_metadata(starter, evolved_copy)
        player['starter_pokemon'] = evolved_copy
        sync_player_inventory(player)
        return evolved

    # Verifica na coleção
    for i, p in enumerate(player['pokemon']):
        if p['id'] == pokemon['id']:
            evolved_copy = copy.deepcopy(evolved)
            evolved_copy['knocked_out'] = False if heal_on_evolve else pokemon.get('knocked_out', False)
            _copy_pokemon_acquisition_metadata(p, evolved_copy)
            player['pokemon'][i] = evolved_copy
            sync_player_inventory(player)
            return evolved

    return None


# ── Remoção de jogador ───────────────────────────────────────────────────────

def remove_player(state: dict, player_id: str) -> dict:
    """
    Remove/desativa um jogador da partida.
    Se era o jogador atual, avança o turno.
    """
    state = copy.deepcopy(state)
    player = _get_player(state, player_id)
    if not player:
        return state

    player['is_active'] = False
    _log(state, player['name'], 'Saiu da partida')

    # Se era o jogador atual, avança o turno
    if state.get('turn', {}).get('current_player_id') == player_id:
        state = end_turn(state)

    # Transfere host se necessário
    if player.get('is_host'):
        active = _get_active_players(state)
        if active:
            active[0]['is_host'] = True

    # Verifica se o jogo deve terminar (apenas 1 ou 0 ativos)
    active = _get_active_players(state)
    if len(active) <= 1 and state.get('status') == 'playing':
        state = _finish_game(state)

    return state


def use_item(
    state: dict,
    player_id: str,
    item_key: str,
    *,
    pokemon_index: int | None = None,
    pokemon_slot_key: str | None = None,
    target_pokemon_index: int | None = None,
) -> tuple[dict | None, str | dict]:
    state = copy.deepcopy(state)
    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'
    if get_item_quantity(player, item_key) <= 0:
        return None, 'Item indisponível no inventário'

    turn = state['turn']
    item_def = get_item_def(item_key)

    if item_key in ('bill', 'prof_oak'):
        if turn.get('phase') != 'roll':
            return None, 'Este item só pode ser usado na fase de rolagem'
        if turn.get('current_player_id') != player_id:
            return None, 'Não é seu turno'
        current_modifier = turn.get('roll_item_modifier') or {}
        if current_modifier.get('player_id') == player_id:
            return None, 'Você já aplicou um modificador de dado nesta rolagem'

        amount = 2 if item_key == 'bill' else -1
        remove_item(player, item_key, 1)
        turn['roll_item_modifier'] = {
            'player_id': player_id,
            'item_key': item_key,
            'amount': amount,
        }
        _log(state, player['name'], f"Usou {item_def.get('name', item_key)} para modificar a próxima rolagem")
        return state, {'item_key': item_key, 'phase': 'roll', 'amount': amount}

    if item_key == 'miracle_stone':
        if turn.get('phase') == 'battle':
            return None, 'Miracle Stone não pode ser usado durante batalha'

        pool = list(player.get('pokemon', []))
        if player.get('starter_pokemon'):
            pool.append(player['starter_pokemon'])
        if not pool:
            return None, 'Você não possui Pokémon para evoluir'
        if pokemon_index is None:
            return None, 'Escolha um Pokémon para evoluir'

        pokemon_index = max(0, min(int(pokemon_index), len(pool) - 1))
        chosen = pool[pokemon_index]
        if not _can_use_miracle_stone_on_pokemon(chosen):
            return None, 'Este Pokémon não pode evoluir com Miracle Stone'

        evolved = _try_evolve(state, player_id, chosen)
        if not evolved:
            return None, 'Não foi possível evoluir este Pokémon com os dados atuais'

        remove_item(player, item_key, 1)
        sync_player_inventory(player)
        _log(state, player['name'], f"Usou Miracle Stone em {chosen['name']} e evoluiu para {evolved['name']}")
        return state, {'item_key': item_key, 'pokemon': chosen['name'], 'evolved_to': evolved['name']}

    if item_key == 'gust_of_wind':
        battle = turn.get('battle') or {}
        if turn.get('phase') != 'battle':
            return None, 'Gust of Wind só pode ser usado durante batalha'
        if player_id not in (battle.get('challenger_id'), battle.get('defender_id')):
            return None, 'Você não está nesta batalha'
        if target_pokemon_index is None:
            return None, 'Escolha qual Pokémon do oponente deverá lutar'

        if battle.get('mode') in ('gym', 'league'):
            if player_id != battle.get('challenger_id'):
                return None, 'Somente o desafiante pode usar Gust of Wind no ginásio/liga'
            team = battle.get('leader_team') or []
            defeated_indexes = set(battle.get('defeated_leader_indexes') or [])
            if not team:
                return None, 'O líder não possui Pokémon disponíveis'
            if battle.get('sub_phase') != 'choosing':
                return None, 'Gust of Wind só pode ser usado antes da rolagem do round'

            target_pokemon_index = max(0, min(int(target_pokemon_index), len(team) - 1))
            if target_pokemon_index in defeated_indexes:
                return None, 'Este Pokémon do líder já foi derrotado'

            forced_choice = copy.deepcopy(team[target_pokemon_index])
            battle['leader_current_index'] = target_pokemon_index
            battle['defender_choice'] = forced_choice
            remove_item(player, item_key, 1)
            sync_player_inventory(player)
            _log(state, player['name'], f"Usou Gust of Wind e forçou {battle.get('defender_name', 'o líder')} a enviar {forced_choice['name']}")
            return state, {
                'item_key': item_key,
                'forced_pokemon': forced_choice['name'],
                'target_gym_index': target_pokemon_index,
            }

        if battle.get('challenger_id') == player_id:
            opponent_id = battle.get('defender_id')
            choice_key = 'defender_choice'
        else:
            opponent_id = battle.get('challenger_id')
            choice_key = 'challenger_choice'

        if battle.get(choice_key):
            return None, 'O Pokémon do oponente já foi definido para esta batalha'

        opponent = _get_player(state, opponent_id)
        opponent_pool = list(opponent.get('pokemon', []))
        if opponent.get('starter_pokemon'):
            opponent_pool.append(opponent['starter_pokemon'])
        if not opponent_pool:
            return None, 'O oponente não possui Pokémon disponíveis'

        target_pokemon_index = max(0, min(int(target_pokemon_index), len(opponent_pool) - 1))
        forced_choice = copy.deepcopy(opponent_pool[target_pokemon_index])
        battle[choice_key] = forced_choice
        remove_item(player, item_key, 1)
        sync_player_inventory(player)
        _log(state, player['name'], f"Usou Gust of Wind e forçou {opponent['name']} a lutar com {forced_choice['name']}")

        if battle.get('challenger_choice') and battle.get('defender_choice'):
            return _resolve_duel(state)

        return state, {'item_key': item_key, 'forced_pokemon': forced_choice['name'], 'target_player_id': opponent_id}

    if item_key == 'pluspower':
        battle = turn.get('battle') or {}
        if turn.get('phase') != 'battle':
            return None, 'PlusPower só pode ser usado no início de uma batalha'
        if player_id not in (battle.get('challenger_id'), battle.get('defender_id')):
            return None, 'Você não está nesta batalha'
        if pokemon_index is None and not (pokemon_slot_key or '').strip():
            return None, 'Escolha qual Pokémon seu receberá o bônus'

        choice_key = 'challenger_choice' if battle.get('challenger_id') == player_id else 'defender_choice'
        if battle.get(choice_key):
            return None, 'PlusPower só pode ser usado antes de confirmar seu Pokémon na batalha'

        pool = _build_player_battle_pool(player, include_knocked_out=False)
        chosen, resolved_index = _resolve_battle_pool_choice(
            pool,
            pokemon_index=pokemon_index,
            pokemon_slot_key=pokemon_slot_key,
        )
        if not chosen:
            return None, 'Pokémon inválido'

        remove_item(player, item_key, 1)
        battle['pluspower_pending'] = {
            'player_id': player_id,
            'pokemon_index': int(resolved_index),
            'pokemon_slot_key': chosen.get('battle_slot_key'),
        }
        sync_player_inventory(player)
        _log(state, player['name'], 'Usou PlusPower para preparar +2 BP na batalha')
        return state, {
            'item_key': item_key,
            'pokemon_index': int(resolved_index),
            'pokemon_slot_key': chosen.get('battle_slot_key'),
            'battle_bonus': 2,
        }

    if item_key == 'defender':
        battle = turn.get('battle') or {}
        if turn.get('phase') != 'battle':
            return None, 'Defender só pode ser usado durante batalha'
        if player_id not in (battle.get('challenger_id'), battle.get('defender_id')):
            return None, 'Você não está nesta batalha'
        if battle.get('sub_phase') != 'choosing':
            return None, 'Defender só pode ser usado antes de confirmar seu Pokémon na batalha'

        choice_key = 'challenger_choice' if battle.get('challenger_id') == player_id else 'defender_choice'
        if battle.get(choice_key):
            return None, 'Defender só pode ser usado antes de confirmar seu Pokémon na batalha'

        if battle.get('defender_pending'):
            return None, 'Defender já está ativo nesta batalha'

        remove_item(player, item_key, 1)
        battle['defender_pending'] = {'player_id': player_id}
        sync_player_inventory(player)
        _log(state, player['name'], 'Usou Defender: -2 BP no Pokémon adversário nesta batalha')
        return state, {'item_key': item_key, 'battle_bonus': -2}

    if item_key == 'full_restore':
        if turn.get('phase') == 'battle':
            return None, 'Full Restore não pode ser usado durante batalha'
        if turn.get('current_player_id') != player_id:
            return None, 'Use Full Restore no seu turno'

        pool = _build_player_battle_pool(player, include_knocked_out=True)
        knocked_out_pool = [pokemon for pokemon in pool if pokemon.get('knocked_out')]
        if not knocked_out_pool:
            return None, 'Você não possui Pokémon nocauteados para curar'
        if pokemon_index is None:
            return None, 'Escolha um Pokémon nocauteado para curar'

        pokemon_index = max(0, min(int(pokemon_index), len(pool) - 1))
        chosen = pool[pokemon_index]
        if not chosen.get('knocked_out'):
            return None, 'Este Pokémon não está nocauteado'

        if not remove_item(player, item_key, 1):
            return None, 'Item indisponível no inventário'
        healed_slots = _heal_player_pokemon_slots(player, [chosen.get('battle_slot_key')])
        sync_player_inventory(player)
        if not healed_slots:
            return None, 'Não foi possível curar este Pokémon'

        _log(state, player['name'], f"Usou Full Restore em {chosen['name']} e removeu o nocaute.")
        return state, {
            'item_key': item_key,
            'pokemon': chosen['name'],
            'healed_slots': healed_slots,
            'cleared_knockout': True,
        }

    if item_key == 'master_points_nugget':
        return None, 'Master Points Nugget permanece sem efeito implementado por falta de regra operacional explícita'

    return None, 'Item sem implementação segura no estado atual'


def consume_roll_modifier(state: dict, player_id: str, base_roll: int) -> tuple[dict, int, dict | None]:
    state, resolved = apply_movement_roll_modifiers(state, player_id, base_roll)
    return state, resolved['final_result'], resolved.get('modifier')


def debug_add_item(state: dict, player_id: str, item_key: str, quantity: int) -> tuple[dict | None, str | dict]:
    state = copy.deepcopy(state)
    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'

    quantity = max(1, int(quantity or 1))
    item_def = get_item_def(item_key)
    if not item_def:
        return None, 'Item de debug desconhecido'

    add_item(player, item_key, quantity)
    _queue_item_choice(state, player_id, 'Debug adicionou item ao inventário')
    _log(state, player['name'], f"[DEBUG] Recebeu {quantity}x {item_def.get('name', item_key)}")
    return state, {'item_key': item_key, 'quantity': quantity, 'debug_catalog': list_debug_item_defs()}


def debug_add_item_to_host(state: dict, player_id: str, item_key: str, quantity: int) -> tuple[dict | None, str | dict]:
    error = _require_host_tools_enabled(state)
    if error:
        return None, error
    return debug_add_item(state, player_id, item_key, quantity)


def debug_add_pokemon_to_host(state: dict, player_id: str, pokemon_name: str) -> tuple[dict | None, str | dict]:
    state = copy.deepcopy(state)
    error = _require_host_tools_enabled(state)
    if error:
        return None, error

    player = _get_player(state, player_id)
    if not player:
        return None, 'Jogador não encontrado'

    return _apply_debug_pokemon_grant(state, player, pokemon_name, log_prefix=_HOST_TOOLS_LOG_PREFIX)


def debug_add_pokemon_to_test_player(state: dict, pokemon_name: str) -> tuple[dict | None, str | dict]:
    state = copy.deepcopy(state)
    session = _get_debug_visual_session(state)
    if not session:
        return None, 'Player de teste do debug não está habilitado'

    player = _get_player(session, _DEBUG_TEST_PLAYER_ID)
    if not player:
        return None, 'Player de teste do debug não encontrado'

    result_state, result = _apply_debug_pokemon_grant(session, player, pokemon_name, log_prefix='[DEBUG]')
    if result_state is None:
        return None, result
    _store_debug_visual_session(state, session, enabled=True)
    return state, result


def set_debug_test_player_enabled(state: dict, enabled: bool) -> tuple[dict | None, str | dict]:
    state = copy.deepcopy(state)
    if not enabled:
        if (state.get('turn', {}).get('battle') or {}).get('source') == _DEBUG_SHARED_BATTLE_SOURCE:
            state = _restore_debug_shared_battle_state(state)
        else:
            state = _set_debug_shared_battle_resume_state(state, None)
        _store_debug_visual_session(state, None, enabled=False)
        return state, {'enabled': False}

    session, error = _build_debug_visual_session()
    if session is None:
        return None, error

    _store_debug_visual_session(state, session, enabled=True)
    _set_debug_shared_battle_resume_state(state, None)
    return state, {
        'enabled': True,
        'player_id': _DEBUG_TEST_PLAYER_ID,
        'player_name': _DEBUG_TEST_PLAYER_NAME,
    }


def move_debug_test_player(state: dict, steps: int) -> tuple[dict | None, str | dict]:
    state = copy.deepcopy(state)
    session = _get_debug_visual_session(state)
    if not session:
        return None, 'Player de teste do debug não está habilitado'
    if int(steps or 0) <= 0:
        return None, 'O movimento do player de teste exige um inteiro positivo'

    session = _reset_debug_visual_session_for_free_actions(session)
    player = _get_player(session, _DEBUG_TEST_PLAYER_ID)
    if not player:
        return None, 'Player de teste do debug não encontrado'

    new_position = calculate_new_position(player.get('position', 0), int(steps), session.get('board', {}))
    player['position'] = new_position
    tile = get_tile(session.get('board', {}), new_position)
    session['turn']['dice_result'] = int(steps)
    session['turn']['current_tile'] = tile
    _record_roll(
        session,
        roll_type='movimento',
        player_id=player['id'],
        player_name=player['name'],
        raw_result=int(steps),
        final_result=int(steps),
        context='debug_manual_move',
    )
    _log(session, player['name'], f"[DEBUG] Moveu {int(steps)} casa(s) para {tile.get('name', '?')}")

    _store_debug_visual_session(state, session, enabled=True)
    return state, {
        'success': True,
        'steps': int(steps),
        'position': new_position,
        'tile_id': tile.get('id'),
        'tile_name': tile.get('name'),
    }


def roll_debug_test_player(state: dict) -> tuple[dict | None, str | dict]:
    state = copy.deepcopy(state)
    session = _get_debug_visual_session(state)
    if not session:
        return None, 'Player de teste do debug não está habilitado'

    session = _reset_debug_visual_session_for_free_actions(session)
    player = _get_player(session, _DEBUG_TEST_PLAYER_ID)
    if not player:
        return None, 'Player de teste do debug não encontrado'

    old_position = player.get('position', 0)
    old_name = player['name']
    session, roll_entry = perform_movement_roll(session, player['id'])
    if (session.get('turn', {}).get('pending_action') or {}).get('type') == 'ability_decision':
        _store_debug_visual_session(state, session, enabled=True)
        return state, {
            'success': True,
            'roll': int(roll_entry['final_result']),
            'raw_roll': int(roll_entry['raw_result']),
            'requires_pending_action': True,
        }

    player = _get_player(session, _DEBUG_TEST_PLAYER_ID)
    new_position = calculate_new_position(old_position, int(roll_entry['final_result']), session.get('board', {}))
    player['position'] = new_position
    tile = get_tile(session.get('board', {}), new_position)
    session['turn']['dice_result'] = int(roll_entry['final_result'])
    session['turn']['current_tile'] = tile
    _log(session, old_name, f"[DEBUG] Rolou {int(roll_entry['final_result'])} e foi para {tile.get('name', '?')}")

    _store_debug_visual_session(state, session, enabled=True)
    return state, {
        'success': True,
        'roll': int(roll_entry['final_result']),
        'raw_roll': int(roll_entry['raw_result']),
        'position': new_position,
        'tile_id': tile.get('id'),
        'tile_name': tile.get('name'),
    }


def trigger_debug_test_player_tile(state: dict) -> tuple[dict | None, str | dict]:
    state = copy.deepcopy(state)
    session = _get_debug_visual_session(state)
    if not session:
        return None, 'Player de teste do debug não está habilitado'

    new_session, result = trigger_current_tile_effect(session, _DEBUG_TEST_PLAYER_ID, source='debug_test_player')
    if new_session is None:
        return None, result

    _store_debug_visual_session(state, new_session, enabled=True)
    return state, result


def debug_roll_capture_for_test_player(state: dict, use_full_restore: bool = False) -> tuple[dict | None, str | dict]:
    """Rola dado de captura para o player de teste, usando a mesma lógica dos jogadores reais."""
    state = copy.deepcopy(state)
    session = _get_debug_visual_session(state)
    if not session:
        return None, 'Player de teste do debug não está habilitado'

    new_session, result = roll_capture_attempt(session, _DEBUG_TEST_PLAYER_ID, use_full_restore=use_full_restore)
    if new_session is None:
        return None, result

    _store_debug_visual_session(state, new_session, enabled=True)
    return state, result


def debug_resolve_event_for_test_player(state: dict, use_run_away: bool = False) -> tuple[dict | None, str | dict]:
    """Resolve evento pendente para o player de teste, usando a mesma lógica dos jogadores reais."""
    state = copy.deepcopy(state)
    session = _get_debug_visual_session(state)
    if not session:
        return None, 'Player de teste do debug não está habilitado'

    new_session, result = resolve_event(session, _DEBUG_TEST_PLAYER_ID, use_run_away=use_run_away)
    if new_session is None:
        return None, result

    _store_debug_visual_session(state, new_session, enabled=True)
    return state, result


def debug_skip_test_player_pending(state: dict) -> tuple[dict | None, str | dict]:
    """Descarta qualquer estado pendente do player de teste e retorna à fase de rolagem."""
    state = copy.deepcopy(state)
    session = _get_debug_visual_session(state)
    if not session:
        return None, 'Player de teste do debug não está habilitado'

    if (state.get('turn', {}).get('battle') or {}).get('source') == _DEBUG_SHARED_BATTLE_SOURCE:
        state = _restore_debug_shared_battle_state(state)
        session = _get_debug_visual_session(state) or session
    else:
        state = _set_debug_shared_battle_resume_state(state, None)

    session = _reset_debug_visual_session_for_free_actions(session)
    player = _get_player(session, _DEBUG_TEST_PLAYER_ID)
    if player:
        _log(session, player['name'], '[DEBUG] Ação pendente descartada.')
    _store_debug_visual_session(state, session, enabled=True)
    return state, {'success': True}


def debug_start_duel_with_player(state: dict, target_player_id: str) -> tuple[dict | None, str | dict]:
    """
    Inicia um duelo compartilhado usando o pipeline real de batalha.
    O player de teste continua isolado em debug_visual, mas participa do
    state['turn']['battle'] principal para que o jogador real desafiado receba a UI normal.
    """
    state = copy.deepcopy(state)
    session = _get_debug_visual_session(state)
    if not session:
        return None, 'Player de teste do debug não está habilitado'

    turn = session.get('turn', {})
    if turn.get('phase') != 'action' or turn.get('capture_context') != 'duel':
        return None, 'Player de teste não está em tile de duelo'
    if state.get('turn', {}).get('battle'):
        return None, 'Já existe uma batalha ativa no jogo principal'

    real_player = next((player for player in state.get('players', []) if player.get('id') == target_player_id), None)
    if not real_player:
        return None, f'Jogador {target_player_id} não encontrado'
    if not real_player.get('is_active'):
        return None, 'Jogador inativo'

    # Verifica que o oponente tem pokemon para duelar
    opponent_pool = list(real_player.get('pokemon', []))
    if real_player.get('starter_pokemon'):
        opponent_pool.append(real_player['starter_pokemon'])
    if not opponent_pool:
        return None, f'{real_player["name"]} não tem Pokémon disponíveis para duelar'

    snapshot = _snapshot_debug_shared_battle_state(state)
    new_state = start_duel(state, _DEBUG_TEST_PLAYER_ID, target_player_id)
    if new_state is None:
        return None, 'Não foi possível iniciar o duelo (verifique se ambos têm Pokémon)'

    battle = new_state.get('turn', {}).get('battle') or {}
    battle['source'] = _DEBUG_SHARED_BATTLE_SOURCE

    session = _reset_debug_visual_session_for_free_actions(_get_debug_visual_session(new_state) or session)
    _store_debug_visual_session(new_state, session, enabled=True)
    _set_debug_shared_battle_resume_state(new_state, snapshot)
    return new_state, {
        'success': True,
        'opponent_name': real_player['name'],
        'challenger_id': _DEBUG_TEST_PLAYER_ID,
        'defender_id': target_player_id,
    }


def debug_duel_choose_pokemon(
    state: dict,
    pokemon_index: int | None = None,
    pokemon_slot_key: str | None = None,
) -> tuple[dict | None, str | dict]:
    """
    Registra a escolha de Pokémon do player de teste no duelo compartilhado.
    """
    state = copy.deepcopy(state)
    session = _get_debug_visual_session(state)
    if not session:
        return None, 'Player de teste do debug não está habilitado'

    shared_battle = state.get('turn', {}).get('battle') or {}
    if shared_battle.get('challenger_id') == _DEBUG_TEST_PLAYER_ID:
        if shared_battle.get('mode') != 'player':
            return None, 'Sem duelo compartilhado ativo do player de teste'
        if shared_battle.get('sub_phase') != 'choosing':
            return None, 'Duelo não está na fase de escolha'

        new_state, err = register_battle_choice(
            state,
            _DEBUG_TEST_PLAYER_ID,
            pokemon_index,
            pokemon_slot_key=pokemon_slot_key,
        )
        if err and err.get('error'):
            return None, err['error']
        return new_state, err or {'success': True}

    battle = session.get('turn', {}).get('battle') or {}
    if not battle or battle.get('challenger_id') != _DEBUG_TEST_PLAYER_ID:
        return None, 'Sem batalha ativa do player de teste'
    if battle.get('sub_phase') != 'choosing':
        return None, 'Batalha não está na fase de escolha'

    new_session, err = register_battle_choice(
        session,
        _DEBUG_TEST_PLAYER_ID,
        pokemon_index,
        pokemon_slot_key=pokemon_slot_key,
    )
    if err and err.get('error'):
        return None, err['error']

    _store_debug_visual_session(state, new_session, enabled=True)
    return state, err or {'success': True, 'mode': battle.get('mode')}


def debug_duel_roll_battle(state: dict) -> tuple[dict | None, str | dict]:
    """
    Rola o dado de batalha do player de teste no duelo compartilhado.
    O lado real continua usando o mesmo fluxo padrão de batalha.
    """
    state = copy.deepcopy(state)
    session = _get_debug_visual_session(state)
    if not session:
        return None, 'Player de teste do debug não está habilitado'

    shared_battle = state.get('turn', {}).get('battle') or {}
    if shared_battle.get('challenger_id') == _DEBUG_TEST_PLAYER_ID:
        if shared_battle.get('sub_phase') != 'rolling':
            return None, 'Duelo não está na fase de rolagem'

        new_state, result = register_battle_roll(state, _DEBUG_TEST_PLAYER_ID)
        if result and result.get('error'):
            return None, result['error']
        return new_state, result or {'success': True}

    battle = session.get('turn', {}).get('battle') or {}
    if not battle or battle.get('challenger_id') != _DEBUG_TEST_PLAYER_ID:
        return None, 'Sem batalha ativa do player de teste'
    if battle.get('sub_phase') != 'rolling':
        return None, 'Batalha não está na fase de rolagem'

    new_session, result = register_battle_roll(session, _DEBUG_TEST_PLAYER_ID)
    if result and result.get('error'):
        return None, result['error']

    _store_debug_visual_session(state, new_session, enabled=True)
    return state, result or {'success': True, 'mode': battle.get('mode')}


def debug_resolve_pending_action_for_test_player(state: dict, option_id: str) -> tuple[dict | None, str | dict]:
    state = copy.deepcopy(state)
    session = _get_debug_visual_session(state)
    if not session:
        return None, 'Player de teste do debug não está habilitado'

    new_session, result = resolve_pending_action(session, _DEBUG_TEST_PLAYER_ID, option_id)
    if new_session is None:
        return None, result

    _store_debug_visual_session(state, new_session, enabled=True)
    return state, result


def dismiss_revealed_card(state: dict, player_id: str) -> tuple[dict | None, str]:
    state = copy.deepcopy(state)
    revealed = state.get('revealed_card')
    if not revealed:
        return None, 'Nenhuma carta revelada'
    clear_revealed_card(state)
    return state, 'ok'


# ── Controle de turno ────────────────────────────────────────────────────────

def end_turn(state: dict) -> dict:
    """
    Encerra o turno atual e prepara o próximo.
    Verifica turno extra, atualiza jogador atual.
    """
    state = copy.deepcopy(state)
    state = _clear_host_tools_pending_tile(state)
    turn = state['turn']
    current_player = _get_player(state, turn.get('current_player_id'))
    if current_player:
        reset_player_ability_runtime(current_player, 'turn')
        sync_player_inventory(current_player)

    # Turno extra (ex: carta de evento)
    if turn.get('extra_turn'):
        extra_turn_source = turn.get('extra_turn_source')
        extra_turn_tile_id = turn.get('extra_turn_tile_id')
        turn['extra_turn'] = False
        turn['phase'] = 'roll'
        turn['dice_result'] = None
        turn['current_tile'] = None
        turn['pending_action'] = None
        turn['pending_event'] = None
        turn['pending_pokemon'] = None
        turn['pending_item_choice'] = None
        turn['pending_release_choice'] = None
        turn['pending_reward_choice'] = None
        turn['pending_safari'] = None
        turn['battle'] = None
        turn['capture_context'] = None
        turn.pop('encounter_rolls', None)
        turn.pop('encounter_source', None)
        turn['roll_item_modifier'] = None
        turn['pending_effects'] = []
        turn.pop('movement_context', None)
        turn.pop('battle_result', None)
        turn.pop('league_results', None)
        turn.pop('compound_eyes_active', None)
        turn.pop('seafoam_legendary', None)
        turn.pop('extra_turn_source', None)
        turn.pop('extra_turn_tile_id', None)
        if extra_turn_source == 'teleporter':
            tile = get_tile(state.get('board', {}), int(extra_turn_tile_id)) if extra_turn_tile_id is not None else None
            player_id = turn.get('current_player_id')
            if player_id:
                state = _queue_teleporter_manual_roll_action(state, player_id, source_tile=tile)
        return state

    active_ids = _ordered_active_player_ids(state)
    current_id = turn.get('current_player_id')
    next_id = _next_player_id(state)
    visited = 0
    while next_id and visited < max(1, len(active_ids)):
        next_player = _get_player(state, next_id)
        if not next_player or int(next_player.get('skip_turns', 0) or 0) <= 0:
            break
        next_player['skip_turns'] = max(0, int(next_player.get('skip_turns', 0)) - 1)
        _log(state, next_player['name'], 'Perdeu este turno por efeito de carta.')
        turn['current_player_id'] = next_id
        visited += 1
        next_id = _next_player_id(state)

    if not next_id and active_ids:
        next_id = active_ids[0]

    # Incrementa round ao voltar ao primeiro jogador
    if active_ids and current_id and next_id == active_ids[0]:
        turn['round'] = turn.get('round', 1) + 1

    turn['current_player_id'] = next_id
    turn['phase'] = 'roll'
    turn['dice_result'] = None
    turn['current_tile'] = None
    turn['pending_action'] = None
    turn['pending_event'] = None
    turn['pending_pokemon'] = None
    turn['pending_item_choice'] = None
    turn['pending_release_choice'] = None
    turn['pending_reward_choice'] = None
    turn['pending_safari'] = None
    turn['pending_effects'] = []
    turn['battle'] = None
    turn['capture_context'] = None
    turn.pop('encounter_rolls', None)
    turn.pop('encounter_source', None)
    turn['roll_item_modifier'] = None
    turn.pop('battle_result', None)
    turn.pop('league_results', None)
    turn.pop('compound_eyes_active', None)
    turn.pop('seafoam_legendary', None)
    turn.pop('movement_context', None)
    turn.pop('extra_turn_source', None)
    turn.pop('extra_turn_tile_id', None)

    current_player = _get_player(state, next_id)
    if current_player:
        if not _activate_deferred_pokecenter_heal_for_current_player(state):
            if not turn.get('pending_action'):
                _queue_abra_transfer_offer_if_pending(state, next_id)
            if not turn.get('pending_action'):
                _log(state, current_player['name'], 'Turno iniciado — role o dado!')

    return state
