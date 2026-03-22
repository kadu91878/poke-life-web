"""
Testes para a camada Redis (game/redis_client.py).

Estratégia:
  - Todos os testes usam mocks do cliente Redis — sem dependência de servidor real.
  - Cada teste reseta o singleton via redis_client._reset_for_testing().
  - Testa comportamento com Redis disponível E comportamento de fallback.
"""

import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, MagicMock, patch

from django.test import SimpleTestCase, override_settings

from game import redis_client


def _make_mock_redis(*, ping_ok: bool = True, set_ok: bool = True, exists: int = 1) -> MagicMock:
    """Cria um mock do cliente redis.asyncio com os métodos assíncronos configurados."""
    r = MagicMock()
    r.ping = AsyncMock(return_value=True if ping_ok else (_ for _ in ()).throw(ConnectionError("down")))
    r.set = AsyncMock(return_value=True if set_ok else None)
    r.exists = AsyncMock(return_value=exists)
    r.delete = AsyncMock(return_value=1)
    r.get = AsyncMock(return_value=None)
    return r


class TestGetRedis(IsolatedAsyncioTestCase):
    def setUp(self):
        redis_client._reset_for_testing()

    async def test_returns_none_when_redis_url_empty(self):
        with override_settings(REDIS_URL=''):
            result = await redis_client.get_redis()
        self.assertIsNone(result)

    async def test_returns_none_when_redis_url_missing(self):
        with override_settings(REDIS_URL=None):
            result = await redis_client.get_redis()
        self.assertIsNone(result)

    async def test_returns_client_when_ping_succeeds(self):
        mock_client = _make_mock_redis(ping_ok=True)
        with override_settings(REDIS_URL='redis://localhost:6379/0'):
            with patch('redis.asyncio.from_url', return_value=mock_client):
                result = await redis_client.get_redis()
        self.assertIs(result, mock_client)
        mock_client.ping.assert_awaited_once()

    async def test_returns_none_when_ping_fails(self):
        mock_client = MagicMock()
        mock_client.ping = AsyncMock(side_effect=ConnectionError("Redis offline"))
        with override_settings(REDIS_URL='redis://localhost:6379/0'):
            with patch('redis.asyncio.from_url', return_value=mock_client):
                result = await redis_client.get_redis()
        self.assertIsNone(result)

    async def test_caches_client_on_second_call(self):
        mock_client = _make_mock_redis()
        with override_settings(REDIS_URL='redis://localhost:6379/0'):
            with patch('redis.asyncio.from_url', return_value=mock_client) as patched:
                await redis_client.get_redis()
                await redis_client.get_redis()
        # from_url deve ser chamado apenas uma vez
        patched.assert_called_once()

    async def test_caches_failure_on_second_call(self):
        mock_client = MagicMock()
        mock_client.ping = AsyncMock(side_effect=ConnectionError("down"))
        with override_settings(REDIS_URL='redis://localhost:6379/0'):
            with patch('redis.asyncio.from_url', return_value=mock_client) as patched:
                await redis_client.get_redis()
                await redis_client.get_redis()
        patched.assert_called_once()


class TestTouchSessionActivity(IsolatedAsyncioTestCase):
    def setUp(self):
        redis_client._reset_for_testing()

    async def test_calls_set_with_correct_key_and_ttl(self):
        mock_r = _make_mock_redis()
        with patch.object(redis_client, 'get_redis', AsyncMock(return_value=mock_r)):
            await redis_client.touch_session_activity('ABC123')

        mock_r.set.assert_awaited_once()
        call_args = mock_r.set.call_args
        key, value = call_args.args
        self.assertEqual(key, 'session:activity:ABC123')
        self.assertEqual(call_args.kwargs.get('ex'), redis_client.SESSION_ACTIVITY_TTL)

    async def test_noop_when_redis_unavailable(self):
        with patch.object(redis_client, 'get_redis', AsyncMock(return_value=None)):
            # Não deve levantar exceção
            await redis_client.touch_session_activity('ABC123')

    async def test_handles_redis_exception_gracefully(self):
        mock_r = _make_mock_redis()
        mock_r.set = AsyncMock(side_effect=ConnectionError("dropped"))
        with patch.object(redis_client, 'get_redis', AsyncMock(return_value=mock_r)):
            # Não deve propagar exceção — apenas loga warning
            await redis_client.touch_session_activity('ABC123')


