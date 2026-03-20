import unittest
from unittest.mock import AsyncMock, patch

from game.consumers import GameConsumer
from game.engine import state as engine
from game.state_schema import build_initial_state


def _make_consumer(room_code='ABC123', player_id=None):
    consumer = GameConsumer()
    consumer.room_code = room_code
    consumer.room_group_name = f'game_{room_code}'
    consumer.player_id = player_id
    consumer.broadcast_state = AsyncMock()
    consumer.send_json = AsyncMock()
    consumer.send_error = AsyncMock()
    return consumer


def _attach_state(consumer, state):
    holder = {'state': state}

    async def fake_get():
        return holder['state']

    async def fake_save(s):
        holder['state'] = s

    consumer.get_game_state = fake_get
    consumer.save_game_state = fake_save
    return holder


class TestJoinGame(unittest.IsolatedAsyncioTestCase):

    async def test_first_player_join_creates_entry(self):
        consumer = _make_consumer()
        state = build_initial_state('ABC123')
        holder = _attach_state(consumer, state)

        await consumer.handle_join_game({'player_name': 'Ash'})

        self.assertIsNotNone(consumer.player_id)
        self.assertEqual(len(holder['state']['players']), 1)
        self.assertEqual(holder['state']['players'][0]['name'], 'Ash')
        consumer.broadcast_state.assert_called()
        consumer.send_json.assert_called()

    async def test_second_player_join_broadcasts_to_all(self):
        """Quando P2 entra, broadcast é enviado (P1 recebe atualização do lobby)."""
        c1 = _make_consumer()
        state = build_initial_state('ABC123')
        holder = _attach_state(c1, state)
        await c1.handle_join_game({'player_name': 'Ash'})
        c1.broadcast_state.reset_mock()

        c2 = _make_consumer()
        _attach_state(c2, holder['state'])
        c2.save_game_state = c1.save_game_state
        c2.get_game_state = c1.get_game_state

        await c2.handle_join_game({'player_name': 'Misty'})

        # Deve ter broadcastado para que P1 veja P2 no lobby
        c2.broadcast_state.assert_called()
        # Estado deve ter 2 jogadores
        final = holder['state']
        names = [p['name'] for p in final['players']]
        self.assertIn('Ash', names)
        self.assertIn('Misty', names)

    async def test_join_during_playing_reconnects_by_id(self):
        """Reconexão por player_id funciona mesmo quando dois jogadores têm o mesmo nome."""
        state = build_initial_state('ABC123')
        # Simula partida em andamento com dois jogadores de mesmo nome (pior caso)
        p1_id = 'uuid-p1'
        p2_id = 'uuid-p2'
        state['status'] = 'playing'
        state['players'] = [
            {'id': p1_id, 'name': 'Trainer', 'is_active': True, 'is_connected': True},
            {'id': p2_id, 'name': 'Trainer', 'is_active': True, 'is_connected': False},
        ]

        consumer = _make_consumer()
        _attach_state(consumer, state)

        # P2 reconecta enviando o player_id correto
        await consumer.handle_join_game({'player_name': 'Trainer', 'player_id': p2_id})

        # Deve ter ligado ao P2, não ao P1
        self.assertEqual(consumer.player_id, p2_id)
        consumer.send_error.assert_not_called()
        # Deve ter broadcastado a reconexão
        consumer.broadcast_state.assert_called()

    async def test_join_during_playing_does_not_steal_connected_player(self):
        """Reconexão por nome NÃO vincula a um jogador já conectado (previne roubo de identidade)."""
        state = build_initial_state('ABC123')
        p1_id = 'uuid-p1'
        state['status'] = 'playing'
        state['players'] = [
            {'id': p1_id, 'name': 'Ash', 'is_active': True, 'is_connected': True},
        ]

        consumer = _make_consumer()
        _attach_state(consumer, state)

        # Outro cliente tenta entrar com mesmo nome, sem enviar player_id
        await consumer.handle_join_game({'player_name': 'Ash'})

        # Deve rejeitar — não pode ligar ao jogador já conectado pelo nome
        consumer.send_error.assert_called()

    async def test_join_during_playing_fallback_by_name_for_disconnected(self):
        """Fallback por nome funciona para jogadores desconectados (sem player_id salvo)."""
        state = build_initial_state('ABC123')
        p2_id = 'uuid-p2'
        state['status'] = 'playing'
        state['players'] = [
            {'id': 'uuid-p1', 'name': 'Ash', 'is_active': True, 'is_connected': True},
            {'id': p2_id, 'name': 'Misty', 'is_active': True, 'is_connected': False},
        ]

        consumer = _make_consumer()
        _attach_state(consumer, state)

        # Misty reconecta sem player_id (sessão perdida)
        await consumer.handle_join_game({'player_name': 'Misty'})

        self.assertEqual(consumer.player_id, p2_id)
        consumer.send_error.assert_not_called()

    async def test_join_during_playing_unknown_player_rejected(self):
        """Novo jogador durante partida ativa é rejeitado."""
        state = build_initial_state('ABC123')
        state['status'] = 'playing'
        state['players'] = [
            {'id': 'uuid-p1', 'name': 'Ash', 'is_active': True, 'is_connected': True},
        ]

        consumer = _make_consumer()
        _attach_state(consumer, state)

        await consumer.handle_join_game({'player_name': 'Giovanni'})

        consumer.send_error.assert_called()


