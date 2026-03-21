"""CPU player decision engine.

Provides deterministic/heuristic decisions for computer-controlled players.
No LLM, no external services — pure rule-based logic.

Public API:
    is_cpu_player(player)        → bool
    get_cpu_player_ids(state)    → list[str]
    needs_cpu_action(state)      → list[str]   # IDs that must act now
    decide_action(state, pid)    → list[tuple[str, dict]]
"""
from __future__ import annotations

__all__ = ['is_cpu_player', 'get_cpu_player_ids', 'needs_cpu_action', 'decide_action']

from .mechanics import calculate_type_bonus

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def is_cpu_player(player: dict) -> bool:
    return bool(player.get('is_cpu', False))


def get_cpu_player_ids(state: dict) -> list[str]:
    return [
        p['id']
        for p in state.get('players', [])
        if p.get('is_active', True) and is_cpu_player(p)
    ]


def needs_cpu_action(state: dict) -> list[str]:
    """Return list of CPU player IDs that need to act right now."""
    if state.get('status') != 'playing':
        return []

    turn = state.get('turn', {})
    phase = turn.get('phase', '')
    current_player_id = turn.get('current_player_id')
    cpu_ids = get_cpu_player_ids(state)

    if not cpu_ids:
        return []

    active: list[str] = []

    # Current player is CPU
    if current_player_id in cpu_ids:
        active.append(current_player_id)

    # Inventory discard may temporarily belong to another CPU (e.g. global effects)
    pending_item_choice = turn.get('pending_item_choice') or {}
    pending_item_player_id = pending_item_choice.get('player_id')
    if pending_item_player_id in cpu_ids and pending_item_player_id not in active:
        active.append(pending_item_player_id)

    pending_action = turn.get('pending_action') or {}
    pending_action_player_id = pending_action.get('player_id')
    if pending_action_player_id in cpu_ids and pending_action_player_id not in active:
        active.append(pending_action_player_id)

    # Battle: both participants may need to act independently
    battle = turn.get('battle')
    if battle and phase == 'battle':
        sub_phase = battle.get('sub_phase', '')
        challenger_id = battle.get('challenger_id')
        defender_id = battle.get('defender_id')
        mode = battle.get('mode', 'player')
        for cpu_id in cpu_ids:
            if cpu_id not in (challenger_id, defender_id):
                continue
            if cpu_id in active:
                continue
            is_challenger = cpu_id == challenger_id
            if sub_phase == 'choosing':
                if is_challenger and battle.get('challenger_choice') is None:
                    active.append(cpu_id)
                elif not is_challenger and mode == 'player' and battle.get('defender_choice') is None:
                    active.append(cpu_id)
            elif sub_phase == 'rolling':
                if is_challenger and battle.get('challenger_roll') is None:
                    active.append(cpu_id)
                elif not is_challenger and mode == 'player' and battle.get('defender_roll') is None:
                    active.append(cpu_id)

    return active


# ---------------------------------------------------------------------------
# Main decision function
# ---------------------------------------------------------------------------

