<template>
  <div class="board-calibration-view">
    <header class="calibration-header">
      <div>
        <p class="eyebrow">Calibracao Manual</p>
        <h1>Espacos visuais e mapeamento logico</h1>
        <p class="intro">
          Cada espaco visual do tabuleiro recebe um centro explicito. Separadamente, cada tile logico do backend
          aponta para um `spaceId` e para um `tileTypeId` do catalogo de 26 tipos base.
        </p>
      </div>
      <div class="header-actions">
        <RouterLink class="nav-link" :to="{ name: 'home' }">Inicio</RouterLink>
      </div>
    </header>

    <div class="calibration-layout">
      <section class="sidebar">
        <div class="stats-card">
          <strong>{{ calibratedSpaces }}/{{ editableSpaces.length }}</strong>
          <span>espacos calibrados</span>
          <strong>{{ mappedLogicalTiles }}/{{ editableLogicalSlots.length }}</strong>
          <span>tiles logicos mapeados</span>
        </div>

        <div class="editor-card">
          <div class="editor-card-header">
            <h2>Espaco visual</h2>
            <button class="btn-primary" @click="addSpace">Novo espaco</button>
          </div>

          <div v-if="selectedSpace" class="form-grid">
            <label>
              <span>Space ID</span>
              <input :value="selectedSpace.id" disabled />
            </label>
            <label>
              <span>Tile type</span>
              <select :value="selectedSpace.tileTypeId ?? ''" @change="updateSelectedSpaceType($event.target.value)">
                <option value="">Sem tipo</option>
                <option v-for="tileType in tileTypes" :key="tileType.id" :value="tileType.id">
                  {{ tileType.label }}
                </option>
              </select>
            </label>
            <label>
              <span>Label</span>
              <input :value="selectedSpace.label ?? ''" @input="updateSelectedSpaceLabel($event.target.value)" />
            </label>
            <label>
              <span>X / Y</span>
              <input :value="spaceCoordinatesLabel(selectedSpace)" disabled />
            </label>
          </div>

          <div class="row-actions">
            <button class="btn-secondary" :disabled="!selectedSpace" @click="clearSelectedSpaceCoords">Limpar coords</button>
            <button class="btn-ghost" :disabled="!selectedSpace" @click="removeSelectedSpace">Excluir espaco</button>
          </div>
        </div>

        <div class="editor-card">
          <div class="editor-card-header">
            <h2>Tile logico</h2>
            <span>#{{ selectedLogicalTile.tileId }}</span>
          </div>

          <div class="form-grid">
            <label>
              <span>Selecionar tile</span>
              <select :value="selectedLogicalTileId" @change="selectedLogicalTileId = Number($event.target.value)">
                <option v-for="slot in editableLogicalSlots" :key="slot.tileId" :value="slot.tileId">
                  Tile {{ slot.tileId }}
                </option>
              </select>
            </label>
            <label>
              <span>Tile type</span>
              <select :value="selectedLogicalTile.tileTypeId ?? ''" @change="updateLogicalTileType($event.target.value)">
                <option value="">Sem tipo</option>
                <option v-for="tileType in tileTypes" :key="tileType.id" :value="tileType.id">
                  {{ tileType.label }}
                </option>
              </select>
            </label>
            <label>
              <span>Space ID</span>
              <input :value="selectedLogicalTile.spaceId ?? ''" disabled />
            </label>
          </div>

          <div class="row-actions">
            <button class="btn-primary" :disabled="!selectedSpace" @click="assignSelectedSpaceToLogicalTile">
              Usar space selecionado
            </button>
            <button class="btn-secondary" @click="clearLogicalTileMapping">Limpar mapeamento</button>
          </div>
        </div>

        <label class="debug-toggle">
          <input v-model="showDebug" type="checkbox" />
          <span>Mostrar overlay numerado</span>
        </label>

        <div class="help-card">
          <h2>Fluxo recomendado</h2>
          <ol>
            <li>Crie um `spaceId` para cada espaco visual do tabuleiro.</li>
            <li>Clique no centro real de cada espaco na imagem.</li>
            <li>Associe cada `tileId` logico a um `spaceId` e a um `tileTypeId`.</li>
            <li>Exporte os dois JSONs e substitua os arquivos do projeto.</li>
          </ol>
        </div>

        <div class="editor-card">
          <h2>Exportar spaces JSON</h2>
          <textarea :value="spacesExportText" readonly spellcheck="false" />
          <div class="row-actions">
            <button class="btn-primary" @click="downloadJson('kanto-board.spaces.json', spacesExportText)">Baixar</button>
            <button class="btn-ghost" @click="copyText(spacesExportText)">Copiar</button>
          </div>
        </div>

        <div class="editor-card">
          <h2>Exportar logical map JSON</h2>
          <textarea :value="logicalMapExportText" readonly spellcheck="false" />
          <div class="row-actions">
            <button class="btn-primary" @click="downloadJson('kanto-board.logical-map.json', logicalMapExportText)">Baixar</button>
            <button class="btn-ghost" @click="copyText(logicalMapExportText)">Copiar</button>
          </div>
        </div>
      </section>

      <section class="canvas-column">
        <div class="canvas-card">
          <div
            ref="mapRef"
            class="board-map"
            :style="{ '--board-aspect': BOARD_ASPECT_RATIO }"
            @click="capturePoint"
          >
            <img class="board-image" :src="BOARD_IMAGE" alt="Tabuleiro Kanto para calibracao manual" />

            <button
              v-for="space in editableSpaces"
              :key="space.id"
              class="debug-marker"
              :class="{
                'debug-marker--selected': selectedSpace?.id === space.id,
                'debug-marker--uncalibrated': !isCalibratedSpace(space),
              }"
              :style="markerStyle(space.id)"
              type="button"
              @click.stop="selectedSpaceId = space.id"
            >
              <span v-if="showDebug">{{ space.id }}</span>
            </button>
          </div>
        </div>

        <div class="lists-row">
          <div class="list-card">
            <div class="editor-card-header">
              <h2>Spaces</h2>
              <span>{{ editableSpaces.length }}</span>
            </div>
            <div class="entity-list">
              <button
                v-for="space in editableSpaces"
                :key="space.id"
                class="entity-item"
                :class="{
                  'entity-item--selected': selectedSpace?.id === space.id,
                  'entity-item--done': isCalibratedSpace(space),
                }"
                @click="selectedSpaceId = space.id"
              >
                <strong>#{{ space.id }}</strong>
                <span>{{ tileTypeLabel(space.tileTypeId) }}</span>
                <span>{{ spaceCoordinatesLabel(space) }}</span>
              </button>
            </div>
          </div>

          <div class="list-card">
            <div class="editor-card-header">
              <h2>Tiles logicos</h2>
              <span>{{ editableLogicalSlots.length }}</span>
            </div>
            <div class="entity-list">
              <button
                v-for="slot in editableLogicalSlots"
                :key="slot.tileId"
                class="entity-item"
                :class="{
                  'entity-item--selected': selectedLogicalTileId === slot.tileId,
                  'entity-item--done': isLogicalSlotMapped(slot),
                }"
                @click="selectedLogicalTileId = slot.tileId"
              >
                <strong>Tile {{ slot.tileId }}</strong>
                <span>{{ tileTypeLabel(slot.tileTypeId) }}</span>
                <span>space {{ slot.spaceId ?? '-' }}</span>
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { RouterLink } from 'vue-router'
import {
  BOARD_ASPECT_RATIO,
  BOARD_IMAGE,
  BOARD_IMAGE_HEIGHT,
  BOARD_IMAGE_WIDTH,
  BOARD_LOGICAL_MAP,
  BOARD_SPACES,
  TILE_TYPES,
  countCalibratedSpaces,
  countMappedLogicalTiles,
  createLogicalMapSnapshot,
  createSpacesSnapshot,
  getSpaceVisualPosition,
  isCalibratedSpace,
} from '@/lib/boardCalibration'

