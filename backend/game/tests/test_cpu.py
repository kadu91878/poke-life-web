import asyncio
import uuid
from unittest import TestCase

from game.consumers import GameConsumer
from game.engine import cpu as cpu_engine
from game.engine.inventory import sync_player_inventory
from game.state_schema import build_initial_state


def _make_player(name: str, *, is_cpu: bool = False, **kwargs) -> dict:
    player = {
        'id': str(uuid.uuid4()),
        'name': name,
        'color': 'red',
        'is_host': False,
        'is_active': True,
        'is_connected': True,
        'is_cpu': is_cpu,
        'position': 0,
        'pokeballs': 6,
        'full_restores': 2,
        'starter_pokemon': None,
        'pokemon': [],
        'capture_sequence_counter': 0,
        'special_tile_flags': {
            'celadon_dept_store_bonus_claimed': False,
        },
        'items': {'pokeballs': 6, 'full_restores': 2},
        'badges': [],
        'master_points': 0,
        'has_reached_league': False,
    }
    player.update(kwargs)
    return player


def _make_pokemon(name: str, *, bp: int, types: list[str], knocked_out: bool = False, mp: int = 10) -> dict:
    return {
        'id': str(uuid.uuid4()),
        'name': name,
        'types': types,
        'battle_points': bp,
        'master_points': mp,
        'knocked_out': knocked_out,
    }


def _base_state(players: list[dict]) -> dict:
    state = build_initial_state('CPU01')
    state['status'] = 'playing'
    state['players'] = players
    state['turn']['current_player_id'] = players[0]['id']
    state['turn']['phase'] = 'roll'
    state['turn']['battle'] = None
    state['turn']['capture_context'] = None
    return state


def _sync_player_items(player: dict) -> dict:
    sync_player_inventory(player)
    return player


class TestCpuDuelDecisions(TestCase):

    def test_duel_tile_challenges_best_target_by_effective_bp(self):
        cpu_player = _make_player(
            'CPU',
            is_cpu=True,
            pokemon=[
                _make_pokemon('Pikachu', bp=5, types=['Electric']),
            ],
        )
        misty = _make_player(
            'Misty',
            pokemon=[
                _make_pokemon('Squirtle', bp=6, types=['Water']),
            ],
        )
        brock = _make_player(
            'Brock',
            pokemon=[
                _make_pokemon('Geodude', bp=6, types=['Rock', 'Ground']),
            ],
        )
        state = _base_state([cpu_player, misty, brock])
        state['turn']['phase'] = 'action'
        state['turn']['capture_context'] = 'duel'

        actions = cpu_engine.decide_action(state, cpu_player['id'])

        self.assertEqual(
            actions,
            [('challenge_player', {'target_player_id': misty['id']})],
        )

    def test_battle_choice_uses_effective_bp_instead_of_raw_bp(self):
        cpu_player = _make_player(
            'CPU',
            is_cpu=True,
            pokemon=[
                _make_pokemon('Snorlax', bp=6, types=['Normal']),
                _make_pokemon('Pikachu', bp=5, types=['Electric']),
            ],
        )
        opponent = _make_player(
            'Lance',
            pokemon=[
                _make_pokemon('Gyarados', bp=5, types=['Water', 'Flying']),
            ],
        )
        state = _base_state([cpu_player, opponent])
        state['turn']['phase'] = 'battle'
        state['turn']['battle'] = {
            'mode': 'player',
            'challenger_id': cpu_player['id'],
            'defender_id': opponent['id'],
            'challenger_choice': None,
            'defender_choice': {
                'name': 'Gyarados',
                'battle_points': 5,
                'types': ['Water', 'Flying'],
                'battle_slot_key': 'pokemon:0',
            },
            'challenger_roll': None,
            'defender_roll': None,
            'sub_phase': 'choosing',
            'choice_stage': 'challenger',
        }

        actions = cpu_engine.decide_action(state, cpu_player['id'])

        self.assertEqual(actions[0][0], 'battle_choice')
        self.assertEqual(actions[0][1]['pokemon_slot_key'], 'pokemon:1')

    def test_apply_cpu_action_challenge_player_starts_duel(self):
        cpu_player = _make_player(
            'CPU',
            is_cpu=True,
            pokemon=[
                _make_pokemon('Pikachu', bp=5, types=['Electric']),
            ],
        )
        opponent = _make_player(
            'Misty',
            pokemon=[
                _make_pokemon('Squirtle', bp=6, types=['Water']),
            ],
        )
        state = _base_state([cpu_player, opponent])
        state['turn']['phase'] = 'action'
        state['turn']['capture_context'] = 'duel'

        result = asyncio.run(
            GameConsumer._apply_cpu_action(
                object(),
                state,
                cpu_player['id'],
                'challenge_player',
                {'target_player_id': opponent['id']},
            )
        )

        self.assertIsNotNone(result)
        new_state, event = result
        self.assertEqual(new_state['turn']['phase'], 'battle')
        self.assertEqual(new_state['turn']['battle']['challenger_id'], cpu_player['id'])
        self.assertEqual(new_state['turn']['battle']['defender_id'], opponent['id'])
        self.assertEqual(
            event,
            {
                'type': 'duel_started',
                'challenger_id': cpu_player['id'],
                'defender_id': opponent['id'],
            },
        )


