/**
 * Tipos e constantes para cartas de Pokémon no frontend.
 *
 * Espelha o contrato definido em backend/game/engine/models.py (PokemonCard)
 * e o runtime gerado a partir de backend/cards_metadata.json.
 */

/** @enum {string} */
export const AbilityType = {
  PASSIVE: 'passive',   // sempre ativa, sem custo
  ACTIVE: 'active',     // ativada pelo jogador no turno
  BATTLE: 'battle',     // efeito automático em batalha
  NONE: 'none',
}

/** @enum {string} */
export const Rarity = {
  COMMON: 'common',
  UNCOMMON: 'uncommon',
  RARE: 'rare',
  EPIC: 'epic',
  LEGENDARY: 'legendary',
}

/**
 * @typedef {Object} PokemonCard
 * @property {number}      id                  - ID nacional da Pokédex
 * @property {string}      name                - Nome do Pokémon
 * @property {string[]}    types               - Tipos (ex: ['Fire', 'Flying'])
 * @property {number}      battle_points       - Pontos de batalha (BP)
 * @property {number}      master_points       - Master Points concedidos ao capturar
 * @property {string}      ability             - Nome da habilidade
 * @property {string}      ability_description - Descrição da habilidade
 * @property {AbilityType} ability_type        - Tipo da habilidade
 * @property {string|null} battle_effect       - Tag de efeito de batalha (ex: 'critical_hit')
 * @property {number|null} ability_charges     - Usos disponíveis (null = ilimitado)
 * @property {number|null} evolves_to          - ID do Pokémon evoluído (null = não evolui)
 * @property {boolean}     is_starter          - É um Pokémon inicial
 * @property {boolean}     is_legendary        - É um Pokémon lendário
 * @property {boolean}     is_baby             - É um baby Pokémon
 * @property {Rarity}      rarity              - Raridade da carta
 * @property {string|null} image_path          - URL relativa da imagem (ex: /assets/pokemon/pikachu.png)
 * @property {boolean}     [ability_used]      - Estado de runtime: habilidade já usada no turno
 */

/**
 * Retorna true se o Pokémon pode evoluir.
 * @param {PokemonCard} card
 * @returns {boolean}
 */
export function canEvolve(card) {
  return card.evolves_to != null
}

/**
 * Retorna a URL da imagem da carta ou null se não disponível.
 * @param {PokemonCard} card
 * @returns {string|null}
 */
export function getCardImageUrl(card) {
  return card.image_path ?? null
}

/**
 * Retorna true se a habilidade é do tipo ativa (acionada pelo jogador).
 * @param {PokemonCard} card
 * @returns {boolean}
 */
export function isActiveAbility(card) {
  return card.ability_type === AbilityType.ACTIVE
}

/**
 * Retorna true se a habilidade é passiva (sempre ativa).
 * @param {PokemonCard} card
 * @returns {boolean}
 */
export function isPassiveAbility(card) {
  return card.ability_type === AbilityType.PASSIVE
}

/**
 * Retorna true se a habilidade tem efeito automático em batalha.
 * @param {PokemonCard} card
 * @returns {boolean}
 */
export function isBattleAbility(card) {
  return card.ability_type === AbilityType.BATTLE && card.battle_effect != null
}
