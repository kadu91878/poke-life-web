"""
Modelo formal da carta física de Pokémon.

Fonte de dados: backend/cards_metadata.json
Campos espelham exatamente o schema do JSON, sem inferência visual das imagens.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Constantes de ability_type ─────────────────────────────────────────────
ABILITY_ACTIVE = "active"
ABILITY_PASSIVE = "passive"
ABILITY_BATTLE = "battle"
ABILITY_NONE = "none"

VALID_ABILITY_TYPES = {ABILITY_ACTIVE, ABILITY_PASSIVE, ABILITY_BATTLE, ABILITY_NONE, None}

# Prefixo público das imagens servidas pelo frontend
CARD_IMAGE_BASE_URL = "/assets/pokemon/"
PROJECT_ROOT = Path(__file__).resolve().parents[3]
PUBLIC_POKEMON_IMAGE_DIR = PROJECT_ROOT / "frontend" / "public" / "assets" / "pokemon"


@dataclass
class PhysicalCard:
    """
    Representa uma carta física do jogo Pokémon Life conforme o cards_metadata.json.

    Esta classe é separada de PokemonCard (engine/models.py):
    - PhysicalCard = catálogo de cartas físicas (display, regras, evolução)
    - PokemonCard  = representação em-jogo usada pelo engine de batalha

    Campos de identidade:
      id           — string única (ex: 'bulbasaur') — chave principal
      real_name    — nome canônico de exibição (ex: 'Bulbasaur')

    Campos de exibição:
      reference_image — nome do arquivo de imagem (ex: 'bulbasaur.png')
      image_url       — URL resolvida para o frontend (/assets/pokemon/bulbasaur.png)
      power           — Pontos de Batalha (pode ser None para Pokémon sem combate)
      points          — Master Points concedidos ao capturar

    Campos de habilidade:
      ability_type        — 'active' | 'passive' | 'battle' | 'none' | None
      ability_description — texto descritivo da habilidade
      charges             — número de cargas (None = ilimitado)

    Campos de evolução:
      evolves     — True se a carta pode evoluir
      evolves_to  — real_name do Pokémon evoluído (ex: 'Ivysaur'), ou None

    Metadados extras:
      notes       — observações da carta (ex: anomalias visuais)
      is_initial  — True se é um Pokémon inicial selecionável
    """

    # Identidade
    id: str
    real_name: str

    # Imagem
    reference_image: str
    image_url: Optional[str]  # resolvido em from_dict()

    # Estatísticas
    power: Optional[int]           # None = não batalha (ex: Celebi)
    points: int                    # Master Points

    # Habilidade
    ability_type: Optional[str]
    ability_description: Optional[str]
    charges: Optional[int]         # None = ilimitado

    # Evolução
    evolves: bool
    evolves_to: Optional[str]      # real_name do alvo, ou None

    # Metadados
    notes: Optional[str]
    is_initial: Optional[bool]

    # ── Factories ──────────────────────────────────────────────────────────

    @classmethod
    def from_dict(cls, data: dict) -> "PhysicalCard":
        """Constrói um PhysicalCard a partir de um dict do cards_metadata.json."""
        ref_img = data.get("reference_image") or f"{data['id']}.png"
        explicit_image_url = data.get("image_path")
        if explicit_image_url:
            image_url = explicit_image_url
        elif ref_img and (PUBLIC_POKEMON_IMAGE_DIR / ref_img).exists():
            image_url = CARD_IMAGE_BASE_URL + ref_img
        else:
            image_url = None
        return cls(
            id=data["id"],
            real_name=data.get("real_name") or data["id"].capitalize(),
            reference_image=ref_img,
            image_url=image_url,
            power=data.get("power"),
            points=data.get("points", 0),
            ability_type=data.get("ability_type"),
            ability_description=data.get("ability_description"),
            charges=data.get("charges"),
            evolves=bool(data.get("evolves", False)),
            evolves_to=data.get("evolves_to"),
            notes=data.get("notes"),
            is_initial=data.get("is_initial"),
        )

    # ── Serialização ───────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serializa para dict compatível com resposta JSON da API."""
        return {
            "id": self.id,
            "real_name": self.real_name,
            "reference_image": self.reference_image,
            "image_url": self.image_url,
            "power": self.power,
            "points": self.points,
            "ability_type": self.ability_type,
            "ability_description": self.ability_description,
            "charges": self.charges,
            "evolves": self.evolves,
            "evolves_to": self.evolves_to,
            "notes": self.notes,
            "is_initial": self.is_initial,
        }

    # ── Helpers de domínio ─────────────────────────────────────────────────

    def can_battle(self) -> bool:
        """Retorna True se a carta tem poder de batalha definido."""
        return self.power is not None

    def can_evolve(self) -> bool:
        """Retorna True se a carta pode evoluir."""
        return self.evolves and self.evolves_to is not None

    def has_charges(self) -> bool:
        """Retorna True se a habilidade usa cargas limitadas."""
        return self.charges is not None

    def is_active_ability(self) -> bool:
        return self.ability_type == ABILITY_ACTIVE

    def is_passive_ability(self) -> bool:
        return self.ability_type == ABILITY_PASSIVE

    def is_battle_ability(self) -> bool:
        return self.ability_type == ABILITY_BATTLE

    def __repr__(self) -> str:
        return f"<PhysicalCard id={self.id!r} name={self.real_name!r} power={self.power}>"