const mapRef = ref(null)
const showDebug = ref(true)
const selectedSpaceId = ref(null)
const selectedLogicalTileId = ref(0)
const editableSpaces = ref(BOARD_SPACES.spaces.map(space => ({ ...space })))
const editableLogicalSlots = ref(BOARD_LOGICAL_MAP.slots.map(slot => ({ ...slot })))
const tileTypes = TILE_TYPES

const calibratedSpaces = computed(() => countCalibratedSpaces(editableSpaces.value))
const mappedLogicalTiles = computed(() => countMappedLogicalTiles(editableLogicalSlots.value))
const selectedSpace = computed(() =>
  editableSpaces.value.find(space => space.id === selectedSpaceId.value) ?? null
)
const selectedLogicalTile = computed(() =>
  editableLogicalSlots.value.find(slot => slot.tileId === selectedLogicalTileId.value) ?? editableLogicalSlots.value[0]
)
const spacesExportText = computed(() => JSON.stringify(createSpacesSnapshot(editableSpaces.value), null, 2))
const logicalMapExportText = computed(() => JSON.stringify(createLogicalMapSnapshot(editableLogicalSlots.value), null, 2))

function nextSpaceId() {
  return editableSpaces.value.length
    ? Math.max(...editableSpaces.value.map(space => space.id)) + 1
    : 0
}

