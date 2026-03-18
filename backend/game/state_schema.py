import copy
from datetime import datetime, timezone
from typing import Any
from .engine.cards import canonicalize_runtime_pokemon
from .engine.inventory import get_starting_resource_defaults, sync_player_inventory, normalize_items

STATE_SCHEMA_VERSION = 1
MAX_LOGS = 200



def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_player_pokemon_metadata(player: dict[str, Any]) -> None:
    starter = player.get('starter_pokemon')
    if isinstance(starter, dict):
        canonical_starter = canonicalize_runtime_pokemon(starter)
        if canonical_starter:
            runtime_fields = {
                key: copy.deepcopy(value)
                for key, value in starter.items()
                if key in {
                    'ability_charges',
                    'ability_used',
                    'knocked_out',
                    'acquisition_origin',
                    'capture_sequence',
                    'capture_context',
                }
            }
            starter = {**canonical_starter, **runtime_fields}
            player['starter_pokemon'] = starter
        starter.setdefault('knocked_out', False)
        starter['acquisition_origin'] = 'starter'
        starter['capture_sequence'] = None
        starter.setdefault('capture_context', None)

    highest_sequence = 0
    normalized_team = []
    for pokemon in player.get('pokemon', []):
        if not isinstance(pokemon, dict):
            continue
        canonical = canonicalize_runtime_pokemon(pokemon)
        if canonical:
            runtime_fields = {
                key: copy.deepcopy(value)
                for key, value in pokemon.items()
                if key in {
                    'ability_charges',
                    'ability_used',
                    'knocked_out',
                    'acquisition_origin',
                    'capture_sequence',
                    'capture_context',
                }
            }
            pokemon = {**canonical, **runtime_fields}
        normalized_team.append(pokemon)
        pokemon.setdefault('knocked_out', False)
        if pokemon.get('acquisition_origin') == 'captured':
            try:
                sequence = int(pokemon.get('capture_sequence'))
            except (TypeError, ValueError):
                sequence = None
            if sequence is not None:
                pokemon['capture_sequence'] = sequence
                highest_sequence = max(highest_sequence, sequence)
        elif pokemon.get('capture_sequence') is None:
            pokemon['capture_sequence'] = None
        pokemon.setdefault('capture_context', None)
    player['pokemon'] = normalized_team

    for pokemon in player.get('pokemon', []):
        if not isinstance(pokemon, dict):
            continue
        origin = pokemon.get('acquisition_origin')
        if origin:
            if origin != 'captured' and pokemon.get('capture_sequence') is None:
                pokemon['capture_sequence'] = None
            continue

        # Estados antigos não rastreavam a origem. Como a coleção extra era
        # majoritariamente formada por capturas, migramos pela ordem do time.
        highest_sequence += 1
        pokemon['acquisition_origin'] = 'captured'
        pokemon['capture_sequence'] = highest_sequence

    try:
        current_counter = int(player.get('capture_sequence_counter', 0) or 0)
    except (TypeError, ValueError):
        current_counter = 0
    player['capture_sequence_counter'] = max(current_counter, highest_sequence)



def build_initial_state(room_code: str) -> dict[str, Any]:
    return {
        'schema_version': STATE_SCHEMA_VERSION,
        'room_code': room_code,
        'status': 'waiting',
        'room': {
            'code': room_code,
            'private': True,
            'created_at': _utc_now(),
            'last_saved_at': _utc_now(),
        },
        'players': [],
        'host_player_id': None,
        'active_player_ids': [],
        'inactive_player_ids': [],
        'turn_order': [],
        'turn': {
            'round': 1,
            'current_player_id': None,
            'phase': 'waiting',
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
            'pending_effects': [],
            'starters_chosen': [],
            'extra_turn': False,
        },
        'board': {},
        'decks': {
            'pokemon_deck': [],
            'pokemon_discard': [],
            'event_deck': [],
            'event_discard': [],
            'victory_deck': [],
            'victory_discard': [],
        },
        'consumed': {
            'events': [],
            'pokemon': [],
            'victory': [],
        },
        'custom_rules': {},
        'special_tile_state': {
            'bill_teleport_used_by': None,
            'bicycle_bridge_first_player_id': None,
            'mr_fuji_first_player_id': None,
        },
        'debug_visual': {
            'enabled': False,
            'session_state': None,
        },
        'revealed_card': None,
        'log': [],
        'logs': [],
    }



