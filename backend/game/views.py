import random
import string
import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .catalog.repository import card_repo
from .engine import mechanics
from .engine import state as game_state
from .engine.inventory import get_starting_resource_defaults
from .models import GameRoom
from .serializers import GameRoomDetailSerializer, GameRoomSerializer
from .state_schema import build_initial_state, mark_saved, normalize_state

PLAYER_COLORS = ['red', 'blue', 'green', 'yellow', 'purple']



def _generate_room_code() -> str:
    chars = string.ascii_uppercase + string.digits
    while True:
        code = ''.join(random.choices(chars, k=6))
        if not GameRoom.objects.filter(room_code=code).exists():
            return code



def _broadcast_room_state(room_code: str, state: dict, event: dict | None = None):
    channel_layer = get_channel_layer()
    if not channel_layer:
        return
    async_to_sync(channel_layer.group_send)(
        f'game_{room_code}',
        {
            'type': 'send_state_update',
            'state': state,
            'event': event or {'type': 'state_saved'},
        },
    )



def _new_player(name: str, index: int) -> dict:
    starting_defaults = get_starting_resource_defaults()
    return {
        'id': str(uuid.uuid4()),
        'name': name,
        'color': PLAYER_COLORS[index % len(PLAYER_COLORS)],
        'is_host': index == 0,
        'is_active': True,
        'is_connected': True,
        'position': 0,
        'pokeballs': starting_defaults['pokeballs'],
        'full_restores': starting_defaults['full_restores'],
        'starter_slot_applied': False,
        'starter_pokemon': None,
        'pokemon': [],
        'capture_sequence_counter': 0,
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



class CreateRoomView(APIView):
    def post(self, request):
        room_code = _generate_room_code()
        state = build_initial_state(room_code)
        room = GameRoom.objects.create(room_code=room_code, status='waiting', game_state=state)
        return Response(
            {'room_code': room.room_code, 'status': room.status, 'game_state': room.game_state},
            status=status.HTTP_201_CREATED,
        )


class HealthcheckView(APIView):
    def get(self, request):
        return Response({'status': 'ok'})


class RoomListView(APIView):
    def get(self, request):
        rooms = GameRoom.objects.filter(status__in=['waiting', 'playing'])
        return Response(GameRoomSerializer(rooms, many=True).data)


class RoomDetailView(APIView):
    def _get_room(self, room_code):
        try:
            return GameRoom.objects.get(room_code=room_code)
        except GameRoom.DoesNotExist:
            return None

    def get(self, request, room_code):
        room = self._get_room(room_code)
        if not room:
            return Response({'error': 'Sala não encontrada'}, status=status.HTTP_404_NOT_FOUND)
        room.game_state = normalize_state(room_code, room.game_state)
        room.save(update_fields=['game_state'])
        return Response(GameRoomDetailSerializer(room).data)

    def delete(self, request, room_code):
        room = self._get_room(room_code)
        if not room:
            return Response({'error': 'Sala não encontrada'}, status=status.HTTP_404_NOT_FOUND)
        room.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoomActionBase(APIView):
    def get_room(self, room_code: str):
        try:
            return GameRoom.objects.get(room_code=room_code)
        except GameRoom.DoesNotExist:
            return None

    def get_state(self, room: GameRoom) -> dict:
        return normalize_state(room.room_code, room.game_state)

    def save_state(self, room: GameRoom, state: dict, event: dict | None = None):
        normalized = normalize_state(room.room_code, state)
        room.game_state = mark_saved(normalized)
        room.status = room.game_state.get('status', room.status)
        room.save(update_fields=['game_state', 'status', 'updated_at'])
        _broadcast_room_state(room.room_code, room.game_state, event)
        return room.game_state


class JoinRoomView(RoomActionBase):
    def post(self, request, room_code):
        room = self.get_room(room_code)
        if not room:
            return Response({'error': 'Sala não encontrada'}, status=status.HTTP_404_NOT_FOUND)

        state = self.get_state(room)
        player_name = (request.data.get('player_name') or 'Trainer').strip()[:20]
        if not player_name:
            player_name = 'Trainer'

        if state.get('status') == 'finished':
            return Response({'error': 'Partida finalizada'}, status=status.HTTP_400_BAD_REQUEST)

        existing = next((p for p in state['players'] if p['name'] == player_name and p.get('is_active', True)), None)
        if existing:
            existing['is_connected'] = True
            saved = self.save_state(room, state, {'type': 'player_reconnected', 'player_id': existing['id']})
            return Response({'player_id': existing['id'], 'state': saved})

        if state.get('status') == 'playing':
            return Response({'error': 'A partida já começou'}, status=status.HTTP_400_BAD_REQUEST)

        active_players = [p for p in state['players'] if p.get('is_active', True)]
        if len(active_players) >= 5:
            return Response({'error': 'Sala cheia (máximo 5 jogadores)'}, status=status.HTTP_400_BAD_REQUEST)

        player = _new_player(player_name, len(state['players']))
        state['players'].append(player)
        saved = self.save_state(room, state, {'type': 'player_joined', 'player_id': player['id'], 'player_name': player_name})
        return Response({'player_id': player['id'], 'state': saved}, status=status.HTTP_201_CREATED)


class StartGameView(RoomActionBase):
    def post(self, request, room_code):
        room = self.get_room(room_code)
        if not room:
            return Response({'error': 'Sala não encontrada'}, status=status.HTTP_404_NOT_FOUND)

        player_id = request.data.get('player_id')
        state = self.get_state(room)
        host = next((p for p in state['players'] if p.get('is_host')), None)

        if not host or host.get('id') != player_id:
            return Response({'error': 'Apenas o host pode iniciar'}, status=status.HTTP_403_FORBIDDEN)

        if state.get('status') != 'waiting':
            return Response({'error': 'Partida já iniciada'}, status=status.HTTP_400_BAD_REQUEST)

        active = [p for p in state['players'] if p.get('is_active', True)]
        if len(active) < 2:
            return Response({'error': 'Mínimo de 2 jogadores ativos'}, status=status.HTTP_400_BAD_REQUEST)

        started = game_state.initialize_game(state)
        saved = self.save_state(room, started, {'type': 'game_started'})
        return Response({'state': saved})


class AddCpuPlayerView(RoomActionBase):
    """Adiciona um jogador CPU à sala (apenas enquanto aguarda jogadores)."""

    _CPU_NAMES = ['CPU Ash', 'CPU Misty', 'CPU Brock', 'CPU Gary', 'CPU Jessie']

    def post(self, request, room_code):
        room = self.get_room(room_code)
        if not room:
            return Response({'error': 'Sala não encontrada'}, status=status.HTTP_404_NOT_FOUND)

        state = self.get_state(room)

        if state.get('status') != 'waiting':
            return Response({'error': 'Só é possível adicionar CPU antes de iniciar a partida'},
                            status=status.HTTP_400_BAD_REQUEST)

        active_players = [p for p in state['players'] if p.get('is_active', True)]
        if len(active_players) >= 5:
            return Response({'error': 'Sala cheia (máximo 5 jogadores)'},
                            status=status.HTTP_400_BAD_REQUEST)

        # Pick a name not already taken
        existing_names = {p['name'] for p in state['players']}
        cpu_name = next(
            (n for n in self._CPU_NAMES if n not in existing_names),
            f'CPU {len(active_players) + 1}',
        )

        player = _new_player(cpu_name, len(state['players']))
        player['is_cpu'] = True
        player['is_connected'] = False  # CPU tem presença lógica, não WebSocket

        state['players'].append(player)
        saved = self.save_state(room, state, {'type': 'cpu_player_added',
                                              'player_id': player['id'],
                                              'player_name': cpu_name})
        return Response({'player_id': player['id'], 'state': saved},
                        status=status.HTTP_201_CREATED)


class SelectStarterView(RoomActionBase):
    def post(self, request, room_code):
        room = self.get_room(room_code)
        if not room:
            return Response({'error': 'Sala não encontrada'}, status=status.HTTP_404_NOT_FOUND)

        player_id = request.data.get('player_id')
        starter_id = request.data.get('starter_id')
        state = self.get_state(room)
        updated = game_state.select_starter(state, player_id, starter_id)
        if updated is None:
            return Response({'error': 'Starter inválido ou fora de turno'}, status=status.HTTP_400_BAD_REQUEST)

        saved = self.save_state(room, updated, {'type': 'starter_selected', 'player_id': player_id, 'starter_id': starter_id})
        return Response({'state': saved})


class RollDiceView(RoomActionBase):
    def post(self, request, room_code):
        room = self.get_room(room_code)
        if not room:
            return Response({'error': 'Sala não encontrada'}, status=status.HTTP_404_NOT_FOUND)

        player_id = request.data.get('player_id')
        state = self.get_state(room)
        if state.get('turn', {}).get('current_player_id') != player_id:
            return Response({'error': 'Não é seu turno'}, status=status.HTTP_400_BAD_REQUEST)
        if state.get('turn', {}).get('phase') != 'roll':
            return Response({'error': 'Não é fase de rolagem'}, status=status.HTTP_400_BAD_REQUEST)

        rolled_state, roll_entry = game_state.perform_movement_roll(state, player_id)
        updated = game_state.process_move(rolled_state, player_id, int(roll_entry['final_result']))
        saved = self.save_state(room, updated, {
            'type': 'dice_rolled',
            'roll_type': 'movement',
            'player_id': player_id,
            'result': roll_entry['final_result'],
            'raw_result': roll_entry['raw_result'],
            'final_result': roll_entry['final_result'],
            'modifier': roll_entry.get('modifier'),
            'modifier_reason': roll_entry.get('modifier_reason'),
        })
        return Response({'result': roll_entry['final_result'], 'state': saved})


class MovePlayerView(RoomActionBase):
    def post(self, request, room_code):
        room = self.get_room(room_code)
        if not room:
            return Response({'error': 'Sala não encontrada'}, status=status.HTTP_404_NOT_FOUND)

        player_id = request.data.get('player_id')
        dice_result = int(request.data.get('dice_result', 0))
        if dice_result < 1 or dice_result > 6:
            return Response({'error': 'dice_result deve estar entre 1 e 6'}, status=status.HTTP_400_BAD_REQUEST)

        state = self.get_state(room)
        if state.get('turn', {}).get('current_player_id') != player_id:
            return Response({'error': 'Não é seu turno'}, status=status.HTTP_400_BAD_REQUEST)

        updated = game_state.process_move(state, player_id, dice_result)
        saved = self.save_state(room, updated, {'type': 'player_moved', 'player_id': player_id, 'steps': dice_result})
        return Response({'state': saved})


class ResolveTileView(RoomActionBase):
    def post(self, request, room_code):
        room = self.get_room(room_code)
        if not room:
            return Response({'error': 'Sala não encontrada'}, status=status.HTTP_404_NOT_FOUND)

        player_id = request.data.get('player_id')
        action = request.data.get('resolution', 'auto')
        state = self.get_state(room)

        if state.get('turn', {}).get('current_player_id') != player_id:
            return Response({'error': 'Não é seu turno'}, status=status.HTTP_400_BAD_REQUEST)

        updated = state
        if state.get('turn', {}).get('phase') == 'event':
            use_run_away = bool(request.data.get('use_run_away', False))
            resolved, result = game_state.resolve_event(state, player_id, use_run_away=use_run_away)
            if resolved is None:
                return Response({'error': result}, status=status.HTTP_400_BAD_REQUEST)
            updated = resolved

        saved = self.save_state(room, updated, {'type': 'tile_resolved', 'player_id': player_id, 'resolution': action})
        return Response({'state': saved})


class PassTurnView(RoomActionBase):
    def post(self, request, room_code):
        room = self.get_room(room_code)
        if not room:
            return Response({'error': 'Sala não encontrada'}, status=status.HTTP_404_NOT_FOUND)

        player_id = request.data.get('player_id')
        state = self.get_state(room)
        if state.get('turn', {}).get('current_player_id') != player_id:
            return Response({'error': 'Não é seu turno'}, status=status.HTTP_400_BAD_REQUEST)
        if game_state.turn_has_blocking_interaction(state.get('turn', {})):
            return Response({'error': 'Não é possível passar o turno durante uma interação pendente'}, status=status.HTTP_400_BAD_REQUEST)

        updated = game_state.end_turn(state)
        saved = self.save_state(room, updated, {'type': 'turn_passed', 'player_id': player_id})
        return Response({'state': saved})


class LeaveRoomView(RoomActionBase):
    def post(self, request, room_code):
        room = self.get_room(room_code)
        if not room:
            return Response({'error': 'Sala não encontrada'}, status=status.HTTP_404_NOT_FOUND)

        player_id = request.data.get('player_id')
        state = self.get_state(room)
        updated = game_state.remove_player(state, player_id)
        saved = self.save_state(room, updated, {'type': 'player_left', 'player_id': player_id})
        return Response({'state': saved})


class RemovePlayerView(RoomActionBase):
    def post(self, request, room_code):
        room = self.get_room(room_code)
        if not room:
            return Response({'error': 'Sala não encontrada'}, status=status.HTTP_404_NOT_FOUND)

        actor_id = request.data.get('actor_id')
        target_id = request.data.get('player_id')
        state = self.get_state(room)

        actor = next((p for p in state['players'] if p['id'] == actor_id), None)
        if not actor or not actor.get('is_host'):
            return Response({'error': 'Apenas host pode remover jogador'}, status=status.HTTP_403_FORBIDDEN)

        updated = game_state.remove_player(state, target_id)
        saved = self.save_state(room, updated, {'type': 'player_removed', 'player_id': target_id})
        return Response({'state': saved})


class SaveStateView(RoomActionBase):
    def post(self, request, room_code):
        room = self.get_room(room_code)
        if not room:
            return Response({'error': 'Sala não encontrada'}, status=status.HTTP_404_NOT_FOUND)

        provided_state = request.data.get('state')
        current = self.get_state(room)
        state_to_save = normalize_state(room_code, provided_state if isinstance(provided_state, dict) else current)
        saved = self.save_state(room, state_to_save, {'type': 'state_saved'})
        return Response({'state': saved})


class RestoreStateView(RoomActionBase):
    def post(self, request, room_code):
        room = self.get_room(room_code)
        if not room:
            return Response({'error': 'Sala não encontrada'}, status=status.HTTP_404_NOT_FOUND)

        payload = request.data.get('state')
        if not isinstance(payload, dict):
            return Response({'error': 'Envie um objeto JSON no campo state'}, status=status.HTTP_400_BAD_REQUEST)

        restored = normalize_state(room_code, payload)
        saved = self.save_state(room, restored, {'type': 'state_restored'})
        return Response({'state': saved})


# ── Catálogo de cartas físicas ────────────────────────────────────────────────

class CardCatalogView(APIView):
    """
    GET /api/cards/
      Retorna a lista de todas as cartas físicas do catálogo.

    Query params opcionais:
      ability_type  — filtra por tipo de habilidade ('active', 'passive', 'battle')
      can_evolve    — filtra cartas que evoluem ('true'/'false')
      can_battle    — filtra cartas com poder de batalha ('true'/'false')
      is_initial    — filtra starters ('true'/'false')
    """

    def get(self, request):
        ability_type = request.query_params.get('ability_type')
        can_evolve   = _parse_bool(request.query_params.get('can_evolve'))
        can_battle   = _parse_bool(request.query_params.get('can_battle'))
        is_initial   = _parse_bool(request.query_params.get('is_initial'))

        cards = card_repo.filter(
            ability_type=ability_type,
            can_evolve=can_evolve,
            can_battle=can_battle,
            is_initial=is_initial,
        )
        return Response({
            'count': len(cards),
            'cards': [c.to_dict() for c in cards],
        })


class CardDetailView(APIView):
    """
    GET /api/cards/<card_id>/
      Retorna os dados de uma carta específica pelo id.
      Inclui dados da evolução se existir.
    """

    def get(self, request, card_id):
        card = card_repo.get_by_id(card_id)
        if card is None:
            return Response({'error': f"Carta '{card_id}' não encontrada"}, status=status.HTTP_404_NOT_FOUND)

        data = card.to_dict()
        evolution = card_repo.get_evolution(card)
        data['evolution'] = evolution.to_dict() if evolution else None

        return Response(data)


def _parse_bool(value: str | None) -> bool | None:
    """Converte string query param para bool, ou None se ausente."""
    if value is None:
        return None
    return value.lower() in ('true', '1', 'yes')