class TestStarterIdentity(unittest.IsolatedAsyncioTestCase):
    """Testa que select_starter aceita o jogador correto após P1 escolher."""

    def _make_two_player_game_state(self):
        from game.engine.state import initialize_game
        state = build_initial_state('ROOM01')
        state['players'] = [
            {'id': 'p1', 'name': 'Ash',   'is_active': True, 'is_connected': True,
             'position': 0, 'pokeballs': 6, 'full_restores': 2, 'starter_pokemon': None,
             'pokemon': [], 'items': {}, 'badges': [], 'master_points': 0,
             'has_reached_league': False, 'is_host': True, 'color': 'red'},
            {'id': 'p2', 'name': 'Misty', 'is_active': True, 'is_connected': True,
             'position': 0, 'pokeballs': 6, 'full_restores': 2, 'starter_pokemon': None,
             'pokemon': [], 'items': {}, 'badges': [], 'master_points': 0,
             'has_reached_league': False, 'is_host': False, 'color': 'blue'},
        ]
        with patch('game.engine.state.random.shuffle', new=lambda ids: None):
            return initialize_game(state)

    async def test_p1_selects_then_p2_can_select(self):
        state = self._make_two_player_game_state()
        starters = state['turn']['available_starters']

        # P1 selects
        c1 = _make_consumer(player_id='p1')
        holder = _attach_state(c1, state)
        await c1.handle_select_starter({'starter_id': starters[0]['id']})

        c1.send_error.assert_not_called()
        c1.broadcast_state.assert_called()

        # Current player must be P2 now
        updated = holder['state']
        self.assertEqual(updated['turn']['current_player_id'], 'p2')

        # P2 selects
        c2 = _make_consumer(player_id='p2')
        c2.get_game_state = c1.get_game_state
        c2.save_game_state = c1.save_game_state
        await c2.handle_select_starter({'starter_id': starters[1]['id']})

        c2.send_error.assert_not_called()
        c2.broadcast_state.assert_called()
        self.assertEqual(holder['state']['turn']['phase'], 'roll')

    async def test_wrong_player_id_rejected(self):
        """Socket com player_id errado (ex: reconectou como P1) é rejeitado ao tentar selecionar."""
        state = self._make_two_player_game_state()
        starters = state['turn']['available_starters']

        # Simula P1 selecionando → current_player_id vira p2
        state = engine.select_starter(state, 'p1', starters[0]['id'])

        # Socket que diz ser P1 (identidade errada) tenta selecionar na vez de P2
        consumer = _make_consumer(player_id='p1')
        _attach_state(consumer, state)
        await consumer.handle_select_starter({'starter_id': starters[1]['id']})

        consumer.send_error.assert_called()

    async def test_reconnect_preserves_correct_player_id(self):
        """Após reconexão por ID, o jogador correto é identificado na partida."""
        state = build_initial_state('ROOM02')
        state['status'] = 'playing'
        state['players'] = [
            {'id': 'p1', 'name': 'Trainer', 'is_active': True, 'is_connected': True},
            {'id': 'p2', 'name': 'Trainer', 'is_active': True, 'is_connected': False},
        ]

        consumer = _make_consumer()
        _attach_state(consumer, state)

        await consumer.handle_join_game({'player_name': 'Trainer', 'player_id': 'p2'})

        # DEVE ter ligado ao p2, não ao p1
        self.assertEqual(consumer.player_id, 'p2')


