"""
Testes unitários do engine de jogo.
Testa: inicialização, seleção de starters, movimento, captura,
       tiles especiais, duelo, evolução, fim de jogo,
       battle_effects, modelos formais de carta.
"""
import copy
import json
import uuid
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from game.engine import state as engine
from game.engine.cards import load_playable_pokemon_by_name, load_victory_cards
from game.engine.mechanics import (
    roll_dice, calculate_battle_score, resolve_duel,
    resolve_gym_battle, can_evolve, calculate_final_scores,
)
from game.engine.models import PokemonCard, EventCard, ALL_BATTLE_EFFECTS
from game.state_schema import build_initial_state, normalize_state
from game.engine.inventory import get_starting_resource_defaults, pokemon_slot_cost, sync_player_inventory


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_player(name: str, host: bool = False, **kwargs) -> dict:
    p = {
        'id': str(uuid.uuid4()),
        'name': name,
        'color': 'red',
        'is_host': host,
        'is_active': True,
        'is_connected': True,
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
    p.update(kwargs)
    return p


def _make_pokemon(name: str = 'Pikachu', bp: int = 5, mp: int = 10,
                  evolves_to: int | None = None, ability: str = 'none') -> dict:
    return {
        'id': 25,
        'name': name,
        'types': ['Electric'],
        'battle_points': bp,
        'master_points': mp,
        'ability': ability,
        'ability_type': 'none',
        'ability_description': '',
        'evolves_to': evolves_to,
        'ability_used': False,
    }


def _init_two_player_game() -> tuple[dict, str, str]:
    """Cria um estado de jogo com 2 jogadores prontos para jogar."""
    p1 = _make_player('Ash', host=True)
    p2 = _make_player('Misty')
    state = build_initial_state('TEST01')
    state['players'] = [p1, p2]
    state = engine.initialize_game(state)
    return state, p1['id'], p2['id']


def _land_on_tile(state: dict, player_id: str, tile_id: int) -> dict:
    player = next(p for p in state['players'] if p['id'] == player_id)
    board_len = len(state['board']['tiles'])
    player['position'] = (tile_id - 1) % board_len
    return engine.process_move(state, player_id, 1)


# ── Testes de Mecânicas Básicas ──────────────────────────────────────────────

class TestMechanics(TestCase):

    def test_roll_dice_range(self):
        for _ in range(100):
            result = roll_dice()
            self.assertGreaterEqual(result, 1)
            self.assertLessEqual(result, 6)

    def test_battle_score_base(self):
        pokemon = _make_pokemon(bp=5)
        score = calculate_battle_score(pokemon, 3)
        self.assertEqual(score, 15)

    def test_can_evolve_true(self):
        p = _make_pokemon(evolves_to=2)
        self.assertTrue(can_evolve(p))

    def test_can_evolve_false(self):
        p = _make_pokemon(evolves_to=None)
        self.assertFalse(can_evolve(p))

    def test_calculate_final_scores(self):
        players = [
            {**_make_player('Ash'), 'pokemon': [_make_pokemon(mp=30), _make_pokemon(mp=20)],
             'starter_pokemon': _make_pokemon(mp=10), 'badges': ['Badge1', 'Badge2'],
             'master_points': 100, 'league_bonus': 50},
            {**_make_player('Misty'), 'pokemon': [_make_pokemon(mp=10)],
             'starter_pokemon': _make_pokemon(mp=5), 'badges': [],
             'master_points': 20, 'league_bonus': 0},
        ]
        scores = calculate_final_scores(players)
        self.assertEqual(len(scores), 2)
        # Ash tem mais pontos
        self.assertEqual(scores[0]['player_name'], 'Ash')
        self.assertGreater(scores[0]['total'], scores[1]['total'])

    def test_resolve_duel_returns_winner(self):
        p1 = _make_pokemon('Charizard', bp=9)
        p2 = _make_pokemon('Rattata', bp=1)
        # Com dado cheio (6), Charizard deve vencer quase sempre
        with patch('game.engine.mechanics.roll_dice', side_effect=[6, 1]):
            result = resolve_duel(p1, p2)
        self.assertTrue(result['challenger_wins'])
        self.assertEqual(result['challenger_score'], 9 * 6)

    def test_resolve_duel_flags_tie(self):
        p1 = _make_pokemon('Pikachu', bp=5)
        p2 = _make_pokemon('Eevee', bp=5)
        with patch('game.engine.mechanics.roll_dice', side_effect=[3, 3]):
            result = resolve_duel(p1, p2)
        self.assertTrue(result['is_tie'])
        self.assertFalse(result['challenger_wins'])
        self.assertEqual(result['challenger_score'], result['defender_score'])

    def test_resolve_gym_battle_no_pokemon(self):
        player = _make_player('Ash')
        gym = {'leader_name': 'Brock', 'badge': 'Boulder Badge', 'leader_bp': 4}
        result = resolve_gym_battle(player, gym)
        self.assertFalse(result['player_wins'])
        self.assertEqual(result['reason'], 'Sem Pokémon')


# ── Testes de Inicialização ──────────────────────────────────────────────────

class TestGameInitialization(TestCase):

    def test_initialize_game_sets_playing_status(self):
        state, p1_id, p2_id = _init_two_player_game()
        self.assertEqual(state['status'], 'playing')

    def test_initialize_game_creates_decks(self):
        state, _, _ = _init_two_player_game()
        self.assertGreater(len(state['decks']['pokemon_deck']), 0)
        self.assertGreater(len(state['decks']['event_deck']), 0)
        self.assertGreater(len(state['decks']['victory_deck']), 0)

    def test_initialize_game_sets_starter_phase(self):
        state, _, _ = _init_two_player_game()
        self.assertEqual(state['turn']['phase'], 'select_starter')

    def test_initialize_game_has_available_starters(self):
        state, _, _ = _init_two_player_game()
        starters = state['turn']['available_starters']
        self.assertGreaterEqual(len(starters), 3)

    def test_players_start_with_visual_rule_items(self):
        state, _, _ = _init_two_player_game()
        player = state['players'][0]
        self.assertEqual(player['pokeballs'], 6)
        self.assertEqual(player['full_restores'], 2)


# ── Testes de Seleção de Starter ─────────────────────────────────────────────

class TestStarterSelection(TestCase):

    def _get_starters(self, state):
        return state['turn']['available_starters']

    def test_select_starter_sequential(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = self._get_starters(state)

        # P1 escolhe primeiro
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        self.assertIsNotNone(state)
        # Agora é vez do P2
        self.assertEqual(state['turn']['current_player_id'], p2_id)
        self.assertEqual(state['turn']['phase'], 'select_starter')

    def test_select_starter_wrong_player_returns_none(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = self._get_starters(state)

        # P2 tenta escolher quando é vez do P1
        result = engine.select_starter(state, p2_id, starters[0]['id'])
        self.assertIsNone(result)

    def test_select_starter_invalid_id_returns_none(self):
        state, p1_id, _ = _init_two_player_game()
        result = engine.select_starter(state, p1_id, 9999)
        self.assertIsNone(result)

    def test_all_starters_selected_transitions_to_roll(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = self._get_starters(state)

        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])

        self.assertEqual(state['turn']['phase'], 'roll')

    def test_starter_assigned_to_player(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = self._get_starters(state)

        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])

        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertIsNotNone(p1['starter_pokemon'])
        self.assertEqual(p1['starter_pokemon']['id'], starters[0]['id'])

    def test_duplicate_starter_rejected(self):
        """P2 não pode escolher o mesmo starter que P1 já escolheu."""
        state, p1_id, p2_id = _init_two_player_game()
        starters = self._get_starters(state)

        state = engine.select_starter(state, p1_id, starters[0]['id'])
        self.assertIsNotNone(state)

        # P2 tenta escolher o mesmo starter de P1
        result = engine.select_starter(state, p2_id, starters[0]['id'])
        self.assertIsNone(result)

    def test_chosen_starter_removed_from_available(self):
        """Após P1 escolher, o starter escolhido é removido de available_starters."""
        state, p1_id, p2_id = _init_two_player_game()
        starters = self._get_starters(state)
        chosen_id = starters[0]['id']

        initial_count = len(starters)
        state = engine.select_starter(state, p1_id, chosen_id)
        self.assertIsNotNone(state)
        available_ids = [s['id'] for s in state['turn']['available_starters']]
        self.assertNotIn(chosen_id, available_ids)
        self.assertEqual(len(available_ids), initial_count - 1)

    def test_p2_can_select_after_p1(self):
        """P2 consegue selecionar um starter diferente após P1 ter selecionado."""
        state, p1_id, p2_id = _init_two_player_game()
        starters = self._get_starters(state)

        state = engine.select_starter(state, p1_id, starters[0]['id'])
        self.assertIsNotNone(state)
        self.assertEqual(state['turn']['current_player_id'], p2_id)

        state = engine.select_starter(state, p2_id, starters[1]['id'])
        self.assertIsNotNone(state)
        self.assertEqual(state['turn']['phase'], 'roll')

        p2 = next(p for p in state['players'] if p['id'] == p2_id)
        self.assertIsNotNone(p2['starter_pokemon'])
        self.assertEqual(p2['starter_pokemon']['id'], starters[1]['id'])

    def test_p1_cannot_select_twice(self):
        """P1 não pode selecionar starter duas vezes."""
        state, p1_id, p2_id = _init_two_player_game()
        starters = self._get_starters(state)

        state = engine.select_starter(state, p1_id, starters[0]['id'])
        result = engine.select_starter(state, p1_id, starters[1]['id'])
        self.assertIsNone(result)

    def test_available_starters_cleared_after_all_choose(self):
        """available_starters é removido do estado quando todos escolheram."""
        state, p1_id, p2_id = _init_two_player_game()
        starters = self._get_starters(state)

        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])

        self.assertNotIn('available_starters', state['turn'])


class TestItems(TestCase):

    def _state_after_starters(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        return state, p1_id, p2_id

    def test_bill_sets_roll_modifier(self):
        state, p1_id, _ = self._state_after_starters()
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['items'].append({'key': 'bill', 'quantity': 1})

        new_state, result = engine.use_item(state, p1_id, 'bill')

        self.assertIsNotNone(new_state)
        self.assertEqual(result['amount'], 2)
        self.assertEqual(new_state['turn']['roll_item_modifier']['item_key'], 'bill')

    def test_prof_oak_reduces_roll_without_going_below_zero(self):
        state, p1_id, _ = self._state_after_starters()
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['items'].append({'key': 'prof_oak', 'quantity': 1})

        modified_state, _ = engine.use_item(state, p1_id, 'prof_oak')
        consumed_state, adjusted, modifier = engine.consume_roll_modifier(modified_state, p1_id, 1)

        self.assertEqual(adjusted, 0)
        self.assertEqual(modifier['item_key'], 'prof_oak')
        self.assertIsNone(consumed_state['turn']['roll_item_modifier'])

    def test_miracle_stone_evolves_using_existing_chain(self):
        state, p1_id, _ = self._state_after_starters()
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['pokemon'] = [_make_pokemon(name='Bulbasaur', evolves_to=2)]
        player['items'].append({'key': 'miracle_stone', 'quantity': 1})

        new_state, result = engine.use_item(state, p1_id, 'miracle_stone', pokemon_index=0)

        self.assertIsNotNone(new_state)
        self.assertEqual(result['evolved_to'], 'Ivysaur')

    def test_pluspower_is_consumed_and_applied_to_battle_choice(self):
        state, p1_id, p2_id = self._state_after_starters()
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        p2 = next(p for p in state['players'] if p['id'] == p2_id)
        p1['items'].append({'key': 'pluspower', 'quantity': 1})
        p1['pokemon'] = [_make_pokemon(name='Eevee', bp=4)]
        p2['pokemon'] = [_make_pokemon(name='Zubat', bp=2)]
        state['turn']['phase'] = 'battle'
        state['turn']['battle'] = {
            'mode': 'player',
            'challenger_id': p1_id,
            'defender_id': p2_id,
            'challenger_choice': None,
            'defender_choice': None,
            'choice_stage': 'challenger',
        }

        prepared_state, result = engine.use_item(state, p1_id, 'pluspower', pokemon_index=0)
        battle_state, _ = engine.register_battle_choice(prepared_state, p1_id, 0)

        self.assertEqual(result['battle_bonus'], 2)
        self.assertEqual(battle_state['turn']['battle']['challenger_choice']['battle_points'], 6)

    def test_debug_add_item_puts_item_in_inventory(self):
        state, p1_id, _ = self._state_after_starters()

        new_state, result = engine.debug_add_item(state, p1_id, 'gust_of_wind', 2)

        player = next(p for p in new_state['players'] if p['id'] == p1_id)
        gust = next(item for item in player['items'] if item['key'] == 'gust_of_wind')
        self.assertEqual(result['quantity'], 2)
        self.assertEqual(gust['quantity'], 2)


# ── Testes de Movimento ──────────────────────────────────────────────────────

class TestMovement(TestCase):

    def _ready_to_roll(self) -> tuple[dict, str, str]:
        """Cria estado pronto para rolar (após seleção de starters)."""
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        return state, p1_id, p2_id

    def test_process_move_updates_position(self):
        state, p1_id, _ = self._ready_to_roll()
        state = engine.process_move(state, p1_id, 3)
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertEqual(p1['position'], 3)

    def test_process_move_records_dice_result(self):
        state, p1_id, _ = self._ready_to_roll()
        # Use dice=1 (grass tile) so turn stays in action phase, dice_result preserved
        state = engine.process_move(state, p1_id, 1)
        self.assertEqual(state['turn']['dice_result'], 1)

    def test_perform_movement_roll_records_movement_roll_history(self):
        state, p1_id, _ = self._ready_to_roll()

        with patch('game.engine.state.roll_movement_dice', return_value=4):
            rolled_state, roll_entry = engine.perform_movement_roll(state, p1_id)

        self.assertEqual(roll_entry['roll_type'], 'movimento')
        self.assertEqual(roll_entry['raw_result'], 4)
        self.assertEqual(roll_entry['final_result'], 4)
        self.assertEqual(rolled_state['turn']['last_roll']['roll_type'], 'movimento')
        self.assertEqual(rolled_state['turn']['roll_history'][-1]['final_result'], 4)

    def test_apply_movement_roll_modifiers_keeps_value_without_abilities(self):
        state, p1_id, _ = self._ready_to_roll()

        resolved_state, resolved = engine.apply_movement_roll_modifiers(state, p1_id, 3)

        self.assertEqual(resolved['raw_result'], 3)
        self.assertEqual(resolved['final_result'], 3)
        self.assertIsNone(resolved['modifier'])
        self.assertEqual(resolved_state['turn'].get('roll_item_modifier'), state['turn'].get('roll_item_modifier'))

    def test_process_move_sets_current_tile(self):
        state, p1_id, _ = self._ready_to_roll()
        state = engine.process_move(state, p1_id, 1)
        self.assertIsNotNone(state['turn']['current_tile'])

    def test_movement_does_not_exceed_board_length(self):
        state, p1_id, _ = self._ready_to_roll()
        # Move player near the end
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        p1['position'] = 167
        state = engine.process_move(state, p1_id, 6)
        p1_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertLessEqual(p1_after['position'], 169)  # max board position

    def test_grass_tile_sets_capture_attempt_without_predeciding_pokemon(self):
        state, p1_id, _ = self._ready_to_roll()
        state = _land_on_tile(state, p1_id, 85)  # route 1 table with supported Pokémon
        self.assertEqual(state['turn']['phase'], 'action')
        self.assertEqual((state['turn'].get('pending_action') or {}).get('type'), 'capture_attempt')
        self.assertIsNone(state['turn']['pending_pokemon'])

    def test_city_tile_grants_full_restore(self):
        state, p1_id, _ = self._ready_to_roll()
        p1_before = next(p for p in state['players'] if p['id'] == p1_id)
        fr_before = p1_before['full_restores']
        state = _land_on_tile(state, p1_id, 8)
        p1_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertEqual(p1_after['full_restores'], fr_before + 1)


class TestTeamRocketTile(TestCase):

    def _ready_state(self) -> tuple[dict, str, str]:
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        return state, p1_id, p2_id

    def _captured_pokemon(self, name: str, *, sequence: int, bp: int = 5, knocked_out: bool = False, evolves_to: int | None = None) -> dict:
        return {
            **_make_pokemon(name=name, bp=bp, evolves_to=evolves_to),
            'acquisition_origin': 'captured',
            'capture_sequence': sequence,
            'capture_context': 'grass',
            'knocked_out': knocked_out,
        }

    def _reward_pokemon(self, name: str, *, bp: int = 5) -> dict:
        return {
            **_make_pokemon(name=name, bp=bp),
            'acquisition_origin': 'reward',
            'capture_sequence': None,
            'capture_context': 'victory',
        }

    def _set_team(self, state: dict, player_id: str, pokemon_list: list[dict]) -> dict:
        player = next(p for p in state['players'] if p['id'] == player_id)
        player['pokemon'] = copy.deepcopy(pokemon_list)
        used_slots = sum(pokemon_slot_cost(pokemon) for pokemon in player['pokemon'])
        used_slots += pokemon_slot_cost(player.get('starter_pokemon'))
        player['pokeballs'] = max(0, get_starting_resource_defaults()['pokeballs'] - used_slots)
        sync_player_inventory(player)
        return player

    def test_team_rocket_forces_stop_and_rolls_separately_from_movement(self):
        state, p1_id, p2_id = self._ready_state()
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 36

        with patch('game.engine.state.roll_movement_dice', return_value=4), \
             patch('game.engine.state.roll_team_rocket_dice', return_value=6):
            rolled_state, roll_entry = engine.perform_movement_roll(state, p1_id)
            new_state = engine.process_move(rolled_state, p1_id, int(roll_entry['final_result']))

        player_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after['position'], 38)
        self.assertEqual(new_state['turn']['current_player_id'], p2_id)
        recent_rolls = new_state['turn']['roll_history'][-2:]
        self.assertEqual([entry['roll_type'] for entry in recent_rolls], ['movimento', 'Equipe Rocket'])
        self.assertEqual(recent_rolls[1]['context'], 'team_rocket_tile')

    def test_team_rocket_roll_1_steals_only_captured_pokemon_and_keeps_starter(self):
        state, p1_id, _ = self._ready_state()
        player = self._set_team(state, p1_id, [self._captured_pokemon('Caterpie', sequence=1, bp=2)])
        player['position'] = 37
        starter_name = player['starter_pokemon']['name']

        with patch('game.engine.state.roll_team_rocket_dice', return_value=1):
            state = engine.process_move(state, p1_id, 1)

        player_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after['position'], 38)
        self.assertEqual(player_after['starter_pokemon']['name'], starter_name)
        self.assertEqual(player_after['pokemon'], [])
        self.assertEqual(player_after['pokeball_slots_used'], pokemon_slot_cost(player_after['starter_pokemon']))

    def test_team_rocket_roll_2_steals_only_the_last_captured_pokemon(self):
        state, p1_id, _ = self._ready_state()
        player = self._set_team(state, p1_id, [
            self._captured_pokemon('Pidgey', sequence=1, bp=3),
            self._reward_pokemon('Lapras', bp=6),
            self._captured_pokemon('Bulbasaur', sequence=2, bp=4),
            self._captured_pokemon('Squirtle', sequence=3, bp=4),
        ])
        player['position'] = 37

        with patch('game.engine.state.roll_team_rocket_dice', return_value=2):
            state = engine.process_move(state, p1_id, 1)

        player_after = next(p for p in state['players'] if p['id'] == p1_id)
        remaining_names = [pokemon['name'] for pokemon in player_after['pokemon']]
        self.assertEqual(remaining_names, ['Pidgey', 'Lapras', 'Bulbasaur'])
        self.assertNotIn('Squirtle', remaining_names)
        self.assertIn('Lapras', remaining_names)

    def test_team_rocket_roll_3_with_only_starter_does_not_remove_anything(self):
        state, p1_id, p2_id = self._ready_state()
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 37
        starter_name = player['starter_pokemon']['name']

        with patch('game.engine.state.roll_team_rocket_dice', return_value=3):
            state = engine.process_move(state, p1_id, 1)

        player_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after['starter_pokemon']['name'], starter_name)
        self.assertEqual(len(player_after['pokemon']), 0)
        self.assertEqual(state['turn']['current_player_id'], p2_id)
        self.assertTrue(any('não tinha Pokémon capturado elegível' in entry['message'] for entry in state['log']))

    def test_team_rocket_rolls_4_to_6_do_not_remove_any_pokemon(self):
        for rocket_roll in (4, 5, 6):
            with self.subTest(rocket_roll=rocket_roll):
                state, p1_id, _ = self._ready_state()
                player = self._set_team(state, p1_id, [
                    self._captured_pokemon('Oddish', sequence=1, bp=3),
                    self._captured_pokemon('Psyduck', sequence=2, bp=3),
                ])
                player['position'] = 37

                with patch('game.engine.state.roll_team_rocket_dice', return_value=rocket_roll):
                    state = engine.process_move(state, p1_id, 1)

                player_after = next(p for p in state['players'] if p['id'] == p1_id)
                self.assertEqual([pokemon['name'] for pokemon in player_after['pokemon']], ['Oddish', 'Psyduck'])

    def test_team_rocket_steals_evolved_last_captured_pokemon_by_capture_sequence(self):
        state, p1_id, _ = self._ready_state()
        player = self._set_team(state, p1_id, [
            self._captured_pokemon('Pidgey', sequence=1, bp=3),
            self._captured_pokemon('Bulbasaur', sequence=2, bp=4, evolves_to=2),
        ])
        player['position'] = 37

        evolved = engine._try_evolve(  # noqa: SLF001 - valida persistência do metadado real na engine
            state,
            p1_id,
            {**player['pokemon'][1], 'battle_slot_key': 'pokemon:1'},
        )
        self.assertEqual(evolved['name'], 'Ivysaur')
        self.assertEqual(player['pokemon'][1]['capture_sequence'], 2)

        with patch('game.engine.state.roll_team_rocket_dice', return_value=1):
            state = engine.process_move(state, p1_id, 1)

        player_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertEqual([pokemon['name'] for pokemon in player_after['pokemon']], ['Pidgey'])

    def test_team_rocket_can_steal_last_captured_pokemon_even_when_knocked_out(self):
        state, p1_id, _ = self._ready_state()
        player = self._set_team(state, p1_id, [
            self._captured_pokemon('Geodude', sequence=1, bp=4),
            self._captured_pokemon('Gastly', sequence=2, bp=4, knocked_out=True),
        ])
        player['position'] = 37

        with patch('game.engine.state.roll_team_rocket_dice', return_value=1):
            state = engine.process_move(state, p1_id, 1)

        player_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertEqual([pokemon['name'] for pokemon in player_after['pokemon']], ['Geodude'])


# ── Testes de Ginásio ────────────────────────────────────────────────────────