def decide_action(state: dict, cpu_player_id: str) -> list[tuple[str, dict]]:
    """
    Decide the next action for a CPU player.

    Returns a list with ONE (action_name, kwargs) tuple.
    action_name values used by the consumer:
        select_starter, roll_dice, challenge_player, discard_item,
        skip_action, pass_turn,
        resolve_event, roll_capture_dice, battle_choice,
        roll_battle_dice, resolve_pending_action,
        confirm_league_intermission, release_pokemon,
        dismiss_revealed_card, wait
    """
    turn = state.get('turn', {})
    phase = turn.get('phase', '')
    current_player_id = turn.get('current_player_id')

    player = _find_player(state, cpu_player_id)
    if not player or not player.get('is_active', True):
        return [('wait', {})]

    # ── Revealed card ─────────────────────────────────────────────────────
    if turn.get('revealed_card') and current_player_id == cpu_player_id:
        return [('dismiss_revealed_card', {})]

    # ── Battle phase (either participant must act) ────────────────────────
    battle = turn.get('battle')
    if battle and phase == 'battle':
        return _decide_battle(state, cpu_player_id, player, battle)

    # ── Pending inventory discard (may belong to non-current CPU) ─────────
    pending_item_choice = turn.get('pending_item_choice')
    if pending_item_choice and pending_item_choice.get('player_id') == cpu_player_id:
        return _decide_item_discard(player)

    pending_action = turn.get('pending_action')
    if pending_action and pending_action.get('player_id') == cpu_player_id:
        return _decide_pending(cpu_player_id, player, pending_action, turn)

    # ── Only act on own turn for non-battle phases ────────────────────────
    if current_player_id != cpu_player_id:
        return [('wait', {})]

    # ── Pending action ────────────────────────────────────────────────────
    if pending_action:
        return _decide_pending(cpu_player_id, player, pending_action, turn)

    # ── Pending release ───────────────────────────────────────────────────
    if turn.get('pending_release_choice') or phase == 'release_pokemon':
        return _decide_release(player)

    # ── Select starter ────────────────────────────────────────────────────
    if phase == 'select_starter':
        return _decide_select_starter(turn)

    # ── Event ─────────────────────────────────────────────────────────────
    if phase == 'event' or turn.get('pending_event'):
        return [('resolve_event', {'use_run_away': False})]

    # ── Roll ──────────────────────────────────────────────────────────────
    if phase == 'roll':
        return [('roll_dice', {})]

    # ── Action ───────────────────────────────────────────────────────────
    if phase == 'action':
        return _decide_action_phase(state, player, turn)

    # ── Fallback: pass turn if nothing is blocking ─────────────────────
    from .state import turn_has_blocking_interaction
    if not turn_has_blocking_interaction(turn):
        return [('pass_turn', {})]

    return [('wait', {})]


# ---------------------------------------------------------------------------
# Sub-decision helpers
# ---------------------------------------------------------------------------

def _find_player(state: dict, player_id: str) -> dict | None:
    return next((p for p in state.get('players', []) if p['id'] == player_id), None)


def _decide_battle(
    state: dict,
    cpu_player_id: str,
    player: dict,
    battle: dict,
) -> list[tuple[str, dict]]:
    challenger_id = battle.get('challenger_id')
    defender_id = battle.get('defender_id')
    if cpu_player_id not in (challenger_id, defender_id):
        return [('wait', {})]

    sub_phase = battle.get('sub_phase', '')
    is_challenger = cpu_player_id == challenger_id
    mode = battle.get('mode', 'player')

    if sub_phase == 'choosing':
        already_chose = (
            battle.get('challenger_choice') is not None if is_challenger
            else battle.get('defender_choice') is not None
        )
        if already_chose:
            return [('wait', {})]

        if mode == 'player':
            choice_stage = battle.get('choice_stage', 'defender')
            if is_challenger and choice_stage == 'defender':
                return [('wait', {})]
            if not is_challenger and choice_stage == 'challenger':
                return [('wait', {})]

        opponent_choice = (
            battle.get('defender_choice') if is_challenger
            else battle.get('challenger_choice')
        )
        opponent_id = defender_id if is_challenger else challenger_id
        opponent_player = _find_player(state, opponent_id)
        slot_key = _best_slot_key(
            player,
            opponent=opponent_choice,
            opponent_player=opponent_player,
        )
        if slot_key is None:
            return [('wait', {})]
        return [('battle_choice', {'pokemon_slot_key': slot_key, 'pokemon_index': 0})]

    if sub_phase == 'rolling':
        already_rolled = (
            battle.get('challenger_roll') is not None if is_challenger
            else battle.get('defender_roll') is not None
        )
        if already_rolled:
            return [('wait', {})]
        return [('roll_battle_dice', {})]

    return [('wait', {})]


