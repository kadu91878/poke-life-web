from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_FRONTEND_ACTION_CONTRACT_PATH = Path(__file__).resolve().parents[2] / 'frontend' / 'src' / 'constants' / 'gameActions.json'
_BACKEND_ACTION_CONTRACT_PATH = Path(__file__).resolve().with_name('gameActions.json')
_ACTION_CONTRACT_CANDIDATES = (
    _FRONTEND_ACTION_CONTRACT_PATH,
    _BACKEND_ACTION_CONTRACT_PATH,
)


@lru_cache(maxsize=1)
def load_game_actions() -> dict[str, str]:
    for path in _ACTION_CONTRACT_CANDIDATES:
        if path.exists():
            return json.loads(path.read_text(encoding='utf-8'))

    searched_paths = ', '.join(str(path) for path in _ACTION_CONTRACT_CANDIDATES)
    raise FileNotFoundError(f'Nenhum contrato de ações encontrado. Caminhos verificados: {searched_paths}')


GAME_ACTIONS = load_game_actions()

SOCKET_HANDLER_NAMES = {
    GAME_ACTIONS['joinGame']: 'handle_join_game',
    GAME_ACTIONS['startGame']: 'handle_start_game',
    GAME_ACTIONS['selectStarter']: 'handle_select_starter',
    GAME_ACTIONS['rollDice']: 'handle_roll_dice',
    GAME_ACTIONS['movePlayer']: 'handle_move_player',
    GAME_ACTIONS['resolveTile']: 'handle_resolve_tile',
    GAME_ACTIONS['capturePokemon']: 'handle_capture_pokemon',
    GAME_ACTIONS['rollCaptureDice']: 'handle_roll_capture_dice',
    GAME_ACTIONS['passTurn']: 'handle_pass_turn',
    GAME_ACTIONS['skipAction']: 'handle_skip_action',
    GAME_ACTIONS['challengePlayer']: 'handle_challenge_player',
    GAME_ACTIONS['battleChoice']: 'handle_battle_choice',
    GAME_ACTIONS['rollBattleDice']: 'handle_roll_battle_dice',
    GAME_ACTIONS['removePlayer']: 'handle_remove_player',
    GAME_ACTIONS['leaveGame']: 'handle_leave_game',
    GAME_ACTIONS['saveState']: 'handle_save_state',
    GAME_ACTIONS['restoreState']: 'handle_restore_state',
    GAME_ACTIONS['useAbility']: 'handle_use_ability',
    GAME_ACTIONS['resolveEvent']: 'handle_resolve_event',
    GAME_ACTIONS['resolvePendingAction']: 'handle_resolve_pending_action',
    GAME_ACTIONS['discardItem']: 'handle_discard_item',
    GAME_ACTIONS['releasePokemon']: 'handle_release_pokemon',
    GAME_ACTIONS['useItem']: 'handle_use_item',
    GAME_ACTIONS['debugAddItem']: 'handle_debug_add_item',
    GAME_ACTIONS['debugToggleHostTools']: 'handle_debug_toggle_host_tools',
    GAME_ACTIONS['debugMoveHost']: 'handle_debug_move_host',
    GAME_ACTIONS['debugAddPokemonToHost']: 'handle_debug_add_pokemon_to_host',
    GAME_ACTIONS['debugAddPokemonToTestPlayer']: 'handle_debug_add_pokemon_to_test_player',
    GAME_ACTIONS['debugTriggerCurrentTile']: 'handle_debug_trigger_current_tile',
    GAME_ACTIONS['debugToggleTestPlayer']: 'handle_debug_toggle_test_player',
    GAME_ACTIONS['debugMoveTestPlayer']: 'handle_debug_move_test_player',
    GAME_ACTIONS['debugRollTestPlayer']: 'handle_debug_roll_test_player',
    GAME_ACTIONS['debugTriggerTestPlayerTile']: 'handle_debug_trigger_test_player_tile',
    GAME_ACTIONS['debugRollCaptureForTestPlayer']: 'handle_debug_roll_capture_for_test_player',
    GAME_ACTIONS['debugResolveEventForTestPlayer']: 'handle_debug_resolve_event_for_test_player',
    GAME_ACTIONS['debugSkipTestPlayerPending']: 'handle_debug_skip_test_player_pending',
    GAME_ACTIONS['debugStartDuelWithPlayer']: 'handle_debug_start_duel_with_player',
    GAME_ACTIONS['debugDuelChoosePokemon']: 'handle_debug_duel_choose_pokemon',
    GAME_ACTIONS['debugDuelRollBattle']: 'handle_debug_duel_roll_battle',
    GAME_ACTIONS['debugResolvePendingActionForTestPlayer']: 'handle_debug_resolve_pending_action_for_test_player',
    GAME_ACTIONS['dismissRevealedCard']: 'handle_dismiss_revealed_card',
    GAME_ACTIONS['confirmLeagueIntermission']: 'handle_confirm_league_intermission',
    GAME_ACTIONS['chatMessage']: 'handle_chat_message',
}
