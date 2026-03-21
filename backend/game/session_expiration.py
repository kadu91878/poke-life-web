import logging
from datetime import timedelta

from django.utils import timezone

from .models import GameRoom

SESSION_INACTIVITY_TIMEOUT = timedelta(hours=24)

logger = logging.getLogger(__name__)


def is_session_expired(room: GameRoom, *, now=None) -> bool:
    reference = now or timezone.now()
    last_activity = room.updated_at or room.created_at
    if last_activity is None:
        return False
    return reference - last_activity > SESSION_INACTIVITY_TIMEOUT


def prune_expired_sessions(*, room_code: str | None = None, now=None) -> list[str]:
    reference = now or timezone.now()
    cutoff = reference - SESSION_INACTIVITY_TIMEOUT

    queryset = GameRoom.objects.all()
    if room_code:
        queryset = queryset.filter(room_code=room_code)

    expired_rooms = list(
        queryset
        .filter(updated_at__lt=cutoff)
        .values_list('room_code', 'updated_at')
    )
    if not expired_rooms:
        return []

    expired_codes = [code for code, _ in expired_rooms]
    queryset.filter(room_code__in=expired_codes).delete()
    for expired_code, last_activity in expired_rooms:
        logger.info(
            "Removing expired game room %s after inactivity since %s",
            expired_code,
            last_activity.isoformat() if last_activity else 'unknown',
        )
    return expired_codes


def get_room_if_active(room_code: str) -> tuple[GameRoom | None, bool]:
    expired_codes = prune_expired_sessions(room_code=room_code)
    if expired_codes:
        return None, True
    try:
        return GameRoom.objects.get(room_code=room_code), False
    except GameRoom.DoesNotExist:
        return None, False
