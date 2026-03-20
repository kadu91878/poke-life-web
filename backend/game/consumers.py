import asyncio
import json
import re
import uuid
from typing import ClassVar

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings

from .engine import mechanics
from .engine import state as game_state
from .engine import cpu as cpu_engine
from .engine.inventory import get_starting_resource_defaults
from .models import GameRoom
from .socket_contract import SOCKET_HANDLER_NAMES
from .state_schema import mark_saved, normalize_state


def _format_debug_fields(**fields) -> str:
    parts = []
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f'{key}={value!r}')
    return ' '.join(parts)


def _cpu_state_snapshot(state: dict | None) -> str:
    turn = (state or {}).get('turn') or {}
    battle = turn.get('battle') or {}
    return _format_debug_fields(
        phase=turn.get('phase'),
        current_player=turn.get('current_player_id'),
        pending_action=(turn.get('pending_action') or {}).get('type'),
        pending_item=(turn.get('pending_item_choice') or {}).get('player_id'),
        battle_mode=battle.get('mode'),
        battle_phase=battle.get('sub_phase'),
    )


def _cpu_debug(level: str, message: str, *, state: dict | None = None, **fields) -> None:
    parts = [f'[CPU][{level}]', message]
    field_text = _format_debug_fields(**fields)
    if field_text:
        parts.append(field_text)
    state_text = _cpu_state_snapshot(state)
    if state_text:
        parts.append(state_text)
    print(' '.join(parts))