class TestGymBattles(TestCase):

    def _ready_state(self) -> tuple[dict, str, str]:
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        state['decks']['event_deck'] = []
        state['decks']['event_discard'] = []
        return state, p1_id, p2_id

    def _set_team(self, state: dict, player_id: str, pokemon_list: list[dict]) -> dict:
        player = next(p for p in state['players'] if p['id'] == player_id)
        player['starter_pokemon'] = None
        player['pokemon'] = copy.deepcopy(pokemon_list)
        return player

    def _prime_turn(self, state: dict, player_id: str) -> dict:
        state['turn']['current_player_id'] = player_id
        state['turn']['phase'] = 'roll'
        state['turn']['battle'] = None
        state['turn']['pending_action'] = None
        state['turn']['pending_event'] = None
        state['turn']['pending_pokemon'] = None
        return state

    def _simple_victory_card(self) -> dict:
        return {
            'id': 99001,
            'title': 'Simple Gym Victory',
            'description': 'Reward card used in tests.',
            'category': 'special_event',
        }

    def test_first_approach_forces_stop_at_gym(self):
        state, p1_id, _ = self._ready_state()
        self._set_team(state, p1_id, [{**_make_pokemon(name='Squirtle', bp=6), 'types': ['Water']}])
        self._prime_turn(state, p1_id)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 23

        new_state = engine.process_move(state, p1_id, 6)

        player_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after['position'], 24)
        self.assertEqual(new_state['turn']['phase'], 'battle')
        self.assertEqual(new_state['turn']['battle']['mode'], 'gym')
        self.assertEqual(new_state['turn']['battle']['gym_id'], 'brock')
        self.assertIn('brock', player_after['gyms_attempted'])

    def test_gym_victory_awards_badge_master_points_victory_card_and_heal(self):
        state, p1_id, _ = self._ready_state()
        self._set_team(state, p1_id, [
            {**_make_pokemon(name='Pidgey', bp=3), 'types': ['Flying']},
            {**_make_pokemon(name='Bulbasaur', bp=5, evolves_to=2), 'types': ['Grass']},
        ])
        state['decks']['victory_deck'] = [self._simple_victory_card()]
        state['decks']['victory_discard'] = []
        self._prime_turn(state, p1_id)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 48

        with patch('game.engine.state.apply_victory_effect', side_effect=lambda game_state, *_args: (game_state, {'category': 'noop'})), \
             patch('game.engine.state.roll_battle_dice', side_effect=[1, 3, 6, 1, 6, 1]):
            state = engine.process_move(state, p1_id, 1)
            self.assertEqual(state['turn']['battle']['defender_choice']['name'], 'Horsea')
            state, _ = engine.register_battle_choice(state, p1_id, 0)
            state, result = engine.register_battle_roll(state, p1_id)
            self.assertTrue(result['needs_new_choice'])
            state, _ = engine.register_battle_choice(state, p1_id, 1)
            state, result = engine.register_battle_roll(state, p1_id)
            self.assertEqual(state['turn']['battle']['defender_choice']['name'], 'Vaporeon')
            state, result = engine.register_battle_roll(state, p1_id)

        player_after_battle = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertTrue(result['gym_victory'])
        self.assertIn('Cascade Badge', [b['name'] if isinstance(b, dict) else b for b in player_after_battle['badges']])
        pokemon_mp = sum(p.get('master_points', 0) for p in player_after_battle.get('pokemon', []))
        self.assertEqual(player_after_battle['master_points'], pokemon_mp + 20)
        self.assertEqual(state['turn']['pending_action']['type'], 'gym_heal')
        self.assertTrue(player_after_battle['pokemon'][0]['knocked_out'])

        state, heal_result = engine.resolve_pending_action(state, p1_id, 'pokemon:0')
        player_after_heal = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertTrue(heal_result['success'])
        self.assertFalse(player_after_heal['pokemon'][0]['knocked_out'])
        self.assertEqual(len(state['decks']['victory_discard']), 1)

    def test_gym_choice_uses_requested_second_pokemon_slot(self):
        state, p1_id, _ = self._ready_state()
        self._set_team(state, p1_id, [
            {**_make_pokemon(name='Pidgey', bp=3), 'types': ['Flying']},
            {**_make_pokemon(name='Bulbasaur', bp=5), 'types': ['Grass']},
            {**_make_pokemon(name='Squirtle', bp=4), 'types': ['Water']},
        ])
        self._prime_turn(state, p1_id)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 48

        state = engine.process_move(state, p1_id, 1)
        state, _ = engine.register_battle_choice(state, p1_id, pokemon_slot_key='pokemon:1')

        self.assertEqual(state['turn']['battle']['challenger_choice']['name'], 'Bulbasaur')
        self.assertEqual(state['turn']['battle']['challenger_choice']['battle_slot_key'], 'pokemon:1')

    def test_gym_choice_uses_requested_third_pokemon_slot(self):
        state, p1_id, _ = self._ready_state()
        self._set_team(state, p1_id, [
            {**_make_pokemon(name='Pidgey', bp=3), 'types': ['Flying']},
            {**_make_pokemon(name='Bulbasaur', bp=5), 'types': ['Grass']},
            {**_make_pokemon(name='Squirtle', bp=4), 'types': ['Water']},
        ])
        self._prime_turn(state, p1_id)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 48

        state = engine.process_move(state, p1_id, 1)
        state, _ = engine.register_battle_choice(state, p1_id, pokemon_slot_key='pokemon:2')

        self.assertEqual(state['turn']['battle']['challenger_choice']['name'], 'Squirtle')
        self.assertEqual(state['turn']['battle']['challenger_choice']['battle_slot_key'], 'pokemon:2')

    def test_gym_loss_returns_player_to_previous_pokemon_center(self):
        state, p1_id, p2_id = self._ready_state()
        self._set_team(state, p1_id, [{**_make_pokemon(name='Rattata', bp=1), 'types': ['Normal']}])
        self._prime_turn(state, p1_id)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 23
        player['last_pokemon_center'] = {
            'tile_id': 20,
            'tile_name': 'Victory Road / Pewter Approach - Pokemon Center',
            'visit_kind': 'passed',
        }

        with patch('game.engine.state.roll_battle_dice', side_effect=[1, 6]):
            state = engine.process_move(state, p1_id, 1)
            state, _ = engine.register_battle_choice(state, p1_id, 0)
            state, result = engine.register_battle_roll(state, p1_id)

        player_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertFalse(result['gym_victory'])
        self.assertEqual(player_after['position'], 20)
        self.assertEqual(result['returned_to_tile_id'], 20)
        self.assertTrue(player_after['pokemon'][0]['knocked_out'])
        self.assertEqual(state['turn']['current_player_id'], p1_id)
        self.assertEqual(state['turn']['pending_action']['type'], 'pokecenter_heal')
        self.assertEqual(state['turn']['pending_action']['remaining_heals'], 1)

        state, heal_result = engine.resolve_pending_action(state, p1_id, 'pokemon:0')
        player_after_heal = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertTrue(heal_result['success'])
        self.assertFalse(player_after_heal['pokemon'][0]['knocked_out'])
        self.assertEqual(state['turn']['current_player_id'], p2_id)

    def test_failed_gym_is_not_forced_when_passing_by_again(self):
        state, p1_id, _ = self._ready_state()
        self._set_team(state, p1_id, [{**_make_pokemon(name='Rattata', bp=1), 'types': ['Normal']}])
        self._prime_turn(state, p1_id)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 23

        with patch('game.engine.state.roll_battle_dice', side_effect=[1, 6]):
            state = engine.process_move(state, p1_id, 1)
            state, _ = engine.register_battle_choice(state, p1_id, 0)
            state, _ = engine.register_battle_roll(state, p1_id)

        self._prime_turn(state, p1_id)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 23
        state = engine.process_move(state, p1_id, 6)
        player_after = next(p for p in state['players'] if p['id'] == p1_id)

        self.assertEqual(player_after['position'], 29)
        self.assertNotEqual((state['turn'].get('battle') or {}).get('mode'), 'gym')

    def test_player_landing_on_gym_without_available_pokemon_is_sent_back_again(self):
        state, p1_id, p2_id = self._ready_state()
        self._set_team(state, p1_id, [{**_make_pokemon(name='Rattata', bp=1), 'types': ['Normal']}])
        self._prime_turn(state, p1_id)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 23
        player['last_pokemon_center'] = {
            'tile_id': 20,
            'tile_name': 'Victory Road / Pewter Approach - Pokemon Center',
            'visit_kind': 'passed',
        }

        with patch('game.engine.state.roll_battle_dice', side_effect=[1, 6]):
            state = engine.process_move(state, p1_id, 1)
            state, _ = engine.register_battle_choice(state, p1_id, 0)
            state, _ = engine.register_battle_roll(state, p1_id)

        self._prime_turn(state, p1_id)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 23
        state = engine.process_move(state, p1_id, 1)

        player_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after['position'], 20)
        self.assertEqual(state['turn']['phase'], 'action')
        self.assertEqual(state['turn']['pending_action']['type'], 'pokecenter_heal')
        self.assertTrue(player_after['pokemon'][0]['knocked_out'])

        state, heal_result = engine.resolve_pending_action(state, p1_id, 'pokemon:0')
        player_after_heal = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertTrue(heal_result['success'])
        self.assertFalse(player_after_heal['pokemon'][0]['knocked_out'])
        self.assertEqual(state['turn']['current_player_id'], p2_id)

    def test_gym_defers_evolution_until_battle_finishes(self):
        state, p1_id, _ = self._ready_state()
        self._set_team(state, p1_id, [{**_make_pokemon(name='Bulbasaur', bp=5, evolves_to=2), 'types': ['Grass']}])
        state['decks']['victory_deck'] = [self._simple_victory_card()]
        state['decks']['victory_discard'] = []
        self._prime_turn(state, p1_id)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 48

        with patch('game.engine.state.apply_victory_effect', side_effect=lambda game_state, *_args: (game_state, {'category': 'noop'})), \
             patch('game.engine.state.roll_battle_dice', side_effect=[6, 1, 6, 1]):
            state = engine.process_move(state, p1_id, 1)
            state, _ = engine.register_battle_choice(state, p1_id, 0)
            state, result = engine.register_battle_roll(state, p1_id)

            player_mid_battle = next(p for p in state['players'] if p['id'] == p1_id)
            self.assertFalse(result['battle_finished'])
            self.assertEqual(player_mid_battle['pokemon'][0]['name'], 'Bulbasaur')
            self.assertEqual(state['turn']['battle']['challenger_choice']['name'], 'Bulbasaur')

            state, result = engine.register_battle_roll(state, p1_id)

        player_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertTrue(result['gym_victory'])
        self.assertEqual(player_after['pokemon'][0]['name'], 'Ivysaur')

    def test_gym_switches_player_pokemon_and_tracks_leader_order(self):
        state, p1_id, _ = self._ready_state()
        self._set_team(state, p1_id, [
            {**_make_pokemon(name='Pidgey', bp=3), 'types': ['Flying']},
            {**_make_pokemon(name='Bulbasaur', bp=5), 'types': ['Grass']},
        ])
        self._prime_turn(state, p1_id)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 48

        with patch('game.engine.state.roll_battle_dice', side_effect=[1, 3, 6, 1]):
            state = engine.process_move(state, p1_id, 1)
            state, _ = engine.register_battle_choice(state, p1_id, 0)
            state, result = engine.register_battle_roll(state, p1_id)

            self.assertTrue(result['needs_new_choice'])
            self.assertEqual(state['turn']['battle']['defender_choice']['name'], 'Horsea')
            self.assertIn('pokemon:0', state['turn']['battle']['defeated_player_slots'])

            state, _ = engine.register_battle_choice(state, p1_id, 1)
            state, result = engine.register_battle_roll(state, p1_id)

        self.assertFalse(result['battle_finished'])
        self.assertEqual(state['turn']['battle']['defender_choice']['name'], 'Vaporeon')
        self.assertEqual(state['turn']['battle']['challenger_choice']['name'], 'Bulbasaur')

    def test_gym_reselection_after_knockout_uses_requested_slot_without_fallback(self):
        state, p1_id, _ = self._ready_state()
        self._set_team(state, p1_id, [
            {**_make_pokemon(name='Pidgey', bp=3), 'types': ['Flying']},
            {**_make_pokemon(name='Bulbasaur', bp=5), 'types': ['Grass']},
            {**_make_pokemon(name='Squirtle', bp=4), 'types': ['Water']},
        ])
        self._prime_turn(state, p1_id)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 48

        with patch('game.engine.state.roll_battle_dice', side_effect=[1, 3]):
            state = engine.process_move(state, p1_id, 1)
            state, _ = engine.register_battle_choice(state, p1_id, pokemon_slot_key='pokemon:0')
            state, result = engine.register_battle_roll(state, p1_id)

        self.assertTrue(result['needs_new_choice'])
        state, _ = engine.register_battle_choice(state, p1_id, pokemon_slot_key='pokemon:2')
        self.assertEqual(state['turn']['battle']['challenger_choice']['name'], 'Squirtle')
        self.assertEqual(state['turn']['battle']['challenger_choice']['battle_slot_key'], 'pokemon:2')

    def test_gym_type_bonus_and_items_still_apply(self):
        state, p1_id, _ = self._ready_state()
        player = self._set_team(state, p1_id, [{**_make_pokemon(name='Bulbasaur', bp=5), 'types': ['Grass']}])
        player['items'].append({'key': 'pluspower', 'quantity': 1})
        self._prime_turn(state, p1_id)
        player['position'] = 48

        with patch('game.engine.state.roll_battle_dice', side_effect=[2, 1]):
            state = engine.process_move(state, p1_id, 1)
            state, item_result = engine.use_item(state, p1_id, 'pluspower', pokemon_index=0)
            state, _ = engine.register_battle_choice(state, p1_id, 0)
            self.assertEqual(state['turn']['battle']['challenger_choice']['battle_points'], 7)
            state, result = engine.register_battle_roll(state, p1_id)

        self.assertEqual(item_result['battle_bonus'], 2)
        self.assertGreater(result['challenger_score'], result['defender_score'])
        self.assertEqual(result['challenger_type_bonus'], 1)

    def test_gym_battle_logs_rolls_scores_and_round_winner(self):
        state, p1_id, _ = self._ready_state()
        self._set_team(state, p1_id, [{**_make_pokemon(name='Pidgey', bp=3), 'types': ['Flying']}])
        self._prime_turn(state, p1_id)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 48

        with patch('game.engine.state.roll_battle_dice', side_effect=[6, 3]):
            state = engine.process_move(state, p1_id, 1)
            state, _ = engine.register_battle_choice(state, p1_id, 0)
            state, result = engine.register_battle_roll(state, p1_id)

        self.assertIsNotNone(result)
        messages = [entry['message'] for entry in state['log']]
        self.assertIn('Ash rolou 6 com Pidgey.', messages)
        self.assertIn('Misty rolou 3 com Horsea.', messages)
        self.assertIn('Resultado final — Ash: 6 x (3 + 0) = 18 | Misty: 3 x (5 + 0) = 15.', messages)
        self.assertIn('Ash venceu o round.', messages)

    def test_gym_battle_tie_requires_new_roll(self):
        state, p1_id, _ = self._ready_state()
        self._set_team(state, p1_id, [{**_make_pokemon(name='Pidgey', bp=3), 'types': ['Flying']}])
        self._prime_turn(state, p1_id)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 48

        with patch('game.engine.state.roll_battle_dice', side_effect=[5, 3]):
            state = engine.process_move(state, p1_id, 1)
            state, _ = engine.register_battle_choice(state, p1_id, 0)
            state, result = engine.register_battle_roll(state, p1_id)

        self.assertTrue(result['reroll_required'])
        self.assertTrue(result['tied_round'])
        self.assertEqual(state['turn']['phase'], 'battle')
        self.assertEqual(state['turn']['battle']['sub_phase'], 'rolling')
        self.assertIsNone(state['turn']['battle']['challenger_roll'])
        self.assertIsNone(state['turn']['battle']['defender_roll'])
        self.assertEqual(state['turn']['battle']['challenger_choice']['name'], 'Pidgey')
        self.assertEqual(state['turn']['battle']['defender_choice']['name'], 'Horsea')

    def test_gym_battle_does_not_change_pokeballs_without_capture_effects(self):
        state, p1_id, _ = self._ready_state()
        self._set_team(state, p1_id, [{**_make_pokemon(name='Bulbasaur', bp=5), 'types': ['Grass']}])
        self._prime_turn(state, p1_id)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 48
        pokeballs_before = player['pokeballs']

        with patch('game.engine.state.roll_battle_dice', side_effect=[6, 1]):
            state = engine.process_move(state, p1_id, 1)
            state, _ = engine.register_battle_choice(state, p1_id, pokemon_slot_key='pokemon:0')
            state, _ = engine.register_battle_roll(state, p1_id)

        player_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after['pokeballs'], pokeballs_before)


class TestKnockoutAndPokecenter(TestCase):

    def _ready_state(self) -> tuple[dict, str, str]:
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        state['decks']['event_deck'] = []
        state['decks']['event_discard'] = []
        return state, p1_id, p2_id

    def _set_team(self, state: dict, player_id: str, pokemon_list: list[dict]) -> dict:
        player = next(p for p in state['players'] if p['id'] == player_id)
        player['starter_pokemon'] = None
        player['pokemon'] = copy.deepcopy(pokemon_list)
        sync_player_inventory(player)
        return player

    def _prime_turn(self, state: dict, player_id: str, phase: str = 'roll') -> dict:
        state['turn']['current_player_id'] = player_id
        state['turn']['phase'] = phase
        state['turn']['battle'] = None
        state['turn']['pending_action'] = None
        state['turn']['pending_event'] = None
        state['turn']['pending_pokemon'] = None
        state['turn']['pending_item_choice'] = None
        state['turn']['pending_release_choice'] = None
        return state

    def test_pvp_defeat_marks_pokemon_as_knocked_out(self):
        state, p1_id, p2_id = self._ready_state()
        self._set_team(state, p1_id, [{**_make_pokemon(name='Charizard', bp=9), 'types': ['Fire']}])
        self._set_team(state, p2_id, [{**_make_pokemon(name='Rattata', bp=1), 'types': ['Normal']}])
        self._prime_turn(state, p1_id)

        state = engine.start_duel(state, p1_id, p2_id)
        state, _ = engine.register_battle_choice(state, p2_id, 0)
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        with patch('game.engine.state.roll_battle_dice', side_effect=[6, 1]):
            state, _ = engine.register_battle_roll(state, p1_id)
            state, result = engine.register_battle_roll(state, p2_id)

        defeated_player = next(p for p in state['players'] if p['id'] == p2_id)
        self.assertTrue(defeated_player['pokemon'][0]['knocked_out'])
        self.assertEqual(result['knocked_out_pokemon'], 'Rattata')

    def test_event_battle_defeat_marks_pokemon_as_knocked_out(self):
        state, p1_id, p2_id = self._ready_state()
        player = self._set_team(state, p1_id, [{**_make_pokemon(name='Pikachu', bp=2), 'types': ['Electric']}])
        player['position'] = 12
        player['last_pokemon_center'] = {
            'tile_id': 8,
            'tile_name': 'Viridian City / Route 1 - Pokemon Center',
            'visit_kind': 'passed',
        }
        self._prime_turn(state, p1_id)

        state = engine._start_trainer_battle(  # noqa: SLF001 - valida o fluxo real da batalha de evento
            state,
            p1_id,
            {'trainer_name': 'Team Rocket', 'trainer_bp': 6, 'reward_plan': {}},
            source='event_card',
        )
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        with patch('game.engine.state.roll_battle_dice', side_effect=[1, 6]):
            state, result = engine.register_battle_roll(state, p1_id)

        player_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertTrue(player_after['pokemon'][0]['knocked_out'])
        self.assertEqual(result['mode'], 'trainer')
        self.assertEqual(result['returned_to_tile_id'], 8)
        self.assertEqual(state['turn']['pending_action']['type'], 'pokecenter_heal')
        self.assertEqual(state['turn']['current_player_id'], p1_id)

        state, heal_result = engine.resolve_pending_action(state, p1_id, 'pokemon:0')
        player_after_heal = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertTrue(heal_result['success'])
        self.assertFalse(player_after_heal['pokemon'][0]['knocked_out'])
        self.assertEqual(state['turn']['current_player_id'], p2_id)

    def test_knocked_out_pokemon_is_not_selectable_for_new_battle(self):
        state, p1_id, p2_id = self._ready_state()
        self._set_team(state, p1_id, [{**_make_pokemon(name='Charizard', bp=9), 'types': ['Fire']}])
        self._set_team(state, p2_id, [
            {**_make_pokemon(name='Magikarp', bp=1), 'types': ['Water'], 'knocked_out': True},
            {**_make_pokemon(name='Squirtle', bp=4), 'types': ['Water']},
        ])
        self._prime_turn(state, p1_id)

        state = engine.start_duel(state, p1_id, p2_id)
        state, _ = engine.register_battle_choice(state, p2_id, 0)

        self.assertEqual(state['turn']['battle']['defender_choice']['name'], 'Squirtle')

    def test_passing_through_pokecenter_allows_healing_exactly_one_knocked_out_pokemon(self):
        state, p1_id, _ = self._ready_state()
        self._set_team(state, p1_id, [
            {**_make_pokemon(name='Bulbasaur', bp=4), 'types': ['Grass'], 'knocked_out': True},
            {**_make_pokemon(name='Charmander', bp=4), 'types': ['Fire'], 'knocked_out': True},
        ])
        self._prime_turn(state, p1_id)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 6

        state = engine.process_move(state, p1_id, 3)
        player_after_move = next(p for p in state['players'] if p['id'] == p1_id)

        pending = state['turn']['pending_action']
        self.assertEqual(pending['type'], 'pokecenter_heal')
        self.assertEqual(pending['remaining_heals'], 1)
        self.assertEqual(player_after_move['last_pokemon_center']['tile_id'], 8)
        self.assertEqual(player_after_move['last_pokemon_center']['visit_kind'], 'passed')

        state, result = engine.resolve_pending_action(state, p1_id, 'pokemon:0')
        player_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertTrue(result['success'])
        self.assertFalse(player_after['pokemon'][0]['knocked_out'])
        self.assertTrue(player_after['pokemon'][1]['knocked_out'])
        self.assertEqual(state['turn']['current_tile']['id'], 9)

    def test_stopping_on_pokecenter_allows_healing_up_to_three_knocked_out_pokemon(self):
        state, p1_id, _ = self._ready_state()
        self._set_team(state, p1_id, [
            {**_make_pokemon(name='Bulbasaur', bp=4), 'types': ['Grass'], 'knocked_out': True},
            {**_make_pokemon(name='Charmander', bp=4), 'types': ['Fire'], 'knocked_out': True},
            {**_make_pokemon(name='Squirtle', bp=4), 'types': ['Water'], 'knocked_out': True},
            {**_make_pokemon(name='Pidgey', bp=3), 'types': ['Flying'], 'knocked_out': True},
        ])
        self._prime_turn(state, p1_id)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 5
        full_restores_before = player['full_restores']

        state = engine.process_move(state, p1_id, 3)
        player_after_move = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after_move['last_pokemon_center']['tile_id'], 8)
        self.assertEqual(player_after_move['last_pokemon_center']['visit_kind'], 'stopped')
        self.assertEqual(state['turn']['pending_action']['type'], 'pokecenter_heal')

        state, _ = engine.resolve_pending_action(state, p1_id, 'pokemon:0')
        state, _ = engine.resolve_pending_action(state, p1_id, 'pokemon:1')
        state, result = engine.resolve_pending_action(state, p1_id, 'pokemon:2')

        player_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertTrue(result['success'])
        self.assertFalse(player_after['pokemon'][0]['knocked_out'])
        self.assertFalse(player_after['pokemon'][1]['knocked_out'])
        self.assertFalse(player_after['pokemon'][2]['knocked_out'])
        self.assertTrue(player_after['pokemon'][3]['knocked_out'])
        self.assertEqual(player_after['full_restores'], full_restores_before + 1)

    def test_full_restore_removes_knockout(self):
        state, p1_id, _ = self._ready_state()
        player = self._set_team(state, p1_id, [{**_make_pokemon(name='Bulbasaur', bp=4), 'types': ['Grass'], 'knocked_out': True}])
        self._prime_turn(state, p1_id)
        full_restores_before = player['full_restores']

        state, result = engine.use_item(state, p1_id, 'full_restore', pokemon_index=0)

        player_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertIsNotNone(state)
        self.assertTrue(result['cleared_knockout'])
        self.assertFalse(player_after['pokemon'][0]['knocked_out'])
        self.assertEqual(player_after['full_restores'], full_restores_before - 1)

    def test_gym_evolution_after_battle_cures_knockout_and_does_not_happen_mid_battle(self):
        state, p1_id, _ = self._ready_state()
        self._set_team(state, p1_id, [{**_make_pokemon(name='Bulbasaur', bp=6, evolves_to=2), 'types': ['Grass']}])
        self._prime_turn(state, p1_id)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 48

        with patch('game.engine.state.roll_battle_dice', side_effect=[6, 1, 1, 6]):
            state = engine.process_move(state, p1_id, 1)
            state, _ = engine.register_battle_choice(state, p1_id, 0)
            state, first_result = engine.register_battle_roll(state, p1_id)

            player_mid_battle = next(p for p in state['players'] if p['id'] == p1_id)
            self.assertFalse(first_result['battle_finished'])
            self.assertEqual(player_mid_battle['pokemon'][0]['name'], 'Bulbasaur')

            state, final_result = engine.register_battle_roll(state, p1_id)

        player_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertFalse(final_result['gym_victory'])
        self.assertEqual(player_after['pokemon'][0]['name'], 'Ivysaur')
        self.assertFalse(player_after['pokemon'][0]['knocked_out'])

    def test_player_with_no_previous_pokecenter_returns_to_pallet_town(self):
        state, p1_id, p2_id = self._ready_state()
        self._set_team(state, p1_id, [{**_make_pokemon(name='Pikachu', bp=2), 'types': ['Electric']}])
        self._prime_turn(state, p1_id)

        state = engine._start_trainer_battle(  # noqa: SLF001 - valida fallback sem PokéCenter prévio
            state,
            p1_id,
            {'trainer_name': 'Team Rocket', 'trainer_bp': 6, 'reward_plan': {}},
            source='event_card',
        )
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        with patch('game.engine.state.roll_battle_dice', side_effect=[1, 6]):
            state, result = engine.register_battle_roll(state, p1_id)

        player_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after['position'], 0)
        self.assertEqual(result['returned_to_tile_name'], 'Pallet Town')
        self.assertEqual(state['turn']['pending_action']['type'], 'pokecenter_heal')
        self.assertEqual(state['turn']['pending_action']['center_tile_name'], 'Pallet Town')
        self.assertEqual(state['turn']['current_player_id'], p1_id)

        state, heal_result = engine.resolve_pending_action(state, p1_id, 'pokemon:0')
        player_after_heal = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertTrue(heal_result['success'])
        self.assertFalse(player_after_heal['pokemon'][0]['knocked_out'])
        self.assertEqual(state['turn']['current_player_id'], p2_id)

    def test_total_knockout_on_pokecenter_keeps_player_in_place_and_heals_before_turn_passes(self):
        state, p1_id, p2_id = self._ready_state()
        player = self._set_team(state, p1_id, [{**_make_pokemon(name='Pikachu', bp=2), 'types': ['Electric']}])
        self._prime_turn(state, p1_id)
        player['position'] = 8
        player['last_pokemon_center'] = {
            'tile_id': 20,
            'tile_name': 'Victory Road / Pewter Approach - Pokemon Center',
            'visit_kind': 'passed',
        }

        state = engine._start_trainer_battle(
            state,
            p1_id,
            {'trainer_name': 'Team Rocket', 'trainer_bp': 6, 'reward_plan': {}},
            source='event_card',
        )
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        with patch('game.engine.state.roll_battle_dice', side_effect=[1, 6]):
            state, result = engine.register_battle_roll(state, p1_id)

        player_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after['position'], 8)
        self.assertEqual(result['returned_to_tile_id'], 8)
        self.assertTrue(result['stayed_on_safe_tile'])
        self.assertEqual(state['turn']['current_player_id'], p1_id)
        self.assertEqual(state['turn']['pending_action']['visit_kind'], 'remained')

        state, heal_result = engine.resolve_pending_action(state, p1_id, 'pokemon:0')
        player_after_heal = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertTrue(heal_result['success'])
        self.assertFalse(player_after_heal['pokemon'][0]['knocked_out'])
        self.assertEqual(state['turn']['current_player_id'], p2_id)

    def test_total_knockout_on_pallet_keeps_player_in_place_and_heals_before_turn_passes(self):
        state, p1_id, p2_id = self._ready_state()
        player = self._set_team(state, p1_id, [{**_make_pokemon(name='Pikachu', bp=2), 'types': ['Electric']}])
        self._prime_turn(state, p1_id)
        player['position'] = 0
        player['last_pokemon_center'] = {
            'tile_id': 8,
            'tile_name': 'Viridian City / Route 1 - Pokemon Center',
            'visit_kind': 'passed',
        }

        state = engine._start_trainer_battle(
            state,
            p1_id,
            {'trainer_name': 'Team Rocket', 'trainer_bp': 6, 'reward_plan': {}},
            source='event_card',
        )
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        with patch('game.engine.state.roll_battle_dice', side_effect=[1, 6]):
            state, result = engine.register_battle_roll(state, p1_id)

        player_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after['position'], 0)
        self.assertEqual(result['returned_to_tile_id'], 0)
        self.assertTrue(result['stayed_on_safe_tile'])
        self.assertEqual(state['turn']['pending_action']['center_tile_name'], 'Pallet Town')
        self.assertEqual(state['turn']['pending_action']['visit_kind'], 'remained')
        self.assertEqual(state['turn']['current_player_id'], p1_id)

        state, heal_result = engine.resolve_pending_action(state, p1_id, 'pokemon:0')
        player_after_heal = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertTrue(heal_result['success'])
        self.assertFalse(player_after_heal['pokemon'][0]['knocked_out'])
        self.assertEqual(state['turn']['current_player_id'], p2_id)

    def test_event_trainer_battle_tie_requires_new_roll(self):
        state, p1_id, _ = self._ready_state()
        self._set_team(state, p1_id, [{**_make_pokemon(name='Pikachu', bp=3), 'types': ['Electric']}])
        self._prime_turn(state, p1_id)

        state = engine._start_trainer_battle(  # noqa: SLF001 - valida o fluxo real da batalha de evento
            state,
            p1_id,
            {'trainer_name': 'Team Rocket', 'trainer_bp': 6, 'reward_plan': {}},
            source='event_card',
        )
        state, _ = engine.register_battle_choice(state, p1_id, 0)

        with patch('game.engine.state.roll_battle_dice', side_effect=[2, 1, 6, 1]):
            state, tie_result = engine.register_battle_roll(state, p1_id)

            self.assertTrue(tie_result['reroll_required'])
            self.assertTrue(tie_result['tied_round'])
            self.assertEqual(state['turn']['phase'], 'battle')
            self.assertEqual(state['turn']['battle']['sub_phase'], 'rolling')
            self.assertIsNone(state['turn']['battle']['challenger_roll'])
            self.assertIsNone(state['turn']['battle']['defender_roll'])
            self.assertEqual(state['turn']['battle']['challenger_choice']['name'], 'Pikachu')
            self.assertEqual(state['turn']['battle']['defender_choice']['name'], 'Team Rocket')

            state, final_result = engine.register_battle_roll(state, p1_id)

        self.assertFalse(final_result.get('reroll_required', False))
        self.assertEqual(final_result['mode'], 'trainer')
        self.assertEqual(final_result['winner_name'], 'Ash')
        self.assertEqual(state['turn']['phase'], 'roll')
        self.assertIsNone(state['turn']['battle'])

    def test_pvp_total_knockout_waits_for_defender_heal_before_turn_passes(self):
        state, p1_id, p2_id = self._ready_state()
        self._set_team(state, p1_id, [{**_make_pokemon(name='Charizard', bp=9), 'types': ['Fire']}])
        defender = self._set_team(state, p2_id, [{**_make_pokemon(name='Rattata', bp=1), 'types': ['Normal']}])
        defender['position'] = 12
        defender['last_pokemon_center'] = {
            'tile_id': 8,
            'tile_name': 'Viridian City / Route 1 - Pokemon Center',
            'visit_kind': 'passed',
        }
        self._prime_turn(state, p1_id)

        state = engine.start_duel(state, p1_id, p2_id)
        state, _ = engine.register_battle_choice(state, p2_id, 0)
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        with patch('game.engine.state.roll_battle_dice', side_effect=[6, 1]):
            state, _ = engine.register_battle_roll(state, p1_id)
            state, result = engine.register_battle_roll(state, p2_id)

        defender_after = next(p for p in state['players'] if p['id'] == p2_id)
        self.assertEqual(defender_after['position'], 8)
        self.assertEqual(result['returned_to_tile_id'], 8)
        self.assertEqual(state['turn']['current_player_id'], p1_id)
        self.assertEqual(state['turn']['pending_action']['player_id'], p2_id)
        self.assertEqual(state['turn']['pending_action']['remaining_heals'], 1)

        state, heal_result = engine.resolve_pending_action(state, p2_id, 'pokemon:0')
        defender_after_heal = next(p for p in state['players'] if p['id'] == p2_id)
        self.assertTrue(heal_result['success'])
        self.assertFalse(defender_after_heal['pokemon'][0]['knocked_out'])
        self.assertEqual(state['turn']['current_player_id'], p2_id)

    def test_passing_through_pokecenter_without_knocked_out_pokemon_does_not_break_flow(self):
        state, p1_id, _ = self._ready_state()
        self._set_team(state, p1_id, [{**_make_pokemon(name='Bulbasaur', bp=4), 'types': ['Grass']}])
        self._prime_turn(state, p1_id)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 6

        state = engine.process_move(state, p1_id, 3)
        player_after_move = next(p for p in state['players'] if p['id'] == p1_id)

        self.assertEqual(player_after_move['last_pokemon_center']['tile_id'], 8)
        self.assertNotEqual((state['turn'].get('pending_action') or {}).get('type'), 'pokecenter_heal')
        self.assertEqual(state['turn']['current_tile']['id'], 9)

    def test_stopping_on_pokecenter_without_knocked_out_pokemon_does_not_break_flow(self):
        state, p1_id, p2_id = self._ready_state()
        player = self._set_team(state, p1_id, [{**_make_pokemon(name='Bulbasaur', bp=4), 'types': ['Grass']}])
        self._prime_turn(state, p1_id)
        player['position'] = 5
        full_restores_before = player['full_restores']

        state = engine.process_move(state, p1_id, 3)

        player_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after['last_pokemon_center']['tile_id'], 8)
        self.assertNotEqual((state['turn'].get('pending_action') or {}).get('type'), 'pokecenter_heal')
        self.assertEqual(player_after['full_restores'], full_restores_before + 1)
        self.assertEqual(state['turn']['current_player_id'], p2_id)


