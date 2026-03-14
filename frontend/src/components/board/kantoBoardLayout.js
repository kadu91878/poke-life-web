export const BOARD_IMAGE = '/assets/cards/Kanto/Board & Rules/Kanto Board (Compact; borders 8,8,8,8).png'
export const BOARD_ASPECT_RATIO = '1432 / 2096'

export const REGION_LABELS = [
  { name: 'Pallet Town',    left: 38,   top: 73   },
  { name: 'Viridian City',  left: 28,   top: 48   },
  { name: 'Viridian Forest',left: 28,   top: 33   },
  { name: 'Pewter City',    left: 16,   top: 18   },
  { name: 'Mt. Moon',       left: 49,   top: 22   },
  { name: 'Cerulean City',  left: 82,   top: 6    },
  { name: 'Vermilion City', left: 85,   top: 55   },
  { name: 'Lavender Town',  left: 71,   top: 48   },
  { name: 'Celadon City',   left: 41,   top: 55   },
  { name: 'Fuchsia City',   left: 56,   top: 79   },
  { name: 'Safari Zone',    left: 47,   top: 86   },
  { name: 'Cinnabar Island',left: 13,   top: 86   },
  { name: 'Saffron City',   left: 57,   top: 42   },
  { name: 'Victory Road',   left: 10,   top: 28   },
  { name: 'Pokemon League', left: 10,   top: 8    },
]