def _normalize_player(player: dict[str, Any], index: int) -> dict[str, Any]:
    normalized = copy.deepcopy(player)
    starting_defaults = get_starting_resource_defaults()
    normalized.setdefault('id', f'player-{index + 1}')
    normalized.setdefault('name', f'Trainer {index + 1}')
    normalized.setdefault('color', ['red', 'blue', 'green', 'yellow', 'purple'][index % 5])
    normalized.setdefault('is_host', index == 0)
    normalized.setdefault('is_active', True)
    normalized.setdefault('is_connected', False)
    normalized.setdefault('position', 0)
    normalized.setdefault('pokeballs', starting_defaults['pokeballs'])
    normalized.setdefault('full_restores', starting_defaults['full_restores'])
    normalized.setdefault('starter_slot_applied', False)
    normalized.setdefault('starter_pokemon', None)
    normalized.setdefault('pokemon', [])
    normalized.setdefault('capture_sequence_counter', 0)
    _normalize_player_pokemon_metadata(normalized)
    normalized.setdefault('last_pokemon_center', None)
    normalized.setdefault('deferred_pokecenter_heal', None)
    normalized.setdefault('special_tile_flags', {})
    normalized['special_tile_flags'].setdefault('celadon_dept_store_bonus_claimed', False)
    normalized['items'] = normalize_items(normalized.get('items'), normalized.get('full_restores', starting_defaults['full_restores']))
    normalized.setdefault('badges', [])
    normalized.setdefault('master_points', 0)
    normalized.setdefault('gyms_attempted', [])
    normalized.setdefault('gyms_defeated', [])
    normalized.setdefault('has_reached_league', False)
    normalized.setdefault('skip_turns', 0)
    return sync_player_inventory(normalized)



def _normalize_debug_visual(debug_visual: dict[str, Any] | None) -> dict[str, Any]:
    normalized = copy.deepcopy(debug_visual) if isinstance(debug_visual, dict) else {}
    normalized['enabled'] = bool(normalized.get('enabled', False))
    normalized['shared_battle_resume_state'] = (
        copy.deepcopy(normalized.get('shared_battle_resume_state'))
        if isinstance(normalized.get('shared_battle_resume_state'), dict)
        else None
    )

    session_state = normalized.get('session_state')
    if not normalized['enabled'] or not isinstance(session_state, dict):
        normalized['session_state'] = None
        return normalized

    session = copy.deepcopy(session_state)
    session_players = session.get('players') or []
    session['players'] = [_normalize_player(player, index) for index, player in enumerate(session_players[:1])]
    session['status'] = 'playing'
    session.setdefault('board', {})
    session.setdefault('turn_order', [player['id'] for player in session['players'] if player.get('is_active', True)])

    turn = session.get('turn') or {}
    turn.setdefault('round', 1)
    turn.setdefault('current_player_id', session['turn_order'][0] if session['turn_order'] else None)
    turn.setdefault('phase', 'roll')
    turn.setdefault('dice_result', None)
    turn.setdefault('last_roll', None)
    turn.setdefault('roll_history', [])
    turn.setdefault('current_tile', None)
    turn.setdefault('battle', None)
    turn.setdefault('pending_action', None)
    turn.setdefault('pending_event', None)
    turn.setdefault('pending_pokemon', None)
    turn.setdefault('pending_item_choice', None)
    turn.setdefault('pending_release_choice', None)
    turn.setdefault('pending_reward_choice', None)
    turn.setdefault('pending_effects', [])
    turn.setdefault('pending_safari', None)
    turn.setdefault('capture_context', None)
    turn.setdefault('roll_item_modifier', None)
    session['turn'] = turn

    decks = session.get('decks') or {}
    decks.setdefault('pokemon_deck', [])
    decks.setdefault('pokemon_discard', [])
    decks.setdefault('event_deck', [])
    decks.setdefault('event_discard', [])
    decks.setdefault('victory_deck', [])
    decks.setdefault('victory_discard', [])
    session['decks'] = decks

    consumed = session.get('consumed') or {}
    consumed.setdefault('events', [])
    consumed.setdefault('pokemon', [])
    consumed.setdefault('victory', [])
    session['consumed'] = consumed
    special_tile_state = session.get('special_tile_state') or {}
    special_tile_state.setdefault('bill_teleport_used_by', None)
    special_tile_state.setdefault('bicycle_bridge_first_player_id', None)
    special_tile_state.setdefault('mr_fuji_first_player_id', None)
    session['special_tile_state'] = special_tile_state

    logs = session.get('logs') or session.get('log') or []
    session['logs'] = logs[-MAX_LOGS:]
    session['log'] = session['logs']
    session.setdefault('revealed_card', None)

    normalized['session_state'] = session
    return normalized