def _decide_pending(
    cpu_player_id: str,
    player: dict,
    pending_action: dict,
    turn: dict,
) -> list[tuple[str, dict]]:
    pa_type = pending_action.get('type', '')
    options = pending_action.get('options', [])

    if pa_type == 'capture_attempt':
        return [('roll_capture_dice', {})]

    if pa_type == 'league_intermission':
        return [('confirm_league_intermission', {})]

    if pa_type == 'trade_proposal':
        decline_opt = next((opt for opt in options if (_opt_id(opt) or '').lower() == 'decline'), None)
        target_opt = _pick_trade_option(pending_action, options)
        if target_opt is None:
            target_opt = decline_opt or (options[0] if options else None)
        if target_opt:
            return [('resolve_pending_action', {'option_id': _opt_id(target_opt)})]
        return [('wait', {})]

    if pa_type in ('ability_decision', 'capture_reroll_decision',
                   'battle_reroll_decision', 'capture_choice_decision'):
        # Skip ability use — avoid complex side-effects
        skip_opt = next(
            (o for o in options if 'skip' in (_opt_id(o) or '').lower()),
            None,
        )
        if skip_opt:
            return [('resolve_pending_action', {'option_id': _opt_id(skip_opt)})]
        if options:
            return [('resolve_pending_action', {'option_id': _opt_id(options[0])})]
        return [('skip_action', {})]

    if pa_type in ('gym_heal', 'pokecenter_heal', 'heal_other_choice'):
        # Always heal before finishing: pick first non-finish option, then finish
        heal_opts = [o for o in options if _opt_id(o) != 'finish']
        if heal_opts:
            return [('resolve_pending_action', {'option_id': _opt_id(heal_opts[0])})]
        # No more pokemon to heal — conclude
        finish_opt = next((o for o in options if _opt_id(o) == 'finish'), None)
        if finish_opt:
            return [('resolve_pending_action', {'option_id': 'finish'})]
        return [('wait', {})]

    if pa_type == 'abra_transfer_offer':
        # Accept the free transfer
        accept_opt = next(
            (o for o in options
             if 'accept' in (_opt_id(o) or '').lower()
             or 'aceitar' in (o.get('label') or '').lower()),
            None,
        )
        target = accept_opt or (options[0] if options else None)
        if target:
            return [('resolve_pending_action', {'option_id': _opt_id(target)})]
        return [('wait', {})]

    if pa_type == 'reward_choice':
        best_id = _pick_best_reward(options)
        if best_id:
            return [('resolve_pending_action', {'option_id': best_id})]
        return [('wait', {})]

    # Generic: pick first option
    if options:
        return [('resolve_pending_action', {'option_id': _opt_id(options[0])})]

    # No options: wait — never skip as it would end the turn abruptly
    return [('wait', {})]


def _decide_release(player: dict) -> list[tuple[str, dict]]:
    """Release the weakest non-starter pokemon."""
    roster = player.get('pokemon_inventory', [])
    non_starters = [p for p in roster if not p.get('is_starter_slot', False)]
    pool = non_starters if non_starters else roster
    if not pool:
        return [('wait', {})]
    weakest = min(pool, key=lambda p: (p.get('battle_points', 0), p.get('master_points', 0)))
    return [('release_pokemon', {'pokemon_slot_key': weakest.get('slot_key')})]


def _decide_item_discard(player: dict) -> list[tuple[str, dict]]:
    item_key = _pick_discard_item_key(player)
    if not item_key:
        return [('wait', {})]
    return [('discard_item', {'item_key': item_key})]


def _decide_select_starter(turn: dict) -> list[tuple[str, dict]]:
    available = turn.get('available_starters', [])
    if not available:
        return [('wait', {})]
    best = max(available, key=lambda s: s.get('battle_points', 0))
    return [('select_starter', {'starter_id': best['id']})]


