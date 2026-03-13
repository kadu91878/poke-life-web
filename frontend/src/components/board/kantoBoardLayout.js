export const BOARD_GRID = { columns: 12, rows: 9 }

export const TILE_GRID_POSITIONS = [
  { col: 3, row: 9 }, { col: 3, row: 8 }, { col: 3, row: 7 }, { col: 3, row: 6 },
  { col: 2, row: 6 }, { col: 1, row: 6 }, { col: 1, row: 5 }, { col: 1, row: 4 },
  { col: 1, row: 3 }, { col: 1, row: 2 }, { col: 2, row: 2 }, { col: 3, row: 2 },
  { col: 4, row: 2 }, { col: 5, row: 2 }, { col: 6, row: 2 }, { col: 7, row: 2 },
  { col: 8, row: 2 }, { col: 9, row: 2 }, { col: 10, row: 2 }, { col: 11, row: 2 },
  { col: 11, row: 3 }, { col: 11, row: 4 }, { col: 11, row: 5 }, { col: 11, row: 6 },
  { col: 10, row: 6 }, { col: 9, row: 6 }, { col: 8, row: 6 }, { col: 7, row: 6 },
  { col: 6, row: 6 }, { col: 5, row: 6 }, { col: 4, row: 6 }, { col: 4, row: 7 },
  { col: 5, row: 7 }, { col: 6, row: 7 }, { col: 7, row: 7 }, { col: 8, row: 7 },
  { col: 8, row: 8 }, { col: 7, row: 8 }, { col: 6, row: 8 }, { col: 5, row: 8 },
  { col: 4, row: 8 }, { col: 2, row: 7 }, { col: 2, row: 5 }, { col: 2, row: 4 },
  { col: 2, row: 3 }, { col: 3, row: 3 }, { col: 4, row: 3 }, { col: 5, row: 3 },
  { col: 6, row: 3 }, { col: 7, row: 3 }, { col: 8, row: 3 }, { col: 9, row: 3 },
  { col: 10, row: 3 }, { col: 10, row: 4 }, { col: 10, row: 5 }, { col: 9, row: 5 },
  { col: 8, row: 5 }, { col: 7, row: 5 }, { col: 6, row: 5 }, { col: 5, row: 5 },
  { col: 4, row: 5 }, { col: 3, row: 5 }, { col: 3, row: 4 }, { col: 4, row: 4 },
  { col: 5, row: 4 }, { col: 6, row: 4 }, { col: 7, row: 4 }, { col: 8, row: 4 },
  { col: 9, row: 4 }, { col: 12, row: 5 }, { col: 12, row: 4 }
]

export const REGION_LABELS = [
  { name: 'Pallet Town', col: 3, row: 9 },
  { name: 'Viridian City', col: 1, row: 5 },
  { name: 'Viridian Forest', col: 3, row: 3 },
  { name: 'Mt. Moon', col: 6, row: 2 },
  { name: 'Cerulean City', col: 10, row: 2 },
  { name: 'Vermilion City', col: 11, row: 6 },
  { name: 'Saffron City', col: 7, row: 4 },
  { name: 'Celadon City', col: 5, row: 6 },
  { name: 'Fuchsia City', col: 7, row: 8 },
  { name: 'Safari Zone', col: 6, row: 9 },
  { name: 'Cinnabar', col: 1, row: 9 },
  { name: 'Victory Road', col: 1, row: 3 },
  { name: 'Pokemon League', col: 1, row: 1 },
]

export function getTileGridPosition(tileId) {
  return TILE_GRID_POSITIONS[tileId] ?? { col: 1, row: 1 }
}
