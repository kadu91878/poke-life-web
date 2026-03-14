<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal">
      <div class="modal-header">
        <div>
          <p class="eyebrow">Inventario do jogador</p>
          <h2>{{ player.name }}</h2>
        </div>
        <button class="btn-ghost close-btn" @click="$emit('close')">Fechar</button>
      </div>

      <div class="inventory-summary">
        <div class="summary-card">
          <span class="summary-label">Pokebolas livres</span>
          <strong>{{ freeSlots }}</strong>
        </div>
        <div class="summary-card">
          <span class="summary-label">Slots usados</span>
          <strong>{{ usedSlots }}/{{ totalCapacity }}</strong>
        </div>
        <div class="summary-card">
          <span class="summary-label">Itens</span>
          <strong>{{ itemCount }}/{{ itemCapacity }}</strong>
        </div>
        <div class="summary-card">
          <span class="summary-label">Master Points</span>
          <strong>{{ player.master_points ?? 0 }}</strong>
        </div>
      </div>

      <div class="tab-row">
        <button
          class="tab-btn"
          :class="{ 'tab-btn--active': activeTab === 'pokemon' }"
          @click="activeTab = 'pokemon'"
        >
          Pokemon
        </button>
        <button
          class="tab-btn"
          :class="{ 'tab-btn--active': activeTab === 'items' }"
          @click="activeTab = 'items'"
        >
          Itens
        </button>
      </div>

      <section v-if="activeTab === 'pokemon'" class="tab-panel">
        <div class="section-head">
          <h3>Slots de Pokebola</h3>
          <span>{{ pokemonInventory.length }} Pokemon · {{ usedSlots }} ocupados · {{ freeSlots }} livres</span>
        </div>

        <div class="slot-layout">
          <div
            v-for="group in slotGroups"
            :key="group.id"
            class="slot-group"
            :class="{ 'slot-group--free': group.kind === 'free' }"
          >
            <div class="pokeball-stack">
              <div
                v-for="slot in group.slots"
                :key="slot.id"
                class="pokeball-slot"
                :class="{
                  'pokeball-slot--used': group.kind === 'pokemon',
                  'pokeball-slot--free': group.kind === 'free',
                }"
              >
                <div
                  v-if="group.kind === 'pokemon' && slot.offset === 0"
                  class="pokemon-slot-card"
                  :style="{ width: `calc(${group.pokemon.slotCost} * 48px + ${(group.pokemon.slotCost - 1) * 0.45}rem)` }"
                >
                  <img
                    v-if="group.pokemon.image_path"
                    :src="group.pokemon.image_path"
                    :alt="group.pokemon.name"
                    class="pokemon-card-image"
                  />
                  <div class="pokemon-hover-card">
                    <img
                      v-if="group.pokemon.image_path"
                      :src="group.pokemon.image_path"
                      :alt="group.pokemon.name"
                      class="pokemon-hover-image"
                    />
                  </div>
                </div>
                <img
                  v-else
                  :src="POKEBALL_SLOT_IMAGE"
                  alt="Slot de Pokebola"
                  class="pokeball-icon"
                />
                <span class="pokeball-index">{{ slot.id + 1 }}</span>
              </div>
            </div>
          </div>
        </div>

        <p v-if="!pokemonInventory.length" class="empty-copy">Nenhum Pokemon guardado.</p>
      </section>

      <section v-else class="tab-panel">
        <div class="section-head">
          <h3>Inventario de itens</h3>
          <span>{{ itemCount }}/{{ itemCapacity }} ocupados</span>
        </div>

        <div v-if="inventoryItems.length" class="item-card-grid">
          <article v-for="item in inventoryItems" :key="item.key" class="item-card">
            <img v-if="item.image_path" :src="item.image_path" :alt="item.name" class="item-card-image" />
            <div class="item-card-top">
              <span class="item-card-kind">{{ item.category || 'item' }}</span>
              <span class="item-card-qty">x{{ item.quantity }}</span>
            </div>
            <strong>{{ item.name }}</strong>
            <p>{{ item.notes || itemDescription(item) }}</p>
          </article>
        </div>
        <p v-else class="empty-copy">Nenhum item guardado no momento.</p>
      </section>

    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'

const POKEBALL_SLOT_IMAGE = '/assets/items/pokeball-slot.png'