# ── Testes de Captura ────────────────────────────────────────────────────────

class TestCapture(TestCase):

    def _state_with_pending_pokemon(self) -> tuple[dict, str]:
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        state = _land_on_tile(state, p1_id, 85)
        return state, p1_id

    def _add_team_pokemon(self, state: dict, player_id: str, pokemon_name: str, *, acquisition_origin: str = 'captured') -> dict:
        player = next(p for p in state['players'] if p['id'] == player_id)
        pokemon = copy.deepcopy(load_playable_pokemon_by_name(pokemon_name))
        self.assertIsNotNone(pokemon, f'{pokemon_name} precisa existir no dataset jogável')
        if acquisition_origin == 'captured':
            pokemon = engine._apply_pokemon_acquisition_metadata(  # noqa: SLF001 - helper autoritativo do engine
                pokemon,
                acquisition_origin='captured',
                capture_sequence=engine._next_capture_sequence(player),  # noqa: SLF001 - mantém ordem real de captura
                capture_context='test_capture',
            )
        else:
            pokemon = engine._apply_pokemon_acquisition_metadata(  # noqa: SLF001 - helper autoritativo do engine
                pokemon,
                acquisition_origin=acquisition_origin,
                capture_sequence=None,
                capture_context='test_reward',
            )
        player['pokemon'].append(pokemon)
        player['pokeballs'] = max(0, int(player.get('pokeballs', 0) or 0) - pokemon_slot_cost(pokemon))
        sync_player_inventory(player)
        return pokemon

    def test_capture_deducts_pokeball(self):
        state, p1_id = self._state_with_pending_pokemon()
        p1_before = next(p for p in state['players'] if p['id'] == p1_id)
        pokeballs_before = p1_before['pokeballs']

        new_state, result = engine.capture_pokemon(state, p1_id)
        self.assertIsNotNone(new_state)
        p1_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(p1_after['pokeballs'], pokeballs_before - 1)

    def test_capture_pokeball_count_persists_after_turn_sync(self):
        state, p1_id = self._state_with_pending_pokemon()
        p1_before = next(p for p in state['players'] if p['id'] == p1_id)
        pokeballs_before = p1_before['pokeballs']

        captured_state, _ = engine.capture_pokemon(state, p1_id)
        after_capture = next(p for p in captured_state['players'] if p['id'] == p1_id)
        next_state = engine.end_turn(captured_state)
        after_turn = next(p for p in next_state['players'] if p['id'] == p1_id)

        self.assertEqual(after_capture['pokeballs'], pokeballs_before - 1)
        self.assertEqual(after_turn['pokeballs'], pokeballs_before - 1)

    def test_capture_adds_pokemon_to_collection(self):
        state, p1_id = self._state_with_pending_pokemon()

        with patch('game.engine.state.roll_capture_dice', return_value=4):
            new_state, result = engine.capture_pokemon(state, p1_id)
        self.assertIsNotNone(new_state)
        p1 = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(len(p1['pokemon']), 1)

    def test_capture_marks_pokemon_as_captured_with_sequence(self):
        state, p1_id = self._state_with_pending_pokemon()

        with patch('game.engine.state.roll_capture_dice', return_value=4):
            new_state, _ = engine.capture_pokemon(state, p1_id)

        p1 = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(p1['pokemon'][0]['acquisition_origin'], 'captured')
        self.assertEqual(p1['pokemon'][0]['capture_sequence'], 1)

    def test_capture_adds_master_points(self):
        state, p1_id = self._state_with_pending_pokemon()
        mp = load_playable_pokemon_by_name('Pidgey').get('master_points', 0)
        p1_before = next(p for p in state['players'] if p['id'] == p1_id)
        mp_before = p1_before['master_points']

        with patch('game.engine.state.roll_capture_dice', return_value=4):
            new_state, result = engine.capture_pokemon(state, p1_id)
        p1 = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(p1['master_points'], mp_before + mp)

    def test_capture_with_full_party_enters_release_phase(self):
        state, p1_id = self._state_with_pending_pokemon()
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        incoming_name = 'Pidgey'
        p1['pokeballs'] = 0
        sync_player_inventory(p1)

        with patch('game.engine.state.roll_capture_dice', return_value=4):
            new_state, result = engine.capture_pokemon(state, p1_id)

        self.assertIsNotNone(new_state)
        self.assertTrue(result['requires_release'])
        self.assertEqual(new_state['turn']['phase'], 'release_pokemon')
        self.assertEqual(new_state['turn']['pending_release_choice']['player_id'], p1_id)
        self.assertEqual(new_state['turn']['pending_release_choice']['pokemon']['name'], incoming_name)
        option_slot_keys = {option['slot_key'] for option in new_state['turn']['pending_release_choice']['options']}
        self.assertIn('starter', option_slot_keys)

    def test_capture_fails_without_pending_pokemon(self):
        state, p1_id, _ = _init_two_player_game()
        new_state, error = engine.capture_pokemon(state, p1_id)
        self.assertIsNone(new_state)

    def test_capture_cinnabar_free(self):
        """Cinnabar Lab: captura gratuita sem gastar Pokébola."""
        state, p1_id = self._state_with_pending_pokemon()
        state['turn']['compound_eyes_active'] = True
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        pokeballs_before = p1['pokeballs']

        with patch('game.engine.state.roll_capture_dice', return_value=4):
            new_state, result = engine.capture_pokemon(state, p1_id)
        self.assertIsNotNone(new_state)
        p1_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(p1_after['pokeballs'], pokeballs_before)  # sem custo

    def test_capture_legendary_costs_2_pokeballs(self):
        """Lendário (seafoam/power_plant): custa 2 Pokébolas."""
        state, p1_id = self._state_with_pending_pokemon()
        state['turn']['seafoam_legendary'] = True
        state['turn']['capture_context'] = 'seafoam'
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        pokeballs_before = p1['pokeballs']

        with patch('game.engine.state.roll_capture_dice', return_value=4):
            new_state, result = engine.capture_pokemon(state, p1_id)
        self.assertIsNotNone(new_state)
        p1_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(p1_after['pokeballs'], pokeballs_before - 2)

    def test_capture_legendary_with_full_restore(self):
        """Lendário com Full Restore como pagamento."""
        state, p1_id = self._state_with_pending_pokemon()
        state['turn']['seafoam_legendary'] = True
        state['turn']['capture_context'] = 'seafoam'
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        pokeballs_before = p1['pokeballs']
        fr_before = p1['full_restores']

        with patch('game.engine.state.roll_capture_dice', return_value=4):
            new_state, result = engine.capture_pokemon(state, p1_id, use_full_restore=True)
        self.assertIsNotNone(new_state)
        p1_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(p1_after['pokeballs'], pokeballs_before)  # pokeballs intactas
        self.assertEqual(p1_after['full_restores'], fr_before - 1)

    def test_capture_roll_is_recorded_separately_from_movement(self):
        state, p1_id = self._state_with_pending_pokemon()
        state['turn']['last_roll'] = {
            'roll_type': 'movimento',
            'raw_result': 5,
            'final_result': 5,
        }

        with patch('game.engine.state.roll_capture_dice', return_value=2):
            new_state, result = engine.capture_pokemon(state, p1_id)

        self.assertIsNotNone(new_state)
        self.assertEqual(result['capture_roll']['roll_type'], 'captura')
        self.assertEqual(result['capture_roll']['raw_result'], 2)
        self.assertEqual(new_state['turn']['last_roll']['roll_type'], 'captura')

    def test_victory_capture_uses_capture_dice(self):
        state, p1_id = self._state_with_pending_pokemon()
        state['turn']['capture_context'] = 'victory_wild'

        with patch('game.engine.state.roll_capture_dice', return_value=6):
            new_state, result = engine.capture_pokemon(state, p1_id)

        self.assertIsNotNone(new_state)
        self.assertEqual(result['capture_roll']['roll_type'], 'captura')
        self.assertEqual(result['capture_roll']['context'], 'victory_wild')

    def test_capture_failure_does_not_add_pokemon(self):
        state, p1_id = self._state_with_pending_pokemon()
        pokemon = copy.deepcopy(load_playable_pokemon_by_name('Pidgey'))
        state = engine._queue_capture_attempt(  # noqa: SLF001 - teste do fluxo autoritativo
            state,
            p1_id,
            pokemon=pokemon,
            capture_context='event_card',
            source='event_card',
            allowed_rolls=[6],
        )
        player_before = next(p for p in state['players'] if p['id'] == p1_id)

        with patch('game.engine.state.roll_capture_dice', return_value=2):
            new_state, result = engine.roll_capture_attempt(state, p1_id)

        player_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertFalse(result['success'])
        self.assertEqual(len(player_after['pokemon']), len(player_before['pokemon']))
        self.assertIsNone(new_state['turn']['pending_action'])

    def test_capture_success_requires_explicit_roll(self):
        state, p1_id = self._state_with_pending_pokemon()
        player_before = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertEqual(len(player_before['pokemon']), 0)
        self.assertIsNotNone(state['turn']['pending_action'])

        with patch('game.engine.state.roll_capture_dice', return_value=4):
            new_state, result = engine.roll_capture_attempt(state, p1_id)

        player_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(len(player_after['pokemon']), 1)
        self.assertIn('capture_roll', result)

    def test_capture_pending_action_exists_before_roll_and_does_not_auto_capture(self):
        state, p1_id = self._state_with_pending_pokemon()

        player = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertEqual(len(player['pokemon']), 0)
        self.assertEqual(state['turn']['pending_action']['type'], 'capture_attempt')
        self.assertIsNone(state['turn']['pending_pokemon'])

    def test_route1_capture_table_uses_capture_die_mapping(self):
        expected_by_roll = {
            1: 'Rattata',
            2: 'Rattata',
            3: 'Pidgey',
            4: 'Pidgey',
            5: 'Weedle',
            6: 'Weedle',
        }

        for capture_roll, expected_name in expected_by_roll.items():
            with self.subTest(capture_roll=capture_roll, expected=expected_name):
                state, p1_id = self._state_with_pending_pokemon()
                with patch('game.engine.state.roll_capture_dice', return_value=capture_roll):
                    new_state, result = engine.roll_capture_attempt(state, p1_id)

                player_after = next(p for p in new_state['players'] if p['id'] == p1_id)
                self.assertEqual(player_after['pokemon'][0]['name'], expected_name)
                self.assertEqual(result['capture_roll']['raw_result'], capture_roll)

    def test_movement_roll_never_decides_route1_capture_result(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 80

        with patch('game.engine.state.roll_movement_dice', return_value=5):
            rolled_state, movement_roll = engine.perform_movement_roll(state, p1_id)
        moved_state = engine.process_move(rolled_state, p1_id, int(movement_roll['final_result']))

        self.assertEqual(movement_roll['raw_result'], 5)
        self.assertEqual(moved_state['turn']['current_tile']['id'], 85)
        self.assertEqual(moved_state['turn']['last_roll']['roll_type'], 'movimento')
        self.assertIsNone(moved_state['turn']['pending_pokemon'])

        with patch('game.engine.state.roll_capture_dice', return_value=2):
            new_state, result = engine.roll_capture_attempt(moved_state, p1_id)

        player_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after['pokemon'][0]['name'], 'Rattata')
        self.assertEqual(result['capture_roll']['raw_result'], 2)
        self.assertEqual(new_state['turn']['last_roll']['roll_type'], 'captura')

    def test_board_capture_reroll_waits_for_new_capture_die(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        state = _land_on_tile(state, p1_id, 15)

        with patch('game.engine.state.roll_capture_dice', return_value=6):
            mid_state, result = engine.roll_capture_attempt(state, p1_id)

        self.assertTrue(result['requires_additional_roll'])
        self.assertEqual(mid_state['turn']['pending_action']['capture_rolls'], [6])
        self.assertTrue(mid_state['turn']['pending_action']['requires_additional_roll'])
        self.assertIsNone(mid_state['turn']['pending_pokemon'])

        with patch('game.engine.state.roll_capture_dice', return_value=5):
            new_state, final_result = engine.roll_capture_attempt(mid_state, p1_id)

        player_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after['pokemon'][0]['name'], 'Pinsir')
        self.assertEqual(final_result['capture_roll']['all_rolls'], [6, 5])

    def test_moltres_capture_succeeds_only_with_two_capture_ones(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        state = _land_on_tile(state, p1_id, 156)

        with patch('game.engine.state.roll_capture_dice', return_value=1):
            mid_state, result = engine.roll_capture_attempt(state, p1_id)

        self.assertTrue(result['requires_additional_roll'])
        self.assertEqual(mid_state['turn']['pending_action']['capture_rolls'], [1])

        with patch('game.engine.state.roll_capture_dice', return_value=1):
            new_state, final_result = engine.roll_capture_attempt(mid_state, p1_id)

        player_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after['pokemon'][0]['name'], 'Moltres')
        self.assertEqual(final_result['capture_roll']['all_rolls'], [1, 1])

    def test_moltres_capture_fails_when_second_capture_roll_differs(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        state = _land_on_tile(state, p1_id, 156)

        with patch('game.engine.state.roll_capture_dice', return_value=1):
            mid_state, result = engine.roll_capture_attempt(state, p1_id)

        self.assertTrue(result['requires_additional_roll'])

        with patch('game.engine.state.roll_capture_dice', return_value=2):
            new_state, final_result = engine.roll_capture_attempt(mid_state, p1_id)

        player_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after['pokemon'], [])
        self.assertFalse(final_result['success'])
        self.assertIsNone(new_state['turn']['pending_action'])

    def test_moltres_capture_fails_immediately_without_initial_one(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        state = _land_on_tile(state, p1_id, 156)

        with patch('game.engine.state.roll_capture_dice', return_value=2):
            new_state, result = engine.roll_capture_attempt(state, p1_id)

        player_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after['pokemon'], [])
        self.assertFalse(result['success'])
        self.assertIsNone(new_state['turn']['pending_action'])

    def test_victory_choice_pack_uses_new_capture_die_for_follow_up_roll(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        card = next(card for card in load_victory_cards() if card.get('category') == 'wild_pokemon_choice')
        state = engine._queue_capture_attempt(  # noqa: SLF001 - cobre a fila autoritativa da carta
            state,
            p1_id,
            pokemon=None,
            capture_context='victory_wild',
            source='victory_card',
            resolver_card=card,
            source_card=card,
        )

        with patch('game.engine.state.roll_capture_dice', return_value=1):
            mid_state, result = engine.roll_capture_attempt(state, p1_id)

        self.assertTrue(result['requires_additional_roll'])
        self.assertEqual(mid_state['turn']['pending_action']['capture_rolls'], [1])
        self.assertIsNone(mid_state['turn']['pending_pokemon'])

        with patch('game.engine.state.roll_capture_dice', return_value=2):
            new_state, final_result = engine.roll_capture_attempt(mid_state, p1_id)

        player_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after['pokemon'][0]['name'], 'Growlithe')
        self.assertEqual(final_result['capture_roll']['all_rolls'], [1, 2])

    def test_capture_attempt_rejects_other_player(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        state = _land_on_tile(state, p1_id, 85)

        new_state, error = engine.roll_capture_attempt(state, p2_id)

        self.assertIsNone(new_state)
        self.assertIn('não pertence', error.lower())

    def test_unsupported_runtime_pokemon_is_never_added_to_inventory(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        unsupported = {
            'id': 'missingno',
            'name': 'Missingno',
            'battle_points': 9,
            'master_points': 999,
            'types': ['Bird'],
            'ability': 'none',
        }

        state = engine._queue_capture_attempt(  # noqa: SLF001 - cobre a fila autoritativa de captura
            state,
            p1_id,
            pokemon=unsupported,
            capture_context='grass',
            source='test_unsupported_metadata',
        )

        with patch('game.engine.state.roll_capture_dice', return_value=4):
            new_state, result = engine.roll_capture_attempt(state, p1_id)

        player_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertFalse(result['success'])
        self.assertFalse(any(p['name'] == 'Missingno' for p in player_after['pokemon']))
        self.assertTrue(any('cards_metadata.json' in entry['message'] for entry in new_state['log']))

    def test_capture_release_choice_lists_team_and_starter_options(self):
        state, p1_id = self._state_with_pending_pokemon()
        player = next(p for p in state['players'] if p['id'] == p1_id)
        starter_name = player['starter_pokemon']['name']
        incoming_name = 'Pidgey'
        self._add_team_pokemon(state, p1_id, 'Rattata')
        player['pokeballs'] = 0
        sync_player_inventory(player)

        with patch('game.engine.state.roll_capture_dice', return_value=4):
            new_state, result = engine.roll_capture_attempt(state, p1_id)

        pending = new_state['turn']['pending_release_choice']
        labels = {option['label'] for option in pending['options']}
        slot_keys = {option['slot_key'] for option in pending['options']}

        self.assertTrue(result['requires_release'])
        self.assertEqual(new_state['turn']['pending_pokemon']['name'], incoming_name)
        self.assertEqual(new_state['turn']['phase'], 'release_pokemon')
        self.assertIn('pokemon:0', slot_keys)
        self.assertIn('starter', slot_keys)
        self.assertTrue(any('Rattata' in label for label in labels))
        self.assertTrue(any(starter_name in label for label in labels))

    def test_capture_release_choice_replaces_selected_team_pokemon(self):
        state, p1_id = self._state_with_pending_pokemon()
        player = next(p for p in state['players'] if p['id'] == p1_id)
        incoming_name = 'Pidgey'
        self._add_team_pokemon(state, p1_id, 'Rattata')
        player['pokeballs'] = 0
        sync_player_inventory(player)

        with patch('game.engine.state.roll_capture_dice', return_value=4):
            state, _ = engine.roll_capture_attempt(state, p1_id)

        new_state, result = engine.release_pokemon_for_capture(state, p1_id, pokemon_slot_key='pokemon:0')

        self.assertIsNotNone(new_state)
        self.assertEqual(result['released_pokemon']['name'], 'Rattata')
        player_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual([pokemon['name'] for pokemon in player_after['pokemon']], [incoming_name])
        self.assertIsNotNone(player_after['starter_pokemon'])
        self.assertEqual(player_after['starter_pokemon']['name'], player['starter_pokemon']['name'])
        self.assertIsNone(new_state['turn']['pending_release_choice'])

    def test_capture_release_choice_can_replace_starter_when_selected(self):
        state, p1_id = self._state_with_pending_pokemon()
        player = next(p for p in state['players'] if p['id'] == p1_id)
        starter_name = player['starter_pokemon']['name']
        incoming_name = 'Pidgey'
        player['pokeballs'] = 0
        sync_player_inventory(player)

        with patch('game.engine.state.roll_capture_dice', return_value=4):
            state, _ = engine.roll_capture_attempt(state, p1_id)

        new_state, result = engine.release_pokemon_for_capture(state, p1_id, pokemon_slot_key='starter')

        self.assertIsNotNone(new_state)
        self.assertEqual(result['released_pokemon']['name'], starter_name)
        player_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertIsNone(player_after['starter_pokemon'])
        self.assertEqual([pokemon['name'] for pokemon in player_after['pokemon']], [incoming_name])

    def test_capture_release_choice_cancel_keeps_party_intact(self):
        state, p1_id = self._state_with_pending_pokemon()
        player = next(p for p in state['players'] if p['id'] == p1_id)
        starter_name = player['starter_pokemon']['name']
        self._add_team_pokemon(state, p1_id, 'Rattata')
        original_team = [pokemon['name'] for pokemon in player['pokemon']]
        player['pokeballs'] = 0
        sync_player_inventory(player)

        with patch('game.engine.state.roll_capture_dice', return_value=4):
            state, _ = engine.roll_capture_attempt(state, p1_id)

        new_state = engine.skip_action(state, p1_id)

        player_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual([pokemon['name'] for pokemon in player_after['pokemon']], original_team)
        self.assertEqual(player_after['starter_pokemon']['name'], starter_name)
        self.assertIsNone(new_state['turn']['pending_release_choice'])
        self.assertIsNone(new_state['turn']['pending_pokemon'])
        self.assertEqual(new_state['turn']['current_player_id'], next(p['id'] for p in new_state['players'] if p['id'] != p1_id))

    def test_capture_release_choice_rejects_invalid_selection_without_auto_release(self):
        state, p1_id = self._state_with_pending_pokemon()
        player = next(p for p in state['players'] if p['id'] == p1_id)
        self._add_team_pokemon(state, p1_id, 'Rattata')
        player['pokeballs'] = 0
        sync_player_inventory(player)

        with patch('game.engine.state.roll_capture_dice', return_value=4):
            state, _ = engine.roll_capture_attempt(state, p1_id)

        new_state, error = engine.release_pokemon_for_capture(state, p1_id, pokemon_slot_key='pokemon:99')

        self.assertIsNone(new_state)
        self.assertIn('inválido', error.lower())

    def test_master_ball_simple_capture_uses_chosen_capture_roll_and_is_consumed_on_success(self):
        state, p1_id = self._state_with_pending_pokemon()
        player = next(p for p in state['players'] if p['id'] == p1_id)
        engine.add_item(player, 'master_ball', 1)
        before_quantity = engine.get_item_quantity(player, 'master_ball')

        new_state, result = engine.roll_capture_attempt(
            state,
            p1_id,
            use_master_ball=True,
            chosen_capture_roll=2,
        )

        player_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after['pokemon'][0]['name'], 'Rattata')
        self.assertTrue(result['used_master_ball'])
        self.assertTrue(result['master_ball_consumed'])
        self.assertEqual(engine.get_item_quantity(player_after, 'master_ball'), before_quantity - 1)

    def test_master_ball_captures_when_pokeballs_empty(self):
        """Master Ball deve contar como slot de Pokébola: captura mesmo com pokebolas = 0."""
        state, p1_id = self._state_with_pending_pokemon()
        player = next(p for p in state['players'] if p['id'] == p1_id)
        engine.add_item(player, 'master_ball', 1)
        before_quantity = engine.get_item_quantity(player, 'master_ball')
        player['pokeballs'] = 0
        sync_player_inventory(player)

        state, result = engine.roll_capture_attempt(
            state,
            p1_id,
            use_master_ball=True,
            chosen_capture_roll=2,
        )

        # Captura deve ter sucesso usando a Master Ball como slot
        self.assertFalse(result.get('requires_release', False))
        player_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertEqual(engine.get_item_quantity(player_after, 'master_ball'), before_quantity - 1)

    def test_master_ball_on_moltres_controls_only_first_roll_and_is_preserved_on_failure(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        state = _land_on_tile(state, p1_id, 156)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        engine.add_item(player, 'master_ball', 1)
        before_quantity = engine.get_item_quantity(player, 'master_ball')

        mid_state, first_result = engine.roll_capture_attempt(
            state,
            p1_id,
            use_master_ball=True,
            chosen_capture_roll=1,
        )

        self.assertTrue(first_result['requires_additional_roll'])
        self.assertTrue(first_result['used_master_ball'])
        self.assertEqual(
            engine.get_item_quantity(next(p for p in mid_state['players'] if p['id'] == p1_id), 'master_ball'),
            before_quantity,
        )

        with patch('game.engine.state.roll_capture_dice', return_value=2):
            new_state, final_result = engine.roll_capture_attempt(mid_state, p1_id)

        player_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after['pokemon'], [])
        self.assertFalse(final_result['success'])
        self.assertTrue(final_result['master_ball_preserved'])
        self.assertEqual(engine.get_item_quantity(player_after, 'master_ball'), before_quantity)

    def test_master_ball_on_moltres_is_consumed_only_after_final_success(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        state = _land_on_tile(state, p1_id, 156)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        engine.add_item(player, 'master_ball', 1)
        before_quantity = engine.get_item_quantity(player, 'master_ball')

        mid_state, first_result = engine.roll_capture_attempt(
            state,
            p1_id,
            use_master_ball=True,
            chosen_capture_roll=1,
        )

        self.assertTrue(first_result['requires_additional_roll'])
        self.assertEqual(
            engine.get_item_quantity(next(p for p in mid_state['players'] if p['id'] == p1_id), 'master_ball'),
            before_quantity,
        )

        with patch('game.engine.state.roll_capture_dice', return_value=1):
            new_state, final_result = engine.roll_capture_attempt(mid_state, p1_id)

        player_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(player_after['pokemon'][0]['name'], 'Moltres')
        self.assertTrue(final_result['master_ball_consumed'])
        self.assertEqual(engine.get_item_quantity(player_after, 'master_ball'), before_quantity - 1)


# ── Testes dos Special Tiles Restantes ───────────────────────────────────────

class TestRemainingSpecialTiles(TestCase):

    def _ready_state(self) -> tuple[dict, str, str]:
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        return state, p1_id, p2_id

    def _player(self, state: dict, player_id: str) -> dict:
        return next(player for player in state['players'] if player['id'] == player_id)

    def _force_turn(self, state: dict, player_id: str) -> dict:
        state['turn']['current_player_id'] = player_id
        state['turn']['phase'] = 'roll'
        state['turn']['pending_action'] = None
        state['turn']['pending_event'] = None
        state['turn']['pending_pokemon'] = None
        state['turn']['pending_item_choice'] = None
        state['turn']['pending_release_choice'] = None
        state['turn']['pending_effects'] = []
        return state

    def _give_pokemon(
        self,
        state: dict,
        player_id: str,
        pokemon_name: str,
        *,
        acquisition_origin: str = 'reward',
        knocked_out: bool = False,
        capture_sequence: int | None = None,
    ) -> dict:
        player = self._player(state, player_id)
        pokemon = copy.deepcopy(load_playable_pokemon_by_name(pokemon_name))
        self.assertIsNotNone(pokemon, f'{pokemon_name} precisa existir no dataset jogável')
        if acquisition_origin == 'captured':
            sequence = capture_sequence or engine._next_capture_sequence(player)  # noqa: SLF001 - helper autoritativo de teste
            pokemon = engine._apply_pokemon_acquisition_metadata(  # noqa: SLF001 - valida metadata real usada pelo engine
                pokemon,
                acquisition_origin='captured',
                capture_sequence=sequence,
                capture_context='test_capture',
            )
            player['capture_sequence_counter'] = max(int(player.get('capture_sequence_counter', 0) or 0), int(sequence))
        else:
            pokemon = engine._apply_pokemon_acquisition_metadata(  # noqa: SLF001 - valida metadata real usada pelo engine
                pokemon,
                acquisition_origin=acquisition_origin,
                capture_sequence=None,
                capture_context='test_reward',
            )
        pokemon['knocked_out'] = knocked_out
        player['pokemon'].append(pokemon)
        player['pokeballs'] = max(0, int(player.get('pokeballs', 0) or 0) - pokemon_slot_cost(pokemon))
        sync_player_inventory(player)
        return pokemon

    def _find_option_id(self, pending_action: dict, label_fragment: str) -> str:
        fragment = label_fragment.lower()
        for option in pending_action.get('options', []):
            if fragment in option.get('label', '').lower():
                return option['id']
        self.fail(f'Opção contendo "{label_fragment}" não encontrada em {pending_action.get("options", [])}')

    def test_miracle_stone_tile_evolves_eligible_pokemon(self):
        state, p1_id, _ = self._ready_state()
        self._give_pokemon(state, p1_id, 'Bulbasaur')

        state = _land_on_tile(state, p1_id, 35)
        pending = state['turn']['pending_action']

        self.assertEqual(pending['type'], 'miracle_stone_tile')
        option_id = self._find_option_id(pending, 'Bulbasaur')
        state, result = engine.resolve_pending_action(state, p1_id, option_id)

        team_names = [pokemon['name'] for pokemon in self._player(state, p1_id)['pokemon']]
        self.assertTrue(result['success'])
        self.assertEqual(result['evolved_to'], 'Ivysaur')
        self.assertIn('Ivysaur', team_names)

    def test_miracle_stone_tile_rejects_special_method_evolution(self):
        state, p1_id, _ = self._ready_state()
        player = self._player(state, p1_id)
        player['pokeballs'] += pokemon_slot_cost(player.get('starter_pokemon'))
        player['starter_pokemon'] = None
        sync_player_inventory(player)
        self._give_pokemon(state, p1_id, 'Magikarp')

        state = _land_on_tile(state, p1_id, 35)

        self.assertIsNone(state['turn']['pending_action'])
        self.assertTrue(any('não tinha pokémon elegível' in entry['message'].lower() for entry in state['log']))

    def test_bill_tile_gives_bill_item(self):
        state, p1_id, _ = self._ready_state()

        state = _land_on_tile(state, p1_id, 47)
        player = self._player(state, p1_id)

        self.assertEqual(engine.get_item_quantity(player, 'bill'), 1)
        self.assertEqual(state['turn']['pending_action']['type'], 'bill_teleport')

    def test_bill_tile_teleport_can_only_be_used_once_per_game(self):
        state, p1_id, p2_id = self._ready_state()
        p2 = self._player(state, p2_id)
        p2['position'] = 80

        state = _land_on_tile(state, p1_id, 47)
        state, result = engine.resolve_pending_action(state, p1_id, p2_id)

        self.assertTrue(result['teleported'])
        self.assertEqual(self._player(state, p1_id)['position'], 80)
        self.assertEqual(state['special_tile_state']['bill_teleport_used_by'], p1_id)

        state = self._force_turn(state, p2_id)
        before_bill = engine.get_item_quantity(self._player(state, p2_id), 'bill')
        state = _land_on_tile(state, p2_id, 47)
        p2_after = self._player(state, p2_id)

        self.assertEqual(engine.get_item_quantity(p2_after, 'bill'), before_bill + 1)
        self.assertNotEqual((state['turn'].get('pending_action') or {}).get('type'), 'bill_teleport')

    def test_game_corner_grants_prize_on_successful_roll(self):
        state, p1_id, _ = self._ready_state()
        player = self._player(state, p1_id)
        before_bill = engine.get_item_quantity(player, 'bill')

        state = _land_on_tile(state, p1_id, 72)
        with patch('game.engine.state.roll_game_corner_dice', return_value=4):
            state, result = engine.resolve_pending_action(state, p1_id, 'roll')
        self.assertEqual(result['prize_key'], 'bill')
        self.assertEqual(state['turn']['pending_action']['type'], 'game_corner')

        stop_id = self._find_option_id(state['turn']['pending_action'], 'parar')
        state, result = engine.resolve_pending_action(state, p1_id, stop_id)

        self.assertTrue(result['success'])
        self.assertEqual(engine.get_item_quantity(self._player(state, p1_id), 'bill'), before_bill + 1)

    def test_game_corner_gives_nothing_on_roll_one_or_two(self):
        state, p1_id, _ = self._ready_state()
        player = self._player(state, p1_id)
        before_bill = engine.get_item_quantity(player, 'bill')

        state = _land_on_tile(state, p1_id, 72)
        with patch('game.engine.state.roll_game_corner_dice', return_value=1):
            state, result = engine.resolve_pending_action(state, p1_id, 'roll')

        self.assertFalse(result['success'])
        self.assertEqual(engine.get_item_quantity(self._player(state, p1_id), 'bill'), before_bill)

    def test_game_corner_can_continue_to_next_prize_without_accumulating_previous(self):
        state, p1_id, _ = self._ready_state()
        player = self._player(state, p1_id)
        before_bill = engine.get_item_quantity(player, 'bill')
        before_full_restore = engine.get_item_quantity(player, 'full_restore')

        state = _land_on_tile(state, p1_id, 72)
        with patch('game.engine.state.roll_game_corner_dice', return_value=5):
            state, _ = engine.resolve_pending_action(state, p1_id, 'roll')

        continue_id = self._find_option_id(state['turn']['pending_action'], 'tentar')
        state, _ = engine.resolve_pending_action(state, p1_id, continue_id)

        with patch('game.engine.state.roll_game_corner_dice', return_value=6):
            state, result = engine.resolve_pending_action(state, p1_id, 'roll')

        self.assertEqual(result['prize_key'], 'full_restore')
        stop_id = self._find_option_id(state['turn']['pending_action'], 'parar')
        state, _ = engine.resolve_pending_action(state, p1_id, stop_id)

        player_after = self._player(state, p1_id)
        self.assertEqual(engine.get_item_quantity(player_after, 'bill'), before_bill)
        self.assertEqual(engine.get_item_quantity(player_after, 'full_restore'), before_full_restore + 1)

    def test_bicycle_bridge_draws_victory_card_and_first_player_gets_snubbull(self):
        state, p1_id, _ = self._ready_state()
        state['decks']['victory_deck'] = [{
            'id': 801,
            'title': 'Simple MP',
            'description': 'Gain 20 Master Points.',
            'category': 'master_points',
            'pile': 'victory',
        }]
        state['decks']['victory_discard'] = []

        state = _land_on_tile(state, p1_id, 92)
        player = self._player(state, p1_id)

        self.assertTrue(any(pokemon['name'] == 'Snubbull' for pokemon in player['pokemon']))
        self.assertEqual(state['special_tile_state']['bicycle_bridge_first_player_id'], p1_id)
        self.assertIn(801, state['consumed']['victory'])

    def test_bicycle_bridge_first_bonus_is_only_given_once(self):
        state, p1_id, p2_id = self._ready_state()
        state['decks']['victory_deck'] = [{
            'id': 811,
            'title': 'Simple MP',
            'description': 'Gain 20 Master Points.',
            'category': 'master_points',
            'pile': 'victory',
        }, {
            'id': 812,
            'title': 'Simple MP 2',
            'description': 'Gain 20 Master Points.',
            'category': 'master_points',
            'pile': 'victory',
        }]

        state = _land_on_tile(state, p1_id, 92)
        state = self._force_turn(state, p2_id)
        state = _land_on_tile(state, p2_id, 92)

        p2 = self._player(state, p2_id)
        self.assertFalse(any(pokemon['name'] == 'Snubbull' for pokemon in p2['pokemon']))

    def test_safari_zone_offers_capture_for_displayed_pokemon(self):
        state, p1_id, _ = self._ready_state()

        state = _land_on_tile(state, p1_id, 96)

        self.assertEqual(state['turn']['pending_action']['type'], 'capture_attempt')
        self.assertEqual(state['turn']['capture_context'], 'safari')
        self.assertEqual(state['turn']['pending_pokemon']['name'], 'Tauros')

    def test_safari_zone_exit_returns_player_to_house(self):
        state, p1_id, _ = self._ready_state()

        state = _land_on_tile(state, p1_id, 105)

        self.assertEqual(self._player(state, p1_id)['position'], 96)

    def test_mr_fuji_house_draws_two_event_cards_and_first_player_gets_snorlax(self):
        state, p1_id, _ = self._ready_state()
        state['decks']['event_deck'] = [
            {'id': 901, 'title': 'Evento A', 'description': 'Nada acontece.', 'category': 'special_event', 'pile': 'event'},
            {'id': 902, 'title': 'Evento B', 'description': 'Nada acontece.', 'category': 'special_event', 'pile': 'event'},
        ]
        state['decks']['event_discard'] = []

        state = _land_on_tile(state, p1_id, 124)
        player = self._player(state, p1_id)

        self.assertTrue(any(pokemon['name'] == 'Snorlax' for pokemon in player['pokemon']))
        self.assertEqual(state['special_tile_state']['mr_fuji_first_player_id'], p1_id)
        self.assertEqual(state['consumed']['events'], [901, 902])

    def test_celadon_dept_store_grants_one_pokeball_only_once_per_player(self):
        state, p1_id, _ = self._ready_state()
        state['decks']['event_deck'] = [{
            'id': 44,
            'title': 'PokéMarket',
            'description': 'Throw the dice in order to receive any of these items! 2 = Pokéball, 3 = Bill.',
            'category': 'market',
            'pile': 'event',
        }, {
            'id': 52,
            'title': 'PokéMarket',
            'description': 'Throw the dice in order to receive any of these items! 2 = Pokéball, 3 = Bill.',
            'category': 'market',
            'pile': 'event',
        }]
        player = self._player(state, p1_id)
        before_pokeballs = player['pokeballs']

        state = _land_on_tile(state, p1_id, 79)
        after_first_reach = self._player(state, p1_id)['pokeballs']
        state = self._force_turn(state, p1_id)
        state = _land_on_tile(state, p1_id, 79)
        after_second_reach = self._player(state, p1_id)['pokeballs']

        self.assertEqual(after_first_reach, before_pokeballs + 1)
        self.assertEqual(after_second_reach, after_first_reach)

    def test_celadon_dept_store_landing_behaves_like_market(self):
        state, p1_id, _ = self._ready_state()
        state['decks']['event_deck'] = [{
            'id': 44,
            'title': 'PokéMarket',
            'description': 'Throw the dice in order to receive any of these items! 2 = Pokéball, 3 = Bill.',
            'category': 'market',
            'pile': 'event',
        }]

        state = _land_on_tile(state, p1_id, 79)

        self.assertEqual(state['turn']['phase'], 'event')
        self.assertEqual(state['turn']['pending_event']['category'], 'market')

    def test_pokemart_tile_queues_manual_roll_without_hidden_rng_or_reward(self):
        state, p1_id, _ = self._ready_state()
        player_before = self._player(state, p1_id)
        rewards_before = {
            'gust_of_wind': engine.get_item_quantity(player_before, 'gust_of_wind'),
            'bill': engine.get_item_quantity(player_before, 'bill'),
            'full_restore': engine.get_item_quantity(player_before, 'full_restore'),
            'miracle_stone': engine.get_item_quantity(player_before, 'miracle_stone'),
            'master_ball': engine.get_item_quantity(player_before, 'master_ball'),
            'pokeballs': player_before['pokeballs'],
        }

        with patch('game.engine.state.roll_market_dice') as market_roll:
            state = _land_on_tile(state, p1_id, 21)

        pending = state['turn']['pending_action']
        player_after = self._player(state, p1_id)

        market_roll.assert_not_called()
        self.assertEqual(state['turn']['phase'], 'action')
        self.assertEqual(state['turn']['current_player_id'], p1_id)
        self.assertEqual(pending['type'], 'pokemart_roll')
        self.assertEqual(pending['player_id'], p1_id)
        self.assertTrue(pending['pending_pokemart_roll'])
        self.assertEqual(pending['pokemart_phase'], 'initial_roll')
        self.assertEqual(pending['rolls'], [])
        self.assertIn('Role o dado do Poké-Mart', pending['prompt'])
        self.assertIn('Rolar dado do Poké-Mart', pending['options'][0]['label'])
        self.assertEqual(engine.get_item_quantity(player_after, 'gust_of_wind'), rewards_before['gust_of_wind'])
        self.assertEqual(engine.get_item_quantity(player_after, 'bill'), rewards_before['bill'])
        self.assertEqual(engine.get_item_quantity(player_after, 'full_restore'), rewards_before['full_restore'])
        self.assertEqual(engine.get_item_quantity(player_after, 'miracle_stone'), rewards_before['miracle_stone'])
        self.assertEqual(engine.get_item_quantity(player_after, 'master_ball'), rewards_before['master_ball'])
        self.assertEqual(player_after['pokeballs'], rewards_before['pokeballs'])
        self.assertTrue(any('aguardando rolagem explícita' in entry['message'].lower() for entry in state['log']))

    def test_pokemart_tile_first_manual_roll_grants_reward_and_finishes_turn_for_rolls_one_to_five(self):
        scenarios = [
            (1, 'gust_of_wind'),
            (2, 'bill'),
            (3, 'full_restore'),
            (4, 'full_restore'),
            (5, 'miracle_stone'),
        ]

        for first_roll, reward_key in scenarios:
            with self.subTest(first_roll=first_roll, reward_key=reward_key):
                state, p1_id, p2_id = self._ready_state()
                state = _land_on_tile(state, p1_id, 21)
                option_id = self._find_option_id(state['turn']['pending_action'], 'Rolar dado do Poké-Mart')
                player_before = self._player(state, p1_id)
                reward_before = engine.get_item_quantity(player_before, reward_key)

                with patch('game.engine.state.roll_market_dice', return_value=first_roll) as market_roll:
                    state, result = engine.resolve_pending_action(state, p1_id, option_id)

                market_roll.assert_called_once()
                player_after = self._player(state, p1_id)
                self.assertTrue(result['success'])
                self.assertEqual(result['type'], 'pokemart_roll')
                self.assertEqual(result['pokemart_phase'], 'initial_roll')
                self.assertEqual(result['roll'], first_roll)
                self.assertEqual(result['rolls'], [first_roll])
                self.assertEqual(result['reward_key'], reward_key)
                self.assertEqual(engine.get_item_quantity(player_after, reward_key), reward_before + 1)
                self.assertIsNone(state['turn'].get('pending_action'))
                self.assertEqual(state['turn']['current_player_id'], p2_id)
                self.assertTrue(any(f"rolou {first_roll}" in entry['message'].lower() for entry in state['log']))

    def test_pokemart_tile_roll_of_six_requires_explicit_reroll_without_granting_item(self):
        state, p1_id, _ = self._ready_state()
        state = _land_on_tile(state, p1_id, 21)
        option_id = self._find_option_id(state['turn']['pending_action'], 'Rolar dado do Poké-Mart')
        player_before = self._player(state, p1_id)
        rewards_before = {
            'gust_of_wind': engine.get_item_quantity(player_before, 'gust_of_wind'),
            'bill': engine.get_item_quantity(player_before, 'bill'),
            'full_restore': engine.get_item_quantity(player_before, 'full_restore'),
            'miracle_stone': engine.get_item_quantity(player_before, 'miracle_stone'),
            'master_ball': engine.get_item_quantity(player_before, 'master_ball'),
            'pokeballs': player_before['pokeballs'],
        }

        with patch('game.engine.state.roll_market_dice', return_value=6) as market_roll:
            state, result = engine.resolve_pending_action(state, p1_id, option_id)

        pending = state['turn']['pending_action']
        player_after = self._player(state, p1_id)
        market_roll.assert_called_once()
        self.assertTrue(result['success'])
        self.assertTrue(result['requires_additional_roll'])
        self.assertEqual(result['roll'], 6)
        self.assertEqual(result['rolls'], [6])
        self.assertEqual(state['turn']['phase'], 'action')
        self.assertEqual(state['turn']['current_player_id'], p1_id)
        self.assertEqual(pending['type'], 'pokemart_roll')
        self.assertEqual(pending['pokemart_phase'], 'reroll')
        self.assertEqual(pending['rolls'], [6])
        self.assertIn('Rerrolar dado do Poké-Mart', pending['options'][0]['label'])
        self.assertEqual(engine.get_item_quantity(player_after, 'gust_of_wind'), rewards_before['gust_of_wind'])
        self.assertEqual(engine.get_item_quantity(player_after, 'bill'), rewards_before['bill'])
        self.assertEqual(engine.get_item_quantity(player_after, 'full_restore'), rewards_before['full_restore'])
        self.assertEqual(engine.get_item_quantity(player_after, 'miracle_stone'), rewards_before['miracle_stone'])
        self.assertEqual(engine.get_item_quantity(player_after, 'master_ball'), rewards_before['master_ball'])
        self.assertEqual(player_after['pokeballs'], rewards_before['pokeballs'])
        self.assertTrue(any('segunda rolagem explícita' in entry['message'].lower() for entry in state['log']))

    def test_pokemart_tile_second_manual_roll_grants_pokeball_for_rolls_one_to_five(self):
        for second_roll in range(1, 6):
            with self.subTest(second_roll=second_roll):
                state, p1_id, p2_id = self._ready_state()
                state = _land_on_tile(state, p1_id, 21)
                first_option_id = self._find_option_id(state['turn']['pending_action'], 'Rolar dado do Poké-Mart')
                player_before = self._player(state, p1_id)
                pokeballs_before = player_before['pokeballs']

                with patch('game.engine.state.roll_market_dice', return_value=6):
                    state, first_result = engine.resolve_pending_action(state, p1_id, first_option_id)

                self.assertTrue(first_result['requires_additional_roll'])
                reroll_option_id = self._find_option_id(state['turn']['pending_action'], 'Rerrolar dado do Poké-Mart')

                with patch('game.engine.state.roll_market_dice', return_value=second_roll) as market_roll:
                    state, result = engine.resolve_pending_action(state, p1_id, reroll_option_id)

                market_roll.assert_called_once()
                player_after = self._player(state, p1_id)
                self.assertTrue(result['success'])
                self.assertEqual(result['pokemart_phase'], 'reroll')
                self.assertEqual(result['roll'], second_roll)
                self.assertEqual(result['rolls'], [6, second_roll])
                self.assertEqual(result['reward_key'], 'pokeball')
                self.assertEqual(player_after['pokeballs'], pokeballs_before + 1)
                self.assertIsNone(state['turn'].get('pending_action'))
                self.assertEqual(state['turn']['current_player_id'], p2_id)

    def test_pokemart_tile_second_manual_roll_grants_master_ball_on_six(self):
        state, p1_id, p2_id = self._ready_state()
        state = _land_on_tile(state, p1_id, 21)
        first_option_id = self._find_option_id(state['turn']['pending_action'], 'Rolar dado do Poké-Mart')
        player_before = self._player(state, p1_id)
        master_ball_before = engine.get_item_quantity(player_before, 'master_ball')

        with patch('game.engine.state.roll_market_dice', return_value=6):
            state, first_result = engine.resolve_pending_action(state, p1_id, first_option_id)

        self.assertTrue(first_result['requires_additional_roll'])
        reroll_option_id = self._find_option_id(state['turn']['pending_action'], 'Rerrolar dado do Poké-Mart')

        with patch('game.engine.state.roll_market_dice', return_value=6) as market_roll:
            state, result = engine.resolve_pending_action(state, p1_id, reroll_option_id)

        market_roll.assert_called_once()
        player_after = self._player(state, p1_id)
        self.assertTrue(result['success'])
        self.assertEqual(result['pokemart_phase'], 'reroll')
        self.assertEqual(result['roll'], 6)
        self.assertEqual(result['rolls'], [6, 6])
        self.assertEqual(result['reward_key'], 'master_ball')
        self.assertEqual(engine.get_item_quantity(player_after, 'master_ball'), master_ball_before + 1)
        self.assertIsNone(state['turn'].get('pending_action'))
        self.assertEqual(state['turn']['current_player_id'], p2_id)

    def test_teleporter_moves_player_and_grants_extra_turn_on_exact_landing(self):
        state, p1_id, _ = self._ready_state()

        state = _land_on_tile(state, p1_id, 136)

        self.assertEqual(self._player(state, p1_id)['position'], 137)
        self.assertEqual(state['turn']['current_player_id'], p1_id)
        self.assertEqual(state['turn']['pending_action']['type'], 'teleporter_manual_roll')

    def test_teleporter_manual_roll_uses_chosen_value(self):
        state, p1_id, _ = self._ready_state()
        state = _land_on_tile(state, p1_id, 136)

        option_id = self._find_option_id(state['turn']['pending_action'], 'Mover 4')
        state, result = engine.resolve_pending_action(state, p1_id, option_id)

        self.assertTrue(result['success'])
        self.assertEqual(self._player(state, p1_id)['position'], 141)

    def test_teleporter_extra_turn_is_consumed_after_manual_move(self):
        state, p1_id, p2_id = self._ready_state()
        state = _land_on_tile(state, p1_id, 136)

        option_id = self._find_option_id(state['turn']['pending_action'], 'Mover 5')
        state, _ = engine.resolve_pending_action(state, p1_id, option_id)
        state = engine.skip_action(state, p1_id)

        self.assertEqual(state['turn']['current_player_id'], p2_id)
        self.assertIsNone(state['turn'].get('pending_action'))


# ── Testes de Duelo ──────────────────────────────────────────────────────────

class TestDuel(TestCase):

    def _two_players_with_pokemon(self) -> tuple[dict, str, str]:
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        return state, p1_id, p2_id

    def test_start_duel_sets_battle_phase(self):
        state, p1_id, p2_id = self._two_players_with_pokemon()
        new_state = engine.start_duel(state, p1_id, p2_id)
        self.assertIsNotNone(new_state)
        self.assertEqual(new_state['turn']['phase'], 'battle')

    def test_start_duel_stores_participants(self):
        state, p1_id, p2_id = self._two_players_with_pokemon()
        new_state = engine.start_duel(state, p1_id, p2_id)
        battle = new_state['turn']['battle']
        self.assertEqual(battle['challenger_id'], p1_id)
        self.assertEqual(battle['defender_id'], p2_id)

    def test_start_duel_returns_none_for_invalid_target(self):
        state, p1_id, p2_id = self._two_players_with_pokemon()
        result = engine.start_duel(state, p1_id, 'invalid-id')
        self.assertIsNone(result)

    def test_battle_choice_resolves_when_both_choose(self):
        state, p1_id, p2_id = self._two_players_with_pokemon()
        state = engine.start_duel(state, p1_id, p2_id)

        # Fase 1: defensor escolhe antes do desafiante
        state, result1 = engine.register_battle_choice(state, p1_id, 0)
        self.assertEqual(result1['error'], 'O jogador desafiado deve escolher primeiro')
        state, result_choice = engine.register_battle_choice(state, p2_id, 0)
        self.assertIsNone(result_choice)  # Ambos escolheram, mas precisam rolar
        self.assertEqual(state['turn']['battle']['choice_stage'], 'challenger')
        state, result_choice = engine.register_battle_choice(state, p1_id, 0)
        self.assertIsNone(result_choice)
        self.assertEqual(state['turn']['battle']['sub_phase'], 'rolling')

        # Fase 2: ambos rolam o dado (sub_phase='rolling' → resolve)
        state, r1 = engine.register_battle_roll(state, p1_id)
        self.assertIsNone(r1)  # Ainda esperando P2 rolar
        state, result2 = engine.register_battle_roll(state, p2_id)
        self.assertIsNotNone(result2)  # Batalha resolvida
        self.assertIn('winner_id', result2)

    def test_duel_winner_gets_master_points(self):
        state, p1_id, p2_id = self._two_players_with_pokemon()
        state = engine.start_duel(state, p1_id, p2_id)
        state, _ = engine.register_battle_choice(state, p2_id, 0)
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        with patch('game.engine.state.roll_battle_dice', side_effect=[6, 1]):
            state, _ = engine.register_battle_roll(state, p1_id)
            state, result = engine.register_battle_roll(state, p2_id)

        winner_id = result['winner_id']
        winner = next(p for p in state['players'] if p['id'] == winner_id)
        self.assertGreaterEqual(winner['master_points'], 5)

    def test_duel_records_battle_rolls_in_history(self):
        state, p1_id, p2_id = self._two_players_with_pokemon()
        state = engine.start_duel(state, p1_id, p2_id)

        # Choices não consomem dados; rolls consomem [6, 1]
        state, _ = engine.register_battle_choice(state, p2_id, 0)
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        with patch('game.engine.state.roll_battle_dice', side_effect=[6, 1]):
            state, _ = engine.register_battle_roll(state, p1_id)
            state, result = engine.register_battle_roll(state, p2_id)

        self.assertIsNotNone(result)
        battle_rolls = [roll for roll in state['turn']['roll_history'] if roll['roll_type'] == 'batalha']
        self.assertEqual(len(battle_rolls), 2)
        self.assertEqual(battle_rolls[0]['raw_result'], 6)
        self.assertEqual(battle_rolls[1]['raw_result'], 1)

    def test_double_battle_choice_is_idempotent(self):
        state, p1_id, p2_id = self._two_players_with_pokemon()
        state = engine.start_duel(state, p1_id, p2_id)
        state, _ = engine.register_battle_choice(state, p2_id, 0)

        state, ignored = engine.register_battle_choice(state, p2_id, 0)

        self.assertTrue(ignored['ignored'])
        self.assertEqual(state['turn']['battle']['defender_choice']['name'], state['turn']['battle']['defender_choice']['name'])

    def test_double_battle_roll_is_idempotent(self):
        state, p1_id, p2_id = self._two_players_with_pokemon()
        state = engine.start_duel(state, p1_id, p2_id)
        state, _ = engine.register_battle_choice(state, p2_id, 0)
        state, _ = engine.register_battle_choice(state, p1_id, 0)

        with patch('game.engine.state.roll_battle_dice', side_effect=[5, 2]):
            state, _ = engine.register_battle_roll(state, p1_id)
            state, ignored = engine.register_battle_roll(state, p1_id)

        self.assertTrue(ignored['ignored'])
        self.assertEqual(state['turn']['battle']['challenger_roll'], 5)

    def test_non_participant_cannot_choose_or_roll(self):
        state, p1_id, p2_id = self._two_players_with_pokemon()
        extra = _make_player('Brock')
        state['players'].append(extra)
        state = engine.start_duel(state, p1_id, p2_id)

        state, choice_error = engine.register_battle_choice(state, extra['id'], 0)
        self.assertEqual(choice_error['error'], 'Você não participa desta batalha')

        state, _ = engine.register_battle_choice(state, p2_id, 0)
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        state, roll_error = engine.register_battle_roll(state, extra['id'])
        self.assertEqual(roll_error['error'], 'Você não participa desta batalha')

    def test_detailed_duel_logging_contains_formula(self):
        state, p1_id, p2_id = self._two_players_with_pokemon()
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        p2 = next(p for p in state['players'] if p['id'] == p2_id)
        p1['pokemon'] = [{**_make_pokemon(name='Ivysaur', bp=6), 'types': []}]
        p2['pokemon'] = [{**_make_pokemon(name='Charmeleon', bp=7), 'types': []}]

        state = engine.start_duel(state, p1_id, p2_id)
        state, _ = engine.register_battle_choice(state, p2_id, 0)
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        with patch('game.engine.state.roll_battle_dice', side_effect=[4, 4]):
            state, _ = engine.register_battle_roll(state, p1_id)
            state, _ = engine.register_battle_roll(state, p2_id)

        messages = [entry['message'] for entry in state['log']]
        self.assertIn('Ash rolou 4 com Ivysaur.', messages)
        self.assertIn('Misty rolou 4 com Charmeleon.', messages)
        self.assertIn('Resultado final — Ash: 4 x (6 + 0) = 24 | Misty: 4 x (7 + 0) = 28.', messages)
        self.assertTrue(any('comprou uma carta de vitória' in message for message in messages))

    def test_duel_tie_clears_rolls_and_preserves_choices_before_reroll(self):
        state, p1_id, p2_id = self._two_players_with_pokemon()
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        p2 = next(p for p in state['players'] if p['id'] == p2_id)
        p1['pokemon'] = [{**_make_pokemon(name='Pikachu', bp=5), 'types': ['Electric']}]
        p2['pokemon'] = [{**_make_pokemon(name='Eevee', bp=5), 'types': ['Normal']}]

        state = engine.start_duel(state, p1_id, p2_id)
        state, _ = engine.register_battle_choice(state, p2_id, 0)
        state, _ = engine.register_battle_choice(state, p1_id, 0)

        with patch('game.engine.state.roll_battle_dice', side_effect=[3, 3]):
            state, _ = engine.register_battle_roll(state, p1_id)
            state, result = engine.register_battle_roll(state, p2_id)

        self.assertTrue(result['reroll_required'])
        self.assertTrue(result['tied_round'])
        self.assertEqual(state['turn']['phase'], 'battle')
        self.assertEqual(state['turn']['battle']['sub_phase'], 'rolling')
        self.assertIsNone(state['turn']['battle']['challenger_roll'])
        self.assertIsNone(state['turn']['battle']['defender_roll'])
        self.assertEqual(state['turn']['battle']['challenger_choice']['name'], 'Pikachu')
        self.assertEqual(state['turn']['battle']['defender_choice']['name'], 'Eevee')

    def test_duel_can_finish_normally_after_tie_reroll(self):
        state, p1_id, p2_id = self._two_players_with_pokemon()
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        p2 = next(p for p in state['players'] if p['id'] == p2_id)
        p1['pokemon'] = [{**_make_pokemon(name='Pikachu', bp=5), 'types': ['Electric']}]
        p2['pokemon'] = [{**_make_pokemon(name='Eevee', bp=5), 'types': ['Normal']}]

        state = engine.start_duel(state, p1_id, p2_id)
        state, _ = engine.register_battle_choice(state, p2_id, 0)
        state, _ = engine.register_battle_choice(state, p1_id, 0)

        with patch('game.engine.state.roll_battle_dice', side_effect=[4, 4, 6, 1]):
            state, first_roll = engine.register_battle_roll(state, p1_id)
            state, tie_result = engine.register_battle_roll(state, p2_id)
            state, second_roll = engine.register_battle_roll(state, p1_id)
            state, final_result = engine.register_battle_roll(state, p2_id)

        self.assertIsNone(first_roll)
        self.assertIsNone(second_roll)
        self.assertTrue(tie_result['reroll_required'])
        self.assertFalse(final_result.get('reroll_required', False))
        self.assertEqual(final_result['winner_id'], p1_id)
        self.assertEqual(state['turn']['phase'], 'roll')
        self.assertIsNone(state['turn']['battle'])

        messages = [entry['message'] for entry in state['log']]
        self.assertIn('Empate na batalha. Ambos devem rolar novamente.', messages)
        self.assertIn('Pikachu e Eevee empataram. A batalha continua com nova rolagem.', messages)


# ── Testes de Remoção de Jogador ──────────────────────────────────────────────

class TestPlayerRemoval(TestCase):

    def test_remove_player_sets_inactive(self):
        state, p1_id, p2_id = _init_two_player_game()
        new_state = engine.remove_player(state, p2_id)
        p2 = next(p for p in new_state['players'] if p['id'] == p2_id)
        self.assertFalse(p2['is_active'])

    def test_remove_current_player_advances_turn(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])

        # P1 is current player
        self.assertEqual(state['turn']['current_player_id'], p1_id)
        new_state = engine.remove_player(state, p1_id)
        # After removing, should advance to P2
        self.assertEqual(new_state['turn']['current_player_id'], p2_id)

    def test_remove_host_transfers_host(self):
        state, p1_id, p2_id = _init_two_player_game()
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertTrue(p1['is_host'])

        new_state = engine.remove_player(state, p1_id)
        # P2 should now be host
        p2 = next(p for p in new_state['players'] if p['id'] == p2_id)
        self.assertTrue(p2['is_host'])

    def test_game_finishes_when_only_one_player_remains(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])

        new_state = engine.remove_player(state, p2_id)
        self.assertEqual(new_state['status'], 'finished')