function addSpace() {
  const id = nextSpaceId()
  editableSpaces.value = [
    ...editableSpaces.value,
    { id, tileTypeId: null, label: '', x: null, y: null },
  ]
  selectedSpaceId.value = id
}

function updateSelectedSpace(partial) {
  if (!selectedSpace.value) {
    return
  }

  editableSpaces.value = editableSpaces.value.map(space =>
    space.id === selectedSpace.value.id
      ? { ...space, ...partial }
      : space
  )
}

function updateSelectedSpaceType(tileTypeId) {
  updateSelectedSpace({ tileTypeId: tileTypeId || null })
}

function updateSelectedSpaceLabel(label) {
  updateSelectedSpace({ label })
}

function clearSelectedSpaceCoords() {
  updateSelectedSpace({ x: null, y: null })
}

function removeSelectedSpace() {
  if (!selectedSpace.value) {
    return
  }

  const removedId = selectedSpace.value.id
  editableSpaces.value = editableSpaces.value.filter(space => space.id !== removedId)
  editableLogicalSlots.value = editableLogicalSlots.value.map(slot =>
    slot.spaceId === removedId
      ? { ...slot, spaceId: null }
      : slot
  )
  selectedSpaceId.value = editableSpaces.value[0]?.id ?? null
}

function updateLogicalTileType(tileTypeId) {
  editableLogicalSlots.value = editableLogicalSlots.value.map(slot =>
    slot.tileId === selectedLogicalTile.value.tileId
      ? { ...slot, tileTypeId: tileTypeId || null }
      : slot
  )
}

function assignSelectedSpaceToLogicalTile() {
  if (!selectedSpace.value) {
    return
  }

  editableLogicalSlots.value = editableLogicalSlots.value.map(slot =>
    slot.tileId === selectedLogicalTile.value.tileId
      ? {
          ...slot,
          spaceId: selectedSpace.value.id,
          tileTypeId: slot.tileTypeId ?? selectedSpace.value.tileTypeId ?? null,
        }
      : slot
  )
}

function clearLogicalTileMapping() {
  editableLogicalSlots.value = editableLogicalSlots.value.map(slot =>
    slot.tileId === selectedLogicalTile.value.tileId
      ? { ...slot, tileTypeId: null, spaceId: null }
      : slot
  )
}

function capturePoint(event) {
  if (!selectedSpace.value || !mapRef.value) {
    return
  }

  const rect = mapRef.value.getBoundingClientRect()
  const x = ((event.clientX - rect.left) / rect.width) * BOARD_IMAGE_WIDTH
  const y = ((event.clientY - rect.top) / rect.height) * BOARD_IMAGE_HEIGHT

  updateSelectedSpace({ x: Math.round(x), y: Math.round(y) })
}

function markerStyle(spaceId) {
  const lookup = new Map(editableSpaces.value.map(space => [space.id, space]))
  const position = getSpaceVisualPosition(spaceId, lookup)

  if (!position) {
    return { display: 'none' }
  }

  return {
    left: position.left,
    top: position.top,
  }
}