class GameWebSocketActionTests(unittest.IsolatedAsyncioTestCase):
    async def test_join_and_save_handlers(self):
        consumer = _make_consumer()
        state = build_initial_state('ABC123')
        holder = _attach_state(consumer, state)

        await consumer.handle_join_game({'player_name': 'Ash'})

        self.assertEqual(len(holder['state']['players']), 1)
        self.assertEqual(holder['state']['players'][0]['name'], 'Ash')
        consumer.broadcast_state.assert_called()

        await consumer.handle_save_state({'state': holder['state']})
        self.assertTrue(consumer.broadcast_state.called)
        self.assertEqual(holder['state']['room_code'], 'ABC123')


class DebugVisualWebSocketTests(unittest.IsolatedAsyncioTestCase):

    def _make_state_with_debug_duel_tile(self):
        p1 = {
            'id': 'p1',
            'name': 'Ash',
            'is_active': True,
            'is_connected': True,
            'is_host': True,
            'position': 0,
            'pokeballs': 6,
            'full_restores': 2,
            'starter_pokemon': {
                'id': 25,
                'name': 'Pikachu',
                'types': ['Electric'],
                'battle_points': 5,
                'master_points': 10,
                'ability': 'none',
                'ability_type': 'none',
                'battle_effect': None,
                'evolves_to': None,
                'slot_cost': 1,
            },
            'pokemon': [],
            'items': {'pokeballs': 6, 'full_restores': 2},
            'badges': [],
            'master_points': 0,
            'has_reached_league': False,
            'color': 'red',
        }
        p2 = {
            'id': 'p2',
            'name': 'Misty',
            'is_active': True,
            'is_connected': True,
            'is_host': False,
            'position': 0,
            'pokeballs': 6,
            'full_restores': 2,
            'starter_pokemon': {
                'id': 4,
                'name': 'Charmander',
                'types': ['Fire'],
                'battle_points': 4,
                'master_points': 10,
                'ability': 'none',
                'ability_type': 'none',
                'battle_effect': None,
                'evolves_to': None,
                'slot_cost': 1,
            },
            'pokemon': [],
            'items': {'pokeballs': 6, 'full_restores': 2},
            'badges': [],
            'master_points': 0,
            'has_reached_league': False,
            'color': 'blue',
        }
        state = build_initial_state('DBGDUEL')
        state['players'] = [p1, p2]
        state = engine.initialize_game(state)
        state, _ = engine.set_debug_test_player_enabled(state, True)
        session = state['debug_visual']['session_state']
        duel_tile = next((tile for tile in session.get('board', {}).get('tiles', []) if tile.get('type') == 'duel'), None)
        if duel_tile is None:
            self.skipTest('Sem tile de duelo no tabuleiro')
        session['players'][0]['position'] = duel_tile['id']
        session['turn']['current_player_id'] = '__debug_test_player__'
        session['turn']['phase'] = 'action'
        session['turn']['capture_context'] = 'duel'
        state['debug_visual']['session_state'] = session
        state['turn']['phase'] = 'action'
        state['turn']['current_player_id'] = 'p2'
        return state

    async def test_toggle_test_player_handler_enables_and_disables_session(self):
        consumer = _make_consumer(player_id='p1')
        state = build_initial_state('DBG123')
        state['players'] = [{'id': 'p1', 'name': 'Ash', 'is_active': True, 'is_connected': True}]
        holder = _attach_state(consumer, state)

        with patch('game.consumers.settings.DEBUG', True):
            await consumer.handle_debug_toggle_test_player({'enabled': True})

        self.assertTrue(holder['state']['debug_visual']['enabled'])
        self.assertIsNotNone(holder['state']['debug_visual']['session_state'])
        consumer.broadcast_state.assert_called()

        consumer.broadcast_state.reset_mock()
        with patch('game.consumers.settings.DEBUG', True):
            await consumer.handle_debug_toggle_test_player({'enabled': False})

        self.assertFalse(holder['state']['debug_visual']['enabled'])
        self.assertIsNone(holder['state']['debug_visual']['session_state'])
        consumer.broadcast_state.assert_called()

    async def test_move_test_player_handler_rejects_non_integer_steps(self):
        consumer = _make_consumer(player_id='p1')
        state = build_initial_state('DBG124')
        state['players'] = [{'id': 'p1', 'name': 'Ash', 'is_active': True, 'is_connected': True}]
        state, _ = engine.set_debug_test_player_enabled(state, True)
        _attach_state(consumer, state)

        with patch('game.consumers.settings.DEBUG', True):
            await consumer.handle_debug_move_test_player({'steps': '1.5'})

        consumer.send_error.assert_called()

    async def test_debug_duel_start_broadcasts_shared_battle_and_real_defender_uses_normal_handler(self):
        debug_consumer = _make_consumer(room_code='DBGDUEL', player_id='p1')
        state = self._make_state_with_debug_duel_tile()
        holder = _attach_state(debug_consumer, state)

        with patch('game.consumers.settings.DEBUG', True):
            await debug_consumer.handle_debug_start_duel_with_player({'target_player_id': 'p1'})

        debug_consumer.send_error.assert_not_called()
        debug_consumer.broadcast_state.assert_called()
        event = debug_consumer.broadcast_state.call_args.args[1]
        self.assertEqual(event['type'], 'duel_started')
        self.assertEqual(holder['state']['turn']['battle']['challenger_id'], '__debug_test_player__')
        self.assertEqual(holder['state']['turn']['battle']['defender_id'], 'p1')

        defender_consumer = _make_consumer(room_code='DBGDUEL', player_id='p1')
        defender_consumer.get_game_state = debug_consumer.get_game_state
        defender_consumer.save_game_state = debug_consumer.save_game_state
        defender_consumer.broadcast_state = AsyncMock()
        defender_consumer.send_error = AsyncMock()

        await defender_consumer.handle_battle_choice({'pokemon_index': 0})

        defender_consumer.send_error.assert_not_called()
        defender_event = defender_consumer.broadcast_state.call_args.args[1]
        self.assertEqual(defender_event['type'], 'battle_choice_registered')
        self.assertEqual(defender_event['player_id'], 'p1')
        self.assertEqual(holder['state']['turn']['battle']['choice_stage'], 'challenger')

    async def test_debug_duel_roll_broadcasts_standard_battle_resolution_event(self):
        debug_consumer = _make_consumer(room_code='DBGDUEL', player_id='p1')
        state = self._make_state_with_debug_duel_tile()
        holder = _attach_state(debug_consumer, state)

        with patch('game.consumers.settings.DEBUG', True):
            await debug_consumer.handle_debug_start_duel_with_player({'target_player_id': 'p1'})

        defender_consumer = _make_consumer(room_code='DBGDUEL', player_id='p1')
        defender_consumer.get_game_state = debug_consumer.get_game_state
        defender_consumer.save_game_state = debug_consumer.save_game_state
        defender_consumer.broadcast_state = AsyncMock()
        defender_consumer.send_error = AsyncMock()

        await defender_consumer.handle_battle_choice({'pokemon_index': 0})
        with patch('game.consumers.settings.DEBUG', True):
            await debug_consumer.handle_debug_duel_choose_pokemon({'pokemon_index': 0})

        with patch('game.engine.state.roll_battle_dice', side_effect=[6, 1]):
            await defender_consumer.handle_roll_battle_dice({})
            debug_consumer.broadcast_state.reset_mock()
            with patch('game.consumers.settings.DEBUG', True):
                await debug_consumer.handle_debug_duel_roll_battle({})

        debug_consumer.send_error.assert_not_called()
        resolution_event = debug_consumer.broadcast_state.call_args.args[1]
        self.assertEqual(resolution_event['type'], 'battle_resolved')
        self.assertIn('winner_id', resolution_event['result'])
        self.assertIsNone(holder['state']['turn'].get('battle'))