class TestCpuInventoryOverflow(TestCase):

    def test_needs_cpu_action_and_decide_action_handle_pending_item_choice(self):
        human = _make_player('Ash')
        cpu_player = _sync_player_items(_make_player(
            'CPU',
            is_cpu=True,
            full_restores=2,
            items=[
                {'key': 'bill', 'quantity': 7},
                {'key': 'full_restore', 'quantity': 2},
            ],
        ))
        state = _base_state([human, cpu_player])
        state['turn']['phase'] = 'item_choice'
        state['turn']['current_player_id'] = human['id']
        state['turn']['pending_item_choice'] = {
            'player_id': cpu_player['id'],
            'reason': 'Inventario cheio',
            'discard_count': 1,
        }

        self.assertEqual(cpu_engine.needs_cpu_action(state), [cpu_player['id']])
        self.assertEqual(
            cpu_engine.decide_action(state, cpu_player['id']),
            [('discard_item', {'item_key': 'bill'})],
        )

    def test_apply_cpu_action_discard_item_clears_overflow_and_turn_continues(self):
        cpu_player = _sync_player_items(_make_player(
            'CPU',
            is_cpu=True,
            full_restores=2,
            items=[
                {'key': 'bill', 'quantity': 7},
                {'key': 'full_restore', 'quantity': 2},
            ],
        ))
        opponent = _make_player('Misty')
        state = _base_state([cpu_player, opponent])
        state['turn']['phase'] = 'item_choice'
        state['turn']['current_player_id'] = cpu_player['id']
        state['turn']['pending_item_choice'] = {
            'player_id': cpu_player['id'],
            'reason': 'Inventario cheio',
            'discard_count': 1,
        }

        result = asyncio.run(
            GameConsumer._apply_cpu_action(
                object(),
                state,
                cpu_player['id'],
                'discard_item',
                {'item_key': 'bill'},
            )
        )

        self.assertIsNotNone(result)
        new_state, event = result
        updated_cpu = next(player for player in new_state['players'] if player['id'] == cpu_player['id'])
        self.assertIsNone(new_state['turn']['pending_item_choice'])
        self.assertNotEqual(new_state['turn']['phase'], 'item_choice')
        self.assertEqual(new_state['turn']['current_player_id'], opponent['id'])
        self.assertEqual(event['type'], 'item_discarded')
        self.assertEqual(event['item_key'], 'bill')
        self.assertEqual(next(item['quantity'] for item in updated_cpu['items'] if item['key'] == 'bill'), 6)


class TestCpuTradeDecisions(TestCase):

    def test_needs_cpu_action_handles_trade_proposal_owned_by_cpu(self):
        human = _make_player('Ash', position=5, pokemon=[_make_pokemon('Bulbasaur', bp=4, types=['Grass'])])
        cpu_player = _make_player('CPU', is_cpu=True, position=5, pokemon=[_make_pokemon('Charmander', bp=5, types=['Fire'])])
        _sync_player_items(human)
        _sync_player_items(cpu_player)
        state = _base_state([human, cpu_player])
        state['turn']['phase'] = 'action'
        state['turn']['current_player_id'] = human['id']
        state['turn']['pending_action'] = {
            'type': 'trade_proposal',
            'player_id': cpu_player['id'],
            'proposer_id': human['id'],
            'offered_pokemon': {'name': 'Bulbasaur', 'battle_points': 5, 'master_points': 18, 'types': ['Grass', 'Poison']},
            'options': [
                {'id': 'pokemon:0', 'slot_key': 'pokemon:0', 'label': 'Trocar Charmander', 'pokemon': {'name': 'Charmander', 'battle_points': 5, 'master_points': 10, 'types': ['Fire']}},
                {'id': 'decline', 'label': 'Recusar'},
            ],
        }

        self.assertEqual(cpu_engine.needs_cpu_action(state), [cpu_player['id']])
        self.assertEqual(
            cpu_engine.decide_action(state, cpu_player['id']),
            [('resolve_pending_action', {'option_id': 'pokemon:0'})],
        )

    def test_cpu_rejects_absurd_trade(self):
        human = _make_player('Ash', position=5, pokemon=[_make_pokemon('Rattata', bp=1, types=['Normal'], mp=2)])
        cpu_player = _make_player('CPU', is_cpu=True, position=5, pokemon=[_make_pokemon('Mewtwo', bp=10, types=['Psychic'], mp=60)])
        _sync_player_items(human)
        _sync_player_items(cpu_player)
        state = _base_state([human, cpu_player])
        state['turn']['phase'] = 'action'
        state['turn']['current_player_id'] = human['id']
        state['turn']['pending_action'] = {
            'type': 'trade_proposal',
            'player_id': cpu_player['id'],
            'proposer_id': human['id'],
            'offered_pokemon': {'name': 'Rattata', 'battle_points': 1, 'master_points': 2, 'types': ['Normal']},
            'options': [
                {'id': 'pokemon:0', 'slot_key': 'pokemon:0', 'label': 'Trocar Mewtwo', 'pokemon': {'name': 'Mewtwo', 'battle_points': 10, 'master_points': 60, 'types': ['Psychic']}},
                {'id': 'decline', 'label': 'Recusar'},
            ],
        }

        self.assertEqual(
            cpu_engine.decide_action(state, cpu_player['id']),
            [('resolve_pending_action', {'option_id': 'decline'})],
        )