function tileTypeLabel(tileTypeId) {
  return tileTypes.find(tileType => tileType.id === tileTypeId)?.label ?? 'Sem tipo'
}

function spaceCoordinatesLabel(space) {
  return Number.isFinite(space?.x) && Number.isFinite(space?.y)
    ? `${space.x}, ${space.y}`
    : 'sem coordenadas'
}

function isLogicalSlotMapped(slot) {
  return Number.isFinite(slot.spaceId) && typeof slot.tileTypeId === 'string'
}

async function copyText(text) {
  await navigator.clipboard.writeText(text)
}

function downloadJson(filename, text) {
  const blob = new Blob([text], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.board-calibration-view {
  min-height: 100vh;
  padding: 1.5rem;
  background:
    radial-gradient(circle at top, rgba(244, 208, 63, 0.12), transparent 28%),
    linear-gradient(180deg, #071423, #0d1e32 44%, #08111f);
  color: var(--color-text);
}

.calibration-header,
.header-actions,
.calibration-layout,
.row-actions,
.lists-row,
.editor-card-header {
  display: flex;
  gap: 0.75rem;
}

.calibration-header {
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1.25rem;
}

.calibration-layout {
  align-items: flex-start;
}

.sidebar {
  width: min(420px, 100%);
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.canvas-column {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.eyebrow {
  margin: 0 0 0.35rem;
  color: #9ec7ff;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  font-size: 0.72rem;
}

h1,
h2,
.stats-card strong {
  color: #fff6cf;
}

h1 {
  margin: 0;
  font-size: 2rem;
}

.intro {
  max-width: 720px;
  margin: 0.5rem 0 0;
  color: #d3ddeb;
}

.nav-link,
.stats-card,
.editor-card,
.help-card,
.canvas-card,
.list-card {
  background: rgba(4, 12, 24, 0.82);
  border: 1px solid rgba(158, 199, 255, 0.14);
  border-radius: 20px;
  box-shadow: 0 22px 50px rgba(0, 0, 0, 0.2);
}

.nav-link {
  color: #eef4ff;
  text-decoration: none;
  padding: 0.8rem 1rem;
}

.stats-card,
.editor-card,
.help-card,
.list-card {
  padding: 1rem;
}

.stats-card,
.help-card {
  display: flex;
  flex-direction: column;
}

.editor-card,
.list-card {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.editor-card-header {
  justify-content: space-between;
  align-items: center;
}

.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
}

.form-grid label {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.row-actions {
  flex-wrap: wrap;
}

.debug-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.editor-card textarea {
  min-height: 220px;
  resize: vertical;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 0.8rem;
}

.canvas-card {
  padding: 1rem;
}

.board-map {
  position: relative;
  width: min(100%, 900px);
  aspect-ratio: var(--board-aspect);
  margin: 0 auto;
  border-radius: 18px;
  overflow: hidden;
  cursor: crosshair;
}

.board-image {
  width: 100%;
  height: 100%;
  display: block;
}

.debug-marker {
  position: absolute;
  width: 28px;
  height: 28px;
  transform: translate(-50%, -50%);
  border-radius: 999px;
  border: 2px solid rgba(255, 255, 255, 0.94);
  background: rgba(230, 57, 70, 0.88);
  color: #fff;
  font-size: 0.72rem;
  font-weight: 800;
  padding: 0;
  z-index: 2;
}

.debug-marker--selected {
  background: rgba(244, 208, 63, 0.96);
  color: #09111f;
}

.debug-marker--uncalibrated {
  display: none;
}

.lists-row {
  align-items: flex-start;
}

.list-card {
  flex: 1;
  min-width: 0;
}

.entity-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 0.65rem;
  max-height: 320px;
  overflow: auto;
}

.entity-item {
  background: rgba(15, 34, 56, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #d8e7fb;
  text-align: left;
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.entity-item--selected {
  border-color: rgba(244, 208, 63, 0.75);
}

.entity-item--done {
  border-color: rgba(94, 234, 212, 0.55);
}

@media (max-width: 1180px) {
  .calibration-layout,
  .lists-row {
    flex-direction: column;
  }

  .sidebar {
    width: 100%;
  }
}
</style>
