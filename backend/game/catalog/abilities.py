"""
Engine de habilidades das cartas físicas.

Arquitetura:
  - AbilityTrigger  — enum dos momentos em que habilidades podem disparar
  - AbilityEffect   — descritor de um efeito (chave + parâmetros)
  - AbilityConfig   — configuração completa de habilidade de uma carta
  - ABILITY_REGISTRY — mapeamento card_id → AbilityConfig
  - AbilityEngine   — ponto de entrada para disparar habilidades

Princípio fundamental:
  NÃO tente executar ability_description como texto livre.
  O mapeamento card_id → effect_key é a fonte de verdade para regras.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional


# ── Gatilhos de jogo ────────────────────────────────────────────────────────

class AbilityTrigger(str, Enum):
    """Momentos em que habilidades podem ser verificadas/disparadas."""

    # Movimento
    ON_MOVE_ROLL          = "on_move_roll"           # dado de movimento rolado
    ON_MOVE_RESOLVED      = "on_move_resolved"       # movimento concluído

    # Batalha
    ON_BATTLE_START       = "on_battle_start"        # início de duelo
    ON_BATTLE_SCORE       = "on_battle_score"        # cálculo de score
    ON_BATTLE_END         = "on_battle_end"          # resultado definido

    # Turno
    ON_TURN_START         = "on_turn_start"          # início do turno do jogador
    ON_TURN_END           = "on_turn_end"            # fim do turno

    # Time/equipe
    ON_TEAM_CAPACITY_CHECK = "on_team_capacity_check" # verificação de slots
    ON_CAPTURE            = "on_capture"             # Pokémon capturado

    # Evolução
    ON_EVOLUTION_CHECK    = "on_evolution_check"     # verificação de evolução
    ON_EVOLUTION_APPLY    = "on_evolution_apply"     # evolução executada

    # Evento
    ON_EVENT_TILE         = "on_event_tile"          # carta de evento sacada

    # Batalha: modificadores de dado do oponente
    ON_OPPONENT_ROLL      = "on_opponent_roll"       # dado do oponente rolado


# ── Chaves de efeito ────────────────────────────────────────────────────────

class EffectKey(str, Enum):
    """
    Chave interna de efeito. Cada chave tem um handler registrado no engine.

    Nomenclatura: verbos no infinitivo descrevendo o que o efeito FAZ.
    """

    # Movimento
    REROLL_MOVE           = "reroll_move"            # rolar o dado de movimento novamente
    MOVE_ADJUST           = "move_adjust"            # ajustar casas (+/-)
    MOVE_HALVE            = "move_halve"             # dividir movimento por 2

    # Batalha
    SCORE_CRITICAL        = "score_critical"         # dado extra, usa maior
    SCORE_BONUS_BP        = "score_bonus_bp"         # +N BP no cálculo
    SCORE_FLAT_BONUS      = "score_flat_bonus"       # +N flat ao score final
    OPPONENT_MINUS_ROLL   = "opponent_minus_roll"    # dado oponente -N
    OPPONENT_MINUS_BP     = "opponent_minus_bp"      # BP oponente -N
    OPPONENT_REROLL_MIN   = "opponent_reroll_min"    # oponente rola 2x, usa menor
    TEAM_BP_BOOST         = "team_bp_boost"          # +N BP para todos do time

    # Recursos
    GAIN_POKEMON_FROM_AREA = "gain_pokemon_from_area"  # pegar Pokémon da área
    HEAL_TEAM_MEMBER      = "heal_team_member"       # curar membro do time

    # Evento
    DRAW_TWO_EVENTS       = "draw_two_events"        # sacar 2 cartas de evento, escolher 1

    # Especiais
    CANNOT_BATTLE         = "cannot_battle"          # esta carta não pode batalhar
    OCCUPIES_EXTRA_SLOT   = "occupies_extra_slot"    # ocupa 2 slots do time
    NO_EVOLVE_OUTSIDE_CONDITION = "no_evolve_outside_condition"  # evolução condicional

    # Passivos genéricos (sem efeito automático implementado ainda)
    PASSIVE_GENERIC       = "passive_generic"


# ── Estruturas de dados ─────────────────────────────────────────────────────

@dataclass
class AbilityEffect:
    """
    Descriptor de um efeito concreto.

    key     — identifica o handler a chamar
    params  — parâmetros livres para o handler (ex: {'bonus': 2, 'condition': '4_or_6'})
    """
    key: EffectKey
    params: dict[str, Any] = field(default_factory=dict)

    def __repr__(self) -> str:
        return f"<Effect {self.key.value} {self.params}>"


@dataclass
class AbilityConfig:
    """
    Configuração completa de habilidade de uma carta.

    card_id  — corresponde ao PhysicalCard.id
    trigger  — quando a habilidade pode disparar
    effects  — lista de efeitos a aplicar (ordem importa)
    is_active — True = jogador ativa manualmente; False = automático/passivo
    charges  — cargas disponíveis (None = ilimitado)
    condition — texto livre opcional descrevendo pré-condição (documentação)
    """
    card_id: str
    trigger: AbilityTrigger
    effects: list[AbilityEffect]
    is_active: bool = True
    charges: Optional[int] = None
    condition: Optional[str] = None


# ── Registro de habilidades ──────────────────────────────────────────────────
#
# Mapeamento explícito card_id → AbilityConfig.
# NÃO derivado de ability_description — aqui ficam as regras implementadas.
#
# Padrão de adição:
#   "card_id": AbilityConfig(
#       card_id="card_id",
#       trigger=AbilityTrigger.TRIGGER,
#       effects=[AbilityEffect(EffectKey.EFFECT, params={...})],
#       is_active=True/False,
#       charges=N ou None,
#       condition="descrição opcional da condição",
#   ),

ABILITY_REGISTRY: dict[str, AbilityConfig] = {

    # ── Geração 1 — Iniciais e evoluções ─────────────────────────────────

    "bulbasaur": AbilityConfig(
        card_id="bulbasaur",
        trigger=AbilityTrigger.ON_MOVE_RESOLVED,
        effects=[AbilityEffect(EffectKey.MOVE_HALVE, {"condition": "roll_is_4_or_6"})],
        is_active=True,
        condition="Se o resultado do dado for 4 ou 6, pode dividir por 2",
    ),
    "ivysaur": AbilityConfig(
        card_id="ivysaur",
        trigger=AbilityTrigger.ON_MOVE_RESOLVED,
        effects=[AbilityEffect(EffectKey.MOVE_HALVE, {"condition": "roll_is_4_or_6"})],
        is_active=True,
        condition="Herda habilidade do Bulbasaur",
    ),
    "venusaur": AbilityConfig(
        card_id="venusaur",
        trigger=AbilityTrigger.ON_MOVE_RESOLVED,
        effects=[AbilityEffect(EffectKey.MOVE_HALVE, {"condition": "roll_is_4_or_6"})],
        is_active=True,
        condition="Herda habilidade do Bulbasaur",
    ),

    "charmander": AbilityConfig(
        card_id="charmander",
        trigger=AbilityTrigger.ON_MOVE_RESOLVED,
        effects=[
            AbilityEffect(EffectKey.MOVE_ADJUST, {"delta": +1, "condition": "roll_is_1_or_3"}),
            AbilityEffect(EffectKey.MOVE_ADJUST, {"delta": -1, "condition": "roll_is_4_or_6"}),
        ],
        is_active=True,
        condition="Resultado 1/3: +1 casa; resultado 4/6: -1 casa",
    ),
    "charmeleon": AbilityConfig(
        card_id="charmeleon",
        trigger=AbilityTrigger.ON_MOVE_RESOLVED,
        effects=[
            AbilityEffect(EffectKey.MOVE_ADJUST, {"delta": +1, "condition": "roll_is_1_or_3"}),
            AbilityEffect(EffectKey.MOVE_ADJUST, {"delta": -1, "condition": "roll_is_4_or_6"}),
        ],
        is_active=True,
    ),
    "charizard": AbilityConfig(
        card_id="charizard",
        trigger=AbilityTrigger.ON_MOVE_RESOLVED,
        effects=[
            AbilityEffect(EffectKey.MOVE_ADJUST, {"delta": +1, "condition": "roll_is_1_or_3"}),
            AbilityEffect(EffectKey.MOVE_ADJUST, {"delta": -1, "condition": "roll_is_4_or_6"}),
        ],
        is_active=True,
    ),

    "squirtle": AbilityConfig(
        card_id="squirtle",
        trigger=AbilityTrigger.ON_MOVE_ROLL,
        effects=[AbilityEffect(EffectKey.REROLL_MOVE, {"max_uses_per_turn": 1})],
        is_active=True,
        condition="Pode rolar o dado de movimento novamente uma vez por turno",
    ),
    "wartortle": AbilityConfig(
        card_id="wartortle",
        trigger=AbilityTrigger.ON_MOVE_ROLL,
        effects=[AbilityEffect(EffectKey.REROLL_MOVE, {"max_uses_per_turn": 1})],
        is_active=True,
    ),
    "blastoise": AbilityConfig(
        card_id="blastoise",
        trigger=AbilityTrigger.ON_MOVE_ROLL,
        effects=[AbilityEffect(EffectKey.REROLL_MOVE, {"max_uses_per_turn": 1})],
        is_active=True,
    ),

    # ── Habilidades de evento ─────────────────────────────────────────────

    "articuno": AbilityConfig(
        card_id="articuno",
        trigger=AbilityTrigger.ON_EVENT_TILE,
        effects=[AbilityEffect(EffectKey.DRAW_TWO_EVENTS, {})],
        is_active=True,
        condition="Ao cair em tile de evento, saca 2 cartas e escolhe qual executar",
    ),

    # ── Habilidades de time ───────────────────────────────────────────────

    "celebi": AbilityConfig(
        card_id="celebi",
        trigger=AbilityTrigger.ON_BATTLE_SCORE,
        effects=[
            AbilityEffect(EffectKey.TEAM_BP_BOOST, {"bonus": 2}),
            AbilityEffect(EffectKey.CANNOT_BATTLE, {}),
        ],
        is_active=False,  # passivo
        condition="Bônus passivo de +2 BP para todo o time; Celebi não pode batalhar",
    ),

    # ── Captura e área ────────────────────────────────────────────────────

    "aerodactyl": AbilityConfig(
        card_id="aerodactyl",
        trigger=AbilityTrigger.ON_CAPTURE,
        effects=[AbilityEffect(EffectKey.GAIN_POKEMON_FROM_AREA, {"exclude_legendary": True, "exclude_self": True})],
        is_active=True,
        charges=1,
        condition="Receber Pokémon da área atual (sem Lendários ou Aerodactyl). Uma carga.",
    ),

    # ── Cura ──────────────────────────────────────────────────────────────

    "chansey": AbilityConfig(
        card_id="chansey",
        trigger=AbilityTrigger.ON_TURN_START,
        effects=[AbilityEffect(EffectKey.HEAL_TEAM_MEMBER, {"target": "other_pokemon"})],
        is_active=True,
        condition="Uma vez por turno (fora de batalha), curar outro Pokémon do time",
    ),
    "blissey": AbilityConfig(
        card_id="blissey",
        trigger=AbilityTrigger.ON_TURN_START,
        effects=[AbilityEffect(EffectKey.HEAL_TEAM_MEMBER, {"target": "other_pokemon"})],
        is_active=True,
    ),
}


# ── Engine de habilidades ────────────────────────────────────────────────────

# Tipo de handler: recebe (card_id, effect, context) e retorna dict com modificações
HandlerFn = Callable[[str, AbilityEffect, dict], dict]

_HANDLERS: dict[EffectKey, HandlerFn] = {}


def register_handler(key: EffectKey) -> Callable[[HandlerFn], HandlerFn]:
    """Decorator para registrar handlers de efeito."""
    def decorator(fn: HandlerFn) -> HandlerFn:
        _HANDLERS[key] = fn
        return fn
    return decorator


class AbilityEngine:
    """
    Ponto central de disparo de habilidades.

    Uso:
        engine = AbilityEngine()
        results = engine.trigger(
            trigger=AbilityTrigger.ON_MOVE_ROLL,
            card_ids=["blastoise"],
            context={"dice_result": 3, "player_id": "..."},
        )

    O contexto é passado como dict mutável — handlers podem inserir
    chaves de resposta (ex: {"rerolled": True, "new_roll": 5}).
    """

    def trigger(
        self,
        trigger: AbilityTrigger,
        card_ids: list[str],
        context: dict,
    ) -> dict:
        """
        Dispara todas as habilidades dos card_ids que respondem ao trigger.

        Retorna o contexto modificado pelos handlers (ou context inalterado
        se nenhum handler modificar nada).
        """
        result = dict(context)
        for card_id in card_ids:
            config = ABILITY_REGISTRY.get(card_id)
            if config is None or config.trigger != trigger:
                continue
            for effect in config.effects:
                handler = _HANDLERS.get(effect.key)
                if handler is not None:
                    result = handler(card_id, effect, result)
        return result

    def get_config(self, card_id: str) -> Optional[AbilityConfig]:
        """Retorna a configuração de habilidade de um card, ou None."""
        return ABILITY_REGISTRY.get(card_id)

    def has_trigger(self, card_id: str, trigger: AbilityTrigger) -> bool:
        """Verifica se um card responde a um trigger específico."""
        config = ABILITY_REGISTRY.get(card_id)
        return config is not None and config.trigger == trigger

    def cards_with_trigger(self, trigger: AbilityTrigger) -> list[str]:
        """Lista todos os card_ids que respondem a um trigger."""
        return [cid for cid, cfg in ABILITY_REGISTRY.items() if cfg.trigger == trigger]


# ── Handlers implementados ────────────────────────────────────────────────────
#
# Cada handler recebe (card_id, effect, context) e retorna context modificado.
# Context é tratado como dict imutável na chamada — retorne sempre uma nova cópia.

@register_handler(EffectKey.REROLL_MOVE)
def _handle_reroll_move(card_id: str, effect: AbilityEffect, ctx: dict) -> dict:
    """Marca no contexto que o reroll de movimento está disponível."""
    return {**ctx, "reroll_move_available": True, "reroll_source": card_id}


@register_handler(EffectKey.CANNOT_BATTLE)
def _handle_cannot_battle(card_id: str, effect: AbilityEffect, ctx: dict) -> dict:
    """Marca que esta carta não pode batalhar."""
    cannot = set(ctx.get("cannot_battle_ids", []))
    cannot.add(card_id)
    return {**ctx, "cannot_battle_ids": list(cannot)}


@register_handler(EffectKey.TEAM_BP_BOOST)
def _handle_team_bp_boost(card_id: str, effect: AbilityEffect, ctx: dict) -> dict:
    """Acumula bônus de BP para o time."""
    bonus = effect.params.get("bonus", 0)
    current = ctx.get("team_bp_bonus", 0)
    return {**ctx, "team_bp_bonus": current + bonus, "team_bp_bonus_source": card_id}


@register_handler(EffectKey.DRAW_TWO_EVENTS)
def _handle_draw_two_events(card_id: str, effect: AbilityEffect, ctx: dict) -> dict:
    """Indica que o jogador deve sacar 2 cartas de evento e escolher 1."""
    return {**ctx, "draw_two_events": True, "draw_two_events_source": card_id}


@register_handler(EffectKey.GAIN_POKEMON_FROM_AREA)
def _handle_gain_pokemon(card_id: str, effect: AbilityEffect, ctx: dict) -> dict:
    """Sinaliza que o jogador ganha um Pokémon da área atual."""
    return {
        **ctx,
        "gain_pokemon_from_area": True,
        "gain_pokemon_exclude_legendary": effect.params.get("exclude_legendary", True),
        "gain_pokemon_exclude_self": effect.params.get("exclude_self", True),
        "gain_pokemon_source": card_id,
    }


@register_handler(EffectKey.HEAL_TEAM_MEMBER)
def _handle_heal_team(card_id: str, effect: AbilityEffect, ctx: dict) -> dict:
    """Sinaliza que o jogador pode curar um membro do time."""
    return {**ctx, "heal_team_member_available": True, "heal_source": card_id}


# ── Instância global ────────────────────────────────────────────────────────
ability_engine = AbilityEngine()