def _decide_action_phase(state: dict, player: dict, turn: dict) -> list[tuple[str, dict]]:
    # Pokemon encounter
    if turn.get('pending_pokemon'):
        return [('roll_capture_dice', {})]
    # Safari zone queue
    if turn.get('pending_safari'):
        return [('roll_capture_dice', {})]
    if turn.get('capture_context') == 'duel':
        target = _best_duel_target(state, player)
        if target is not None:
            return [('challenge_player', {'target_player_id': target['id']})]
    # Nothing to do: end turn
    return [('pass_turn', {})]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _best_slot_key(
    player: dict,
    *,
    opponent: dict | None = None,
    opponent_player: dict | None = None,
) -> str | None:
    """Return the slot_key of the best available Pokemon for the current matchup."""
    roster = _available_battle_roster(player)
    if not roster:
        return None

    opponent_pool = None
    if opponent is None and opponent_player is not None:
        opponent_pool = _available_battle_roster(opponent_player)

    best = _best_roster_choice(roster, opponent=opponent, opponent_pool=opponent_pool)
    return None if best is None else best.get('slot_key')


def _best_duel_target(state: dict, player: dict) -> dict | None:
    own_roster = _available_battle_roster(player)
    if not own_roster:
        return None

    best_target: dict | None = None
    best_rank: tuple | None = None

    for opponent in state.get('players', []):
        if opponent.get('id') == player.get('id'):
            continue
        if not opponent.get('is_active', True):
            continue
        opponent_roster = _available_battle_roster(opponent)
        if not opponent_roster:
            continue

        projected_defender = _best_roster_choice(opponent_roster, opponent_pool=own_roster)
        if projected_defender is None:
            continue
        projected_attacker = _best_roster_choice(own_roster, opponent=projected_defender)
        if projected_attacker is None:
            continue

        candidate_rank = _pokemon_matchup_rank(projected_attacker, projected_defender)
        if best_rank is None or candidate_rank > best_rank:
            best_rank = candidate_rank
            best_target = opponent

    return best_target


def _available_battle_roster(player: dict) -> list[dict]:
    if not isinstance(player, dict):
        return []

    roster: list[dict] = []

    starter = player.get('starter_pokemon')
    if isinstance(starter, dict):
        roster.append(_normalize_battle_candidate(starter, 'starter'))

    for index, pokemon in enumerate(player.get('pokemon', [])):
        if isinstance(pokemon, dict):
            roster.append(_normalize_battle_candidate(pokemon, f'pokemon:{index}'))

    available = [pokemon for pokemon in roster if not pokemon.get('knocked_out', False)]
    if available or roster:
        return available

    fallback = []
    for pokemon in player.get('pokemon_inventory', []):
        if not isinstance(pokemon, dict):
            continue
        slot_key = pokemon.get('slot_key')
        if not slot_key:
            continue
        fallback.append(_normalize_battle_candidate(pokemon, slot_key))
    return [pokemon for pokemon in fallback if not pokemon.get('knocked_out', False)]


def _normalize_battle_candidate(pokemon: dict, slot_key: str) -> dict:
    candidate = dict(pokemon)
    candidate['slot_key'] = slot_key
    candidate['battle_points'] = int(candidate.get('battle_points', 0) or 0)
    candidate['master_points'] = int(candidate.get('master_points', 0) or 0)
    candidate['types'] = [str(poke_type).title() for poke_type in candidate.get('types', [])]
    candidate['knocked_out'] = bool(candidate.get('knocked_out', False))
    return candidate


def _best_roster_choice(
    roster: list[dict],
    *,
    opponent: dict | None = None,
    opponent_pool: list[dict] | None = None,
) -> dict | None:
    if not roster:
        return None

    if opponent is not None:
        return max(roster, key=lambda pokemon: _pokemon_matchup_rank(pokemon, opponent))

    if opponent_pool:
        return max(roster, key=lambda pokemon: _best_projected_matchup_rank(pokemon, opponent_pool))

    return max(
        roster,
        key=lambda pokemon: (
            int(pokemon.get('battle_points', 0) or 0),
            int(pokemon.get('master_points', 0) or 0),
            str(pokemon.get('name') or ''),
        ),
    )


