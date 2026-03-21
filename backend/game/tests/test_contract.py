from pathlib import Path
from unittest import TestCase

from game.socket_contract import GAME_ACTIONS, SOCKET_HANDLER_NAMES


PROJECT_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_ACTIONS_MODULE = PROJECT_ROOT / 'frontend' / 'src' / 'constants' / 'gameActions.js'
FRONTEND_ACTIONS_JSON = PROJECT_ROOT / 'frontend' / 'src' / 'constants' / 'gameActions.json'
BACKEND_ACTIONS_JSON = PROJECT_ROOT / 'backend' / 'game' / 'gameActions.json'
FRONTEND_STORE = PROJECT_ROOT / 'frontend' / 'src' / 'stores' / 'gameStore.js'
FRONTEND_BOARD = PROJECT_ROOT / 'frontend' / 'src' / 'components' / 'board' / 'GameBoard.vue'
FRONTEND_BATTLE_MODAL = PROJECT_ROOT / 'frontend' / 'src' / 'components' / 'ui' / 'BattleModal.vue'


class TestSocketActionContract(TestCase):
    def test_backend_bundled_contract_matches_frontend_contract(self):
        self.assertEqual(
            BACKEND_ACTIONS_JSON.read_text(encoding='utf-8'),
            FRONTEND_ACTIONS_JSON.read_text(encoding='utf-8'),
        )

    def test_capture_and_debug_actions_are_mapped_in_backend(self):
        self.assertEqual(SOCKET_HANDLER_NAMES[GAME_ACTIONS['rollCaptureDice']], 'handle_roll_capture_dice')
        self.assertEqual(SOCKET_HANDLER_NAMES[GAME_ACTIONS['proposeTrade']], 'handle_propose_trade')
        self.assertEqual(SOCKET_HANDLER_NAMES[GAME_ACTIONS['debugToggleHostTools']], 'handle_debug_toggle_host_tools')
        self.assertEqual(SOCKET_HANDLER_NAMES[GAME_ACTIONS['debugMoveHost']], 'handle_debug_move_host')
        self.assertEqual(SOCKET_HANDLER_NAMES[GAME_ACTIONS['debugAddPokemonToHost']], 'handle_debug_add_pokemon_to_host')
        self.assertEqual(SOCKET_HANDLER_NAMES[GAME_ACTIONS['debugTriggerCurrentTile']], 'handle_debug_trigger_current_tile')
        self.assertEqual(SOCKET_HANDLER_NAMES[GAME_ACTIONS['debugToggleTestPlayer']], 'handle_debug_toggle_test_player')
        self.assertEqual(SOCKET_HANDLER_NAMES[GAME_ACTIONS['debugMoveTestPlayer']], 'handle_debug_move_test_player')
        self.assertEqual(SOCKET_HANDLER_NAMES[GAME_ACTIONS['debugRollTestPlayer']], 'handle_debug_roll_test_player')
        self.assertEqual(SOCKET_HANDLER_NAMES[GAME_ACTIONS['debugTriggerTestPlayerTile']], 'handle_debug_trigger_test_player_tile')
        self.assertEqual(SOCKET_HANDLER_NAMES[GAME_ACTIONS['debugRollCaptureForTestPlayer']], 'handle_debug_roll_capture_for_test_player')
        self.assertEqual(SOCKET_HANDLER_NAMES[GAME_ACTIONS['debugResolveEventForTestPlayer']], 'handle_debug_resolve_event_for_test_player')
        self.assertEqual(SOCKET_HANDLER_NAMES[GAME_ACTIONS['debugSkipTestPlayerPending']], 'handle_debug_skip_test_player_pending')
        self.assertEqual(SOCKET_HANDLER_NAMES[GAME_ACTIONS['debugStartDuelWithPlayer']], 'handle_debug_start_duel_with_player')
        self.assertEqual(SOCKET_HANDLER_NAMES[GAME_ACTIONS['debugDuelChoosePokemon']], 'handle_debug_duel_choose_pokemon')
        self.assertEqual(SOCKET_HANDLER_NAMES[GAME_ACTIONS['debugDuelRollBattle']], 'handle_debug_duel_roll_battle')

    def test_frontend_store_uses_shared_action_contract(self):
        constants_source = FRONTEND_ACTIONS_MODULE.read_text(encoding='utf-8')
        store_source = FRONTEND_STORE.read_text(encoding='utf-8')
        board_source = FRONTEND_BOARD.read_text(encoding='utf-8')
        battle_modal_source = FRONTEND_BATTLE_MODAL.read_text(encoding='utf-8')

        self.assertIn("import gameActions from './gameActions.json'", constants_source)
        self.assertIn("import gameActions from '@/constants/gameActions'", store_source)
        self.assertIn("send(gameActions.rollCaptureDice", store_source)
        self.assertIn("send(gameActions.proposeTrade", store_source)
        self.assertIn("send(gameActions.debugToggleHostTools", store_source)
        self.assertIn("send(gameActions.debugMoveHost", store_source)
        self.assertIn("send(gameActions.debugAddPokemonToHost", store_source)
        self.assertIn("send(gameActions.debugTriggerCurrentTile", store_source)
        self.assertIn("send(gameActions.debugRollTestPlayer", store_source)
        self.assertIn("send(gameActions.debugTriggerTestPlayerTile", store_source)
        self.assertIn("send(gameActions.debugRollCaptureForTestPlayer", store_source)
        self.assertIn("send(gameActions.debugResolveEventForTestPlayer", store_source)
        self.assertIn("send(gameActions.debugSkipTestPlayerPending", store_source)
        self.assertIn("send(gameActions.debugStartDuelWithPlayer", store_source)
        self.assertIn("send(gameActions.debugDuelChoosePokemon", store_source)
        self.assertIn("send(gameActions.debugDuelRollBattle", store_source)
        self.assertIn("const allPlayers = computed(() => {", store_source)
        self.assertIn("store.actions.debugToggleHostTools", board_source)
        self.assertIn("store.actions.debugMoveHost", board_source)
        self.assertIn("store.actions.debugAddPokemonToHost", board_source)
        self.assertIn("store.actions.debugAddItemToHost", board_source)
        self.assertIn("store.actions.debugTriggerHostTile", board_source)
        self.assertIn("v-if=\"hostCanUseToolsPanel\"", board_source)
        self.assertIn("tile-node-id", board_source)
        self.assertIn("hostInventoryOpen", board_source)
        self.assertIn("InventoryModal", board_source)
        self.assertIn("const challenger = computed(() => allPlayers.value.find", battle_modal_source)
        self.assertIn("const controlsDebugChallenger = computed(() =>", battle_modal_source)
        self.assertIn("store.actions.debugDuelChoosePokemon", battle_modal_source)
        self.assertIn("store.actions.debugDuelRollBattle", battle_modal_source)