def normalize_state(room_code: str, raw_state: dict[str, Any] | None) -> dict[str, Any]:
    if not raw_state:
        return build_initial_state(room_code)

    state = copy.deepcopy(raw_state)
    state.setdefault('schema_version', STATE_SCHEMA_VERSION)
    state['room_code'] = room_code
    state.setdefault('status', 'waiting')

    room = state.get('room') or {}
    room.setdefault('code', room_code)
    room.setdefault('private', True)
    room.setdefault('created_at', _utc_now())
    room['last_saved_at'] = _utc_now()
    state['room'] = room

    logs = state.get('logs') or state.get('log') or []
    state['logs'] = logs[-MAX_LOGS:]
    state['log'] = state['logs']

    players = state.get('players') or []
    normalized_players = [_normalize_player(player, index) for index, player in enumerate(players)]
    state['players'] = normalized_players

    host = next((p for p in normalized_players if p.get('is_host')), None)
    if not host and normalized_players:
        normalized_players[0]['is_host'] = True
        host = normalized_players[0]
    state['host_player_id'] = host['id'] if host else None

    active = [p['id'] for p in normalized_players if p.get('is_active', True)]
    inactive = [p['id'] for p in normalized_players if not p.get('is_active', True)]
    state['active_player_ids'] = active
    state['inactive_player_ids'] = inactive

    turn_order = state.get('turn_order') or active
    # Keep existing order, filter out inactive players, then append any newly active ones
    existing = [pid for pid in turn_order if pid in active]
    missing = [pid for pid in active if pid not in existing]
    state['turn_order'] = existing + missing or active

    turn = state.get('turn') or {}
    turn.setdefault('round', 1)
    turn.setdefault('current_player_id', state['turn_order'][0] if state['turn_order'] else None)
    turn.setdefault('phase', 'waiting' if state['status'] == 'waiting' else 'roll')
    turn.setdefault('dice_result', None)
    turn.setdefault('last_roll', None)
    turn.setdefault('roll_history', [])
    turn.setdefault('current_tile', None)
    turn.setdefault('battle', None)
    turn.setdefault('pending_action', None)
    turn.setdefault('pending_event', None)
    turn.setdefault('pending_pokemon', None)
    turn.setdefault('pending_item_choice', None)
    turn.setdefault('pending_release_choice', None)
    turn.setdefault('pending_reward_choice', None)
    turn.setdefault('pending_effects', [])
    turn.setdefault('starters_chosen', [])
    turn.setdefault('extra_turn', False)
    turn.setdefault('roll_item_modifier', None)

    if turn.get('current_player_id') and turn['current_player_id'] not in state['turn_order']:
        turn['current_player_id'] = state['turn_order'][0] if state['turn_order'] else None

    state['turn'] = turn

    decks = state.get('decks') or {}
    decks.setdefault('pokemon_deck', [])
    decks.setdefault('pokemon_discard', [])
    decks.setdefault('event_deck', [])
    decks.setdefault('event_discard', [])
    decks.setdefault('victory_deck', [])
    decks.setdefault('victory_discard', [])
    state['decks'] = decks

    consumed = state.get('consumed') or {}
    consumed.setdefault('events', [])
    consumed.setdefault('pokemon', [])
    consumed.setdefault('victory', [])
    state['consumed'] = consumed

    state.setdefault('custom_rules', {})
    special_tile_state = state.get('special_tile_state') or {}
    special_tile_state.setdefault('bill_teleport_used_by', None)
    special_tile_state.setdefault('bicycle_bridge_first_player_id', None)
    special_tile_state.setdefault('mr_fuji_first_player_id', None)
    state['special_tile_state'] = special_tile_state
    state['debug_visual'] = _normalize_debug_visual(state.get('debug_visual'))
    state.setdefault('board', {})
    state.setdefault('revealed_card', None)

    return state



def mark_saved(state: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(state)
    normalized.setdefault('room', {})
    normalized['room']['last_saved_at'] = _utc_now()
    return normalized