def _best_projected_matchup_rank(attacker: dict, opponent_pool: list[dict]) -> tuple:
    if not opponent_pool:
        return (
            int(attacker.get('battle_points', 0) or 0),
            int(attacker.get('battle_points', 0) or 0),
            int(attacker.get('master_points', 0) or 0),
            str(attacker.get('name') or ''),
        )
    return max(_pokemon_matchup_rank(attacker, defender) for defender in opponent_pool)


def _pokemon_matchup_rank(attacker: dict, defender: dict) -> tuple:
    attacker_effective_bp = _effective_battle_points(attacker, defender)
    defender_effective_bp = _effective_battle_points(defender, attacker)
    return (
        attacker_effective_bp,
        attacker_effective_bp - defender_effective_bp,
        int(attacker.get('battle_points', 0) or 0),
        int(attacker.get('master_points', 0) or 0),
        str(attacker.get('name') or ''),
    )


def _effective_battle_points(attacker: dict, defender: dict | None = None) -> int:
    battle_points = int(attacker.get('battle_points', 0) or 0)
    if defender is None:
        return battle_points
    return battle_points + calculate_type_bonus(
        [str(poke_type).title() for poke_type in attacker.get('types', [])],
        [str(poke_type).title() for poke_type in defender.get('types', [])],
    )


def _pick_discard_item_key(player: dict) -> str | None:
    items = [
        item
        for item in (player.get('items') or [])
        if isinstance(item, dict) and int(item.get('quantity', 0) or 0) > 0 and item.get('key')
    ]
    if not items:
        return None

    category_priority = {
        'unknown': 0,
        'reward': 1,
        'utility': 2,
        'battle': 3,
        'healing': 4,
        'capture': 5,
    }

    def discard_rank(item: dict) -> tuple:
        key = str(item.get('key') or '')
        category = str(item.get('category') or '')
        implemented = bool(item.get('implemented', False))
        quantity = int(item.get('quantity', 0) or 0)
        return (
            0 if not implemented else 1,
            category_priority.get(category, 6),
            -quantity,
            key,
        )

    return min(items, key=discard_rank).get('key')


def _pick_trade_option(pending_action: dict, options: list[dict]) -> dict | None:
    incoming = pending_action.get('offered_pokemon') or {}
    best_option: dict | None = None
    best_margin: int | None = None
    for option in options:
        option_id = (_opt_id(option) or '').lower()
        if option_id == 'decline':
            continue
        outgoing = option.get('pokemon') or {}
        incoming_value = _trade_value(incoming)
        outgoing_value = _trade_value(outgoing)
        margin = incoming_value - outgoing_value
        if incoming_value + 3 < outgoing_value:
            continue
        if best_margin is None or margin > best_margin:
            best_margin = margin
            best_option = option
    return best_option


def _trade_value(pokemon: dict | None) -> int:
    if not isinstance(pokemon, dict):
        return -999
    battle_points = int(pokemon.get('battle_points', 0) or 0)
    master_points = int(pokemon.get('master_points', 0) or 0)
    type_count = len(pokemon.get('types') or [])
    knocked_out_penalty = 12 if pokemon.get('knocked_out') else 0
    return (battle_points * 10) + master_points + (type_count * 2) - knocked_out_penalty


def _opt_id(opt: dict) -> str | None:
    return opt.get('id') or opt.get('value')


def _pick_best_reward(options: list[dict]) -> str | None:
    """Heuristically pick the best reward option."""
    if not options:
        return None
    # Prefer higher-value rewards by scanning labels/ids
    priority_keywords = [
        'evolv', 'legendary', 'lendár',
        '60', '30', '20', '15',
        'pokémon', 'pokemon',
        'master', 'point',
        'pokébola', 'pokeball',
        'full_restore', 'restore',
    ]
    for kw in priority_keywords:
        for opt in options:
            label = (opt.get('label') or '').lower()
            opt_id_val = (_opt_id(opt) or '').lower()
            if kw in label or kw in opt_id_val:
                return _opt_id(opt)
    return _opt_id(options[0])
