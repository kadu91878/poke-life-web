"""
Mecânicas básicas do jogo: dados, cálculo de batalha, pontuação.

Convenção de battle_effect:
  Efeitos de score (modificam o cálculo do vencedor):
    critical_hit    — rola dado extra, usa maior resultado
    earthquake      — +1x BP de bônus ao score
    swift           — +2 flat ao score
    shadow_ball     — critical_hit + pós-batalha: perdedor perde 1 FR
    flame_body      — earthquake + pós-batalha: perdedor perde 1 FR
    static_zapdos   — rola 2 dados extras, usa o melhor
    multiscale      — earthquake + ignora habilidades do oponente
    solar_beam      — +3 BP de bônus (ativo pelo jogador)

  Efeitos pré-batalha (modificam dado/BP do oponente antes do score):
    intimidate      — oponente: dado -1 (mín 1)
    thick_fat       — oponente: BP -2 (mín 1)
    pressure        — oponente: re-rola dado, usa menor
    pressure_max    — oponente: dado fixo = 1
    cute_charm_battle — oponente: usa o menor de 2 rolls
    transform       — copia BP do oponente

  Efeitos pós-batalha (aplicados em state.py após resultado):
    poison_sting, super_fang, curse, shed_skin,
    shadow_ball (duplo), flame_body (duplo),
    wing_attack, hyper_voice, dynamic_punch
"""
import random

# ── Tabela de vantagem de tipo ────────────────────────────────────────────────
# Regra: +1 ao BP para CADA tipo do Pokémon adversário que o atacante vence.
# Fonte: tabela canônica de tipos Pokémon Gen 1–2.
TYPE_CHART: dict[str, frozenset] = {
    'Normal':   frozenset(),
    'Fire':     frozenset({'Grass', 'Ice', 'Bug', 'Steel'}),
    'Water':    frozenset({'Fire', 'Ground', 'Rock'}),
    'Grass':    frozenset({'Water', 'Ground', 'Rock'}),
    'Electric': frozenset({'Water', 'Flying'}),
    'Ice':      frozenset({'Grass', 'Ground', 'Flying', 'Dragon'}),
    'Fighting': frozenset({'Normal', 'Ice', 'Rock', 'Dark', 'Steel'}),
    'Poison':   frozenset({'Grass', 'Fairy'}),
    'Ground':   frozenset({'Fire', 'Electric', 'Poison', 'Rock', 'Steel'}),
    'Flying':   frozenset({'Grass', 'Fighting', 'Bug'}),
    'Psychic':  frozenset({'Fighting', 'Poison'}),
    'Bug':      frozenset({'Grass', 'Psychic', 'Dark'}),
    'Rock':     frozenset({'Fire', 'Ice', 'Flying', 'Bug'}),
    'Ghost':    frozenset({'Psychic', 'Ghost'}),
    'Dragon':   frozenset({'Dragon'}),
    'Dark':     frozenset({'Psychic', 'Ghost'}),
    'Steel':    frozenset({'Ice', 'Rock', 'Fairy'}),
    'Fairy':    frozenset({'Fighting', 'Dragon', 'Dark'}),
}


def calculate_type_bonus(attacker_types: list, defender_types: list) -> int:
    """
    Retorna +1 para cada tipo do defensor que o atacante vence.

    Exemplos:
      Fire vs Grass/Poison  → Fire bate Grass → +1
      Water vs Rock/Ground  → Water bate Rock e Ground → +2
    """
    bonus = 0
    for a_type in (attacker_types or []):
        advantages = TYPE_CHART.get(a_type, frozenset())
        for d_type in (defender_types or []):
            if d_type in advantages:
                bonus += 1
    return bonus


def roll_dice() -> int:
    """Rola um dado de 6 faces."""
    return random.randint(1, 6)


def roll_movement_dice() -> int:
    """Rola o dado usado apenas para movimentacao."""
    return roll_dice()


def roll_capture_dice() -> int:
    """Rola o dado usado apenas para tentativas de captura."""
    return roll_dice()


def roll_battle_dice() -> int:
    """Rola o dado usado apenas em fluxos de batalha."""
    return roll_dice()


def roll_team_rocket_dice() -> int:
    """Rola o dado usado apenas no tile da Equipe Rocket."""
    return roll_dice()


def roll_game_corner_dice() -> int:
    """Rola o dado usado apenas no fluxo do Game Corner."""
    return roll_dice()


def roll_market_dice() -> int:
    """Rola o dado usado apenas em fluxos de PokéMarket."""
    return roll_dice()


# ── Score de batalha ──────────────────────────────────────────────────────────

