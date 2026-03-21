from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from game.models import GameRoom
from game.session_expiration import (
    SESSION_INACTIVITY_TIMEOUT,
    is_session_expired,
    prune_expired_sessions,
)
from game.state_schema import build_initial_state


class SessionExpirationTests(TestCase):
    def _create_room(self, room_code: str, *, status_name: str = 'waiting') -> GameRoom:
        return GameRoom.objects.create(
            room_code=room_code,
            status=status_name,
            game_state=build_initial_state(room_code),
        )

    def test_active_session_does_not_expire(self):
        room = self._create_room('ACT123')
        now = room.updated_at + SESSION_INACTIVITY_TIMEOUT - timedelta(seconds=1)

        self.assertFalse(is_session_expired(room, now=now))
        self.assertEqual(prune_expired_sessions(now=now), [])
        self.assertTrue(GameRoom.objects.filter(room_code=room.room_code).exists())

    def test_session_expires_after_more_than_24_hours_without_activity(self):
        room = self._create_room('EXP123', status_name='playing')
        stale_at = timezone.now() - SESSION_INACTIVITY_TIMEOUT - timedelta(seconds=1)
        GameRoom.objects.filter(room_code=room.room_code).update(updated_at=stale_at)

        with self.assertLogs('game.session_expiration', level='INFO') as captured_logs:
            expired = prune_expired_sessions()

        self.assertEqual(expired, [room.room_code])
        self.assertFalse(GameRoom.objects.filter(room_code=room.room_code).exists())
        self.assertTrue(any(room.room_code in message for message in captured_logs.output))

    def test_session_exactly_at_24_hour_limit_does_not_expire(self):
        room = self._create_room('LIM123')
        now = room.updated_at + SESSION_INACTIVITY_TIMEOUT

        self.assertFalse(is_session_expired(room, now=now))
        self.assertEqual(prune_expired_sessions(now=now), [])
        self.assertTrue(GameRoom.objects.filter(room_code=room.room_code).exists())


class SessionExpirationApiTests(APITestCase):
    def _create_room(self, room_code: str, *, status_name: str = 'waiting') -> GameRoom:
        return GameRoom.objects.create(
            room_code=room_code,
            status=status_name,
            game_state=build_initial_state(room_code),
        )

    def test_expired_session_does_not_appear_in_room_list(self):
        active_room = self._create_room('LST123')
        expired_room = self._create_room('OLD123', status_name='playing')
        stale_at = timezone.now() - SESSION_INACTIVITY_TIMEOUT - timedelta(seconds=1)
        GameRoom.objects.filter(room_code=expired_room.room_code).update(updated_at=stale_at)

        list_response = self.client.get(reverse('room-list'))
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        listed_codes = {entry['room_code'] for entry in list_response.data}
        self.assertIn(active_room.room_code, listed_codes)
        self.assertNotIn(expired_room.room_code, listed_codes)

    def test_expired_session_cannot_be_reopened_by_room_code(self):
        expired_room = self._create_room('DET123', status_name='playing')
        stale_at = timezone.now() - SESSION_INACTIVITY_TIMEOUT - timedelta(seconds=1)
        GameRoom.objects.filter(room_code=expired_room.room_code).update(updated_at=stale_at)

        detail_response = self.client.get(reverse('room-detail', kwargs={'room_code': expired_room.room_code}))
        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(detail_response.data['error'], 'Sala expirada por inatividade')
        self.assertFalse(GameRoom.objects.filter(room_code=expired_room.room_code).exists())