class TestHostToolsWebsocket(unittest.IsolatedAsyncioTestCase):

    def _host_tools_state(self):
        state = build_initial_state('HOSTDBG')
        state['players'] = [
            {
                'id': 'p1',
                'name': 'Ash',
                'is_host': True,
                'is_active': True,
                'is_connected': True,
                'position': 0,
                'pokeballs': 6,
                'full_restores': 2,
                'starter_pokemon': None,
                'pokemon': [],
                'capture_sequence_counter': 0,
                'special_tile_flags': {'celadon_dept_store_bonus_claimed': False},
                'items': {'pokeballs': 6, 'full_restores': 2},
                'badges': [],
                'master_points': 0,
                'has_reached_league': False,
                'color': 'red',
            },
            {
                'id': 'p2',
                'name': 'Misty',
                'is_host': False,
                'is_active': True,
                'is_connected': True,
                'position': 0,
                'pokeballs': 6,
                'full_restores': 2,
                'starter_pokemon': None,
                'pokemon': [],
                'capture_sequence_counter': 0,
                'special_tile_flags': {'celadon_dept_store_bonus_claimed': False},
                'items': {'pokeballs': 6, 'full_restores': 2},
                'badges': [],
                'master_points': 0,
                'has_reached_league': False,
                'color': 'blue',
            },
        ]
        state = engine.initialize_game(state)
        state['turn']['current_player_id'] = 'p1'
        state['turn']['phase'] = 'roll'
        return state

    async def test_host_can_toggle_host_tools(self):
        consumer = _make_consumer(player_id='p1')
        holder = _attach_state(consumer, self._host_tools_state())

        with patch('game.consumers.settings.DEBUG', True):
            await consumer.handle_debug_toggle_host_tools({'enabled': True})

        self.assertTrue(holder['state']['debug_visual']['host_tools']['enabled'])
        consumer.send_error.assert_not_called()
        consumer.broadcast_state.assert_called()

    async def test_second_player_cannot_toggle_host_tools(self):
        consumer = _make_consumer(player_id='p2')
        _attach_state(consumer, self._host_tools_state())

        with patch('game.consumers.settings.DEBUG', True):
            await consumer.handle_debug_toggle_host_tools({'enabled': True})

        consumer.send_error.assert_called()
        consumer.broadcast_state.assert_not_called()

    async def test_second_player_cannot_use_host_debug_actions_even_if_mode_enabled(self):
        consumer = _make_consumer(player_id='p2')
        state = self._host_tools_state()
        state, _ = engine.set_host_tools_enabled(state, True)
        _attach_state(consumer, state)

        guarded_calls = [
            (consumer.handle_debug_move_host, {'steps': 2}),
            (consumer.handle_debug_add_pokemon_to_host, {'pokemon_name': 'Pikachu'}),
            (consumer.handle_debug_add_item, {'item_key': 'bill', 'quantity': 1}),
            (consumer.handle_debug_trigger_current_tile, {}),
        ]

        with patch('game.consumers.settings.DEBUG', True):
            for handler, payload in guarded_calls:
                await handler(payload)
                consumer.send_error.assert_called()
                consumer.broadcast_state.assert_not_called()
                consumer.send_error.reset_mock()
