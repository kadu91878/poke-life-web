import boardSpaces from '@/data/kanto-board.spaces.json'

export const BOARD_IMAGE = boardSpaces.imageSrc
export const BOARD_ASPECT_RATIO = `${boardSpaces.imageWidth} / ${boardSpaces.imageHeight}`
export const BOARD_IMAGE_WIDTH = boardSpaces.imageWidth
export const BOARD_IMAGE_HEIGHT = boardSpaces.imageHeight
export const BOARD_SPACES = boardSpaces.spaces

const SPACE_LOOKUP = new Map(BOARD_SPACES.map(space => [space.id, space]))

// Camada genérica e temporária para testes:
// enquanto não houver um mapa lógico formal, assume tileId -> spaceId na ordem.
export function resolveSpaceIdForLogicalTile(tileId) {
  return Number.isInteger(tileId) && tileId >= 0 && tileId < BOARD_SPACES.length
    ? tileId
    : null
}

export function getSpaceById(spaceId) {
  return SPACE_LOOKUP.get(spaceId) ?? null
}

export function getSpacePosition(spaceId) {
  const space = getSpaceById(spaceId)

  if (!space || !Number.isFinite(space.x) || !Number.isFinite(space.y)) {
    return null
  }

  return {
    left: `${(space.x / BOARD_IMAGE_WIDTH) * 100}%`,
    top: `${(space.y / BOARD_IMAGE_HEIGHT) * 100}%`,
    x: space.x,
    y: space.y,
    tileTypeId: space.tileTypeId ?? null,
    label: space.label ?? '',
  }
}

export function getLogicalTilePosition(tileId) {
  const spaceId = resolveSpaceIdForLogicalTile(tileId)
  return spaceId === null ? null : getSpacePosition(spaceId)
}