# ── Testes de Controle de Turno ──────────────────────────────────────────────

class TestTurnControl(TestCase):

    def _game_at_roll_phase(self) -> tuple[dict, str, str]:
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        return state, p1_id, p2_id

    def test_end_turn_advances_to_next_player(self):
        state, p1_id, p2_id = self._game_at_roll_phase()
        self.assertEqual(state['turn']['current_player_id'], p1_id)
        new_state = engine.end_turn(state)
        self.assertEqual(new_state['turn']['current_player_id'], p2_id)

    def test_end_turn_resets_to_roll_phase(self):
        state, p1_id, p2_id = self._game_at_roll_phase()
        new_state = engine.end_turn(state)
        self.assertEqual(new_state['turn']['phase'], 'roll')

    def test_end_turn_without_capture_does_not_change_pokeballs(self):
        state, p1_id, p2_id = self._game_at_roll_phase()
        p1_before = next(p for p in state['players'] if p['id'] == p1_id)['pokeballs']
        p2_before = next(p for p in state['players'] if p['id'] == p2_id)['pokeballs']

        new_state = engine.end_turn(state)

        p1_after = next(p for p in new_state['players'] if p['id'] == p1_id)['pokeballs']
        p2_after = next(p for p in new_state['players'] if p['id'] == p2_id)['pokeballs']
        self.assertEqual(p1_after, p1_before)
        self.assertEqual(p2_after, p2_before)

    def test_end_turn_clears_pending_data(self):
        state, p1_id, p2_id = self._game_at_roll_phase()
        state['turn']['pending_pokemon'] = {'name': 'Pikachu'}
        state['turn']['pending_event'] = {'title': 'Test Event'}
        new_state = engine.end_turn(state)
        self.assertIsNone(new_state['turn']['pending_pokemon'])
        self.assertIsNone(new_state['turn']['pending_event'])

    def test_extra_turn_keeps_same_player(self):
        state, p1_id, p2_id = self._game_at_roll_phase()
        state['turn']['extra_turn'] = True
        new_state = engine.end_turn(state)
        self.assertEqual(new_state['turn']['current_player_id'], p1_id)
        self.assertFalse(new_state['turn'].get('extra_turn', False))

    def test_round_increments_after_full_cycle(self):
        state, p1_id, p2_id = self._game_at_roll_phase()
        initial_round = state['turn']['round']
        # End turn twice (P1 → P2 → P1 again = new round)
        state = engine.end_turn(state)  # P1 → P2
        state = engine.end_turn(state)  # P2 → P1 (new round)
        self.assertEqual(state['turn']['round'], initial_round + 1)


