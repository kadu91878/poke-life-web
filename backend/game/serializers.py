from rest_framework import serializers

from .models import GameRoom
from .state_schema import normalize_state


class GameRoomSerializer(serializers.ModelSerializer):
    player_count = serializers.SerializerMethodField()
    active_player_count = serializers.SerializerMethodField()

    class Meta:
        model = GameRoom
        fields = ('room_code', 'status', 'player_count', 'active_player_count', 'created_at', 'updated_at')

    def get_player_count(self, obj):
        state = normalize_state(obj.room_code, obj.game_state)
        return len(state.get('players', []))

    def get_active_player_count(self, obj):
        state = normalize_state(obj.room_code, obj.game_state)
        return len([p for p in state.get('players', []) if p.get('is_active', True)])


class GameRoomDetailSerializer(serializers.ModelSerializer):
    schema_version = serializers.SerializerMethodField()

    class Meta:
        model = GameRoom
        fields = ('room_code', 'status', 'schema_version', 'game_state', 'created_at', 'updated_at')

    def get_schema_version(self, obj):
        state = normalize_state(obj.room_code, obj.game_state)
        return state.get('schema_version')