// Posições de cada tile como % da imagem (left%, top%).
// Índice = tile.id do board.json (0–70).
//
// Caminho do tabuleiro (sentido de percurso):
//
//  [Partida] Pallet Town (0)
//   └→ Rota 1 × 3 (1-3) → subindo
//   └→ Viridian City (4) → oeste Rota 22 (5)
//   └→ Rota 2 (6) → Viridian Forest (7-8) → subindo
//   └→ Pewter City Gym (9)
//   └→ Rota 3 (10-11) → Mt. Moon (12-13) → Rota 4 (14-16) → [topo, L→R]
//   └→ Cerulean City Gym (17)
//   └→ Rota 24 (18) → Nugget Bridge (19) → Rota 25 (20) → [descendo]
//   └→ Rota 5 (21) → Rota 6 (22-23) → S.S. Anne (24) → Vermilion Gym (25)
//   └→ Rota 11 (26-27) → Rota 12 (28) → Lavender Town (29) → [indo W]
//   └→ Rota 8 (30) → Rota 7 (31-32) → Celadon Gym (33) → Game Corner (34)
//   └→ Rota 16 (35) → Ciclismo (36) → Rota 18 (37-38) → [descendo]
//   └→ Safari Zone (39) → Fuchsia City Gym (40)
//   └→ Rota 15 (41) → Rota 14 (42) → Rota 13 (43) → Rota 12 (44) → [E]
//   └→ Rota 21 water (45-46) → [volta W para Cinnabar]
//   └→ Cinnabar Island (47) → Cinnabar Gym (48)
//   └→ Rota 20 (49) → Seafoam (50) → Rota 19 (51-52) → [subindo costa W]
//   └→ Caverna Misteriosa (53)
//   └→ [salto para centro] Saffron City Gym (54) → Silph Co. (55)
//   └→ Rota 9 (56) → Rota 10 (57) → Power Plant (58) → [indo E]
//   └→ Rock Tunnel (59-60) → Rota 10 (61) → [salto para W]
//   └→ Viridian City Gym (62) → Rota 22 (63)
//   └→ Rota 23 (64-65) → Victory Road (66-69) → [subindo col. esq.]
//   └→ Pokémon League (70)  [fim]
//
// Saltos visuais grandes (por design do tabuleiro):
//   46→47 : Rota 21 → Cinnabar Island  (~43% dist.)
//   53→54 : Caverna Misteriosa → Saffron City (~45% dist.)
//   61→62 : Rota 10 → Viridian City Gym (~54% dist.)
export const TILE_POSITIONS = [
  // ── Pallet Town + Rota 1 (subindo) ──────────────────────────────────────
  { left: 38, top: 73 },  //  0: Pallet Town (start)
  { left: 38, top: 66 },  //  1: Rota 1 (grass)
  { left: 38, top: 59 },  //  2: Rota 1 (grass)
  { left: 38, top: 53 },  //  3: Rota 1 (event)

  // ── Viridian City → oeste Rota 22 ───────────────────────────────────────
  { left: 28, top: 50 },  //  4: Viridian City (city)
  { left: 20, top: 50 },  //  5: Rota 22 (duel)

  // ── Rota 2 + Viridian Forest (subindo) → Pewter ──────────────────────────
  { left: 28, top: 43 },  //  6: Rota 2 (grass)
  { left: 28, top: 37 },  //  7: Viridian Forest (event)
  { left: 28, top: 30 },  //  8: Viridian Forest (grass)
  { left: 20, top: 22 },  //  9: Pewter City Gym (gym)

  // ── Rota 3 + Mt. Moon + Rota 4 → Cerulean (topo, L→R) ───────────────────
  { left: 28, top: 13 },  // 10: Rota 3 (event)
  { left: 37, top: 13 },  // 11: Rota 3 (grass)
  { left: 45, top: 21 },  // 12: Mt. Moon (special)
  { left: 53, top: 21 },  // 13: Mt. Moon (event)
  { left: 62, top: 13 },  // 14: Rota 4 (grass)
  { left: 71, top: 13 },  // 15: Rota 4 (duel)
  { left: 80, top: 13 },  // 16: Rota 4 (grass)
  { left: 88, top:  8 },  // 17: Cerulean City Gym (gym)

  // ── Rota 24/25/5/6 → S.S. Anne → Vermilion (descendo lado direito) ───────
  { left: 88, top: 15 },  // 18: Rota 24 (grass)
  { left: 88, top: 22 },  // 19: Nugget Bridge (duel)
  { left: 88, top: 29 },  // 20: Rota 25 (event)
  { left: 80, top: 36 },  // 21: Rota 5 (grass)
  { left: 80, top: 43 },  // 22: Rota 6 (event)
  { left: 80, top: 50 },  // 23: Rota 6 (grass)
  { left: 80, top: 57 },  // 24: S.S. Anne (special)
  { left: 88, top: 57 },  // 25: Vermilion City Gym (gym)

  // ── Rota 11 → Rota 12 → Lavender Town (indo para a esquerda) ─────────────
  { left: 80, top: 64 },  // 26: Rota 11 (grass)
  { left: 71, top: 64 },  // 27: Rota 11 (duel)
  { left: 71, top: 57 },  // 28: Rota 12 (grass/water)
  { left: 71, top: 50 },  // 29: Lavender Town (special)

  // ── Rota 8/7 → Celadon → Game Corner ────────────────────────────────────
  { left: 62, top: 50 },  // 30: Rota 8 (event)
  { left: 53, top: 50 },  // 31: Rota 7 (grass)
  { left: 44, top: 50 },  // 32: Rota 7 (duel)
  { left: 44, top: 57 },  // 33: Celadon City Gym (gym)
  { left: 44, top: 64 },  // 34: Game Corner (event)

  // ── Rota 16 → Ciclismo → Rota 18 → Safari Zone → Fuchsia ────────────────
  { left: 35, top: 64 },  // 35: Rota 16 (grass)
  { left: 35, top: 71 },  // 36: Pista de Ciclismo (special)
  { left: 35, top: 78 },  // 37: Rota 18 (grass)
  { left: 35, top: 85 },  // 38: Rota 18 (duel)
  { left: 47, top: 88 },  // 39: Safari Zone (special)
  { left: 56, top: 82 },  // 40: Fuchsia City Gym (gym)

  // ── Rota 15/14/13/12 (indo para a direita) ───────────────────────────────
  { left: 65, top: 85 },  // 41: Rota 15 (grass)
  { left: 74, top: 85 },  // 42: Rota 14 (duel)
  { left: 83, top: 85 },  // 43: Rota 13 (grass)
  { left: 83, top: 79 },  // 44: Rota 12 (event/water)

  // ── Rota 21 (water, voltando para Cinnabar pelo sul) ─────────────────────
  { left: 74, top: 89 },  // 45: Rota 21 (grass/water)
  { left: 56, top: 89 },  // 46: Rota 21 (event/water)

  // ── Cinnabar Island (canto inferior esquerdo) ────────────────────────────
  { left: 13, top: 88 },  // 47: Cinnabar Island (special)
  { left: 13, top: 82 },  // 48: Cinnabar Island Gym (gym)

  // ── Rota 20 → Seafoam → Rota 19 → Caverna Misteriosa (subindo costa W) ──
  { left: 13, top: 76 },  // 49: Rota 20 (grass/water)
  { left: 13, top: 70 },  // 50: Seafoam Islands (special/water)
  { left: 13, top: 64 },  // 51: Rota 19 (grass/water)
  { left: 13, top: 58 },  // 52: Rota 19 (duel/water)
  { left: 13, top: 52 },  // 53: Caverna Misteriosa (special)

  // ── Saffron City + Silph Co. (centro) ────────────────────────────────────
  { left: 57, top: 44 },  // 54: Saffron City Gym (gym)
  { left: 57, top: 51 },  // 55: Silph Co. (event)

  // ── Rota 9 → Rota 10 → Power Plant → Rock Tunnel (indo para leste) ───────
  { left: 66, top: 44 },  // 56: Rota 9 (grass)
  { left: 75, top: 37 },  // 57: Rota 10 (event)
  { left: 84, top: 30 },  // 58: Power Plant (special)
  { left: 84, top: 37 },  // 59: Rock Tunnel (grass)
  { left: 84, top: 44 },  // 60: Rock Tunnel (duel)
  { left: 75, top: 44 },  // 61: Rota 10 (event)

  // ── Viridian City Gym → Rota 22/23 → Victory Road → Pokemon League ───────
  { left: 21, top: 44 },  // 62: Viridian City Gym (gym)
  { left: 13, top: 44 },  // 63: Rota 22 (duel)
  { left: 13, top: 37 },  // 64: Rota 23 (grass)
  { left: 13, top: 31 },  // 65: Rota 23 (event)
  { left: 13, top: 25 },  // 66: Victory Road (duel)
  { left: 13, top: 21 },  // 67: Victory Road (grass)
  { left: 13, top: 17 },  // 68: Victory Road (duel)
  { left: 13, top: 13 },  // 69: Victory Road (event)
  { left: 11, top:  9 },  // 70: Pokémon League (league)
]

export function getTilePosition(tileId) {
  return TILE_POSITIONS[tileId] ?? { left: 50, top: 50 }
}
