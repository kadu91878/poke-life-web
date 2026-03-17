"""
Repositório de cartas físicas de Pokémon.

Carrega cards_metadata.json uma única vez e mantém índices para
consulta eficiente por id, real_name e reference_image.

Uso:
    from game.catalog.repository import card_repo

    card = card_repo.get_by_id("bulbasaur")
    evo  = card_repo.get_evolution(card)
    all_cards = card_repo.all()
"""
from __future__ import annotations

import json
import os
from typing import Optional

from .card_model import PhysicalCard

# Caminho do JSON relativo a este arquivo
_METADATA_PATH = os.path.join(
    os.path.dirname(__file__),   # .../game/catalog/
    "..",                         # .../game/
    "..",                         # .../backend/ (app root inside backend/)
    "cards_metadata.json",
)


class CardRepository:
    """
    Repositório singleton de cartas físicas.

    Índices mantidos:
      _by_id    — { card.id          → PhysicalCard }
      _by_name  — { lower(real_name) → PhysicalCard }
      _by_image — { reference_image  → PhysicalCard }
    """

    def __init__(self, metadata_path: str = _METADATA_PATH):
        self._path = os.path.abspath(metadata_path)
        self._cards: list[PhysicalCard] = []
        self._by_id: dict[str, PhysicalCard] = {}
        self._by_name: dict[str, PhysicalCard] = {}
        self._by_image: dict[str, PhysicalCard] = {}
        self._loaded = False

    # ── Carregamento ───────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with open(self._path, encoding="utf-8") as f:
            data = json.load(f)

        for raw in data.get("cards", []):
            card = PhysicalCard.from_dict(raw)
            self._cards.append(card)
            self._by_id[card.id] = card
            self._by_name[card.real_name.lower()] = card
            self._by_image[card.reference_image] = card

        self._loaded = True

    def reload(self) -> None:
        """Força o recarregamento do JSON (útil em testes ou hot-reload)."""
        self._cards.clear()
        self._by_id.clear()
        self._by_name.clear()
        self._by_image.clear()
        self._loaded = False
        self._ensure_loaded()

    # ── Consultas ──────────────────────────────────────────────────────────

    def all(self) -> list[PhysicalCard]:
        """Retorna todas as cartas em ordem de carregamento."""
        self._ensure_loaded()
        return list(self._cards)

    def get_by_id(self, card_id: str) -> Optional[PhysicalCard]:
        """Busca carta pelo id (ex: 'bulbasaur')."""
        self._ensure_loaded()
        return self._by_id.get(card_id)

    def get_by_name(self, name: str) -> Optional[PhysicalCard]:
        """Busca carta pelo real_name, case-insensitive (ex: 'Bulbasaur')."""
        self._ensure_loaded()
        return self._by_name.get(name.lower())

    def get_by_image(self, filename: str) -> Optional[PhysicalCard]:
        """Busca carta pelo nome do arquivo de imagem (ex: 'bulbasaur.png')."""
        self._ensure_loaded()
        return self._by_image.get(filename)

    def get_evolution(self, card: PhysicalCard) -> Optional[PhysicalCard]:
        """
        Retorna a carta de evolução de `card`, ou None se não evoluir.

        Resolução: busca por real_name (evolves_to) e, se não encontrar,
        tenta busca por id normalizado.
        """
        if not card.can_evolve():
            return None
        target = card.evolves_to  # real_name do alvo
        result = self.get_by_name(target)
        if result is None:
            # fallback: tenta id normalizado (ex: "Ivysaur" → "ivysaur")
            result = self.get_by_id(target.lower())
        return result

    def filter(
        self,
        *,
        ability_type: Optional[str] = None,
        can_battle: Optional[bool] = None,
        can_evolve: Optional[bool] = None,
        is_initial: Optional[bool] = None,
    ) -> list[PhysicalCard]:
        """
        Filtra cartas por critérios opcionais.

        Exemplos:
            repo.filter(is_initial=True)          # apenas iniciais
            repo.filter(can_evolve=True)          # com evolução
            repo.filter(ability_type='active')    # habilidades ativas
            repo.filter(can_battle=False)         # sem poder de batalha
        """
        self._ensure_loaded()
        cards = self._cards

        if ability_type is not None:
            cards = [c for c in cards if c.ability_type == ability_type]
        if can_battle is not None:
            cards = [c for c in cards if c.can_battle() == can_battle]
        if can_evolve is not None:
            cards = [c for c in cards if c.can_evolve() == can_evolve]
        if is_initial is not None:
            cards = [c for c in cards if bool(c.is_initial) == is_initial]

        return list(cards)

    def count(self) -> int:
        self._ensure_loaded()
        return len(self._cards)

    def __repr__(self) -> str:
        status = f"{len(self._cards)} cards" if self._loaded else "not loaded"
        return f"<CardRepository {status} from {self._path}>"


# ── Instância global (lazy-loaded) ─────────────────────────────────────────
card_repo = CardRepository()