def _score_with_effect(bp: int, roll: int, battle_effect: str | None) -> int:
    """
    Calcula score de batalha a partir do BP efetivo e do dado já modificado.
    Aplica efeitos que alteram o cálculo de score do próprio Pokémon.
    """
    if battle_effect in ('critical_hit', 'shadow_ball'):
        # Rola dado extra; usa o maior resultado
        extra = random.randint(1, 6)
        return bp * max(roll, extra)

    if battle_effect == 'static_zapdos':
        # Rola 2 dados extras; usa o melhor entre os 3
        extra1, extra2 = random.randint(1, 6), random.randint(1, 6)
        return bp * max(roll, extra1, extra2)

    if battle_effect in ('earthquake', 'flame_body', 'multiscale'):
        # +1x BP de bônus
        return bp * roll + bp

    if battle_effect == 'swift':
        # +2 flat ao score total
        return bp * roll + 2

    if battle_effect == 'solar_beam':
        # +3 BP de bônus (ativado pelo jogador antes da batalha)
        return (bp + 3) * roll

    # Sem efeito ou efeito pós-batalha/pré-batalha
    return bp * roll


def calculate_battle_score(pokemon: dict, dice_roll: int) -> int:
    """
    Calcula o score de batalha de um Pokémon.

    Usa o campo `battle_effect` do Pokémon para aplicar modificadores de score.
    Efeitos que dependem do oponente (intimidate, thick_fat, etc.) são
    resolvidos em resolve_duel() antes de chamar esta função.

    score = f(battle_points, dice_roll, battle_effect)
    """
    bp = pokemon.get('battle_points', 1)
    battle_effect = pokemon.get('battle_effect')
    return _score_with_effect(bp, dice_roll, battle_effect)


# ── Duelo principal ───────────────────────────────────────────────────────────

def resolve_duel(
    challenger_pokemon: dict,
    defender_pokemon: dict,
    *,
    challenger_roll: int | None = None,
    defender_roll: int | None = None,
    battle_roll_fn=roll_battle_dice,
) -> dict:
    """
    Resolve um duelo entre dois Pokémon.

    Fluxo:
      1. Rola dados para ambos.
      2. Aplica efeitos pré-batalha (que modificam dado/BP do oponente).
      3. Calcula scores com battle_effect de score de cada um.
      4. Retorna resultado com informações suficientes para
         state.py aplicar efeitos pós-batalha.

    Retorna dict com:
      challenger_roll, defender_roll — dados (após modificações pré-batalha)
      challenger_score, defender_score — scores finais
      challenger_wins — bool
      is_tie — bool indicando empate de score
      challenger_battle_effect, defender_battle_effect — para pós-batalha
    """
    ch_roll = challenger_roll if challenger_roll is not None else battle_roll_fn()
    def_roll = defender_roll if defender_roll is not None else battle_roll_fn()

    ch_bp = challenger_pokemon.get('battle_points', 1)
    def_bp = defender_pokemon.get('battle_points', 1)

    # Vantagem de tipo: +1 BP por tipo do adversário que o atacante vence
    ch_types = challenger_pokemon.get('types', [])
    def_types = defender_pokemon.get('types', [])
    ch_type_bonus = calculate_type_bonus(ch_types, def_types)
    def_type_bonus = calculate_type_bonus(def_types, ch_types)
    ch_bp += ch_type_bonus
    def_bp += def_type_bonus

    # Efeitos originais (antes de qualquer anulação por Multiscale)
    ch_effect_orig = challenger_pokemon.get('battle_effect')
    def_effect_orig = defender_pokemon.get('battle_effect')

    # Multiscale: ignora habilidades do oponente
    ch_effect = ch_effect_orig if def_effect_orig != 'multiscale' else None
    def_effect = def_effect_orig if ch_effect_orig != 'multiscale' else None

    # Transform: copia BP do oponente (antes de Thick Fat para evitar loop)
    if ch_effect == 'transform':
        ch_bp = defender_pokemon.get('battle_points', 1)
    if def_effect == 'transform':
        def_bp = challenger_pokemon.get('battle_points', 1)

    # Thick Fat: reduz BP do oponente em 2 (mín 1)
    if ch_effect == 'thick_fat':
        def_bp = max(1, def_bp - 2)
    if def_effect == 'thick_fat':
        ch_bp = max(1, ch_bp - 2)

    # Intimidate: dado do oponente -1 (mín 1)
    if ch_effect == 'intimidate':
        def_roll = max(1, def_roll - 1)
    if def_effect == 'intimidate':
        ch_roll = max(1, ch_roll - 1)

    # Pressure (Articuno): oponente re-rola dado, usa menor
    if ch_effect == 'pressure':
        def_roll = min(def_roll, battle_roll_fn())
    if def_effect == 'pressure':
        ch_roll = min(ch_roll, battle_roll_fn())

    # Pressure Max (Mewtwo): dado do oponente = 1
    if ch_effect == 'pressure_max':
        def_roll = 1
    if def_effect == 'pressure_max':
        ch_roll = 1

    # Cute Charm Battle (Jigglypuff): oponente usa menor de 2 rolls
    if ch_effect == 'cute_charm_battle':
        def_roll = min(def_roll, battle_roll_fn())
    if def_effect == 'cute_charm_battle':
        ch_roll = min(ch_roll, battle_roll_fn())

    # Calcula scores com BP efetivo e dado (já modificados pré-batalha)
    score_ch = _score_with_effect(ch_bp, ch_roll, ch_effect)
    score_def = _score_with_effect(def_bp, def_roll, def_effect)

    is_tie = score_ch == score_def
    challenger_wins = score_ch > score_def

    return {
        'challenger_roll': ch_roll,
        'defender_roll': def_roll,
        'challenger_score': score_ch,
        'defender_score': score_def,
        'challenger_wins': challenger_wins,
        'is_tie': is_tie,
        # Efeitos originais (para pós-batalha em state.py)
        'challenger_battle_effect': ch_effect_orig,
        'defender_battle_effect': def_effect_orig,
        # Bônus de tipo aplicados ao BP (já incluídos nos scores)
        'challenger_type_bonus': ch_type_bonus,
        'defender_type_bonus': def_type_bonus,
    }