class GameConsumer(AsyncWebsocketConsumer):
    _room_locks: ClassVar[dict[str, asyncio.Lock]] = {}

    def _room_lock(self) -> asyncio.Lock:
        if self.room_code not in GameConsumer._room_locks:
            GameConsumer._room_locks[self.room_code] = asyncio.Lock()
        return GameConsumer._room_locks[self.room_code]

    async def connect(self):
        self.room_code = self.scope['url_route']['kwargs']['room_code']
        self.room_group_name = f'game_{self.room_code}'
        self.player_id = None

        if not await self.room_exists():
            await self.close(code=4004)
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

        state = await self.get_game_state()
        await self.send_json({'type': 'game_state', 'state': state})

    async def disconnect(self, code):
        if self.player_id:
            await self.mark_player_disconnected()
            await self.channel_layer.group_send(
                self.room_group_name,
                {'type': 'broadcast_event', 'event': {'type': 'player_disconnected', 'player_id': self.player_id}},
            )
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return

        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_error('JSON inválido')
            return

        action = data.get('action')
        handler_name = SOCKET_HANDLER_NAMES.get(action)
        handler = getattr(self, handler_name, None) if handler_name else None
        if not handler:
            await self.send_error(f'Ação desconhecida: {action}')
            return

        try:
            async with self._room_lock():
                await handler(data)
        except Exception as exc:
            await self.send_error(str(exc))

    async def handle_join_game(self, data):
        player_name = (data.get('player_name') or 'Trainer').strip()[:20]
        starting_defaults = get_starting_resource_defaults()
        if not player_name:
            player_name = 'Trainer'
        # player_id enviado pelo frontend (recuperado do sessionStorage) — usado para
        # reconexão confiável sem depender do nome.
        provided_id = (data.get('player_id') or '').strip()

        state = await self.get_game_state()

        print(f'[JOIN] room={self.room_code} name={player_name!r} provided_id={provided_id!r} status={state.get("status")}')

        if state.get('status') == 'finished':
            await self.send_error('Esta partida já foi finalizada')
            return

        if state.get('status') == 'playing':
            existing = self._find_reconnect_player(state, provided_id, player_name)
            if existing:
                self.player_id = existing['id']
                existing['is_connected'] = True
                print(f'[JOIN] reconectando player={self.player_id!r} name={existing["name"]!r}')
                saved_state = await self.save_game_state(state)
                # Notifica todos sobre a reconexão para manter o lobby/jogo sincronizado
                await self.broadcast_state(saved_state, {'type': 'player_reconnected', 'player_id': self.player_id, 'player_name': existing['name']})
                await self.send_json({'type': 'joined', 'player_id': self.player_id, 'state': saved_state})
                return
            await self.send_error('A partida já começou')
            return

        # ── Fase de espera: cria novo jogador ────────────────────────────────
        players = state.get('players', [])
        active_players = [p for p in players if p.get('is_active', True)]
        if len(active_players) >= 5:
            await self.send_error('Sala cheia (máximo 5 jogadores)')
            return

        self.player_id = str(uuid.uuid4())
        colors = ['red', 'blue', 'green', 'yellow', 'purple']
        new_player = {
            'id': self.player_id,
            'name': player_name,
            'color': colors[len(players) % len(colors)],
            'is_host': len(players) == 0,
            'is_active': True,
            'is_connected': True,
            'position': 0,
            'pokeballs': starting_defaults['pokeballs'],
            'full_restores': starting_defaults['full_restores'],
            'starter_slot_applied': False,
            'starter_pokemon': None,
            'pokemon': [],
            'capture_sequence_counter': 0,
            'last_pokemon_center': None,
            'deferred_pokecenter_heal': None,
            'items': starting_defaults['items'],
            'special_tile_flags': {
                'celadon_dept_store_bonus_claimed': False,
            },
            'badges': [],
            'master_points': 0,
            'gyms_attempted': [],
            'gyms_defeated': [],
            'has_reached_league': False,
        }
        players.append(new_player)
        state['players'] = players
        state.setdefault('status', 'waiting')

        print(f'[JOIN] novo jogador player_id={self.player_id!r} name={player_name!r}')
        saved_state = await self.save_game_state(state)
        await self.broadcast_state(saved_state, {'type': 'player_joined', 'player_name': player_name})
        await self.send_json({'type': 'joined', 'player_id': self.player_id, 'state': saved_state})

    async def handle_start_game(self, data):
        state = await self.get_game_state()
        if not self._is_host(state):
            await self.send_error('Apenas o host pode iniciar a partida')
            return
        if state.get('status') != 'waiting':
            await self.send_error('A partida já foi iniciada')
            return

        active_players = [p for p in state.get('players', []) if p.get('is_active', True)]
        if len(active_players) < 2:
            await self.send_error('São necessários pelo menos 2 jogadores ativos')
            return

        new_state = game_state.initialize_game(state)
        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'game_started'})

    async def handle_select_starter(self, data):
        starter_id = data.get('starter_id')
        state = await self.get_game_state()
        current = state.get('turn', {}).get('current_player_id')
        print(f'[SELECT_STARTER] socket_player={self.player_id!r} current_player={current!r} starter_id={starter_id!r}')
        if state.get('turn', {}).get('phase') != 'select_starter':
            await self.send_error('Não é fase de escolha de starter')
            return
        if not self.player_id:
            await self.send_error('Identidade não estabelecida — envie join_game primeiro')
            return
        if not self._is_current_player(state):
            await self.send_error('Aguarde sua vez de escolher o Pokémon inicial')
            return

        new_state = game_state.select_starter(state, self.player_id, starter_id)
        if new_state is None:
            await self.send_error('Starter inválido ou já escolhido')
            return

        next_player = new_state.get('turn', {}).get('current_player_id')
        print(f'[SELECT_STARTER] selecionado. próximo player={next_player!r} fase={new_state.get("turn", {}).get("phase")!r}')
        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'starter_selected', 'player_id': self.player_id, 'starter_id': starter_id})

    async def handle_roll_dice(self, data):
        state = await self.get_game_state()
        if not self._is_current_player(state):
            await self.send_error('Não é seu turno')
            return
        if state.get('turn', {}).get('phase') != 'roll':
            await self.send_error('Não é fase de rolagem')
            return

        rolled_state, roll_entry = game_state.perform_movement_roll(state, self.player_id)
        if (rolled_state.get('turn', {}).get('pending_action') or {}).get('type') == 'ability_decision':
            new_state = rolled_state
        else:
            new_state = game_state.process_move(rolled_state, self.player_id, int(roll_entry['final_result']))
        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {
            'type': 'dice_rolled',
            'roll_type': 'movement',
            'player_id': self.player_id,
            'result': roll_entry['final_result'],
            'raw_result': roll_entry['raw_result'],
            'final_result': roll_entry['final_result'],
            'modifier': roll_entry.get('modifier'),
            'modifier_reason': roll_entry.get('modifier_reason'),
        })

    async def handle_move_player(self, data):
        state = await self.get_game_state()
        if not self._is_current_player(state):
            await self.send_error('Não é seu turno')
            return

        dice_result = int(data.get('dice_result', 0))
        if dice_result < 1 or dice_result > 6:
            await self.send_error('dice_result deve estar entre 1 e 6')
            return

        new_state = game_state.process_move(state, self.player_id, dice_result)
        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'player_moved', 'player_id': self.player_id, 'steps': dice_result})

    async def handle_resolve_tile(self, data):
        state = await self.get_game_state()
        if not self._is_current_player(state):
            await self.send_error('Não é seu turno')
            return

        new_state = state
        if state.get('turn', {}).get('phase') == 'event':
            use_run_away = bool(data.get('use_run_away', False))
            resolved, error = game_state.resolve_event(state, self.player_id, use_run_away=use_run_away)
            if resolved is None:
                await self.send_error(error)
                return
            new_state = resolved

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'tile_resolved', 'player_id': self.player_id})

    async def handle_capture_pokemon(self, data):
        await self.handle_roll_capture_dice(data)

    async def handle_roll_capture_dice(self, data):
        state = await self.get_game_state()
        if not self._is_current_player(state):
            await self.send_error('Não é seu turno')
            return
        if state.get('turn', {}).get('phase') != 'action':
            await self.send_error('Não é fase de ação')
            return

        use_full_restore = bool(data.get('use_full_restore', False))
        use_master_ball = bool(data.get('use_master_ball', False))
        chosen_capture_roll = data.get('chosen_capture_roll')
        new_state, result = game_state.roll_capture_attempt(
            state,
            self.player_id,
            use_full_restore=use_full_restore,
            use_master_ball=use_master_ball,
            chosen_capture_roll=chosen_capture_roll,
        )
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        event_type = 'capture_roll_resolved'
        if isinstance(result, dict) and result.get('pokemon'):
            event_type = 'pokemon_captured'
        await self.broadcast_state(saved_state, {'type': event_type, 'player_id': self.player_id, 'result': result})

    async def handle_skip_action(self, data):
        """Pula ação atual (não capturar/não duelar). Avança safari se necessário."""
        state = await self.get_game_state()
        if not self._is_current_player(state):
            await self.send_error('Não é seu turno')
            return

        new_state = game_state.skip_action(state, self.player_id)
        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'action_skipped', 'player_id': self.player_id})

    async def handle_discard_item(self, data):
        state = await self.get_game_state()
        item_key = (data.get('item_key') or '').strip()
        new_state, result = game_state.discard_item(state, self.player_id, item_key)
        if new_state is None:
            await self.send_error(result)
            return
        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'item_discarded', 'player_id': self.player_id, 'item_key': item_key})

    async def handle_release_pokemon(self, data):
        state = await self.get_game_state()
        if not self._is_current_player(state):
            await self.send_error('Não é seu turno')
            return
        pokemon_index = data.get('pokemon_index')
        pokemon_slot_key = (data.get('pokemon_slot_key') or '').strip() or None
        new_state, result = game_state.release_pokemon_for_capture(
            state,
            self.player_id,
            pokemon_index=pokemon_index,
            pokemon_slot_key=pokemon_slot_key,
        )
        if new_state is None:
            await self.send_error(result)
            return
        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'pokemon_released', 'player_id': self.player_id, 'result': result})

    async def handle_pass_turn(self, data):
        state = await self.get_game_state()
        if not self._is_current_player(state):
            await self.send_error('Não é seu turno')
            return

        phase = state.get('turn', {}).get('phase', '')
        turn = state.get('turn', {})
        if game_state.turn_has_blocking_interaction(turn):
            await self.send_error('Não é possível passar o turno durante uma interação pendente')
            return

        new_state = game_state.end_turn(state)
        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'turn_passed', 'player_id': self.player_id})

    async def handle_challenge_player(self, data):
        target_id = data.get('target_player_id')
        state = await self.get_game_state()

        if not self._is_current_player(state):
            await self.send_error('Não é seu turno')
            return
        if state.get('turn', {}).get('phase') != 'action':
            await self.send_error('Não é fase de duelo')
            return

        new_state = game_state.start_duel(state, self.player_id, target_id)
        if new_state is None:
            await self.send_error('Não é possível desafiar este jogador')
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'duel_started', 'challenger_id': self.player_id, 'defender_id': target_id})

    async def handle_battle_choice(self, data):
        pokemon_slot_key = (data.get('pokemon_slot_key') or '').strip() or None
        try:
            raw_index = data.get('pokemon_index')
            pokemon_index = int(raw_index) if raw_index is not None else None
        except (TypeError, ValueError):
            pokemon_index = 0
        state = await self.get_game_state()

        if state.get('turn', {}).get('phase') != 'battle':
            await self.send_error('Não é fase de batalha')
            return

        battle = state.get('turn', {}).get('battle', {})
        if battle.get('sub_phase') != 'choosing':
            await self.send_error('Fase de escolha de Pokémon já encerrada — aguarde a fase de rolagem')
            return

        is_participant = battle.get('challenger_id') == self.player_id or battle.get('defender_id') == self.player_id
        if not is_participant:
            await self.send_error('Você não está nesta batalha')
            return

        new_state, result = game_state.register_battle_choice(
            state,
            self.player_id,
            pokemon_index,
            pokemon_slot_key=pokemon_slot_key,
        )
        if result and result.get('error'):
            await self.send_error(result['error'])
            return
        saved_state = await self.save_game_state(new_state)

        event = {'type': 'battle_choice_registered', 'player_id': self.player_id}
        if result and result.get('ignored'):
            event = {'type': 'battle_choice_registered', 'player_id': self.player_id, 'ignored': True}
        await self.broadcast_state(saved_state, event)

    async def handle_roll_battle_dice(self, data):
        state = await self.get_game_state()

        if state.get('turn', {}).get('phase') != 'battle':
            await self.send_error('Não é fase de batalha')
            return

        battle = state.get('turn', {}).get('battle', {})
        if battle.get('sub_phase') != 'rolling':
            await self.send_error('Não é fase de rolagem de batalha — ambos precisam escolher Pokémon primeiro')
            return

        is_participant = battle.get('challenger_id') == self.player_id or battle.get('defender_id') == self.player_id
        if not is_participant:
            await self.send_error('Você não está nesta batalha')
            return

        new_state, result = game_state.register_battle_roll(state, self.player_id)
        if result and result.get('error'):
            await self.send_error(result['error'])
            return
        saved_state = await self.save_game_state(new_state)

        event = {'type': 'battle_roll_registered', 'player_id': self.player_id}
        if result and not result.get('reroll_required') and (
            result.get('winner_id') is not None
            or result.get('mode') in ('trainer', 'gym')
            or result.get('battle_finished')
        ):
            event = {'type': 'battle_resolved', 'result': result}
        elif result and result.get('ignored'):
            event = {'type': 'battle_roll_registered', 'player_id': self.player_id, 'ignored': True}
        await self.broadcast_state(saved_state, event)

    async def handle_use_ability(self, data):
        state = await self.get_game_state()
        ability_action = (data.get('ability_action') or '').strip().lower()
        target_id = data.get('target_id')
        target_position = data.get('target_position')
        slot_key = data.get('slot_key')
        ability_id = data.get('ability_id')
        action_id = data.get('action_id')

        if slot_key or ability_id or action_id:
            new_state, result = game_state.use_pokemon_ability(
                state,
                self.player_id,
                slot_key=slot_key,
                ability_id=ability_id,
                action_id=action_id,
            )
        else:
            new_state, result = game_state.use_ability(
                state,
                self.player_id,
                ability_action,
                target_id=target_id,
                target_position=target_position,
            )
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'ability_used', 'player_id': self.player_id, 'result': result})

    async def handle_use_item(self, data):
        state = await self.get_game_state()
        item_key = (data.get('item_key') or '').strip()
        pokemon_index = data.get('pokemon_index')
        target_pokemon_index = data.get('target_pokemon_index')
        pokemon_slot_key = (data.get('pokemon_slot_key') or '').strip() or None

        new_state, result = game_state.use_item(
            state,
            self.player_id,
            item_key,
            pokemon_index=pokemon_index,
            pokemon_slot_key=pokemon_slot_key,
            target_pokemon_index=target_pokemon_index,
        )
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        event = {'type': 'item_used', 'player_id': self.player_id, 'item_key': item_key, 'result': result}
        if isinstance(result, dict) and result.get('winner_id'):
            event = {'type': 'battle_resolved', 'result': result}
        await self.broadcast_state(saved_state, event)

    async def handle_debug_add_item(self, data):
        state = await self.get_game_state()
        debug_error = self._get_debug_access_error(state, require_host_tools=True)
        if debug_error:
            await self.send_error(debug_error)
            return

        item_key = (data.get('item_key') or '').strip()
        quantity = int(data.get('quantity', 1))
        new_state, result = game_state.debug_add_item_to_host(state, self.player_id, item_key, quantity)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {
            'type': 'debug_item_added',
            'player_id': self.player_id,
            'item_key': item_key,
            'quantity': quantity,
            'result': result,
        })

    async def handle_debug_toggle_host_tools(self, data):
        state = await self.get_game_state()
        debug_error = self._get_debug_access_error(state)
        if debug_error:
            await self.send_error(debug_error)
            return

        enabled = bool(data.get('enabled', False))
        new_state, result = game_state.set_host_tools_enabled(state, enabled)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'debug_host_tools_toggled', 'enabled': enabled, 'result': result})

    async def handle_debug_move_host(self, data):
        state = await self.get_game_state()
        debug_error = self._get_debug_access_error(state, require_host_tools=True)
        if debug_error:
            await self.send_error(debug_error)
            return

        try:
            steps = self._parse_non_zero_int(data.get('steps'), 'steps')
        except ValueError as exc:
            await self.send_error(str(exc))
            return

        new_state, result = game_state.debug_move_host(state, self.player_id, steps)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'debug_host_moved', 'steps': steps, 'result': result})

    async def handle_debug_add_pokemon_to_host(self, data):
        state = await self.get_game_state()
        debug_error = self._get_debug_access_error(state, require_host_tools=True)
        if debug_error:
            await self.send_error(debug_error)
            return

        pokemon_name = (data.get('pokemon_name') or '').strip()
        if not pokemon_name:
            await self.send_error('pokemon_name é obrigatório')
            return

        new_state, result = game_state.debug_add_pokemon_to_host(state, self.player_id, pokemon_name)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {
            'type': 'debug_host_pokemon_added',
            'pokemon_name': pokemon_name,
            'result': result,
        })

    async def handle_debug_add_pokemon_to_test_player(self, data):
        state = await self.get_game_state()
        debug_error = self._get_debug_access_error(state)
        if debug_error:
            await self.send_error(debug_error)
            return

        pokemon_name = (data.get('pokemon_name') or '').strip()
        if not pokemon_name:
            await self.send_error('pokemon_name é obrigatório')
            return

        new_state, result = game_state.debug_add_pokemon_to_test_player(state, pokemon_name)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {
            'type': 'debug_test_player_pokemon_added',
            'pokemon_name': pokemon_name,
            'result': result,
        })

    async def handle_debug_trigger_current_tile(self, data):
        state = await self.get_game_state()
        debug_error = self._get_debug_access_error(state, require_host_tools=True)
        if debug_error:
            await self.send_error(debug_error)
            return

        new_state, result = game_state.debug_trigger_host_current_tile(state, self.player_id)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'debug_tile_triggered', 'player_id': self.player_id, 'result': result})

    async def handle_debug_toggle_test_player(self, data):
        state = await self.get_game_state()
        debug_error = self._get_debug_access_error(state)
        if debug_error:
            await self.send_error(debug_error)
            return

        enabled = bool(data.get('enabled', False))
        new_state, result = game_state.set_debug_test_player_enabled(state, enabled)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'debug_test_player_toggled', 'enabled': enabled, 'result': result})

    async def handle_debug_move_test_player(self, data):
        state = await self.get_game_state()
        debug_error = self._get_debug_access_error(state)
        if debug_error:
            await self.send_error(debug_error)
            return

        try:
            steps = self._parse_positive_int(data.get('steps'), 'steps')
        except ValueError as exc:
            await self.send_error(str(exc))
            return

        new_state, result = game_state.move_debug_test_player(state, steps)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'debug_test_player_moved', 'steps': steps, 'result': result})

    async def handle_debug_roll_test_player(self, data):
        state = await self.get_game_state()
        debug_error = self._get_debug_access_error(state)
        if debug_error:
            await self.send_error(debug_error)
            return

        new_state, result = game_state.roll_debug_test_player(state)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'debug_test_player_rolled', 'result': result})

    async def handle_debug_trigger_test_player_tile(self, data):
        state = await self.get_game_state()
        debug_error = self._get_debug_access_error(state)
        if debug_error:
            await self.send_error(debug_error)
            return

        new_state, result = game_state.trigger_debug_test_player_tile(state)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'debug_test_player_tile_triggered', 'result': result})

    async def handle_debug_roll_capture_for_test_player(self, data):
        state = await self.get_game_state()
        debug_error = self._get_debug_access_error(state)
        if debug_error:
            await self.send_error(debug_error)
            return

        use_full_restore = bool(data.get('use_full_restore', False))
        new_state, result = game_state.debug_roll_capture_for_test_player(state, use_full_restore=use_full_restore)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        event_type = 'debug_test_player_pokemon_captured' if isinstance(result, dict) and result.get('pokemon') else 'debug_test_player_capture_rolled'
        await self.broadcast_state(saved_state, {'type': event_type, 'result': result})

    async def handle_debug_resolve_event_for_test_player(self, data):
        state = await self.get_game_state()
        debug_error = self._get_debug_access_error(state)
        if debug_error:
            await self.send_error(debug_error)
            return

        use_run_away = bool(data.get('use_run_away', False))
        new_state, result = game_state.debug_resolve_event_for_test_player(state, use_run_away=use_run_away)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'debug_test_player_event_resolved', 'result': result})

    async def handle_debug_skip_test_player_pending(self, data):
        state = await self.get_game_state()
        debug_error = self._get_debug_access_error(state)
        if debug_error:
            await self.send_error(debug_error)
            return

        new_state, result = game_state.debug_skip_test_player_pending(state)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'debug_test_player_pending_skipped', 'result': result})

    async def handle_debug_start_duel_with_player(self, data):
        state = await self.get_game_state()
        debug_error = self._get_debug_access_error(state)
        if debug_error:
            await self.send_error(debug_error)
            return

        target_player_id = (data.get('target_player_id') or '').strip()
        if not target_player_id:
            await self.send_error('target_player_id é obrigatório')
            return

        new_state, result = game_state.debug_start_duel_with_player(state, target_player_id)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {
            'type': 'duel_started',
            'challenger_id': result.get('challenger_id'),
            'defender_id': result.get('defender_id'),
            'source': 'debug_test_player',
        })

    async def handle_debug_duel_choose_pokemon(self, data):
        state = await self.get_game_state()
        debug_error = self._get_debug_access_error(state)
        if debug_error:
            await self.send_error(debug_error)
            return

        pokemon_slot_key = (data.get('pokemon_slot_key') or '').strip() or None
        try:
            raw_index = data.get('pokemon_index')
            pokemon_index = int(raw_index) if raw_index is not None else None
        except (TypeError, ValueError):
            pokemon_index = 0

        new_state, result = game_state.debug_duel_choose_pokemon(
            state,
            pokemon_index,
            pokemon_slot_key=pokemon_slot_key,
        )
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        event = {'type': 'battle_choice_registered', 'player_id': game_state._DEBUG_TEST_PLAYER_ID}
        if result and result.get('ignored'):
            event = {'type': 'battle_choice_registered', 'player_id': game_state._DEBUG_TEST_PLAYER_ID, 'ignored': True}
        await self.broadcast_state(saved_state, event)

    async def handle_debug_duel_roll_battle(self, data):
        state = await self.get_game_state()
        debug_error = self._get_debug_access_error(state)
        if debug_error:
            await self.send_error(debug_error)
            return

        new_state, result = game_state.debug_duel_roll_battle(state)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        event = {'type': 'battle_roll_registered', 'player_id': game_state._DEBUG_TEST_PLAYER_ID}
        if result and not result.get('reroll_required') and (
            result.get('winner_id') is not None
            or result.get('mode') in ('trainer', 'gym')
            or result.get('battle_finished')
        ):
            event = {'type': 'battle_resolved', 'result': result}
        elif result and result.get('ignored'):
            event = {'type': 'battle_roll_registered', 'player_id': game_state._DEBUG_TEST_PLAYER_ID, 'ignored': True}
        await self.broadcast_state(saved_state, event)

    async def handle_debug_resolve_pending_action_for_test_player(self, data):
        state = await self.get_game_state()
        debug_error = self._get_debug_access_error(state)
        if debug_error:
            await self.send_error(debug_error)
            return

        option_id = (data.get('option_id') or '').strip()
        if not option_id:
            await self.send_error('option_id é obrigatório')
            return

        new_state, result = game_state.debug_resolve_pending_action_for_test_player(state, option_id)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'pending_action_resolved', 'player_id': game_state._DEBUG_TEST_PLAYER_ID, 'result': result})

    async def handle_resolve_event(self, data):
        state = await self.get_game_state()
        use_run_away = bool(data.get('use_run_away', False))
        new_state, result = game_state.resolve_event(state, self.player_id, use_run_away=use_run_away)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'event_resolved', 'player_id': self.player_id})

    async def handle_resolve_pending_action(self, data):
        state = await self.get_game_state()
        option_id = data.get('option_id')
        new_state, result = game_state.resolve_pending_action(state, self.player_id, option_id)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'pending_action_resolved', 'player_id': self.player_id, 'result': result})

    async def handle_confirm_league_intermission(self, data):
        state = await self.get_game_state()
        new_state, result = game_state.confirm_league_intermission(state, self.player_id)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'league_intermission_confirmed', 'player_id': self.player_id, 'result': result})

    async def handle_dismiss_revealed_card(self, data):
        state = await self.get_game_state()
        new_state, result = game_state.dismiss_revealed_card(state, self.player_id)
        if new_state is None:
            await self.send_error(result)
            return

        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'revealed_card_dismissed', 'player_id': self.player_id})

    async def handle_remove_player(self, data):
        target_id = data.get('player_id')
        state = await self.get_game_state()
        if not self._is_host(state):
            await self.send_error('Apenas o host pode remover jogadores')
            return

        new_state = game_state.remove_player(state, target_id)
        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'player_removed', 'player_id': target_id})

    async def handle_leave_game(self, data):
        state = await self.get_game_state()
        new_state = game_state.remove_player(state, self.player_id)
        saved_state = await self.save_game_state(new_state)
        await self.broadcast_state(saved_state, {'type': 'player_left', 'player_id': self.player_id})
        await self.close()

    async def handle_save_state(self, data):
        state = await self.get_game_state()
        provided = data.get('state')
        if isinstance(provided, dict):
            state = normalize_state(self.room_code, provided)
        saved_state = await self.save_game_state(state)
        await self.broadcast_state(saved_state, {'type': 'state_saved'})

    async def handle_restore_state(self, data):
        provided = data.get('state')
        if not isinstance(provided, dict):
            await self.send_error('state deve ser um objeto JSON')
            return

        state = normalize_state(self.room_code, provided)
        saved_state = await self.save_game_state(state)
        await self.broadcast_state(saved_state, {'type': 'state_restored'})

    async def handle_chat_message(self, data):
        text = (data.get('text') or '').strip()[:300]
        if not text:
            return
        state = await self.get_game_state()
        player = next((p for p in state.get('players', []) if p['id'] == self.player_id), None)
        player_name = player['name'] if player else 'Anônimo'
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'broadcast_chat',
                'player_id': self.player_id,
                'player_name': player_name,
                'text': text,
            },
        )

    async def broadcast_chat(self, message):
        try:
            await self.send_json({
                'type': 'chat_message',
                'player_id': message['player_id'],
                'player_name': message['player_name'],
                'text': message['text'],
            })
        except Exception:
            pass

    async def broadcast_state(self, state, event=None):
        await self.channel_layer.group_send(
            self.room_group_name,
            {'type': 'send_state_update', 'state': state, 'event': event or {}},
        )
        self._schedule_cpu_actions(state)

    def _schedule_cpu_actions(self, state: dict) -> None:
        """Schedule delayed tasks for any CPU players that need to act now."""
        cpu_ids = cpu_engine.needs_cpu_action(state)
        for i, cpu_id in enumerate(cpu_ids):
            delay = 1.5 + i * 1.2
            asyncio.create_task(self._delayed_cpu_action(cpu_id, delay))

    async def _delayed_cpu_action(self, cpu_player_id: str, delay: float) -> None:
        await asyncio.sleep(delay)
        try:
            async with self._room_lock():
                state = await self.get_game_state()
                await self._execute_cpu_action(state, cpu_player_id)
        except Exception as exc:
            _cpu_debug('ERROR', 'erro ao executar ação', cpu_player_id=cpu_player_id, error=str(exc))

    async def _execute_cpu_action(self, state: dict, cpu_player_id: str) -> None:
        """Execute one CPU decision step, save, and broadcast."""
        actions = cpu_engine.decide_action(state, cpu_player_id)
        if not actions:
            return
        action_name, kwargs = actions[0]
        if action_name == 'wait':
            return

        _cpu_debug('ACTION', 'executando ação', state=state, cpu_player_id=cpu_player_id, action=action_name, kwargs=kwargs)
        result = await self._apply_cpu_action(state, cpu_player_id, action_name, kwargs)
        if result is None:
            return
        new_state, event = result
        saved = await self.save_game_state(new_state)
        await self.broadcast_state(saved, event)

    async def _apply_cpu_action(
        self,
        state: dict,
        cpu_player_id: str,
        action_name: str,
        kwargs: dict,
    ) -> tuple[dict, dict] | None:
        """Map action_name to a game_state call. Returns (new_state, event) or None."""

        if action_name == 'select_starter':
            new_state = game_state.select_starter(state, cpu_player_id, kwargs['starter_id'])
            if new_state is None:
                return None
            return new_state, {'type': 'starter_selected', 'player_id': cpu_player_id,
                               'starter_id': kwargs['starter_id']}

        if action_name == 'roll_dice':
            rolled_state, roll_entry = game_state.perform_movement_roll(state, cpu_player_id)
            if (rolled_state.get('turn', {}).get('pending_action') or {}).get('type') == 'ability_decision':
                new_state = rolled_state
            else:
                new_state = game_state.process_move(rolled_state, cpu_player_id,
                                                    int(roll_entry['final_result']))
            return new_state, {
                'type': 'dice_rolled', 'roll_type': 'movement',
                'player_id': cpu_player_id,
                'result': roll_entry['final_result'],
                'final_result': roll_entry['final_result'],
            }

        if action_name == 'challenge_player':
            target_id = kwargs.get('target_player_id')
            new_state = game_state.start_duel(state, cpu_player_id, target_id)
            if new_state is None:
                _cpu_debug('ERROR', 'challenge_player falhou', state=state, cpu_player_id=cpu_player_id, target_id=target_id)
                return None
            return new_state, {
                'type': 'duel_started',
                'challenger_id': cpu_player_id,
                'defender_id': target_id,
            }

        if action_name == 'discard_item':
            item_key = (kwargs.get('item_key') or '').strip()
            new_state, result = game_state.discard_item(state, cpu_player_id, item_key)
            if new_state is None:
                _cpu_debug('ERROR', 'discard_item falhou', state=state, cpu_player_id=cpu_player_id, item_key=item_key, error=result)
                return None
            return new_state, {
                'type': 'item_discarded',
                'player_id': cpu_player_id,
                'item_key': item_key,
            }

        if action_name == 'pass_turn':
            new_state = game_state.end_turn(state)
            return new_state, {'type': 'turn_passed', 'player_id': cpu_player_id}

        if action_name == 'resolve_event':
            use_run_away = kwargs.get('use_run_away', False)
            new_state, err = game_state.resolve_event(state, cpu_player_id,
                                                      use_run_away=use_run_away)
            if new_state is None:
                _cpu_debug('ERROR', 'resolve_event falhou', state=state, cpu_player_id=cpu_player_id, use_run_away=use_run_away, error=err)
                return None
            return new_state, {'type': 'event_resolved', 'player_id': cpu_player_id}

        if action_name == 'roll_capture_dice':
            new_state, result = game_state.roll_capture_attempt(
                state, cpu_player_id,
                use_full_restore=kwargs.get('use_full_restore', False),
                use_master_ball=kwargs.get('use_master_ball', False),
            )
            if new_state is None:
                _cpu_debug('ERROR', 'roll_capture_attempt falhou', state=state, cpu_player_id=cpu_player_id, error=result)
                return None
            ev_type = ('pokemon_captured'
                       if isinstance(result, dict) and result.get('pokemon')
                       else 'capture_roll_resolved')
            return new_state, {'type': ev_type, 'player_id': cpu_player_id, 'result': result}

        if action_name == 'skip_action':
            new_state = game_state.skip_action(state, cpu_player_id)
            return new_state, {'type': 'action_skipped', 'player_id': cpu_player_id}

        if action_name == 'battle_choice':
            new_state, result = game_state.register_battle_choice(
                state, cpu_player_id,
                kwargs.get('pokemon_index', 0),
                pokemon_slot_key=kwargs.get('pokemon_slot_key'),
            )
            if result and result.get('error'):
                _cpu_debug('ERROR', 'battle_choice falhou', state=state, cpu_player_id=cpu_player_id, error=result['error'])
                return None
            if result and result.get('ignored'):
                return None
            return new_state, {'type': 'battle_choice_registered', 'player_id': cpu_player_id}

        if action_name == 'roll_battle_dice':
            new_state, result = game_state.register_battle_roll(state, cpu_player_id)
            if result and result.get('error'):
                _cpu_debug('ERROR', 'roll_battle_dice falhou', state=state, cpu_player_id=cpu_player_id, error=result['error'])
                return None
            if result and result.get('ignored'):
                return None
            ev = {'type': 'battle_roll_registered', 'player_id': cpu_player_id}
            if result and not result.get('reroll_required') and (
                result.get('winner_id') is not None
                or result.get('mode') in ('trainer', 'gym')
                or result.get('battle_finished')
            ):
                ev = {'type': 'battle_resolved', 'result': result}
            return new_state, ev

        if action_name == 'resolve_pending_action':
            new_state, result = game_state.resolve_pending_action(
                state, cpu_player_id, kwargs.get('option_id'))
            if new_state is None:
                _cpu_debug('ERROR', 'resolve_pending_action falhou', state=state, cpu_player_id=cpu_player_id, option_id=kwargs.get('option_id'), error=result)
                return None
            return new_state, {'type': 'pending_action_resolved',
                               'player_id': cpu_player_id, 'result': result}

        if action_name == 'confirm_league_intermission':
            new_state, result = game_state.confirm_league_intermission(state, cpu_player_id)
            if new_state is None:
                _cpu_debug('ERROR', 'confirm_league_intermission falhou', state=state, cpu_player_id=cpu_player_id, error=result)
                return None
            return new_state, {'type': 'league_intermission_confirmed',
                               'player_id': cpu_player_id, 'result': result}

        if action_name == 'release_pokemon':
            new_state, result = game_state.release_pokemon_for_capture(
                state, cpu_player_id,
                pokemon_slot_key=kwargs.get('pokemon_slot_key'),
            )
            if new_state is None:
                _cpu_debug('ERROR', 'release_pokemon falhou', state=state, cpu_player_id=cpu_player_id, pokemon_slot_key=kwargs.get('pokemon_slot_key'), error=result)
                return None
            return new_state, {'type': 'pokemon_released',
                               'player_id': cpu_player_id, 'result': result}

        if action_name == 'dismiss_revealed_card':
            new_state, result = game_state.dismiss_revealed_card(state, cpu_player_id)
            if new_state is None:
                _cpu_debug('ERROR', 'dismiss_revealed_card falhou', state=state, cpu_player_id=cpu_player_id, error=result)
                return None
            return new_state, {'type': 'revealed_card_dismissed', 'player_id': cpu_player_id}

        _cpu_debug('ERROR', 'ação desconhecida', state=state, cpu_player_id=cpu_player_id, action=action_name)
        return None

    async def send_state_update(self, message):
        try:
            await self.send_json({'type': 'state_update', 'state': message['state'], 'event': message['event']})
        except Exception:
            pass

    async def broadcast_event(self, message):
        try:
            await self.send_json({'type': 'event', 'event': message['event']})
        except Exception:
            pass

    async def send_error(self, message):
        await self.send_json({'type': 'error', 'message': message})

    async def send_json(self, data):
        await self.send(text_data=json.dumps(data, default=str))

    def _find_reconnect_player(self, state, provided_id: str, player_name: str) -> dict | None:
        """
        Localiza o jogador correto para reconexão durante uma partida em andamento.

        Prioridade:
        1. Por player_id (confiável — enviado pelo frontend via sessionStorage)
        2. Por nome (fallback) — somente se o jogador estiver DESCONECTADO para
           evitar sequestro de identidade quando dois jogadores têm o mesmo nome.
        """
        players = state.get('players', [])

        if provided_id:
            by_id = next(
                (p for p in players if p['id'] == provided_id and p.get('is_active', True)),
                None,
            )
            if by_id:
                print(f'[RECONNECT] por player_id={provided_id!r} → {by_id["name"]!r}')
                return by_id
            print(f'[RECONNECT] player_id={provided_id!r} não encontrado na sala')

        # Fallback por nome — somente jogadores desconectados, evita colisão de nomes
        by_name = next(
            (p for p in players
             if p['name'] == player_name
             and p.get('is_active', True)
             and not p.get('is_connected', False)),
            None,
        )
        if by_name:
            print(f'[RECONNECT] por nome={player_name!r} (fallback) → {by_name["id"]!r}')
        else:
            print(f'[RECONNECT] nenhum jogador encontrado para name={player_name!r}')
        return by_name

    def _is_host(self, state):
        if not self.player_id:
            return False
        player = next((p for p in state.get('players', []) if p['id'] == self.player_id), None)
        if not player:
            return False
        if 'is_host' in player:
            return bool(player.get('is_host'))
        players = state.get('players', [])
        return bool(players and players[0].get('id') == self.player_id)

    def _is_current_player(self, state):
        if not self.player_id:
            return False
        current = state.get('turn', {}).get('current_player_id')
        result = current == self.player_id
        print(f'[TURN_CHECK] player_id={self.player_id!r} current_player_id={current!r} match={result}')
        return result

    def _parse_positive_int(self, value, field_name: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f'{field_name} deve ser um inteiro positivo')
        if isinstance(value, int):
            parsed = value
        elif isinstance(value, str) and re.fullmatch(r'\d+', value.strip() or ''):
            parsed = int(value.strip())
        else:
            raise ValueError(f'{field_name} deve ser um inteiro positivo')
        if parsed <= 0:
            raise ValueError(f'{field_name} deve ser um inteiro positivo')
        return parsed

    def _parse_non_zero_int(self, value, field_name: str) -> int:
        if isinstance(value, bool):
            raise ValueError(f'{field_name} deve ser um inteiro diferente de zero')
        if isinstance(value, int):
            parsed = value
        elif isinstance(value, str) and re.fullmatch(r'[+-]?\d+', value.strip() or ''):
            parsed = int(value.strip())
        else:
            raise ValueError(f'{field_name} deve ser um inteiro diferente de zero')
        if parsed == 0:
            raise ValueError(f'{field_name} deve ser um inteiro diferente de zero')
        return parsed

    def _get_debug_access_error(self, state, *, require_host_tools: bool = False):
        if not settings.DEBUG:
            return 'Ferramentas de debug só estão disponíveis em ambiente de desenvolvimento'
        if not self._is_host(state):
            return 'Apenas o host pode usar as ferramentas de debug'
        if require_host_tools and not game_state.host_tools_enabled(state):
            return 'O modo Host Tools está desabilitado'
        return None

    @database_sync_to_async
    def room_exists(self):
        return GameRoom.objects.filter(room_code=self.room_code).exists()

    @database_sync_to_async
    def get_game_state(self):
        try:
            room = GameRoom.objects.get(room_code=self.room_code)
            return normalize_state(room.room_code, room.game_state)
        except GameRoom.DoesNotExist:
            return {}

    @database_sync_to_async
    def save_game_state(self, state):
        normalized = normalize_state(self.room_code, state)
        normalized = mark_saved(normalized)
        GameRoom.objects.filter(room_code=self.room_code).update(
            game_state=normalized,
            status=normalized.get('status', 'waiting'),
        )
        return normalized

    @database_sync_to_async
    def mark_player_disconnected(self):
        try:
            room = GameRoom.objects.get(room_code=self.room_code)
            state = normalize_state(room.room_code, room.game_state)
            for player in state.get('players', []):
                if player['id'] == self.player_id:
                    player['is_connected'] = False
                    break
            room.game_state = state
            room.save(update_fields=['game_state'])
        except GameRoom.DoesNotExist:
            pass