class TestIsSessionKnownActive(IsolatedAsyncioTestCase):
    def setUp(self):
        redis_client._reset_for_testing()

    async def test_returns_true_when_key_exists(self):
        mock_r = _make_mock_redis(exists=1)
        with patch.object(redis_client, 'get_redis', AsyncMock(return_value=mock_r)):
            result = await redis_client.is_session_known_active('ABC123')
        self.assertTrue(result)
        mock_r.exists.assert_awaited_once_with('session:activity:ABC123')

    async def test_returns_false_when_key_absent(self):
        mock_r = _make_mock_redis(exists=0)
        with patch.object(redis_client, 'get_redis', AsyncMock(return_value=mock_r)):
            result = await redis_client.is_session_known_active('ABC123')
        self.assertFalse(result)

    async def test_returns_none_when_redis_unavailable(self):
        with patch.object(redis_client, 'get_redis', AsyncMock(return_value=None)):
            result = await redis_client.is_session_known_active('ABC123')
        self.assertIsNone(result)

    async def test_returns_none_on_redis_exception(self):
        mock_r = _make_mock_redis()
        mock_r.exists = AsyncMock(side_effect=ConnectionError("lost"))
        with patch.object(redis_client, 'get_redis', AsyncMock(return_value=mock_r)):
            result = await redis_client.is_session_known_active('ABC123')
        self.assertIsNone(result)


class TestClearSessionActivity(IsolatedAsyncioTestCase):
    def setUp(self):
        redis_client._reset_for_testing()

    async def test_calls_delete_with_correct_key(self):
        mock_r = _make_mock_redis()
        with patch.object(redis_client, 'get_redis', AsyncMock(return_value=mock_r)):
            await redis_client.clear_session_activity('ABC123')
        mock_r.delete.assert_awaited_once_with('session:activity:ABC123')

    async def test_noop_when_redis_unavailable(self):
        with patch.object(redis_client, 'get_redis', AsyncMock(return_value=None)):
            await redis_client.clear_session_activity('ABC123')


class TestRoomLock(IsolatedAsyncioTestCase):
    def setUp(self):
        redis_client._reset_for_testing()

    async def test_uses_redis_lock_when_available(self):
        mock_r = MagicMock()
        # SET NX retorna True (lock adquirido imediatamente)
        mock_r.set = AsyncMock(return_value=True)
        mock_r.get = AsyncMock(return_value='some-token')
        mock_r.delete = AsyncMock(return_value=1)

        fallback = {}
        executed = []

        with patch.object(redis_client, 'get_redis', AsyncMock(return_value=mock_r)):
            async with redis_client.room_lock('ABC123', fallback_locks=fallback):
                executed.append('inside')

        self.assertEqual(executed, ['inside'])
        # Confirma que usou Redis (SET foi chamado para adquirir o lock)
        mock_r.set.assert_awaited()
        # Fallback não deve ter sido criado
        self.assertNotIn('ABC123', fallback)

    async def test_falls_back_to_asyncio_lock_when_redis_unavailable(self):
        fallback: dict[str, asyncio.Lock] = {}
        executed = []

        with patch.object(redis_client, 'get_redis', AsyncMock(return_value=None)):
            async with redis_client.room_lock('ABC123', fallback_locks=fallback):
                executed.append('inside')

        self.assertEqual(executed, ['inside'])
        # asyncio.Lock deve ter sido criado no fallback
        self.assertIn('ABC123', fallback)
        self.assertIsInstance(fallback['ABC123'], asyncio.Lock)

    async def test_reuses_existing_fallback_lock(self):
        existing_lock = asyncio.Lock()
        fallback = {'ABC123': existing_lock}

        with patch.object(redis_client, 'get_redis', AsyncMock(return_value=None)):
            async with redis_client.room_lock('ABC123', fallback_locks=fallback):
                pass

        # O lock original deve ser reutilizado, não substituído
        self.assertIs(fallback['ABC123'], existing_lock)

    async def test_lock_is_exclusive(self):
        """Dois coroutines tentando o lock: apenas um entra por vez."""
        fallback: dict[str, asyncio.Lock] = {}
        order = []

        async def task(label: str) -> None:
            with patch.object(redis_client, 'get_redis', AsyncMock(return_value=None)):
                async with redis_client.room_lock('ABC123', fallback_locks=fallback):
                    order.append(f'{label}-enter')
                    await asyncio.sleep(0)  # yield ao event loop
                    order.append(f'{label}-exit')

        await asyncio.gather(task('A'), task('B'))

        # Deve haver interleaving correto: A-enter, A-exit, B-enter, B-exit (ou B antes de A)
        self.assertEqual(len(order), 4)
        enter_idx = order.index('A-enter')
        exit_idx = order.index('A-exit')
        self.assertLess(enter_idx, exit_idx)

    async def test_redis_lock_releases_on_exception(self):
        """Lock Redis deve ser liberado mesmo quando o bloco lança exceção."""
        mock_r = MagicMock()
        mock_r.set = AsyncMock(return_value=True)
        token_holder = {}

        async def capture_set(key, value, **kwargs):
            token_holder['token'] = value
            return True

        mock_r.set.side_effect = capture_set
        mock_r.get = AsyncMock(side_effect=lambda k: token_holder.get('token'))
        mock_r.delete = AsyncMock(return_value=1)

        with patch.object(redis_client, 'get_redis', AsyncMock(return_value=mock_r)):
            with self.assertRaises(ValueError):
                async with redis_client.room_lock('ABC123', fallback_locks={}):
                    raise ValueError("erro no bloco")

        # DELETE deve ter sido chamado para liberar o lock
        mock_r.delete.assert_awaited()