def can_evolve(pokemon: dict) -> bool:
    """Verifica se um Pokémon pode evoluir após vitória em duelo."""
    return pokemon.get('evolves_to') is not None


def calculate_final_scores(players: list) -> list:
    """
    Calcula pontuações finais após o Pokemon League.
    Total = soma dos MPs dos Pokémon atuais + badges×20 + pontos de cartas/eventos + pontos da Liga.
    """
    results = []
    for player in players:
        pokemon_mp = sum(p.get('master_points', 0) for p in player.get('pokemon', []))
        if player.get('starter_pokemon'):
            pokemon_mp += player['starter_pokemon'].get('master_points', 0)

        badge_mp = len(player.get('badges', [])) * 20
        bonus_points = player.get('bonus_points', 0)
        league_bonus = player.get('league_bonus', 0)
        total = pokemon_mp + badge_mp + bonus_points + league_bonus

        results.append({
            'player_id': player['id'],
            'player_name': player['name'],
            'pokemon_mp': pokemon_mp,
            'badge_mp': badge_mp,
            'bonus_points': bonus_points,
            'league_bonus': league_bonus,
            'total': total,
        })

    results.sort(key=lambda x: x['total'], reverse=True)
    return results


def resolve_gym_battle(
    player: dict,
    gym: dict,
    *,
    player_roll: int | None = None,
    leader_roll: int | None = None,
) -> dict:
    """
    Resolve batalha automatizada contra um líder de ginásio.
    O jogador usa seu Pokémon mais forte. O líder tem stats fixos.
    """
    pokemon_pool = list(player.get('pokemon', []))
    if player.get('starter_pokemon'):
        pokemon_pool.append(player['starter_pokemon'])

    if not pokemon_pool:
        return {'player_wins': False, 'reason': 'Sem Pokémon'}

    best_pokemon = max(pokemon_pool, key=lambda p: p.get('battle_points', 0))

    gym_leader = {
        'name': gym.get('leader_name', 'Líder'),
        'battle_points': gym.get('leader_bp', 5),
        'ability_type': 'none',
        'battle_effect': None,
    }

    roll_player = player_roll if player_roll is not None else roll_battle_dice()
    roll_leader = leader_roll if leader_roll is not None else roll_battle_dice()
    score_player = calculate_battle_score(best_pokemon, roll_player)
    score_leader = calculate_battle_score(gym_leader, roll_leader)

    player_wins = score_player >= score_leader  # Empate = vitória do jogador no ginásio

    return {
        'player_wins': player_wins,
        'pokemon_used': best_pokemon,
        'roll_player': roll_player,
        'roll_leader': roll_leader,
        'score_player': score_player,
        'score_leader': score_leader,
        'badge': gym.get('badge') if player_wins else None,
        'master_points': 20 if player_wins else 0,
    }


def resolve_elite_four(
    player: dict,
    elite: dict,
    *,
    player_roll: int | None = None,
    elite_roll: int | None = None,
) -> dict:
    """Resolve batalha contra membro da Elite 4 / Campeão."""
    pokemon_pool = list(player.get('pokemon', []))
    if player.get('starter_pokemon'):
        pokemon_pool.append(player['starter_pokemon'])

    if not pokemon_pool:
        return {'player_wins': False, 'bonus': 0}

    best_pokemon = max(pokemon_pool, key=lambda p: p.get('battle_points', 0))

    elite_bp = elite.get('battle_points', 7)
    roll_player = player_roll if player_roll is not None else roll_battle_dice()
    roll_elite = elite_roll if elite_roll is not None else roll_battle_dice()
    score_player = calculate_battle_score(best_pokemon, roll_player)
    score_elite = elite_bp * roll_elite

    player_wins = score_player >= score_elite

    return {
        'player_wins': player_wins,
        'bonus': elite.get('bonus_mp', 15) if player_wins else 0,
        'roll_player': roll_player,
        'roll_elite': roll_elite,
    }
