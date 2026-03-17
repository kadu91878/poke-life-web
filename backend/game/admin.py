from django.contrib import admin
from .models import GameRoom


@admin.register(GameRoom)
class GameRoomAdmin(admin.ModelAdmin):
    list_display = ('room_code', 'status', 'player_count', 'created_at', 'updated_at')
    list_filter = ('status',)
    search_fields = ('room_code',)
    readonly_fields = ('created_at', 'updated_at')

    def player_count(self, obj):
        players = obj.game_state.get('players', [])
        return len(players)
    player_count.short_description = 'Jogadores'
