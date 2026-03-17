"""
Modelos formais para as entidades do jogo Pokémon Life.

Usa dataclasses para validação e documentação dos campos obrigatórios.
O JSON do estado continua sendo dict puro — esses modelos servem como
contratos explícitos e utilitários de validação/construção.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


# ── Tipos de habilidade ──────────────────────────────────────────────────────
ABILITY_TYPE_PASSIVE = 'passive'   # sempre ativa, sem custo
ABILITY_TYPE_ACTIVE = 'active'     # ativada pelo jogador no turno
ABILITY_TYPE_BATTLE = 'battle'     # efeito automático durante batalha

# ── Efeitos de batalha válidos ────────────────────────────────────────────────
# Efeitos que modificam o cálculo de score
SCORE_EFFECTS = frozenset({
    'critical_hit',     # rola dado extra, usa maior
    'earthquake',       # +1x BP de bônus
    'swift',            # +2 flat ao score
    'shadow_ball',      # critical_hit + pós-batalha: perdedor perde 1 FR
    'flame_body',       # earthquake + pós-batalha: perdedor perde 1 FR
    'static_zapdos',    # critical_hit com 2 dados extras
    'multiscale',       # earthquake + ignora habilidades do oponente
    'solar_beam',       # +3 BP de bônus (ativado pelo jogador)
})

# Efeitos que modificam o dado/BP do OPONENTE antes do cálculo
PRE_BATTLE_EFFECTS = frozenset({
    'intimidate',       # oponente: dado -1 (mín 1)
    'thick_fat',        # oponente: BP -2 (mín 1)
    'pressure',         # oponente: re-rola dado, usa menor
    'pressure_max',     # oponente: dado = 1 sempre
    'cute_charm_battle',# oponente: usa menor de 2 rolls
    'transform',        # copia BP do oponente
})

# Efeitos aplicados depois da batalha (vencedor aplica sobre perdedor)
POST_BATTLE_WINNER_EFFECTS = frozenset({
    'poison_sting',     # perdedor perde 1 Full Restore
    'shadow_ball',      # perdedor perde 1 Full Restore
    'flame_body',       # perdedor perde 1 Full Restore
    'super_fang',       # vencedor rouba 1 Pokébola do perdedor
    'curse',            # perdedor perde 5 Master Points extras
    'shed_skin',        # vencedor recupera 1 Full Restore
    'dynamic_punch',    # perdedor perde 1 item aleatório (quando itens forem implementados)
    'wing_attack',      # vencedor avança 1 casa extra (pendente: movimento pós-batalha)
    'hyper_voice',      # perdedor recua 2 casas (pendente: movimento pós-batalha)
})

# Conjunto completo de battle_effects válidos
ALL_BATTLE_EFFECTS = SCORE_EFFECTS | PRE_BATTLE_EFFECTS | POST_BATTLE_WINNER_EFFECTS | {
    'synchronize',      # copia habilidade do oponente (pendente)
}


@dataclass
class PokemonCard:
    """
    Representação formal de uma carta de Pokémon.

    Campos obrigatórios refletem o contrato mínimo das regras oficiais:
    - name, types, battle_points, master_points
    - ability e metadados de habilidade
    - cadeia evolutiva e flags de categoria
    """
    # Identificação
    id: int
    name: str
    types: list[str]

    # Estatísticas de batalha e pontuação
    battle_points: int
    master_points: int

    # Habilidade
    ability: str
    ability_description: str
    ability_type: str                          # 'passive' | 'active' | 'battle'
    battle_effect: Optional[str] = None        # tag de efeito de batalha
    ability_charges: Optional[int] = None      # None = sem limite específico

    # Cadeia evolutiva
    evolves_to: Optional[int] = None          # ID do Pokémon evoluído
    is_starter: bool = False
    is_legendary: bool = False
    is_baby: bool = False                      # baby Pokémon podem recusar evolução

    # Metadados de raridade
    rarity: str = 'common'

    # Imagem da carta (URL relativa ao frontend, ex: /assets/pokemon/pikachu.png)
    image_path: Optional[str] = None

    # Estado de rastreamento (adicionado em runtime, não presente no JSON original)
    ability_used: bool = field(default=False, repr=False)

    @classmethod
    def from_dict(cls, data: dict) -> 'PokemonCard':
        """Constrói um PokemonCard a partir de um dict (ex: JSON carregado)."""
        return cls(
            id=data['id'],
            name=data['name'],
            types=data.get('types', []),
            battle_points=data.get('battle_points', 1),
            master_points=data.get('master_points', 0),
            ability=data.get('ability', 'none'),
            ability_description=data.get('ability_description', ''),
            ability_type=data.get('ability_type', 'passive'),
            battle_effect=data.get('battle_effect'),
            ability_charges=data.get('ability_charges'),
            evolves_to=data.get('evolves_to'),
            is_starter=data.get('is_starter', False),
            is_legendary=data.get('is_legendary', False),
            is_baby=data.get('is_baby', False),
            rarity=data.get('rarity', 'common'),
            image_path=data.get('image_path'),
            ability_used=data.get('ability_used', False),
        )

    def to_dict(self) -> dict:
        """Serializa para dict compatível com o estado JSON do jogo."""
        return asdict(self)

    def can_evolve(self) -> bool:
        """Verifica se o Pokémon pode evoluir."""
        return self.evolves_to is not None

    def is_active_ability(self) -> bool:
        """Habilidade que o jogador ativa explicitamente."""
        return self.ability_type == ABILITY_TYPE_ACTIVE

    def is_passive_ability(self) -> bool:
        """Habilidade sempre ativa (não requer ação)."""
        return self.ability_type == ABILITY_TYPE_PASSIVE

    def is_battle_ability(self) -> bool:
        """Habilidade com efeito automático em batalha."""
        return self.ability_type == ABILITY_TYPE_BATTLE and self.battle_effect is not None

    def validate(self) -> list[str]:
        """
        Valida campos obrigatórios e retorna lista de erros.
        Retorna lista vazia se válido.
        """
        errors = []
        if not self.name:
            errors.append('name é obrigatório')
        if self.battle_points < 1:
            errors.append('battle_points deve ser >= 1')
        if self.master_points < 0:
            errors.append('master_points deve ser >= 0')
        if self.ability_type not in (ABILITY_TYPE_PASSIVE, ABILITY_TYPE_ACTIVE, ABILITY_TYPE_BATTLE, 'none'):
            errors.append(f'ability_type inválido: {self.ability_type}')
        if self.battle_effect and self.battle_effect not in ALL_BATTLE_EFFECTS:
            errors.append(f'battle_effect desconhecido: {self.battle_effect}')
        return errors


@dataclass
class EventCard:
    """Representação formal de uma carta de Evento."""
    id: int
    title: str
    description: str
    effect: dict  # {'type': str, ...}

    @classmethod
    def from_dict(cls, data: dict) -> 'EventCard':
        return cls(
            id=data['id'],
            title=data.get('title', ''),
            description=data.get('description', ''),
            effect=data.get('effect', {'type': 'none'}),
        )

    @property
    def effect_type(self) -> str:
        return self.effect.get('type', 'none')

    def is_negative(self) -> bool:
        """Eventos negativos que Run Away pode bloquear."""
        return self.effect_type in {
            'lose_pokeball', 'lose_full_restore', 'lose_master_points',
            'move_backward', 'teleport_start',
        }


@dataclass
class ItemCard:
    """
    Representação formal de um Item.

    Sistema de itens ainda não implementado — esta classe documenta
    o contrato esperado para implementação futura.
    """
    id: int
    name: str
    description: str
    effect_type: str    # 'passive' | 'active' | 'consumable'
    effect: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> 'ItemCard':
        return cls(
            id=data['id'],
            name=data['name'],
            description=data.get('description', ''),
            effect_type=data.get('effect_type', 'consumable'),
            effect=data.get('effect', {}),
        )


@dataclass
class VictoryCard:
    """
    Representação formal de uma carta de Vitória (Victory Pile).

    Victory Pile ainda não implementado — esta classe documenta
    o contrato esperado para implementação futura.
    """
    id: int
    title: str
    description: str
    points: int         # Master Points concedidos
    condition: str      # trigger de conquista (ex: 'capture_legendary', 'win_duel')

    @classmethod
    def from_dict(cls, data: dict) -> 'VictoryCard':
        return cls(
            id=data['id'],
            title=data['title'],
            description=data.get('description', ''),
            points=data.get('points', 0),
            condition=data.get('condition', ''),
        )