const ITEM_DESCRIPTIONS = {
  full_restore: 'Item presente no inventário atual.',
  bill: 'Modificador de dado de movimento.',
  gust_of_wind: 'Item de batalha para decidir o Pokémon inimigo.',
  pluspower: 'Bônus temporário de BP em batalha.',
  prof_oak: 'Redução conservadora do dado de movimento.',
  miracle_stone: 'Evolução baseada apenas nos dados atuais da engine.',
  master_points_nugget: 'Sem uso implementado por falta de regra operacional segura.',
}

const props = defineProps({
  player: { type: Object, required: true },
})

defineEmits(['close'])

const activeTab = ref('pokemon')
const inventoryItems = computed(() => props.player.items ?? [])
const pokemonInventory = computed(() => {
  if (props.player.pokemon_inventory?.length) {
    return props.player.pokemon_inventory
  }

  const fallback = []
  if (props.player.starter_pokemon) {
    fallback.push({
      ...props.player.starter_pokemon,
      is_starter_slot: true,
      slot_cost: props.player.starter_pokemon.slot_cost ?? props.player.starter_pokemon.pokeball_slots ?? 1,
    })
  }
  for (const pokemon of props.player.pokemon ?? []) {
    fallback.push({
      ...pokemon,
      is_starter_slot: false,
      slot_cost: pokemon.slot_cost ?? pokemon.pokeball_slots ?? 1,
    })
  }
  return fallback
})
const legacyStarterCost = computed(() => {
  if (!props.player.starter_pokemon || props.player.starter_slot_applied === true) {
    return 0
  }
  return props.player.starter_pokemon.slot_cost ?? props.player.starter_pokemon.pokeball_slots ?? 1
})
const usedSlots = computed(() =>
  props.player.pokeball_slots_used
  ?? pokemonInventory.value.reduce((sum, pokemon) => sum + (pokemon.slot_cost ?? pokemon.pokeball_slots ?? 1), 0)
)
const freeSlots = computed(() =>
  props.player.pokeball_slots_free
  ?? Math.max(0, (props.player.pokeballs ?? 0) - legacyStarterCost.value)
)
const totalCapacity = computed(() => props.player.pokeball_capacity ?? (usedSlots.value + freeSlots.value))
const itemCount = computed(() => props.player.item_count ?? 0)
const itemCapacity = computed(() => props.player.item_capacity ?? 8)

const slotGroups = computed(() => {
  const groups = []
  let slotIndex = 0

  for (const [index, pokemon] of pokemonInventory.value.entries()) {
    const slotCost = pokemon.slot_cost ?? pokemon.pokeball_slots ?? 1
    const slots = Array.from({ length: slotCost }, (_, offset) => ({ id: slotIndex + offset, offset }))
    groups.push({
      id: `pokemon-${pokemonKey(pokemon, index)}`,
      kind: 'pokemon',
      pokemon: { ...pokemon, slotCost },
      slots,
    })
    slotIndex += slotCost
  }

  for (let freeIndex = 0; freeIndex < freeSlots.value; freeIndex += 1) {
    groups.push({
      id: `free-${slotIndex}`,
      kind: 'free',
      slots: [{ id: slotIndex }],
    })
    slotIndex += 1
  }

  return groups
})

function pokemonKey(pokemon, index = 0) {
  return `${pokemon.id}-${pokemon.is_starter_slot ? 'starter' : `team-${index}`}`
}

function itemDescription(item) {
  return ITEM_DESCRIPTIONS[item.key] ?? 'Carta de item exibida no inventario.'
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.82);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 140;
  padding: 1rem;
}

.modal {
  width: min(980px, 100%);
  max-height: none;
  overflow: visible;
  background: linear-gradient(180deg, rgba(10, 24, 45, 0.98), rgba(5, 13, 27, 0.98));
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 20px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.45);
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.modal-header,
.section-head,
.pokemon-row,
.item-card-top,
.tag-row,
.tab-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.75rem;
}

.eyebrow {
  margin: 0 0 0.2rem;
  color: #9ec7ff;
  font-size: 0.72rem;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

h2,
h3 {
  margin: 0;
  color: #fff3bf;
}

.inventory-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.75rem;
}