# ── Testes de Schema/Normalização ────────────────────────────────────────────

class TestStateSchema(TestCase):

    def test_normalize_state_creates_missing_fields(self):
        state = normalize_state('TEST01', {})
        self.assertIn('players', state)
        self.assertIn('turn', state)
        self.assertIn('decks', state)
        self.assertIn('board', state)
        self.assertIn('last_roll', state['turn'])
        self.assertIn('roll_history', state['turn'])

    def test_normalize_state_preserves_players(self):
        raw = build_initial_state('TEST01')
        raw['players'] = [_make_player('Ash', host=True)]
        state = normalize_state('TEST01', raw)
        self.assertEqual(len(state['players']), 1)
        self.assertEqual(state['players'][0]['name'], 'Ash')

    def test_normalize_state_sets_room_code(self):
        state = normalize_state('XYZ123', {'status': 'waiting'})
        self.assertEqual(state['room_code'], 'XYZ123')

    def test_normalize_player_sets_defaults(self):
        raw = build_initial_state('TEST01')
        raw['players'] = [{'name': 'Ash'}]
        state = normalize_state('TEST01', raw)
        p = state['players'][0]
        self.assertIn('pokeballs', p)
        self.assertIn('full_restores', p)
        self.assertIn('badges', p)
        self.assertEqual(p['position'], 0)

    def test_normalize_state_preserves_pending_release_choice(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        with patch('game.engine.state.random.randint', return_value=1):
            state = _land_on_tile(state, p1_id, 85)
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['pokeballs'] = 0
        sync_player_inventory(player)

        with patch('game.engine.state.roll_capture_dice', return_value=4):
            state, result = engine.roll_capture_attempt(state, p1_id)

        normalized = normalize_state('TEST01', state)
        pending = normalized['turn']['pending_release_choice']

        self.assertTrue(result['requires_release'])
        self.assertEqual(normalized['turn']['phase'], 'release_pokemon')
        self.assertEqual(pending['player_id'], p1_id)
        self.assertEqual(pending['pokemon']['name'], state['turn']['pending_pokemon']['name'])
        self.assertTrue(any(option['slot_key'] == 'starter' for option in pending['options']))


# ── Testes de Eventos ─────────────────────────────────────────────────────────

class TestEventCards(TestCase):

    def _game_at_event_phase(self, event_card: dict) -> tuple[dict, str]:
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        # Simulate landing on event tile
        state['turn']['phase'] = 'event'
        state['turn']['current_player_id'] = p1_id
        state['turn']['pending_event'] = event_card
        return state, p1_id

    def test_confirm_event_applies_effect(self):
        event = {
            'id': 44,
            'title': 'PokéMarket',
            'description': 'Throw the dice in order to receive any of these items! 2 = Pokéball, 3 = Bill, 4 = PlusPower, 5 = Master Points Nugget.',
            'category': 'market',
        }
        state, p1_id = self._game_at_event_phase(event)
        p1_before = next(p for p in state['players'] if p['id'] == p1_id)
        item_before = len(p1_before['items'])

        with patch('game.engine.cards.random.randint', return_value=3):
            new_state, result = engine.resolve_event(state, p1_id, use_run_away=False)
        self.assertIsNotNone(new_state)
        self.assertEqual(result, 'ok')
        p1_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertGreaterEqual(len(p1_after['items']), item_before)
        self.assertTrue(any(item['key'] == 'bill' for item in p1_after['items']))

    def test_event_wrong_player_returns_none(self):
        event = {'id': 42, 'title': 'Event', 'description': 'An angry Voltorb paralyzes you for one turn. You have to skip your next turn.', 'category': 'event'}
        state, p1_id = self._game_at_event_phase(event)
        # Get P2 id
        p2_id = next(p['id'] for p in state['players'] if p['id'] != p1_id)

        result, error = engine.resolve_event(state, p2_id)
        self.assertIsNone(result)

    def test_run_away_blocks_negative_event(self):
        event = {
            'id': 42,
            'title': 'Event',
            'description': 'An angry Voltorb paralyzes you for one turn. You have to skip your next turn.',
            'category': 'event',
        }
        state, p1_id = self._game_at_event_phase(event)

        # Give P1 a Rattata with Run Away
        rattata = {
            'id': 19, 'name': 'Rattata', 'ability': 'Run Away',
            'ability_type': 'event', 'battle_points': 1, 'master_points': 2,
            'ability_used': False,
        }
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        p1['pokemon'].append(rattata)
        pb_before = p1['pokeballs']

        new_state, result = engine.resolve_event(state, p1_id, use_run_away=True)
        self.assertIsNotNone(new_state)
        p1_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        # Pokébolas não devem ter sido perdidas
        self.assertEqual(p1_after['pokeballs'], pb_before)

    def test_non_capture_event_does_not_change_pokeballs(self):
        event = {
            'id': 45,
            'title': 'Professor Visit',
            'description': 'Draw an extra event card.',
            'category': 'special_event',
        }
        state, p1_id = self._game_at_event_phase(event)
        p1_before = next(p for p in state['players'] if p['id'] == p1_id)['pokeballs']

        new_state, result = engine.resolve_event(state, p1_id, use_run_away=False)

        self.assertEqual(result, 'ok')
        p1_after = next(p for p in new_state['players'] if p['id'] == p1_id)['pokeballs']
        self.assertEqual(p1_after, p1_before)

    def test_event_moves_card_to_discard_and_reveals(self):
        event = {
            'id': 44,
            'title': 'PokéMarket',
            'description': 'Throw the dice in order to receive any of these items! 2 = Pokéball, 3 = Bill, 4 = PlusPower, 5 = Master Points Nugget.',
            'category': 'market',
            'image_path': '/assets/cards/events/evento_44.png',
        }
        state, p1_id = self._game_at_event_phase(event)
        with patch('game.engine.cards.random.randint', return_value=3):
            new_state, _ = engine.resolve_event(state, p1_id, use_run_away=False)
        self.assertEqual(new_state['decks']['event_discard'][-1]['id'], 44)

    def test_trainer_event_starts_real_battle_flow(self):
        event = {
            'id': 201,
            'title': 'Trainer Emiel',
            'description': 'Battle Emiel using one Pokémon. If you win, you may play an additional turn and you receive 10 Master Points!',
            'category': 'trainer_battle',
        }
        state, p1_id = self._game_at_event_phase(event)
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        p1['pokemon'] = [_make_pokemon(name='Pikachu', bp=8)]

        state, result = engine.resolve_event(state, p1_id, use_run_away=False)
        self.assertEqual(result, 'ok')
        self.assertEqual(state['turn']['phase'], 'battle')
        self.assertEqual(state['turn']['battle']['mode'], 'trainer')

        state, choice_result = engine.register_battle_choice(state, p1_id, 0)
        self.assertIsNone(choice_result)
        with patch('game.engine.state.roll_battle_dice', side_effect=[6, 1]):
            state, battle_result = engine.register_battle_roll(state, p1_id)

        self.assertEqual(battle_result['mode'], 'trainer')
        self.assertTrue(any(reward['type'] == 'master_points' and reward['amount'] == 10 for reward in battle_result['rewards']))
        self.assertEqual(state['turn']['phase'], 'roll')

    def test_event_tile_draws_and_enters_pending_event(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        state['decks']['event_deck'] = [{
            'id': 44,
            'title': 'PokéMarket',
            'description': 'Throw the dice in order to receive any of these items! 2 = Pokéball, 3 = Bill.',
            'category': 'market',
        }]
        state['decks']['event_discard'] = []

        state = _land_on_tile(state, p1_id, 7)

        self.assertEqual(state['turn']['phase'], 'event')
        self.assertEqual(state['turn']['pending_event']['title'], 'PokéMarket')
        self.assertEqual(state['revealed_card']['deck_type'], 'event')

    def test_gift_choice_card_enters_pending_choice_and_grants_selected_reward(self):
        card = {
            'id': 18,
            'title': 'Gift Pokémon',
            'description': 'You may choose one of the above Pokémon to receive as a gift! Eevee, Growlithe, M. Fossil.',
            'category': 'gift_pokemon_choice',
            'pile': 'victory',
        }
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        state['decks']['victory_deck'] = [card]

        state = engine._award_victory_cards(state, p1_id, 1, source='test')  # noqa: SLF001 - fluxo real da engine
        pending = state['turn']['pending_action']
        self.assertEqual(pending['type'], 'reward_choice')
        self.assertTrue(any(option['label'] == 'Eevee' for option in pending['options']))
        self.assertTrue(any(option['label'] == 'Mysterious Fossil' for option in pending['options']))

        state, resolve_result = engine.resolve_pending_action(state, p1_id, 'Eevee')
        player = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertTrue(resolve_result['success'])
        self.assertTrue(any(p['name'] == 'Eevee' for p in player['pokemon']))
        self.assertEqual(state['turn']['phase'], 'roll')

    def test_unknown_reward_pokemon_is_not_inserted(self):
        card = {
            'id': 18,
            'title': 'Gift Pokémon',
            'description': 'You may choose one of the above Pokémon to receive as a gift! Missingno.',
            'category': 'gift_pokemon_choice',
            'pile': 'victory',
        }
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        state['decks']['victory_deck'] = [card]
        player_before = next(p for p in state['players'] if p['id'] == p1_id)

        new_state = engine._award_victory_cards(state, p1_id, 1, source='test')  # noqa: SLF001 - fluxo real da engine

        player_after = next(p for p in new_state['players'] if p['id'] == p1_id)
        self.assertEqual(len(player_after['pokemon']), len(player_before['pokemon']))
        self.assertIsNone(new_state['turn']['pending_action'])
        self.assertEqual(new_state['turn']['phase'], 'roll')


class TestDebugTileTrigger(TestCase):

    def test_debug_trigger_current_tile_uses_same_tile_effect(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        player = next(p for p in state['players'] if p['id'] == p1_id)
        player['position'] = 7  # Tile id 7
        state['decks']['event_deck'] = [{
            'id': 44,
            'title': 'PokéMarket',
            'description': 'Throw the dice in order to receive any of these items! 2 = Pokéball, 3 = Bill.',
            'category': 'market',
        }]

        new_state, result = engine.trigger_current_tile_effect(state, p1_id, source='debug')

        self.assertTrue(result['success'])
        self.assertEqual(new_state['turn']['phase'], 'event')
        self.assertEqual(new_state['turn']['pending_event']['title'], 'PokéMarket')

    def test_debug_trigger_current_tile_rejects_when_turn_has_pending_interaction(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        state['decks']['event_deck'] = [{
            'id': 44,
            'title': 'PokéMarket',
            'description': 'Throw the dice in order to receive any of these items! 2 = Pokéball, 3 = Bill.',
            'category': 'market',
        }]
        state = _land_on_tile(state, p1_id, 7)

        new_state, error = engine.trigger_current_tile_effect(state, p1_id, source='debug')

        self.assertIsNone(new_state)
        self.assertIn('interação pendente', error.lower())


class TestDebugVisualTestPlayer(TestCase):

    def _enabled_debug_state(self) -> tuple[dict, str, str]:
        state, p1_id, p2_id = _init_two_player_game()
        enabled_state, result = engine.set_debug_test_player_enabled(state, True)
        self.assertTrue(result['enabled'])
        self.assertTrue(enabled_state['debug_visual']['enabled'])
        return enabled_state, p1_id, p2_id

    def test_enable_debug_creates_isolated_test_player(self):
        state, p1_id, p2_id = _init_two_player_game()
        real_ids = [player['id'] for player in state['players']]

        new_state, result = engine.set_debug_test_player_enabled(state, True)

        self.assertTrue(result['enabled'])
        self.assertEqual(real_ids, [player['id'] for player in new_state['players']])
        session = new_state['debug_visual']['session_state']
        self.assertIsNotNone(session)
        self.assertEqual(len(session['players']), 1)
        self.assertTrue(session['players'][0]['is_test_player'])
        self.assertNotIn(session['players'][0]['id'], real_ids)

    def test_disable_debug_removes_test_player_session(self):
        state, _, _ = self._enabled_debug_state()

        disabled_state, result = engine.set_debug_test_player_enabled(state, False)

        self.assertFalse(result['enabled'])
        self.assertFalse(disabled_state['debug_visual']['enabled'])
        self.assertIsNone(disabled_state['debug_visual']['session_state'])

    def test_debug_test_player_starts_with_default_inventory_and_pichu(self):
        state, _, _ = self._enabled_debug_state()
        player = state['debug_visual']['session_state']['players'][0]
        starting_defaults = get_starting_resource_defaults()

        self.assertEqual({item['key']: item['quantity'] for item in player['items']},
                         {item['key']: item['quantity'] for item in starting_defaults['items']})
        self.assertEqual(player['starter_pokemon']['name'], 'Pichu')
        self.assertTrue(any(pokemon['name'] == 'Pichu' for pokemon in player['pokemon_inventory']))

    def test_move_debug_test_player_updates_only_debug_position(self):
        state, _, _ = self._enabled_debug_state()
        real_players_before = copy.deepcopy(state['players'])

        moved_state, result = engine.move_debug_test_player(state, 90)

        debug_player = moved_state['debug_visual']['session_state']['players'][0]
        self.assertTrue(result['success'])
        self.assertEqual(debug_player['position'], 90)
        self.assertEqual(moved_state['players'], real_players_before)

    def test_trigger_debug_test_player_tile_uses_real_flow_without_touching_real_players(self):
        state, _, _ = self._enabled_debug_state()
        real_players_before = copy.deepcopy(state['players'])
        session = state['debug_visual']['session_state']
        session['players'][0]['position'] = 7
        session['turn']['current_tile'] = session['board']['tiles'][7]
        session['decks']['event_deck'] = [{
            'id': 44,
            'title': 'PokéMarket',
            'description': 'Throw the dice in order to receive any of these items! 2 = Pokéball, 3 = Bill.',
            'category': 'market',
        }]

        new_state, result = engine.trigger_debug_test_player_tile(state)

        debug_session = new_state['debug_visual']['session_state']
        self.assertTrue(result['success'])
        self.assertEqual(debug_session['turn']['phase'], 'event')
        self.assertEqual(debug_session['turn']['pending_event']['title'], 'PokéMarket')
        self.assertEqual(new_state['players'], real_players_before)


class TestVictoryDeck(TestCase):

    def _state_after_duel(self) -> tuple[dict, str]:
        strong = {
            'id': 6,
            'name': 'Charizard',
            'types': ['fire'],
            'battle_points': 9,
            'master_points': 10,
            'ability': 'none',
            'ability_type': 'none',
            'ability_description': '',
            'ability_used': False,
        }
        weak = {
            'id': 129,
            'name': 'Magikarp',
            'types': ['water'],
            'battle_points': 1,
            'master_points': 1,
            'ability': 'none',
            'ability_type': 'none',
            'ability_description': '',
            'ability_used': False,
        }
        state, p1_id, p2_id = _init_two_player_game()
        for player in state['players']:
            player['starter_pokemon'] = None
            player['pokemon'] = []
        next(p for p in state['players'] if p['id'] == p1_id)['pokemon'] = [copy.deepcopy(strong)]
        next(p for p in state['players'] if p['id'] == p2_id)['pokemon'] = [copy.deepcopy(weak)]
        state['turn']['phase'] = 'roll'
        state = engine.start_duel(state, p1_id, p2_id)
        return state, p1_id

    def test_duel_win_draws_victory_card(self):
        state, p1_id = self._state_after_duel()
        p2_id = next(p['id'] for p in state['players'] if p['id'] != p1_id)
        # Fase 1: escolha de Pokémon (sem dados)
        state, _ = engine.register_battle_choice(state, p2_id, 0)
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        # Fase 2: rolagem de dados
        with patch('game.engine.mechanics.roll_dice', side_effect=[6, 1]), \
             patch('game.engine.state.apply_victory_effect', side_effect=lambda game_state, player_id, card: (game_state, {'category': card.get('category'), 'status': 'applied'})):
            state, _ = engine.register_battle_roll(state, p1_id)
            new_state, result = engine.register_battle_roll(state, p2_id)
        self.assertEqual(result['winner_id'], p1_id)
        self.assertTrue(len(new_state['decks']['victory_discard']) >= 1)
        self.assertEqual(new_state['revealed_card']['deck_type'], 'victory')

    def test_trainer_victory_card_starts_trainer_battle(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        trainer_victory = {
            'id': 999,
            'title': 'Trainer Rita',
            'description': 'Battle Rita using one Pokémon. If you win, you may draw a Victory Card.',
            'category': 'trainer_battle',
        }
        state['decks']['victory_deck'] = [trainer_victory]
        state['decks']['victory_discard'] = []

        new_state = engine._award_victory_cards(state, p1_id, 1, source='test')

        self.assertEqual(new_state['turn']['phase'], 'battle')
        self.assertEqual(new_state['turn']['battle']['mode'], 'trainer')
        self.assertEqual(new_state['turn']['battle']['source'], 'victory_card')

    def test_draw_event_victory_card_does_not_double_resolve_event_draws(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        state['decks']['victory_deck'] = [{
            'id': 901,
            'title': 'Event Storm',
            'description': 'Draw 3 Event Cards.',
            'category': 'draw_event_cards',
            'pile': 'victory',
        }]
        state['decks']['event_deck'] = [
            {'id': 101, 'title': 'PokéMarket A', 'description': '2 = Pokéball.', 'category': 'market', 'pile': 'event'},
            {'id': 102, 'title': 'PokéMarket B', 'description': '2 = Pokéball.', 'category': 'market', 'pile': 'event'},
            {'id': 103, 'title': 'PokéMarket C', 'description': '2 = Pokéball.', 'category': 'market', 'pile': 'event'},
        ]
        state['decks']['event_discard'] = []

        with patch('game.engine.cards.random.randint', return_value=2):
            new_state = engine._award_victory_cards(state, p1_id, 1, source='test')  # noqa: SLF001 - valida o pipeline real da engine

        self.assertEqual(new_state['consumed']['events'], [101, 102, 103])
        self.assertEqual(len(new_state['decks']['event_discard']), 3)
        self.assertEqual(new_state['decks']['event_deck'], [])


class TestEventResolution(TestCase):

    def test_event_tile_choice_card_blocks_turn_until_resolution(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        p2 = next(p for p in state['players'] if p['id'] == p2_id)
        p2['position'] = 0
        state['decks']['event_deck'] = [{
            'id': 301,
            'title': 'Teleporter',
            'description': 'Choose any player and move to their tile.',
            'category': 'special_event',
            'pile': 'event',
        }]

        state = _land_on_tile(state, p1_id, 7)
        self.assertEqual(state['turn']['phase'], 'event')
        self.assertIsNotNone(state['turn']['pending_event'])

        state, result = engine.resolve_event(state, p1_id, use_run_away=False)

        self.assertEqual(result, 'ok')
        self.assertEqual(state['turn']['pending_action']['type'], 'reward_choice')
        self.assertEqual(state['turn']['current_player_id'], p1_id)
        self.assertEqual(state['turn']['phase'], 'event')

        state, resolve_result = engine.resolve_pending_action(state, p1_id, p2_id)
        p1 = next(p for p in state['players'] if p['id'] == p1_id)

        self.assertTrue(resolve_result['success'])
        self.assertEqual(p1['position'], 0)
        self.assertEqual(state['turn']['current_player_id'], p2_id)


# ── Testes de Battle Effects ──────────────────────────────────────────────────

class TestBattleEffects(TestCase):
    """
    Testa o sistema de battle_effect — substituição do campo ability para
    determinação de efeitos de batalha.
    """

    def _make_pokemon_with_effect(self, bp: int = 5, battle_effect: str | None = None) -> dict:
        return {
            'id': 1,
            'name': 'TestMon',
            'types': ['normal'],
            'battle_points': bp,
            'master_points': 5,
            'ability': 'Test',
            'ability_type': 'battle',
            'battle_effect': battle_effect,
            'ability_used': False,
        }

    def test_base_score_no_effect(self):
        """Score sem efeito = BP * dado."""
        pokemon = self._make_pokemon_with_effect(bp=5, battle_effect=None)
        score = calculate_battle_score(pokemon, 3)
        self.assertEqual(score, 15)

    def test_earthquake_score(self):
        """Earthquake: score = BP * dado + BP."""
        pokemon = self._make_pokemon_with_effect(bp=5, battle_effect='earthquake')
        score = calculate_battle_score(pokemon, 4)
        self.assertEqual(score, 5 * 4 + 5)  # 25

    def test_swift_score(self):
        """Swift: score = BP * dado + 2."""
        pokemon = self._make_pokemon_with_effect(bp=4, battle_effect='swift')
        score = calculate_battle_score(pokemon, 3)
        self.assertEqual(score, 4 * 3 + 2)  # 14

    def test_critical_hit_uses_max_roll(self):
        """Critical Hit: rola dado extra, usa maior."""
        pokemon = self._make_pokemon_with_effect(bp=5, battle_effect='critical_hit')
        with patch('game.engine.mechanics.random.randint', return_value=6):
            score = calculate_battle_score(pokemon, 2)
        # max(2, 6) = 6 → 5 * 6 = 30
        self.assertEqual(score, 30)

    def test_static_zapdos_uses_best_of_three(self):
        """Static Zapdos: rola 2 extras, usa melhor dos 3."""
        pokemon = self._make_pokemon_with_effect(bp=9, battle_effect='static_zapdos')
        with patch('game.engine.mechanics.random.randint', side_effect=[5, 6]):
            score = calculate_battle_score(pokemon, 1)
        # max(1, 5, 6) = 6 → 9 * 6 = 54
        self.assertEqual(score, 54)

    def test_shadow_ball_uses_critical_hit_scoring(self):
        """Shadow Ball: usa critical_hit para score."""
        pokemon = self._make_pokemon_with_effect(bp=8, battle_effect='shadow_ball')
        with patch('game.engine.mechanics.random.randint', return_value=6):
            score = calculate_battle_score(pokemon, 2)
        self.assertEqual(score, 8 * 6)

    def test_flame_body_uses_earthquake_scoring(self):
        """Flame Body: usa earthquake para score."""
        pokemon = self._make_pokemon_with_effect(bp=9, battle_effect='flame_body')
        score = calculate_battle_score(pokemon, 3)
        self.assertEqual(score, 9 * 3 + 9)

    # ── Efeitos pré-batalha em resolve_duel ──────────────────────────────────

    def test_intimidate_reduces_opponent_roll(self):
        """Intimidate: dado do oponente -1 (mín 1)."""
        attacker = self._make_pokemon_with_effect(bp=5, battle_effect='intimidate')
        defender = self._make_pokemon_with_effect(bp=5, battle_effect=None)
        with patch('game.engine.mechanics.roll_dice', side_effect=[3, 3]):
            result = resolve_duel(attacker, defender)
        # defender_roll = max(1, 3-1) = 2 → score_def = 5*2 = 10
        # attacker_roll = 3 → score_ch = 5*3 = 15 (sem effect no score)
        self.assertEqual(result['defender_roll'], 2)
        self.assertEqual(result['challenger_score'], 15)

    def test_thick_fat_reduces_opponent_bp(self):
        """Thick Fat: BP do oponente -2 (mín 1)."""
        attacker = self._make_pokemon_with_effect(bp=8, battle_effect='thick_fat')
        defender = self._make_pokemon_with_effect(bp=5, battle_effect=None)
        with patch('game.engine.mechanics.roll_dice', side_effect=[4, 4]):
            result = resolve_duel(attacker, defender)
        # defender_bp = max(1, 5-2) = 3 → score_def = 3*4 = 12
        # score_ch = 8*4 = 32 (thick_fat não afeta score próprio)
        self.assertEqual(result['defender_score'], 12)

    def test_pressure_max_forces_opponent_roll_to_1(self):
        """Pressure Max (Mewtwo): dado do oponente = 1."""
        mewtwo = self._make_pokemon_with_effect(bp=10, battle_effect='pressure_max')
        defender = self._make_pokemon_with_effect(bp=5, battle_effect=None)
        with patch('game.engine.mechanics.roll_dice', side_effect=[4, 6]):
            result = resolve_duel(mewtwo, defender)
        # def_roll forçado = 1 → score_def = 5*1 = 5
        self.assertEqual(result['defender_roll'], 1)
        self.assertEqual(result['defender_score'], 5)

    def test_multiscale_ignores_opponent_effect(self):
        """Multiscale (Dragonite): ignora battle_effect do oponente."""
        dragonite = self._make_pokemon_with_effect(bp=9, battle_effect='multiscale')
        mewtwo = self._make_pokemon_with_effect(bp=10, battle_effect='pressure_max')
        with patch('game.engine.mechanics.roll_dice', side_effect=[4, 5]):
            result = resolve_duel(dragonite, mewtwo)
        # Multiscale anula pressure_max do Mewtwo → ch_roll não é forçado a 1
        # ch_roll = 4 → score_ch = 9*4 + 9 = 45 (multiscale = earthquake)
        self.assertNotEqual(result['challenger_roll'], 1)
        self.assertEqual(result['challenger_score'], 9 * 4 + 9)

    def test_transform_copies_opponent_bp(self):
        """Transform (Ditto): copia BP do oponente."""
        ditto = self._make_pokemon_with_effect(bp=5, battle_effect='transform')
        charizard = self._make_pokemon_with_effect(bp=9, battle_effect=None)
        with patch('game.engine.mechanics.roll_dice', side_effect=[3, 3]):
            result = resolve_duel(ditto, charizard)
        # ditto copia BP=9 → score_ch = 9*3 = 27
        self.assertEqual(result['challenger_score'], 27)

    def test_result_includes_battle_effects(self):
        """resolve_duel retorna challenger_battle_effect e defender_battle_effect."""
        attacker = self._make_pokemon_with_effect(bp=5, battle_effect='earthquake')
        defender = self._make_pokemon_with_effect(bp=5, battle_effect='swift')
        with patch('game.engine.mechanics.roll_dice', side_effect=[3, 3]):
            result = resolve_duel(attacker, defender)
        self.assertEqual(result['challenger_battle_effect'], 'earthquake')
        self.assertEqual(result['defender_battle_effect'], 'swift')

    # ── Efeitos pós-batalha em _resolve_duel (via engine) ────────────────────

    def _two_players_with_specific_pokemon(self, p1_pokemon: dict, p2_pokemon: dict):
        """Cria jogo com 2 jogadores e Pokémon específicos para testar batalha."""
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])

        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        p2 = next(p for p in state['players'] if p['id'] == p2_id)

        p1['pokemon'] = [p1_pokemon]
        p2['pokemon'] = [p2_pokemon]

        # Limpa baralhos de vitória/evento para isolar testes de efeitos de batalha
        # de cartas aleatórias que poderiam consumir rolls extras do mock ou alterar itens.
        state['decks']['victory_deck'] = []
        state['decks']['victory_discard'] = []
        state['decks']['event_deck'] = []
        state['decks']['event_discard'] = []

        return state, p1_id, p2_id

    def test_poison_sting_winner_loses_fr_from_loser(self):
        """Poison Sting: perdedor perde 1 Full Restore."""
        weedle = {**self._make_pokemon_with_effect(bp=10, battle_effect='poison_sting'), 'name': 'Weedle'}
        rattata = {**self._make_pokemon_with_effect(bp=1, battle_effect=None), 'name': 'Rattata'}
        state, p1_id, p2_id = self._two_players_with_specific_pokemon(weedle, rattata)

        state = engine.start_duel(state, p1_id, p2_id)
        p2 = next(p for p in state['players'] if p['id'] == p2_id)
        fr_before = p2['full_restores']

        # Fase 1: ambos escolhem (sem dados); Fase 2: rolagem individual
        state, _ = engine.register_battle_choice(state, p2_id, 0)
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        with patch('game.engine.mechanics.roll_dice', side_effect=[6, 1]):
            state, _ = engine.register_battle_roll(state, p1_id)
            state, result = engine.register_battle_roll(state, p2_id)

        p2_after = next(p for p in state['players'] if p['id'] == p2_id)
        self.assertEqual(result['winner_id'], p1_id)
        self.assertEqual(p2_after['full_restores'], fr_before - 1)

    def test_super_fang_steals_pokeball(self):
        """Super Fang: vencedor rouba 1 Pokébola do perdedor."""
        raticate = {**self._make_pokemon_with_effect(bp=10, battle_effect='super_fang'), 'name': 'Raticate'}
        magikarp = {**self._make_pokemon_with_effect(bp=1, battle_effect=None), 'name': 'Magikarp'}
        state, p1_id, p2_id = self._two_players_with_specific_pokemon(raticate, magikarp)

        state = engine.start_duel(state, p1_id, p2_id)
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        p2 = next(p for p in state['players'] if p['id'] == p2_id)
        p1_pb_before = p1['pokeballs']
        p2_pb_before = p2['pokeballs']

        state, _ = engine.register_battle_choice(state, p2_id, 0)
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        with patch('game.engine.mechanics.roll_dice', side_effect=[6, 1]):
            state, _ = engine.register_battle_roll(state, p1_id)
            state, result = engine.register_battle_roll(state, p2_id)

        p1_after = next(p for p in state['players'] if p['id'] == p1_id)
        p2_after = next(p for p in state['players'] if p['id'] == p2_id)
        self.assertEqual(result['winner_id'], p1_id)
        self.assertEqual(p1_after['pokeballs'], min(p1_pb_before + 1, 12))
        self.assertEqual(p2_after['pokeballs'], p2_pb_before - 1)
        self.assertEqual(p1_after['pokeball_slots_free'], p1_after['pokeballs'])
        self.assertEqual(p2_after['pokeball_slots_free'], p2_after['pokeballs'])

    def test_player_duel_without_pokeball_effects_keeps_pokeballs(self):
        """Duelo comum sem efeito de Pokébola não deve alterar o inventário."""
        pikachu = {**self._make_pokemon_with_effect(bp=8, battle_effect=None), 'name': 'Pikachu'}
        squirtle = {**self._make_pokemon_with_effect(bp=4, battle_effect=None), 'name': 'Squirtle'}
        state, p1_id, p2_id = self._two_players_with_specific_pokemon(pikachu, squirtle)

        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        p2 = next(p for p in state['players'] if p['id'] == p2_id)
        p1_pb_before = p1['pokeballs']
        p2_pb_before = p2['pokeballs']

        state = engine.start_duel(state, p1_id, p2_id)
        state, _ = engine.register_battle_choice(state, p2_id, 0)
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        with patch('game.engine.mechanics.roll_dice', side_effect=[6, 1]):
            state, _ = engine.register_battle_roll(state, p1_id)
            state, result = engine.register_battle_roll(state, p2_id)

        p1_after = next(p for p in state['players'] if p['id'] == p1_id)
        p2_after = next(p for p in state['players'] if p['id'] == p2_id)
        self.assertEqual(result['winner_id'], p1_id)
        self.assertEqual(p1_after['pokeballs'], p1_pb_before)
        self.assertEqual(p2_after['pokeballs'], p2_pb_before)

    def test_shed_skin_winner_recovers_fr(self):
        """Shed Skin: vencedor recupera 1 Full Restore."""
        dratini = {**self._make_pokemon_with_effect(bp=10, battle_effect='shed_skin'), 'name': 'Dratini'}
        magikarp = {**self._make_pokemon_with_effect(bp=1, battle_effect=None), 'name': 'Magikarp'}
        state, p1_id, p2_id = self._two_players_with_specific_pokemon(dratini, magikarp)

        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        p1['full_restores'] = 3  # Abaixo do max
        p1['items'] = {'pokeballs': p1['pokeballs'], 'full_restores': 3}
        sync_player_inventory(p1)
        fr_before = 3

        state = engine.start_duel(state, p1_id, p2_id)
        state, _ = engine.register_battle_choice(state, p2_id, 0)
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        with patch('game.engine.mechanics.roll_dice', side_effect=[6, 1]):
            state, _ = engine.register_battle_roll(state, p1_id)
            state, result = engine.register_battle_roll(state, p2_id)

        p1_after = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertEqual(result['winner_id'], p1_id)
        self.assertEqual(p1_after['full_restores'], fr_before + 1)

    def test_curse_loser_loses_extra_mp(self):
        """Curse: perdedor perde 5 MP extras."""
        haunter = {**self._make_pokemon_with_effect(bp=10, battle_effect='curse'), 'name': 'Haunter'}
        magikarp = {**self._make_pokemon_with_effect(bp=1, battle_effect=None), 'name': 'Magikarp'}
        state, p1_id, p2_id = self._two_players_with_specific_pokemon(haunter, magikarp)

        p2 = next(p for p in state['players'] if p['id'] == p2_id)
        sync_player_inventory(p2)
        mp_before = p2['master_points']

        state = engine.start_duel(state, p1_id, p2_id)
        state, _ = engine.register_battle_choice(state, p2_id, 0)
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        with patch('game.engine.mechanics.roll_dice', side_effect=[6, 1]):
            state, _ = engine.register_battle_roll(state, p1_id)
            state, result = engine.register_battle_roll(state, p2_id)

        p2_after = next(p for p in state['players'] if p['id'] == p2_id)
        self.assertEqual(result['winner_id'], p1_id)
        # Perdedor perde 5 MP extras (curse), não ganha o +5 do vencedor
        self.assertEqual(p2_after['master_points'], mp_before - 5)


# ── Testes de PokemonCard (modelo formal) ─────────────────────────────────────

class TestPokemonCard(TestCase):
    """Testa o dataclass PokemonCard em engine/models.py."""

    def _sample_dict(self, **overrides) -> dict:
        base = {
            'id': 25,
            'name': 'Pikachu',
            'types': ['electric'],
            'battle_points': 5,
            'master_points': 5,
            'ability': 'Static',
            'ability_description': 'critical_hit: rola dado extra em batalha',
            'ability_type': 'battle',
            'battle_effect': 'critical_hit',
            'ability_charges': None,
            'evolves_to': 26,
            'is_starter': False,
            'is_legendary': False,
            'is_baby': False,
            'rarity': 'rare',
        }
        base.update(overrides)
        return base

    def test_from_dict_creates_card(self):
        card = PokemonCard.from_dict(self._sample_dict())
        self.assertEqual(card.name, 'Pikachu')
        self.assertEqual(card.battle_points, 5)
        self.assertEqual(card.battle_effect, 'critical_hit')

    def test_can_evolve_true(self):
        card = PokemonCard.from_dict(self._sample_dict(evolves_to=26))
        self.assertTrue(card.can_evolve())

    def test_can_evolve_false(self):
        card = PokemonCard.from_dict(self._sample_dict(evolves_to=None))
        self.assertFalse(card.can_evolve())

    def test_is_battle_ability(self):
        card = PokemonCard.from_dict(self._sample_dict())
        self.assertTrue(card.is_battle_ability())

    def test_is_not_baby_for_gen1(self):
        card = PokemonCard.from_dict(self._sample_dict())
        self.assertFalse(card.is_baby)

    def test_legendary_flag(self):
        card = PokemonCard.from_dict(self._sample_dict(is_legendary=True))
        self.assertTrue(card.is_legendary)

    def test_validate_valid_card(self):
        card = PokemonCard.from_dict(self._sample_dict())
        errors = card.validate()
        self.assertEqual(errors, [])

    def test_validate_invalid_bp(self):
        card = PokemonCard.from_dict(self._sample_dict(battle_points=0))
        errors = card.validate()
        self.assertTrue(any('battle_points' in e for e in errors))

    def test_validate_unknown_battle_effect(self):
        card = PokemonCard.from_dict(self._sample_dict(battle_effect='nonexistent_effect'))
        errors = card.validate()
        self.assertTrue(any('battle_effect' in e for e in errors))

    def test_to_dict_roundtrip(self):
        original = self._sample_dict()
        card = PokemonCard.from_dict(original)
        d = card.to_dict()
        self.assertEqual(d['name'], original['name'])
        self.assertEqual(d['battle_effect'], original['battle_effect'])
        self.assertEqual(d['is_legendary'], original['is_legendary'])
        self.assertEqual(d['is_baby'], original['is_baby'])

    def test_all_runtime_pokemon_have_valid_battle_effects(self):
        """Todas as cartas runtime derivadas do metadata canônico têm battle_effect válido (ou None)."""
        from game.engine.cards import load_pokemon_cards
        cards = load_pokemon_cards()
        for data in cards:
            card = PokemonCard.from_dict(data)
            errors = card.validate()
            self.assertEqual(
                errors, [],
                msg=f"Pokémon {card.name} (id={card.id}) tem erros: {errors}",
            )

    def test_all_runtime_pokemon_have_is_legendary_field(self):
        """Campo is_legendary presente em todas as cartas runtime derivadas do metadata canônico."""
        from game.engine.cards import load_pokemon_cards
        cards = load_pokemon_cards()
        for data in cards:
            self.assertIn('is_legendary', data, msg=f"{data['name']} sem is_legendary")

    def test_runtime_dataset_comes_from_cards_metadata(self):
        """O loader runtime usa o cards_metadata.json como conjunto canônico de cartas."""
        from game.engine.cards import load_pokemon_cards

        root = Path(__file__).resolve().parents[2]
        metadata = json.loads((root / 'cards_metadata.json').read_text(encoding='utf-8'))['cards']
        runtime_cards = load_pokemon_cards()

        metadata_names = {card['real_name'] for card in metadata}
        runtime_names = {card['name'] for card in runtime_cards}
        self.assertEqual(runtime_names, metadata_names)
        bulbasaur_runtime = next(card for card in runtime_cards if card['name'] == 'Bulbasaur')
        bulbasaur_metadata = next(card for card in metadata if card['real_name'] == 'Bulbasaur')
        self.assertEqual(bulbasaur_runtime['battle_points'], bulbasaur_metadata['power'])

    def test_compatibility_pokemon_json_is_derived_from_runtime_dataset(self):
        """pokemon.json permanece apenas como snapshot derivado do runtime canônico."""
        from game.engine.cards import load_pokemon_cards

        root = Path(__file__).resolve().parents[2]
        compatibility_snapshot = json.loads((root / 'game' / 'data' / 'pokemon.json').read_text(encoding='utf-8'))
        runtime_cards = load_pokemon_cards()

        self.assertEqual(len(compatibility_snapshot), len(runtime_cards))
        self.assertEqual(
            {card['name'] for card in compatibility_snapshot},
            {card['name'] for card in runtime_cards},
        )

    def test_legendary_pokemon_count(self):
        """O conjunto de lendários runtime espelha o metadata canônico consolidado."""
        from game.engine.cards import load_pokemon_cards
        cards = load_pokemon_cards()
        legendary = [p for p in cards if p.get('is_legendary')]
        legendary_names = {p['name'] for p in legendary}
        expected = {'Articuno', 'Celebi', 'Entei', 'Mew', 'Mewtwo', 'Moltres', 'Raikou', 'Suicune', 'Zapdos'}
        self.assertEqual(legendary_names, expected)

    def test_kanto_basic1_cards_resolve_public_images(self):
        """As cartas extraídas do sheet Basic 1 (x8) resolvem image_path público no runtime."""
        from game.engine.cards import load_pokemon_by_name

        expected_public_paths = {
            'Pidgey': '/assets/pokemon/pidgey.png',
            'Pidgeotto': '/assets/pokemon/pidgeotto.png',
            'Pidgeot': '/assets/pokemon/pidgeot.png',
            'Paras': '/assets/pokemon/paras.png',
            'Parasect': '/assets/pokemon/parasect.png',
            'Weedle': '/assets/pokemon/weedle.png',
            'Kakuna': '/assets/pokemon/kakuna.png',
            'Beedrill': '/assets/pokemon/beedrill.png',
        }

        for pokemon_name, expected_path in expected_public_paths.items():
            with self.subTest(pokemon=pokemon_name):
                runtime_card = load_pokemon_by_name(pokemon_name)
                self.assertIsNotNone(runtime_card)
                self.assertEqual(runtime_card['image_path'], expected_path)

    def test_paras_runtime_chain_now_includes_parasect(self):
        """Paras -> Parasect fica resolvido no runtime canônico depois da extração do sheet Kanto."""
        from game.engine.cards import load_pokemon_by_name

        paras = load_pokemon_by_name('Paras')
        parasect = load_pokemon_by_name('Parasect')

        self.assertIsNotNone(paras)
        self.assertIsNotNone(parasect)
        self.assertEqual(paras['evolves_to'], 'Parasect')
        self.assertEqual(parasect['battle_points'], 6)
        self.assertEqual(parasect['master_points'], 70)


# ── Testes de EventCard (modelo formal) ───────────────────────────────────────

class TestEventCard(TestCase):

    def test_is_negative_lose_pokeball(self):
        card = EventCard.from_dict({
            'id': 1, 'title': 'Perde Pokébola', 'description': '',
            'effect': {'type': 'lose_pokeball', 'amount': 1},
        })
        self.assertTrue(card.is_negative())

    def test_is_not_negative_gain_pokeball(self):
        card = EventCard.from_dict({
            'id': 2, 'title': 'Ganha Pokébola', 'description': '',
            'effect': {'type': 'gain_pokeball', 'amount': 1},
        })
        self.assertFalse(card.is_negative())


# ── Testes do Player de Teste Visual (Debug) ──────────────────────────────────

class TestDebugTestPlayer(TestCase):
    """Testes do player de teste isolado para o painel de debug visual do pino."""

    def _base_state(self):
        """Estado real de 2 jogadores como ponto de partida."""
        state, p1_id, p2_id = _init_two_player_game()
        return state, p1_id, p2_id

    # ── Toggle ────────────────────────────────────────────────────────────────

    def test_enable_creates_debug_session(self):
        state, _, _ = self._base_state()
        new_state, result = engine.set_debug_test_player_enabled(state, True)

        self.assertIsNotNone(new_state)
        self.assertTrue(new_state['debug_visual']['enabled'])
        self.assertIsInstance(new_state['debug_visual']['session_state'], dict)
        self.assertTrue(result['enabled'])

    def test_disable_removes_debug_session(self):
        state, _, _ = self._base_state()
        state, _ = engine.set_debug_test_player_enabled(state, True)
        new_state, result = engine.set_debug_test_player_enabled(state, False)

        self.assertIsNotNone(new_state)
        self.assertFalse(new_state['debug_visual']['enabled'])
        self.assertIsNone(new_state['debug_visual']['session_state'])
        self.assertFalse(result['enabled'])

    def test_debug_session_has_test_player(self):
        state, _, _ = self._base_state()
        new_state, _ = engine.set_debug_test_player_enabled(state, True)

        session = new_state['debug_visual']['session_state']
        players = session.get('players', [])
        self.assertEqual(len(players), 1)
        self.assertEqual(players[0]['id'], '__debug_test_player__')
        self.assertTrue(players[0].get('is_test_player'))

    # ── Inventário inicial ────────────────────────────────────────────────────

    def test_debug_player_has_pichu_as_starter(self):
        state, _, _ = self._base_state()
        new_state, _ = engine.set_debug_test_player_enabled(state, True)

        session = new_state['debug_visual']['session_state']
        player = session['players'][0]
        starter = player.get('starter_pokemon')
        self.assertIsNotNone(starter, 'Player de teste deve ter Pichu como starter')
        self.assertEqual(starter['name'], 'Pichu')

    def test_debug_player_has_initial_items(self):
        from game.engine.inventory import get_starting_resource_defaults
        state, _, _ = self._base_state()
        new_state, _ = engine.set_debug_test_player_enabled(state, True)

        session = new_state['debug_visual']['session_state']
        player = session['players'][0]
        defaults = get_starting_resource_defaults()

        self.assertIn('items', player)
        self.assertIn('pokemon_inventory', player, 'sync_player_inventory deve popular pokemon_inventory')

    def test_debug_player_has_pokeballs(self):
        state, _, _ = self._base_state()
        new_state, _ = engine.set_debug_test_player_enabled(state, True)

        session = new_state['debug_visual']['session_state']
        player = session['players'][0]
        self.assertGreaterEqual(player.get('pokeballs', 0), 0)

    # ── Movimento por N casas ─────────────────────────────────────────────────

    def test_move_debug_player_changes_position(self):
        state, _, _ = self._base_state()
        state, _ = engine.set_debug_test_player_enabled(state, True)

        new_state, result = engine.move_debug_test_player(state, 3)

        self.assertIsNotNone(new_state)
        session = new_state['debug_visual']['session_state']
        player = session['players'][0]
        self.assertEqual(player['position'], result['position'])
        self.assertEqual(result['steps'], 3)

    def test_move_debug_player_sets_last_roll(self):
        state, _, _ = self._base_state()
        state, _ = engine.set_debug_test_player_enabled(state, True)

        new_state, _ = engine.move_debug_test_player(state, 5)

        session = new_state['debug_visual']['session_state']
        last_roll = session['turn'].get('last_roll')
        self.assertIsNotNone(last_roll)
        self.assertEqual(last_roll['final_result'], 5)

    def test_move_debug_player_invalid_steps_returns_error(self):
        state, _, _ = self._base_state()
        state, _ = engine.set_debug_test_player_enabled(state, True)

        new_state, error = engine.move_debug_test_player(state, 0)
        self.assertIsNone(new_state)
        self.assertIsInstance(error, str)

    def test_move_requires_debug_enabled(self):
        state, _, _ = self._base_state()
        new_state, error = engine.move_debug_test_player(state, 3)
        self.assertIsNone(new_state)
        self.assertIsInstance(error, str)

    # ── Rolagem de dado ───────────────────────────────────────────────────────

    def test_roll_debug_player_changes_position(self):
        state, _, _ = self._base_state()
        state, _ = engine.set_debug_test_player_enabled(state, True)

        new_state, result = engine.roll_debug_test_player(state)

        self.assertIsNotNone(new_state)
        self.assertTrue(result['success'])
        self.assertIn(result['roll'], range(1, 7))
        session = new_state['debug_visual']['session_state']
        player = session['players'][0]
        self.assertEqual(player['position'], result['position'])

    def test_roll_sets_last_roll_in_session(self):
        state, _, _ = self._base_state()
        state, _ = engine.set_debug_test_player_enabled(state, True)

        new_state, result = engine.roll_debug_test_player(state)

        session = new_state['debug_visual']['session_state']
        last_roll = session['turn'].get('last_roll')
        self.assertIsNotNone(last_roll)
        self.assertEqual(last_roll['final_result'], result['roll'])

    def test_roll_requires_debug_enabled(self):
        state, _, _ = self._base_state()
        new_state, error = engine.roll_debug_test_player(state)
        self.assertIsNone(new_state)
        self.assertIsInstance(error, str)

    # ── Trigger do tile ───────────────────────────────────────────────────────

    def test_trigger_tile_requires_debug_enabled(self):
        state, _, _ = self._base_state()
        new_state, error = engine.trigger_debug_test_player_tile(state)
        self.assertIsNone(new_state)
        self.assertIsInstance(error, str)

    def test_trigger_tile_executes_for_debug_player(self):
        state, _, _ = self._base_state()
        state, _ = engine.set_debug_test_player_enabled(state, True)

        new_state, result = engine.trigger_debug_test_player_tile(state)

        self.assertIsNotNone(new_state)
        self.assertIsInstance(result, (dict, str))

    # ── Isolamento dos jogadores reais ────────────────────────────────────────

    def test_debug_player_does_not_alter_real_players(self):
        state, p1_id, p2_id = self._base_state()
        real_players_before = [p.copy() for p in state['players']]

        state, _ = engine.set_debug_test_player_enabled(state, True)
        state, _ = engine.move_debug_test_player(state, 4)
        state, _ = engine.roll_debug_test_player(state)

        real_players_after = state['players']
        self.assertEqual(len(real_players_after), len(real_players_before))
        for before, after in zip(real_players_before, real_players_after):
            self.assertEqual(before['id'], after['id'])
            self.assertEqual(before['position'], after['position'])

    def test_debug_player_not_in_real_players_list(self):
        state, _, _ = self._base_state()
        state, _ = engine.set_debug_test_player_enabled(state, True)

        debug_id = '__debug_test_player__'
        real_player_ids = [p['id'] for p in state['players']]
        self.assertNotIn(debug_id, real_player_ids)


# ── Testes dos fluxos reais do debug player (captura, evento, skip) ───────────

class TestDebugTestPlayerFlows(TestCase):
    """Testa que o debug player participa de fluxos reais de captura/evento/skip."""

    def _enabled_state(self):
        p1 = _make_player('Ash', host=True)
        p2 = _make_player('Misty')
        state = build_initial_state('FLOW01')
        state['players'] = [p1, p2]
        state = engine.initialize_game(state)
        state, _ = engine.set_debug_test_player_enabled(state, True)
        return state, p1['id'], p2['id']

    def _session(self, state):
        return state['debug_visual']['session_state']

    # ── Inventário real ───────────────────────────────────────────────────────

    def test_debug_player_inventory_is_real_state_not_hardcoded(self):
        """O inventário do debug player existe no estado real, não é texto fixo."""
        state, _, _ = self._enabled_state()
        session = self._session(state)
        player = session['players'][0]

        self.assertIn('pokemon_inventory', player)
        self.assertIn('items', player)
        self.assertIsInstance(player['pokemon_inventory'], list)
        self.assertIsInstance(player['items'], list)

    def test_debug_player_pichu_is_in_state_not_just_text(self):
        """Pichu existe como starter_pokemon real no estado, com campos completos."""
        state, _, _ = self._enabled_state()
        session = self._session(state)
        player = session['players'][0]

        starter = player.get('starter_pokemon')
        self.assertIsNotNone(starter)
        self.assertEqual(starter['name'], 'Pichu')
        self.assertIn('battle_points', starter)
        self.assertIn('id', starter)

    def test_debug_player_pokemon_inventory_includes_pichu(self):
        """Pichu está no pokemon_inventory (campo usado pelo InventoryModal)."""
        state, _, _ = self._enabled_state()
        session = self._session(state)
        player = session['players'][0]

        pokemon_inventory = player.get('pokemon_inventory', [])
        names = [p['name'] for p in pokemon_inventory]
        self.assertIn('Pichu', names)

    def test_debug_add_pokemon_to_test_player_updates_session_inventory(self):
        state, _, _ = self._enabled_state()

        new_state, result = engine.debug_add_pokemon_to_test_player(state, 'Pikachu')

        self.assertIsNotNone(new_state, f'Erro inesperado: {result}')
        self.assertTrue(result['success'])
        session = self._session(new_state)
        player = session['players'][0]
        names = [pokemon['name'] for pokemon in player.get('pokemon_inventory', [])]
        self.assertIn('Pikachu', names)
        self.assertEqual(result['pokemon']['name'], 'Pikachu')

    # ── Captura via lógica real ───────────────────────────────────────────────

    def _state_with_pending_pokemon(self):
        """Move debug player para um tile grass e dispara trigger real."""
        from unittest.mock import patch

        state, p1_id, p2_id = self._enabled_state()
        state_with_enabled, _ = engine.set_debug_test_player_enabled(state, True)

        session = self._session(state_with_enabled)
        board = session.get('board', {})
        tiles = board.get('tiles', [])
        grass_tile = next((t for t in tiles if t.get('type') == 'grass'), None)
        if not grass_tile:
            return None, p1_id, p2_id

        session['players'][0]['position'] = grass_tile['id']
        session['turn']['current_player_id'] = '__debug_test_player__'
        session['turn']['phase'] = 'roll'
        state_with_enabled['debug_visual']['session_state'] = session

        new_state, result = engine.trigger_debug_test_player_tile(state_with_enabled)
        return new_state, p1_id, p2_id

    def test_trigger_tile_on_grass_sets_pending_pokemon(self):
        """Trigger em tile grass define pending_pokemon na sessão de debug."""
        state, _, _ = self._state_with_pending_pokemon()
        if state is None:
            self.skipTest('Nenhum tile grass disponível no tabuleiro de teste')

        session = self._session(state)
        pending = session['turn'].get('pending_pokemon') or session['turn'].get('pending_action')
        self.assertIsNotNone(pending, 'Tile grass deve gerar pending_pokemon ou pending_action')

    def test_roll_capture_uses_real_capture_logic(self):
        """debug_roll_capture_for_test_player usa a mesma lógica real de captura."""
        state, _, _ = self._state_with_pending_pokemon()
        if state is None:
            self.skipTest('Nenhum tile grass disponível')

        session_before = self._session(state)
        pending = session_before['turn'].get('pending_action')
        if not (pending and pending.get('type') == 'capture_attempt'):
            self.skipTest('pending_action de captura não foi gerado para este tile grass')

        new_state, result = engine.debug_roll_capture_for_test_player(state)

        self.assertIsNotNone(new_state, f'Erro inesperado: {result}')
        self.assertIsInstance(result, dict)

    def test_roll_capture_without_pending_returns_error(self):
        """Roll de captura sem captura pendente retorna erro."""
        state, _, _ = self._enabled_state()
        new_state, error = engine.debug_roll_capture_for_test_player(state)
        self.assertIsNone(new_state)
        self.assertIsInstance(error, str)

    def test_roll_capture_does_not_affect_real_players(self):
        """Roll de captura do debug não toca nos jogadores reais."""
        state, p1_id, _ = self._state_with_pending_pokemon()
        if state is None:
            self.skipTest('Sem tile grass')

        real_players_before = [p.copy() for p in state['players']]
        engine.debug_roll_capture_for_test_player(state)

        for before, after in zip(real_players_before, state['players']):
            self.assertEqual(before['id'], after['id'])
            self.assertEqual(before.get('pokemon', []), after.get('pokemon', []))

    # ── Evento via lógica real ────────────────────────────────────────────────

    def _state_with_pending_event(self):
        """Move debug player para um tile event e dispara trigger real."""
        state, p1_id, p2_id = self._enabled_state()
        session = self._session(state)
        board = session.get('board', {})
        tiles = board.get('tiles', [])
        event_tile = next((t for t in tiles if t.get('type') == 'event'), None)
        if not event_tile:
            return None, p1_id, p2_id

        session['players'][0]['position'] = event_tile['id']
        session['turn']['current_player_id'] = '__debug_test_player__'
        session['turn']['phase'] = 'roll'
        state['debug_visual']['session_state'] = session

        new_state, result = engine.trigger_debug_test_player_tile(state)
        return new_state, p1_id, p2_id

    def test_trigger_tile_on_event_sets_pending_event(self):
        """Trigger em tile event define pending_event na sessão de debug."""
        state, _, _ = self._state_with_pending_event()
        if state is None:
            self.skipTest('Nenhum tile event disponível')

        session = self._session(state)
        pending_event = session['turn'].get('pending_event')
        self.assertIsNotNone(pending_event, 'Tile event deve gerar pending_event')
        self.assertIn('title', pending_event)

    def test_resolve_event_uses_real_event_logic(self):
        """debug_resolve_event_for_test_player usa a mesma lógica real de evento."""
        state, _, _ = self._state_with_pending_event()
        if state is None:
            self.skipTest('Nenhum tile event disponível')

        session = self._session(state)
        if not session['turn'].get('pending_event'):
            self.skipTest('Sem pending_event após trigger tile event')

        new_state, result = engine.debug_resolve_event_for_test_player(state)
        self.assertIsNotNone(new_state, f'Erro inesperado: {result}')

    def test_resolve_event_without_pending_returns_error(self):
        """Resolve evento sem evento pendente retorna erro."""
        state, _, _ = self._enabled_state()
        new_state, error = engine.debug_resolve_event_for_test_player(state)
        self.assertIsNone(new_state)
        self.assertIsInstance(error, str)

    def test_resolve_event_does_not_affect_real_players(self):
        """Resolver evento do debug não toca nos jogadores reais."""
        state, _, _ = self._state_with_pending_event()
        if state is None:
            self.skipTest('Sem tile event')

        real_positions_before = {p['id']: p['position'] for p in state['players']}
        engine.debug_resolve_event_for_test_player(state)

        for pid, pos in real_positions_before.items():
            real_player = next(p for p in state['players'] if p['id'] == pid)
            self.assertEqual(real_player['position'], pos)

    # ── Skip pending ─────────────────────────────────────────────────────────

    def test_skip_pending_resets_debug_session(self):
        """debug_skip_test_player_pending reseta a sessão para fase roll."""
        state, _, _ = self._state_with_pending_event()
        if state is None:
            self.skipTest('Sem tile event')

        new_state, result = engine.debug_skip_test_player_pending(state)
        self.assertIsNotNone(new_state)

        session = self._session(new_state)
        self.assertEqual(session['turn']['phase'], 'roll')
        self.assertIsNone(session['turn']['pending_event'])
        self.assertIsNone(session['turn']['pending_pokemon'])

    def test_skip_pending_requires_debug_enabled(self):
        """Skip sem debug habilitado retorna erro."""
        p1 = _make_player('Ash', host=True)
        p2 = _make_player('Misty')
        state = build_initial_state('SKP01')
        state['players'] = [p1, p2]
        state = engine.initialize_game(state)

        new_state, error = engine.debug_skip_test_player_pending(state)
        self.assertIsNone(new_state)
        self.assertIsInstance(error, str)

    def test_skip_pending_does_not_affect_real_players(self):
        """Skip do debug não afeta jogadores reais."""
        state, _, _ = self._enabled_state()
        real_players_before = [p.copy() for p in state['players']]

        engine.debug_skip_test_player_pending(state)

        for before, after in zip(real_players_before, state['players']):
            self.assertEqual(before['id'], after['id'])

    # ── Ginásio via lógica real ──────────────────────────────────────────────

    def _state_with_debug_gym_battle(self):
        state, _, _ = self._enabled_state()
        session = self._session(state)
        debug_player = session['players'][0]
        debug_player['starter_pokemon'] = None
        debug_player['pokemon'] = [
            {**_make_pokemon(name='Pidgey', bp=3), 'types': ['Flying']},
            {**_make_pokemon(name='Bulbasaur', bp=5), 'types': ['Grass']},
        ]
        session['turn']['current_player_id'] = '__debug_test_player__'
        session['turn']['phase'] = 'roll'
        session['players'][0]['position'] = 49
        state['debug_visual']['session_state'] = session
        return state

    def test_trigger_tile_on_gym_starts_gym_battle_for_debug_player(self):
        state = self._state_with_debug_gym_battle()

        new_state, result = engine.trigger_debug_test_player_tile(state)

        self.assertIsNotNone(new_state, f'Erro inesperado: {result}')
        session = self._session(new_state)
        self.assertEqual(session['turn']['phase'], 'battle')
        self.assertEqual(session['turn']['battle']['mode'], 'gym')
        self.assertEqual(session['turn']['battle']['gym_id'], 'misty')

    def test_debug_player_can_play_and_resolve_gym_heal_pending(self):
        state = self._state_with_debug_gym_battle()
        session = self._session(state)
        session['decks']['victory_deck'] = [{
            'id': 99002,
            'title': 'Simple Gym Victory',
            'description': 'Reward card used in tests.',
            'category': 'special_event',
        }]
        session['decks']['victory_discard'] = []
        state['debug_visual']['session_state'] = session

        with patch('game.engine.state.apply_victory_effect', side_effect=lambda game_state, *_args: (game_state, {'category': 'noop'})), \
             patch('game.engine.state.roll_battle_dice', side_effect=[1, 3, 6, 1, 6, 1]):
            state, _ = engine.trigger_debug_test_player_tile(state)
            state, _ = engine.debug_duel_choose_pokemon(state, 0)
            state, result = engine.debug_duel_roll_battle(state)
            self.assertTrue(result['needs_new_choice'])

            state, _ = engine.debug_duel_choose_pokemon(state, 0)
            state, result = engine.debug_duel_roll_battle(state)
            self.assertFalse(result['battle_finished'])

            state, result = engine.debug_duel_roll_battle(state)
            self.assertTrue(result['gym_victory'])

        session_after = self._session(state)
        pending = session_after['turn'].get('pending_action')
        self.assertIsNotNone(pending)
        self.assertEqual(pending['type'], 'gym_heal')

        state, resolve_result = engine.debug_resolve_pending_action_for_test_player(state, 'pokemon:0')
        self.assertIsNotNone(state, f'Erro inesperado: {resolve_result}')
        session_after_heal = self._session(state)
        self.assertEqual(len(session_after_heal['decks']['victory_discard']), 1)
        self.assertFalse(session_after_heal['players'][0]['pokemon'][0].get('knocked_out', False))


# ── Testes do fluxo de duelo do debug player ──────────────────────────────────

class TestDebugTestPlayerDuel(TestCase):
    """Testa o duelo compartilhado do player de teste com jogadores reais."""

    def _state_with_duel_tile(self):
        """Debug player posicionado em um tile de duelo, pronto para desafiar."""
        p1 = _make_player('Ash', host=True)
        p2 = _make_player('Misty')
        # Ambos precisam de pokemon para duelar
        starter_data = {'id': 25, 'name': 'Pikachu', 'types': ['Electric'],
                        'battle_points': 5, 'master_points': 10,
                        'ability': 'none', 'ability_type': 'none', 'battle_effect': None,
                        'evolves_to': None, 'slot_cost': 1}
        p1['starter_pokemon'] = starter_data.copy()
        p2['starter_pokemon'] = {**starter_data, 'id': 4, 'name': 'Charmander', 'types': ['Fire']}

        state = build_initial_state('DUEL01')
        state['players'] = [p1, p2]
        state = engine.initialize_game(state)
        state, _ = engine.set_debug_test_player_enabled(state, True)

        session = state['debug_visual']['session_state']
        board = session.get('board', {})
        tiles = board.get('tiles', [])
        duel_tile = next((t for t in tiles if t.get('type') == 'duel'), None)
        if not duel_tile:
            return None, p1['id'], p2['id']

        session['players'][0]['position'] = duel_tile['id']
        session['turn']['current_player_id'] = '__debug_test_player__'
        session['turn']['phase'] = 'action'
        session['turn']['capture_context'] = 'duel'
        state['debug_visual']['session_state'] = session
        state['turn']['round'] = 3
        state['turn']['current_player_id'] = p2['id']
        state['turn']['phase'] = 'action'
        state['turn']['dice_result'] = 4
        state['turn']['last_roll'] = {'raw_result': 4, 'final_result': 4}
        state['turn']['current_tile'] = {'id': 7, 'name': 'Pokecenter'}
        return state, p1['id'], p2['id']

    def test_start_duel_with_real_player_uses_shared_battle_state(self):
        """Debug player entra no battle state principal e sai da sessão isolada."""
        state, p1_id, _ = self._state_with_duel_tile()
        if state is None:
            self.skipTest('Sem tile de duelo no tabuleiro')

        new_state, result = engine.debug_start_duel_with_player(state, p1_id)

        self.assertIsNotNone(new_state, f'Erro: {result}')
        self.assertTrue(result.get('success'))
        battle = new_state['turn'].get('battle')
        self.assertIsNotNone(battle)
        self.assertEqual(new_state['turn']['phase'], 'battle')
        self.assertEqual(battle['challenger_id'], '__debug_test_player__')
        self.assertEqual(battle['defender_id'], p1_id)
        self.assertEqual(battle['sub_phase'], 'choosing')
        self.assertEqual(battle['choice_stage'], 'defender')
        self.assertEqual(battle.get('source'), 'debug_test_player')
        self.assertIsNone(new_state['debug_visual']['session_state']['turn'].get('battle'))

    def test_start_duel_requires_duel_phase(self):
        """start_duel falha se debug player não está em tile de duelo."""
        p1 = _make_player('Ash', host=True)
        p2 = _make_player('Misty')
        state = build_initial_state('DUEL02')
        state['players'] = [p1, p2]
        state = engine.initialize_game(state)
        state, _ = engine.set_debug_test_player_enabled(state, True)

        new_state, error = engine.debug_start_duel_with_player(state, p1['id'])
        self.assertIsNone(new_state)
        self.assertIsInstance(error, str)

    def test_real_defender_enters_pokemon_choice_phase(self):
        """O jogador real desafiado escolhe primeiro pelo fluxo normal da batalha."""
        state, p1_id, _ = self._state_with_duel_tile()
        if state is None:
            self.skipTest('Sem tile de duelo')

        state, _ = engine.debug_start_duel_with_player(state, p1_id)
        new_state, result = engine.register_battle_choice(state, p1_id, 0)

        self.assertIsNotNone(new_state, f'Erro: {result}')
        self.assertIsNone(result)
        battle = new_state['turn']['battle']
        self.assertIsNotNone(battle['defender_choice'])
        self.assertIsNone(battle['challenger_choice'])
        self.assertEqual(battle['sub_phase'], 'choosing')
        self.assertEqual(battle['choice_stage'], 'challenger')

    def test_debug_challenger_choice_advances_duel_normally(self):
        """Depois da escolha do defensor, o debug player escolhe e a batalha avança."""
        state, p1_id, _ = self._state_with_duel_tile()
        if state is None:
            self.skipTest('Sem tile de duelo')

        state, _ = engine.debug_start_duel_with_player(state, p1_id)
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        new_state, result = engine.debug_duel_choose_pokemon(state, 0)

        self.assertIsNotNone(new_state, f'Erro: {result}')
        battle = new_state['turn']['battle']
        self.assertEqual(result, {'success': True})
        self.assertIsNotNone(battle['defender_choice'])
        self.assertIsNotNone(battle['challenger_choice'])
        self.assertEqual(battle['sub_phase'], 'rolling')
        self.assertEqual(battle['choice_stage'], 'complete')

    def test_duel_resolves_and_restores_real_state(self):
        """O duelo compartilhado volta o jogo principal ao estado anterior ao debug."""
        state, p1_id, p2_id = self._state_with_duel_tile()
        if state is None:
            self.skipTest('Sem tile de duelo')

        state['decks']['victory_deck'] = []
        state['decks']['victory_discard'] = []
        real_players_before = copy.deepcopy(state['players'])
        turn_before = copy.deepcopy(state['turn'])

        state, _ = engine.debug_start_duel_with_player(state, p1_id)
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        state, _ = engine.debug_duel_choose_pokemon(state, 0)

        with patch('game.engine.state.roll_battle_dice', side_effect=[5, 2]):
            state, _ = engine.register_battle_roll(state, p1_id)
            new_state, result = engine.debug_duel_roll_battle(state)

        self.assertIsNotNone(new_state, f'Erro: {result}')
        self.assertIsNotNone(result.get('winner_id'))
        self.assertEqual(new_state['turn'], turn_before)
        self.assertEqual(new_state['players'], real_players_before)
        self.assertIsNone(new_state['debug_visual'].get('shared_battle_resume_state'))
        self.assertIsNone(new_state['turn'].get('battle'))
        self.assertEqual(new_state['turn']['current_player_id'], p2_id)

    def test_skip_shared_duel_restores_real_turn_and_keeps_test_player(self):
        """Cancelar o duelo compartilhado limpa o battle state principal sem afetar jogadores reais."""
        state, p1_id, _ = self._state_with_duel_tile()
        if state is None:
            self.skipTest('Sem tile de duelo')

        turn_before = copy.deepcopy(state['turn'])
        real_players_before = copy.deepcopy(state['players'])
        state, _ = engine.debug_start_duel_with_player(state, p1_id)

        new_state, _ = engine.debug_skip_test_player_pending(state)

        self.assertEqual(new_state['turn'], turn_before)
        self.assertEqual(new_state['players'], real_players_before)
        self.assertIsNone(new_state['turn'].get('battle'))
        session_after_skip = new_state['debug_visual']['session_state']
        player_ids = [p['id'] for p in session_after_skip['players']]
        self.assertEqual(player_ids, ['__debug_test_player__'])


class TestPokemonAbilityRuntime(TestCase):

    def _ready_to_roll(self) -> tuple[dict, str, str]:
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        p1_starter = next((starter for starter in starters if starter['name'] == 'Bulbasaur'), starters[0])
        remaining = [starter for starter in starters if starter['id'] != p1_starter['id']]
        p2_starter = remaining[0]
        state = engine.select_starter(state, p1_id, p1_starter['id'])
        state = engine.select_starter(state, p2_id, p2_starter['id'])
        return normalize_state('TEST01', state), p1_id, p2_id

    def _give_runtime_pokemon(self, state: dict, player_id: str, pokemon_name: str, *, sequence: int = 1) -> dict:
        player = next(player for player in state['players'] if player['id'] == player_id)
        pokemon = copy.deepcopy(load_playable_pokemon_by_name(pokemon_name))
        pokemon['acquisition_origin'] = 'captured'
        pokemon['capture_sequence'] = sequence
        pokemon['capture_context'] = 'grass'
        player['pokemon'].append(pokemon)
        sync_player_inventory(player)
        return normalize_state('TEST01', state)

    def test_normalize_state_populates_ability_runtime_and_inventory_snapshots(self):
        state, p1_id, _ = self._ready_to_roll()

        player = next(player for player in state['players'] if player['id'] == p1_id)
        starter = player['starter_pokemon']
        starter_inventory = next(pokemon for pokemon in player['pokemon_inventory'] if pokemon['slot_key'] == 'starter')

        self.assertIn('ability_runtime', starter)
        self.assertIn('primary', starter['ability_runtime']['abilities'])
        self.assertTrue(starter['abilities'])
        self.assertEqual(
            starter_inventory['abilities'][0]['description'],
            starter['ability_description'],
        )

    def test_movement_roll_can_open_optional_ability_decision(self):
        state, p1_id, _ = self._ready_to_roll()

        with patch('game.engine.state.roll_movement_dice', return_value=4):
            rolled_state, roll_entry = engine.perform_movement_roll(state, p1_id)

        pending = rolled_state['turn']['pending_action']
        self.assertEqual(roll_entry['final_result'], 4)
        self.assertEqual(pending['type'], 'ability_decision')
        self.assertEqual(pending['decision_kind'], 'move_roll')
        self.assertTrue(any(option['id'] == 'skip' for option in pending['options']))
        self.assertTrue(any(option.get('pokemon_name') == 'Bulbasaur' for option in pending['options']))

    def test_optional_move_ability_consumes_charge_only_on_resolution(self):
        state, p1_id, _ = self._ready_to_roll()
        state = self._give_runtime_pokemon(state, p1_id, 'Fearow')

        with patch('game.engine.state.roll_movement_dice', return_value=6):
            rolled_state, _ = engine.perform_movement_roll(state, p1_id)

        player_before = next(player for player in rolled_state['players'] if player['id'] == p1_id)
        self.assertEqual(player_before['pokemon'][0]['ability_charges'], 3)

        pending = rolled_state['turn']['pending_action']
        option_id = next(
            option['id']
            for option in pending['options']
            if option.get('pokemon_name') == 'Fearow'
        )

        resolved_state, result = engine.resolve_pending_action(rolled_state, p1_id, option_id)
        player_after = next(player for player in resolved_state['players'] if player['id'] == p1_id)

        self.assertTrue(result['used'])
        self.assertEqual(result['final_roll'], 3)
        self.assertEqual(player_after['pokemon'][0]['ability_charges'], 2)
        self.assertIsNone(resolved_state['turn'].get('pending_action'))
        self.assertEqual(player_after['position'], 3)

    def test_manual_fixed_move_ability_uses_charge_and_moves_without_roll(self):
        state, p1_id, _ = self._ready_to_roll()
        state = self._give_runtime_pokemon(state, p1_id, 'Doduo')

        new_state, result = engine.use_pokemon_ability(
            state,
            p1_id,
            slot_key='pokemon:0',
            ability_id='primary',
            action_id='fixed_move',
        )
        player = next(player for player in new_state['players'] if player['id'] == p1_id)

        self.assertEqual(result['effect_kind'], 'fixed_move')
        self.assertEqual(result['steps'], 4)
        self.assertEqual(player['pokemon'][0]['ability_charges'], 0)
        self.assertEqual(player['position'], 4)

    def test_capture_free_ability_marks_runtime_without_spending_pokeball(self):
        state, p1_id, _ = self._ready_to_roll()
        state = self._give_runtime_pokemon(state, p1_id, 'Butterfree')
        state = _land_on_tile(state, p1_id, 85)

        new_state, result = engine.use_pokemon_ability(
            state,
            p1_id,
            slot_key='pokemon:0',
            ability_id='primary',
            action_id='capture_free_next',
        )
        player = next(player for player in new_state['players'] if player['id'] == p1_id)

        self.assertTrue(result['capture_free'])
        self.assertTrue(new_state['turn']['compound_eyes_active'])
        self.assertTrue(player['pokemon'][0]['ability_runtime']['abilities']['primary']['used_this_turn'])

    def test_normalize_state_is_idempotent_for_ability_runtime(self):
        state, p1_id, _ = self._ready_to_roll()
        state = self._give_runtime_pokemon(state, p1_id, 'Doduo')
        used_state, _ = engine.use_pokemon_ability(
            state,
            p1_id,
            slot_key='pokemon:0',
            ability_id='primary',
            action_id='fixed_move',
        )

        normalized_once = normalize_state('TEST01', used_state)
        normalized_twice = normalize_state('TEST01', normalized_once)
        pokemon_once = next(player for player in normalized_once['players'] if player['id'] == p1_id)['pokemon'][0]
        pokemon_twice = next(player for player in normalized_twice['players'] if player['id'] == p1_id)['pokemon'][0]

        self.assertEqual(
            pokemon_once['ability_runtime']['abilities']['primary']['charges_remaining'],
            pokemon_twice['ability_runtime']['abilities']['primary']['charges_remaining'],
        )
        self.assertEqual(
            pokemon_once['ability_runtime']['abilities']['primary']['used_this_turn'],
            pokemon_twice['ability_runtime']['abilities']['primary']['used_this_turn'],
        )
        self.assertEqual(len(pokemon_twice['abilities']), 1)


class TestHostToolsRuntime(TestCase):

    def _host_game(self):
        state, p1_id, p2_id = _init_two_player_game()
        state['turn']['current_player_id'] = p1_id
        state['turn']['phase'] = 'roll'
        return state, p1_id, p2_id

    def _enable_host_tools(self, state):
        enabled_state, result = engine.set_host_tools_enabled(state, True)
        self.assertTrue(result['enabled'])
        self.assertTrue(enabled_state['debug_visual']['host_tools']['enabled'])
        return enabled_state

    def _find_tile(self, state, tile_type):
        return next(tile for tile in state['board']['tiles'] if tile.get('type') == tile_type)

    def test_host_tools_toggle_persists_in_state(self):
        state, _, _ = self._host_game()

        enabled_state, enabled_result = engine.set_host_tools_enabled(state, True)
        disabled_state, disabled_result = engine.set_host_tools_enabled(enabled_state, False)

        self.assertTrue(enabled_result['enabled'])
        self.assertFalse(disabled_result['enabled'])
        self.assertTrue(enabled_state['debug_visual']['host_tools']['enabled'])
        self.assertFalse(disabled_state['debug_visual']['host_tools']['enabled'])

    def test_debug_move_host_positive_sets_pending_tile_without_triggering(self):
        state, p1_id, _ = self._host_game()
        duel_tile = self._find_tile(state, 'duel')
        player = next(player for player in state['players'] if player['id'] == p1_id)
        player['position'] = duel_tile['id'] - 2
        state = self._enable_host_tools(state)

        moved_state, result = engine.debug_move_host(state, p1_id, 2)

        self.assertEqual(result['position'], duel_tile['id'])
        self.assertEqual(moved_state['turn']['current_tile']['id'], duel_tile['id'])
        self.assertIsNone(moved_state['turn'].get('capture_context'))
        self.assertEqual(moved_state['turn']['phase'], 'roll')
        self.assertEqual(
            moved_state['debug_visual']['host_tools']['pending_tile_trigger'],
            {'player_id': p1_id, 'position': duel_tile['id'], 'steps': 2},
        )

    def test_debug_move_host_negative_moves_backwards(self):
        state, p1_id, _ = self._host_game()
        player = next(player for player in state['players'] if player['id'] == p1_id)
        player['position'] = 5
        state = self._enable_host_tools(state)

        moved_state, result = engine.debug_move_host(state, p1_id, -3)

        self.assertEqual(result['position'], 2)
        self.assertEqual(moved_state['players'][0]['position'], 2)
        self.assertEqual(moved_state['debug_visual']['host_tools']['pending_tile_trigger']['steps'], -3)

    def test_trigger_host_current_tile_resolves_pending_tile_once(self):
        state, p1_id, _ = self._host_game()
        duel_tile = self._find_tile(state, 'duel')
        player = next(player for player in state['players'] if player['id'] == p1_id)
        player['position'] = duel_tile['id'] - 1
        state = self._enable_host_tools(state)
        state, _ = engine.debug_move_host(state, p1_id, 1)

        triggered_state, result = engine.debug_trigger_host_current_tile(state, p1_id)

        self.assertTrue(result['success'])
        self.assertEqual(triggered_state['turn']['capture_context'], 'duel')
        self.assertIsNone(triggered_state['debug_visual']['host_tools']['pending_tile_trigger'])

        duplicate_state, duplicate_error = engine.debug_trigger_host_current_tile(triggered_state, p1_id)
        self.assertIsNone(duplicate_state)
        self.assertEqual(duplicate_error, 'Não há tile pendente para Host Tools neste turno')

    def test_normal_process_move_clears_pending_host_tile_and_still_triggers_normally(self):
        state, p1_id, _ = self._host_game()
        duel_tile = self._find_tile(state, 'duel')
        player = next(player for player in state['players'] if player['id'] == p1_id)
        player['position'] = duel_tile['id'] - 1
        state = self._enable_host_tools(state)
        state['debug_visual']['host_tools']['pending_tile_trigger'] = {
            'player_id': p1_id,
            'position': duel_tile['id'] - 1,
            'steps': -1,
        }

        moved_state = engine.process_move(state, p1_id, 1)

        self.assertEqual(moved_state['turn']['capture_context'], 'duel')
        self.assertIsNone(moved_state['debug_visual']['host_tools']['pending_tile_trigger'])

    def test_debug_add_pokemon_and_item_to_host_update_serialized_player(self):
        state, p1_id, _ = self._host_game()
        state = self._enable_host_tools(state)

        state, pokemon_result = engine.debug_add_pokemon_to_host(state, p1_id, 'Pikachu')
        state, item_result = engine.debug_add_item_to_host(state, p1_id, 'bill', 2)
        player = next(player for player in state['players'] if player['id'] == p1_id)

        self.assertEqual(pokemon_result['pokemon']['name'], 'Pikachu')
        self.assertEqual(player['pokemon'][0]['name'], 'Pikachu')
        self.assertEqual(item_result['item_key'], 'bill')
        self.assertTrue(any(item['key'] == 'bill' and item['quantity'] == 2 for item in player['items']))

    def test_normalize_state_keeps_host_tools_pending_tile_idempotent(self):
        state, p1_id, _ = self._host_game()
        state = self._enable_host_tools(state)
        state['players'][0]['position'] = 4
        state, _ = engine.debug_move_host(state, p1_id, 2)

        normalized_once = normalize_state('TEST01', state)
        normalized_twice = normalize_state('TEST01', normalized_once)

        self.assertEqual(
            normalized_once['debug_visual']['host_tools']['pending_tile_trigger'],
            normalized_twice['debug_visual']['host_tools']['pending_tile_trigger'],
        )


# ── Testes da Pokémon League ────────────────────────────────────────────────

class TestPokemonLeague(TestCase):
    """Testa a batalha interativa da Pokémon League (Elite Four + Campeão)."""

    def _ready_state(self):
        state, p1_id, p2_id = _init_two_player_game()
        starters = state['turn']['available_starters']
        state = engine.select_starter(state, p1_id, starters[0]['id'])
        state = engine.select_starter(state, p2_id, starters[1]['id'])
        state['decks']['event_deck'] = []
        state['decks']['event_discard'] = []
        state['decks']['victory_deck'] = []
        return state, p1_id, p2_id

    def _prime_turn(self, state, player_id):
        state['turn']['current_player_id'] = player_id
        state['turn']['phase'] = 'roll'
        state['turn']['battle'] = None
        state['turn']['pending_action'] = None
        return state

    def _set_team(self, state, player_id, pokemon_list):
        player = next(p for p in state['players'] if p['id'] == player_id)
        player['starter_pokemon'] = None
        player['pokemon'] = copy.deepcopy(pokemon_list)
        return player

    def test_league_tile_starts_interactive_battle(self):
        """Chegar na Liga inicia batalha interativa mode='league'."""
        state, p1_id, p2_id = self._ready_state()
        self._set_team(state, p1_id, [_make_pokemon(name='Dragonite', bp=12)])
        self._prime_turn(state, p1_id)
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        p1['position'] = 168

        state = engine.process_move(state, p1_id, 1)
        p1 = next(p for p in state['players'] if p['id'] == p1_id)

        battle = state['turn'].get('battle')
        self.assertIsNotNone(battle)
        self.assertEqual(battle['mode'], 'league')
        self.assertEqual(battle['defender_name'], 'Lorelei')
        self.assertEqual(state['turn']['phase'], 'battle')
        self.assertEqual(p1['has_reached_league'], True)

    def test_league_battle_choice_and_roll_work(self):
        """Escolha de Pokémon e rolagem de dado funcionam na Liga."""
        state, p1_id, p2_id = self._ready_state()
        self._set_team(state, p1_id, [_make_pokemon(name='Dragonite', bp=12)])
        self._prime_turn(state, p1_id)
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        p1['position'] = 168

        state = engine.process_move(state, p1_id, 1)
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        self.assertEqual(state['turn']['battle']['sub_phase'], 'rolling')

        with patch('game.engine.state.roll_battle_dice', side_effect=[6, 1]):
            state, result = engine.register_battle_roll(state, p1_id)
        self.assertIsNotNone(result)

    def test_league_defeat_member_advances_to_next(self):
        """Derrotar todos os Pokémon de Lorelei entra em intermission, confirmando avança para Bruno."""
        state, p1_id, p2_id = self._ready_state()
        self._set_team(state, p1_id, [_make_pokemon(name='Dragonite', bp=15)])
        self._prime_turn(state, p1_id)
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        p1['position'] = 168

        state = engine.process_move(state, p1_id, 1)
        # Derrota todos os 5 Pokémon de Lorelei
        for _ in range(5):
            state, _ = engine.register_battle_choice(state, p1_id, 0)
            with patch('game.engine.state.roll_battle_dice', side_effect=[6, 1]):
                state, result = engine.register_battle_roll(state, p1_id)

        # Após derrotar Lorelei, deve entrar em intermission
        self.assertEqual(state['turn'].get('phase'), 'league_intermission')
        self.assertIsNone(state['turn'].get('battle'))
        pending = state['turn'].get('pending_action') or {}
        self.assertEqual(pending.get('type'), 'league_intermission')
        self.assertEqual(pending.get('next_member_name'), 'Bruno')

        # Confirma intermission → inicia batalha com Bruno
        state, _ = engine.confirm_league_intermission(state, p1_id)
        battle = state['turn'].get('battle')
        self.assertIsNotNone(battle)
        self.assertEqual(battle['defender_name'], 'Bruno')
        self.assertEqual(battle['league_member_index'], 1)
        # Pontos foram acumulados
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertGreater(p1['master_points'], 0)

    def test_league_loss_sets_failed_flag(self):
        """Perder para um membro da Liga seta league_failed."""
        state, p1_id, p2_id = self._ready_state()
        self._set_team(state, p1_id, [_make_pokemon(name='Magikarp', bp=1)])
        self._prime_turn(state, p1_id)
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        p1['position'] = 168
        state['decks']['victory_deck'] = []

        state = engine.process_move(state, p1_id, 1)
        state, _ = engine.register_battle_choice(state, p1_id, 0)
        with patch('game.engine.state.roll_battle_dice', side_effect=[1, 6]):
            state, result = engine.register_battle_roll(state, p1_id)

        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertTrue(p1.get('league_failed'))
        self.assertIsNone(state['turn'].get('battle'))

    def test_league_failed_blocks_reentry(self):
        """Player com league_failed não pode reentrar na Liga."""
        state, p1_id, p2_id = self._ready_state()
        self._set_team(state, p1_id, [_make_pokemon(name='Magikarp', bp=1)])
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        p1['league_failed'] = True
        p1['has_reached_league'] = True

        state['turn']['current_player_id'] = p1_id
        state['turn']['phase'] = 'roll'
        p1['position'] = 168
        state['decks']['victory_deck'] = []

        state = engine.process_move(state, p1_id, 1)
        self.assertIsNone(state['turn'].get('battle'))

    def test_starting_items_include_two_full_restores(self):
        """Cada jogador começa com 2 Full Restores."""
        state, p1_id, _ = self._ready_state()
        p1 = next(p for p in state['players'] if p['id'] == p1_id)
        self.assertEqual(p1['full_restores'], 2)

    def test_master_ball_has_capture_category(self):
        """Master Ball tem categoria 'capture', não aparece como item genérico."""
        from game.engine.inventory import ITEM_DEFS
        self.assertEqual(ITEM_DEFS['master_ball']['category'], 'capture')
        self.assertEqual(ITEM_DEFS['master_ball']['effect'], 'choose_capture_dice')

    def test_calculate_final_scores_includes_bonus_points(self):
        """calculate_final_scores inclui bonus_points (eventos/duelos) na pontuação."""
        player = {
            'id': 'p1', 'name': 'P1',
            'pokemon': [_make_pokemon(bp=3)],
            'starter_pokemon': None,
            'badges': ['Boulder Badge'],  # +20
            'bonus_points': 15,           # eventos
            'league_bonus': 60,           # liga
        }
        results = calculate_final_scores([player])
        self.assertEqual(len(results), 1)
        r = results[0]
        # total = pokemon_mp + 20 (badge) + 15 (bonus) + 60 (league)
        pokemon_mp = _make_pokemon(bp=3).get('master_points', 0)
        self.assertEqual(r['total'], pokemon_mp + 20 + 15 + 60)
        self.assertEqual(r['bonus_points'], 15)
        self.assertEqual(r['league_bonus'], 60)

    def test_gym_badge_gives_20_points_in_final_score(self):
        """Cada badge vale 20 pontos na pontuação final."""
        player = {
            'id': 'p1', 'name': 'P1',
            'pokemon': [],
            'starter_pokemon': None,
            'badges': ['Cascade Badge', 'Thunder Badge'],
            'bonus_points': 0,
            'league_bonus': 0,
        }
        results = calculate_final_scores([player])
        self.assertEqual(results[0]['badge_mp'], 40)
        self.assertEqual(results[0]['total'], 40)
