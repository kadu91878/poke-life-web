from django.db import models


class GameRoom(models.Model):
    STATUS_CHOICES = [
        ('waiting', 'Aguardando jogadores'),
        ('playing', 'Em andamento'),
        ('finished', 'Finalizada'),
    ]

    room_code = models.CharField(max_length=6, unique=True, primary_key=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='waiting')
    game_state = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Sala {self.room_code} ({self.get_status_display()})"