.summary-card,
.tab-panel,
.pokemon-slot-card,
.item-card {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 16px;
}

.summary-card {
  padding: 0.9rem;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.summary-label,
.section-head span,
.pokemon-meta,
.empty-copy,
.item-card p,
.item-card-kind {
  color: var(--color-text-muted);
}

.summary-card strong {
  color: #eef4ff;
  font-size: 1.1rem;
}

.tab-row {
  justify-content: flex-start;
}

.tab-btn {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #d8e7fb;
  padding: 0.55rem 0.9rem;
}

.tab-btn--active {
  background: rgba(255, 224, 102, 0.14);
  border-color: rgba(255, 224, 102, 0.26);
  color: #fff3bf;
}

.tab-panel {
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
  overflow: visible;
}

.slot-layout {
  display: flex;
  flex-wrap: wrap;
  gap: 0.9rem 0.75rem;
  align-items: flex-start;
  padding-bottom: 220px;
}

.slot-group {
  position: relative;
}

.slot-group--free {
  padding-top: 0;
}

.pokeball-stack {
  display: flex;
  gap: 0.45rem;
}

.pokeball-slot {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.05);
}

.pokeball-slot--used {
  background: transparent;
  border-color: transparent;
  box-shadow: none;
  overflow: visible;
}

.pokeball-slot--free {
  opacity: 0.42;
}

.pokeball-icon {
  width: 36px;
  height: 36px;
  object-fit: contain;
}

.pokeball-index {
  position: absolute;
  right: 6px;
  bottom: 4px;
  font-size: 0.65rem;
  color: #eef4ff;
}

.pokemon-slot-card {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 36px !important;
  height: 36px;
  transform: translate(-50%, -50%);
  z-index: 2;
}

.pokemon-card-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
  border-radius: 10px;
  transition: transform 0.18s ease, box-shadow 0.18s ease;
  box-shadow: 0 8px 18px rgba(0, 0, 0, 0.28);
}

.pokemon-hover-card {
  position: absolute;
  left: 50%;
  top: calc(100% + 8px);
  transform: translateX(-50%) scale(0.94);
  width: 190px;
  padding: 0.35rem;
  border-radius: 14px;
  background: rgba(8, 18, 35, 0.96);
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.38);
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.18s ease, transform 0.18s ease;
  z-index: 8;
}

.pokemon-hover-image {
  display: block;
  width: 100%;
  height: auto;
  object-fit: contain;
  border-radius: 10px;
}

.pokemon-slot-card:hover .pokemon-card-image {
  transform: scale(1.08);
}

.pokemon-slot-card:hover .pokemon-hover-card {
  opacity: 1;
  transform: translateX(-50%) scale(1);
}

.slot-badge,
.starter-badge,
.type-chip,
.item-card-qty {
  font-size: 0.68rem;
  border-radius: 999px;
  padding: 0.12rem 0.45rem;
}

.slot-badge,
.item-card-qty {
  background: rgba(255, 224, 102, 0.12);
  color: #fff3bf;
}

.starter-badge {
  background: rgba(69, 123, 157, 0.18);
  color: #d7eeff;
}

.type-chip {
  background: rgba(255, 255, 255, 0.06);
  color: #dfe9ff;
}

.item-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 0.75rem;
}

.item-card {
  min-height: 148px;
  padding: 0.9rem;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
  background:
    radial-gradient(circle at top right, rgba(255, 224, 102, 0.1), transparent 36%),
    rgba(255, 255, 255, 0.04);
}

.item-card-image {
  width: 100%;
  max-height: 180px;
  object-fit: contain;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.03);
}

.item-card strong {
  color: #eef4ff;
  font-size: 1rem;
}

.item-card p {
  margin: 0;
  font-size: 0.8rem;
  line-height: 1.35;
}

@media (max-width: 820px) {
  .inventory-summary {
    grid-template-columns: 1fr 1fr;
  }

  .slot-layout {
    padding-bottom: 180px;
  }

  .pokemon-slot-card {
    width: 36px !important;
    height: 36px;
  }

  .pokemon-card-image {
    border-radius: 8px;
  }
}

@media (max-width: 560px) {
  .inventory-summary {
    grid-template-columns: 1fr;
  }

  .slot-layout {
    padding-bottom: 150px;
  }
}
</style>
