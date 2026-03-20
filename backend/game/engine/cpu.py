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
        select_starter, roll_dice, skip_action, pass_turn,
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
        return _decide_battle(cpu_player_id, player, battle)

    # ── Only act on own turn for non-battle phases ────────────────────────
    if current_player_id != cpu_player_id:
        return [('wait', {})]

    # ── Pending action ────────────────────────────────────────────────────
    pending_action = turn.get('pending_action')
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
        return _decide_action_phase(player, turn)

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


def _decide_battle(cpu_player_id: str, player: dict, battle: dict) -> list[tuple[str, dict]]:
    challenger_id = battle.get('challenger_id')
    defender_id = battle.get('defender_id')
    if cpu_player_id not in (challenger_id, defender_id):
        return [('wait', {})]

    sub_phase = battle.get('sub_phase', '')
    is_challenger = cpu_player_id == challenger_id

    if sub_phase == 'choosing':
        already_chose = (
            battle.get('challenger_choice') is not None if is_challenger
            else battle.get('defender_choice') is not None
        )
        if already_chose:
            return [('wait', {})]
        slot_key = _best_slot_key(player)
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


def _decide_select_starter(turn: dict) -> list[tuple[str, dict]]:
    available = turn.get('available_starters', [])
    if not available:
        return [('wait', {})]
    best = max(available, key=lambda s: s.get('battle_points', 0))
    return [('select_starter', {'starter_id': best['id']})]


def _decide_action_phase(player: dict, turn: dict) -> list[tuple[str, dict]]:
    # Pokemon encounter
    if turn.get('pending_pokemon'):
        return [('roll_capture_dice', {})]
    # Safari zone queue
    if turn.get('pending_safari'):
        return [('roll_capture_dice', {})]
    # Nothing to do: end turn
    return [('pass_turn', {})]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _best_slot_key(player: dict) -> str | None:
    """Return slot_key of the pokemon with highest battle_points (prefer not knocked out)."""
    roster = player.get('pokemon_inventory', [])
    available = [p for p in roster if not p.get('knocked_out', False)] or roster
    if not available:
        return None
    best = max(available, key=lambda p: p.get('battle_points', 0))
    return best.get('slot_key')


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
