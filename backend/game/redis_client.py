"""
Camada central de acesso ao Redis para Pokemon Life.

Chaves utilizadas
─────────────────
  session:activity:{room_code}   TTL=86400s  — registro de atividade da sala
  lock:room:{room_code}          TTL=30s     — lock distribuído por sala

Consumo estimado de memória
────────────────────────────
  Chaves de sessão   ~100 bytes × 100 salas  =   ~10 KB
  Locks              ~80  bytes × 100 salas  =    ~8 KB
  Channel layer      gerenciado pelo channels_redis (~2–3 MB de overhead)
  Total estimado     < 5 MB  (muito abaixo do limite de 50 MB)

Fallback
────────
  Todas as funções verificam disponibilidade do Redis antes de executar.
  Se Redis estiver indisponível (REDIS_URL vazio ou servidor fora do ar),
  o sistema opera em modo degradado transparente:
    - touch/clear de sessão → no-op
    - lock distribuído       → asyncio.Lock em memória (processo único)
"""

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from django.conf import settings

logger = logging.getLogger(__name__)

# ── Constantes ──────────────────────────────────────────────────────────────

SESSION_ACTIVITY_TTL: int = 86_400   # 24 h — deve coincidir com SESSION_INACTIVITY_TIMEOUT
LOCK_TTL_MS: int = 30_000            # 30 s em milissegundos
LOCK_RETRY_INTERVAL: float = 0.05    # 50 ms entre tentativas de aquisição
LOCK_MAX_RETRIES: int = 20           # 20 × 50 ms = 1 s de espera máxima


# ── Helpers de chave ────────────────────────────────────────────────────────

def _key_session_activity(room_code: str) -> str:
    return f"session:activity:{room_code}"


def _key_room_lock(room_code: str) -> str:
    return f"lock:room:{room_code}"


# ── Singleton do cliente ────────────────────────────────────────────────────

_redis_client = None
_redis_available: bool | None = None   # None = ainda não testado


async def get_redis():
    """
    Retorna cliente Redis assíncrono, ou None se Redis estiver indisponível.

    A conexão é verificada com PING na primeira chamada e o resultado é cacheado.
    Se REDIS_URL estiver vazio ou o servidor não responder, retorna None e
    não tenta reconectar (reinício de processo necessário para reativar).
    """
    global _redis_client, _redis_available

    if _redis_client is not None:
        return _redis_client
    if _redis_available is False:
        return None

    redis_url = getattr(settings, 'REDIS_URL', '') or ''
    if not redis_url:
        _redis_available = False
        logger.debug("[Redis] REDIS_URL não configurado — operando sem Redis")
        return None

    try:
        import redis.asyncio as aioredis  # importação tardia para não quebrar se lib ausente

        client = aioredis.from_url(redis_url, decode_responses=True, socket_timeout=2.0)
        await client.ping()
        _redis_client = client
        _redis_available = True
        logger.info("[Redis] Conectado em %s", redis_url)
        return _redis_client
    except Exception as exc:
        _redis_available = False
        logger.warning("[Redis] Indisponível (%s) — operações Redis serão ignoradas", exc)
        return None


def _reset_for_testing() -> None:
    """Reseta o singleton para uso em testes. NÃO usar em produção."""
    global _redis_client, _redis_available
    _redis_client = None
    _redis_available = None


# ── Atividade de sessão ─────────────────────────────────────────────────────

async def touch_session_activity(room_code: str) -> None:
    """
    Registra atividade recente de uma sala no Redis.

    A chave expira automaticamente após SESSION_ACTIVITY_TTL segundos (24 h)
    sem que haja uma nova chamada — o que corresponde à expiração por inatividade
    já tratada pelo banco de dados.

    Chamado a cada save_game_state para manter o TTL atualizado.
    """
    r = await get_redis()
    if r is None:
        return
    try:
        await r.set(_key_session_activity(room_code), str(time.time()), ex=SESSION_ACTIVITY_TTL)
        logger.debug("[Redis] touch_session_activity room=%s", room_code)
    except Exception as exc:
        logger.warning("[Redis] touch_session_activity falhou para %s: %s", room_code, exc)


async def is_session_known_active(room_code: str) -> bool | None:
    """
    Verifica se a sala tem atividade recente registrada no Redis.

    Returns:
        True   — chave existe: sala esteve ativa nas últimas 24 h
        False  — chave ausente: sala pode ter expirado (ou nunca salvou estado)
        None   — Redis indisponível: use fallback no banco de dados
    """
    r = await get_redis()
    if r is None:
        return None
    try:
        return bool(await r.exists(_key_session_activity(room_code)))
    except Exception as exc:
        logger.warning("[Redis] is_session_known_active falhou para %s: %s", room_code, exc)
        return None


async def clear_session_activity(room_code: str) -> None:
    """
    Remove a entrada de atividade de uma sala.

    Útil ao deletar ou expirar uma sala explicitamente.
    Não é obrigatório: a chave expira automaticamente via TTL.
    """
    r = await get_redis()
    if r is None:
        return
    try:
        deleted = await r.delete(_key_session_activity(room_code))
        if deleted:
            logger.info("[Redis] clear_session_activity room=%s", room_code)
    except Exception as exc:
        logger.warning("[Redis] clear_session_activity falhou para %s: %s", room_code, exc)


# ── Lock distribuído ────────────────────────────────────────────────────────

@asynccontextmanager
async def room_lock(
    room_code: str,
    *,
    fallback_locks: dict[str, asyncio.Lock],
) -> AsyncGenerator[None, None]:
    """
    Context manager de lock por sala com fallback automático.

    Modo Redis (quando disponível):
        Usa SET NX PX — lock distribuído que funciona com múltiplos processos
        Daphne/Uvicorn. TTL de 30 s garante liberação automática em caso de
        falha do processo.

    Modo fallback (Redis indisponível):
        Usa asyncio.Lock em memória por room_code. Correto para processo único,
        mas não para múltiplos workers.

    Args:
        room_code:      código da sala a ser protegida
        fallback_locks: dict de locks asyncio (normalmente GameConsumer._room_locks)
    """
    r = await get_redis()
    if r is not None:
        async with _redis_lock(r, room_code):
            yield
    else:
        if room_code not in fallback_locks:
            fallback_locks[room_code] = asyncio.Lock()
        async with fallback_locks[room_code]:
            yield


@asynccontextmanager
async def _redis_lock(r, room_code: str) -> AsyncGenerator[None, None]:
    """Implementação interna do lock usando Redis SET NX PX."""
    key = _key_room_lock(room_code)
    token = str(uuid.uuid4())
    acquired = False

    for _ in range(LOCK_MAX_RETRIES):
        if await r.set(key, token, nx=True, px=LOCK_TTL_MS):
            acquired = True
            break
        await asyncio.sleep(LOCK_RETRY_INTERVAL)

    if not acquired:
        # Força aquisição para evitar deadlock deixado por processo que morreu
        # sem liberar o lock. O token anterior expirou em ≤ 30 s via TTL.
        logger.warning(
            "[Redis] Timeout ao aguardar lock para sala %s — forçando aquisição", room_code
        )
        await r.set(key, token, px=LOCK_TTL_MS)

    try:
        yield
    finally:
        try:
            # Libera apenas se ainda somos donos do token (previne liberar lock de outro processo)
            if await r.get(key) == token:
                await r.delete(key)
                logger.debug("[Redis] Lock liberado para sala %s", room_code)
        except Exception as exc:
            logger.warning("[Redis] Falha ao liberar lock para sala %s: %s", room_code, exc)
