/**
 * Tipos e utilitários para o catálogo de cartas físicas.
 *
 * Espelha o schema de backend/cards_metadata.json e o modelo
 * PhysicalCard definido em backend/game/catalog/card_model.py.
 *
 * Separado de types/pokemon.js (que espelha PokemonCard do engine).
 */

// ── Constantes ────────────────────────────────────────────────────────────

/** @enum {string} */
export const AbilityType = {
  ACTIVE:  'active',   // jogador ativa manualmente
  PASSIVE: 'passive',  // sempre ativa, sem custo
  BATTLE:  'battle',   // dispara automaticamente em batalha
  NONE:    'none',
}

// ── Typedef ───────────────────────────────────────────────────────────────

/**
 * @typedef {Object} PhysicalCard
 *
 * Campos de identidade:
 * @property {string}       id                  - Chave única (ex: 'bulbasaur')
 * @property {string}       real_name           - Nome canônico (ex: 'Bulbasaur')
 *
 * Campos de imagem:
 * @property {string}       reference_image     - Filename da imagem (ex: 'bulbasaur.png')
 * @property {string}       image_url           - URL para o frontend (/assets/pokemon/...)
 *
 * Campos de estatísticas:
 * @property {number|null}  power               - Pontos de Batalha (null = não batalha)
 * @property {number}       points              - Master Points ao capturar
 *
 * Campos de habilidade:
 * @property {string|null}  ability_type        - 'active' | 'passive' | 'battle' | null
 * @property {string|null}  ability_description - Texto descritivo da habilidade
 * @property {number|null}  charges             - Cargas disponíveis (null = ilimitado)
 *
 * Campos de evolução:
 * @property {boolean}      evolves             - True se pode evoluir
 * @property {string|null}  evolves_to          - real_name do alvo (ex: 'Ivysaur'), ou null
 *
 * Metadados extras:
 * @property {string|null}  notes               - Observações da carta
 * @property {boolean|null} is_initial          - True se é Pokémon inicial selecionável
 *
 * Campo extra retornado pelo endpoint de detalhe:
 * @property {PhysicalCard|null} [evolution]    - Dados completos da carta evoluída
 */

// ── Funções utilitárias ───────────────────────────────────────────────────

/**
 * Retorna true se a carta pode batalhar (tem power definido).
 * @param {PhysicalCard} card
 * @returns {boolean}
 */
export function canBattle(card) {
  return card.power != null
}

/**
 * Retorna true se a carta pode evoluir.
 * @param {PhysicalCard} card
 * @returns {boolean}
 */
export function canEvolve(card) {
  return card.evolves === true && card.evolves_to != null
}

/**
 * Retorna true se a habilidade usa cargas limitadas.
 * @param {PhysicalCard} card
 * @returns {boolean}
 */
export function hasCharges(card) {
  return card.charges != null
}

/**
 * Retorna a URL da imagem da carta.
 * @param {PhysicalCard} card
 * @returns {string|null}
 */
export function getImageUrl(card) {
  return card.image_url ?? null
}

/**
 * Retorna o rótulo de tipo de habilidade para exibição.
 * @param {PhysicalCard} card
 * @returns {string}
 */
export function abilityTypeLabel(card) {
  const labels = {
    [AbilityType.ACTIVE]:  'Ativa',
    [AbilityType.PASSIVE]: 'Passiva',
    [AbilityType.BATTLE]:  'Batalha',
    [AbilityType.NONE]:    '—',
  }
  return labels[card.ability_type] ?? '—'
}

/**
 * Retorna true se a habilidade é ativa (requer ação do jogador).
 * @param {PhysicalCard} card
 * @returns {boolean}
 */
export function isActiveAbility(card) {
  return card.ability_type === AbilityType.ACTIVE
}

/**
 * Retorna true se a habilidade é passiva (sempre ativa).
 * @param {PhysicalCard} card
 * @returns {boolean}
 */
export function isPassiveAbility(card) {
  return card.ability_type === AbilityType.PASSIVE
}

/**
 * Retorna true se a habilidade é de batalha.
 * @param {PhysicalCard} card
 * @returns {boolean}
 */
export function isBattleAbility(card) {
  return card.ability_type === AbilityType.BATTLE
}

// ── API helpers ───────────────────────────────────────────────────────────

const CATALOG_BASE = '/api/cards'

/**
 * Busca a lista de todas as cartas do catálogo.
 * @param {Object} [filters]
 * @param {string} [filters.ability_type]
 * @param {boolean} [filters.can_evolve]
 * @param {boolean} [filters.can_battle]
 * @param {boolean} [filters.is_initial]
 * @returns {Promise<PhysicalCard[]>}
 */
export async function fetchAllCards(filters = {}) {
  const params = new URLSearchParams()
  for (const [key, val] of Object.entries(filters)) {
    if (val !== undefined && val !== null) params.set(key, String(val))
  }
  const qs = params.toString()
  const url = qs ? `${CATALOG_BASE}/?${qs}` : `${CATALOG_BASE}/`
  const res = await fetch(url)
  if (!res.ok) throw new Error(`Catalog fetch failed: ${res.status}`)
  const data = await res.json()
  return data.cards
}

/**
 * Busca uma carta pelo id.
 * Inclui o campo `evolution` com os dados da carta evoluída (ou null).
 * @param {string} cardId
 * @returns {Promise<PhysicalCard>}
 */
export async function fetchCardById(cardId) {
  const res = await fetch(`${CATALOG_BASE}/${cardId}/`)
  if (!res.ok) throw new Error(`Card '${cardId}' not found: ${res.status}`)
  return res.json()
}
