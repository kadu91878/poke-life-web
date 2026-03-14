import tileTypesCatalog from '@/data/tile-types.catalog.json'
import boardSpaces from '@/data/kanto-board.spaces.json'
import logicalMap from '@/data/kanto-board.logical-map.json'

export const TILE_TYPES = tileTypesCatalog.tileTypes
export const BOARD_SPACES = boardSpaces
export const BOARD_LOGICAL_MAP = logicalMap
export const BOARD_IMAGE = boardSpaces.imageSrc
export const BOARD_IMAGE_WIDTH = boardSpaces.imageWidth
export const BOARD_IMAGE_HEIGHT = boardSpaces.imageHeight
export const BOARD_ASPECT_RATIO = `${BOARD_IMAGE_WIDTH} / ${BOARD_IMAGE_HEIGHT}`

export function isCalibratedSpace(space) {
  return Number.isFinite(space?.x) && Number.isFinite(space?.y)
}

export function buildSpaceLookup(spaces = BOARD_SPACES.spaces) {
  return new Map(spaces.map(space => [space.id, space]))
}

export function buildLogicalLookup(slots = BOARD_LOGICAL_MAP.slots) {
  return new Map(slots.map(slot => [slot.tileId, slot]))
}

export function buildTileTypeLookup(tileTypes = TILE_TYPES) {
  return new Map(tileTypes.map(tileType => [tileType.id, tileType]))
}

export function getSpaceVisualPosition(spaceId, spaceLookup = buildSpaceLookup()) {
  const space = spaceLookup.get(spaceId) ?? null

  if (!isCalibratedSpace(space)) {
    return null
  }

  return {
    left: `${(space.x / BOARD_IMAGE_WIDTH) * 100}%`,
    top: `${(space.y / BOARD_IMAGE_HEIGHT) * 100}%`,
    x: space.x,
    y: space.y,
  }
}

export function getLogicalTileMapping(tileId, logicalLookup = buildLogicalLookup()) {
  return logicalLookup.get(tileId) ?? null
}

export function getLogicalTileVisualPosition(
  tileId,
  logicalLookup = buildLogicalLookup(),
  spaceLookup = buildSpaceLookup(),
) {
  const mapping = getLogicalTileMapping(tileId, logicalLookup)

  if (!mapping || !Number.isFinite(mapping.spaceId)) {
    return null
  }

  return getSpaceVisualPosition(mapping.spaceId, spaceLookup)
}

export function countCalibratedSpaces(spaces = BOARD_SPACES.spaces) {
  return spaces.filter(isCalibratedSpace).length
}

export function countMappedLogicalTiles(slots = BOARD_LOGICAL_MAP.slots) {
  return slots.filter(slot => Number.isFinite(slot.spaceId) && typeof slot.tileTypeId === 'string').length
}

export function createSpacesSnapshot(spaces) {
  return {
    ...BOARD_SPACES,
    spaces: spaces.map(space => ({
      id: space.id,
      tileTypeId: space.tileTypeId ?? null,
      label: space.label ?? '',
      x: Number.isFinite(space.x) ? Math.round(space.x) : null,
      y: Number.isFinite(space.y) ? Math.round(space.y) : null,
    })),
  }
}

export function createLogicalMapSnapshot(slots) {
  return {
    ...BOARD_LOGICAL_MAP,
    slots: slots.map(slot => ({
      tileId: slot.tileId,
      tileTypeId: slot.tileTypeId ?? null,
      spaceId: Number.isFinite(slot.spaceId) ? slot.spaceId : null,
    })),
  }
}
