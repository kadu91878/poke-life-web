"""
Catálogo de habilidades do jogo Pokémon Life.

Este módulo é puramente declarativo — contém metadados sobre todas as
habilidades do jogo: ativas, passivas e efeitos de batalha.

Responsabilidades:
  - Documentar cada habilidade (descrição, fases permitidas, status)
  - Servir como índice de referência para implementadores
  - Distinguir habilidades implementadas das pendentes

A lógica de execução fica em:
  - state.py  → habilidades ativas  (_ACTIVE_ABILITY_HANDLERS + use_ability)
  - mechanics.py → efeitos de batalha (_score_with_effect + resolve_duel)
  - state.py  → passivos de batalha (_apply_post_battle_effects)
"""


# ── Habilidades Ativas ────────────────────────────────────────────────────────
# Acionadas pelo jogador durante o turno via use_ability().
#
# Campos:
#   description     — texto explicativo para o jogador
#   allowed_phases  — fases do turno em que pode ser usada
#   requires_target — precisa de target_id ou target_position
#   target_type     — 'player' | 'position' | None
#   implemented     — True se há handler em state._ACTIVE_ABILITY_HANDLERS
#   notes           — observações de implementação

ACTIVE_ABILITY_METADATA: dict[str, dict] = {
    'hurricane': {
        'description': 'Move 5 casas em linha reta (substitui rolagem de dado)',
        'allowed_phases': ['roll'],
        'requires_target': False,
        'target_type': None,
        'implemented': True,
    },
    'extreme_speed': {
        'description': 'Move 4 casas rapidamente (substitui rolagem de dado)',
        'allowed_phases': ['roll'],
        'requires_target': False,
        'target_type': None,
        'implemented': True,
    },
    'teleport': {
        'description': 'Teleporta para qualquer posição já visitada (0 até posição atual - 1)',
        'allowed_phases': ['roll'],
        'requires_target': True,
        'target_type': 'position',
        'implemented': True,
    },
    'water_gun': {
        'description': 'Avança 2 casas extras após rolar o dado',
        'allowed_phases': ['action'],
        'requires_target': False,
        'target_type': None,
        'implemented': True,
    },
    'hydro_pump': {
        'description': 'Empurra um oponente 3 casas para trás',
        'allowed_phases': ['roll', 'action'],
        'requires_target': True,
        'target_type': 'player',
        'implemented': True,
    },
    'compound_eyes': {
        'description': 'Próxima captura não gasta Pokébola',
        'allowed_phases': ['action'],
        'requires_target': False,
        'target_type': None,
        'implemented': True,
    },
    'run_away': {
        'description': 'Foge de uma carta de evento negativa sem sofrer efeito',
        'allowed_phases': ['event'],
        'requires_target': False,
        'target_type': None,
        'implemented': True,
    },
    'psychic': {
        'description': 'Espia a próxima carta de evento sem comprá-la',
        'allowed_phases': ['roll', 'action'],
        'requires_target': False,
        'target_type': None,
        'implemented': True,
    },
    'solar_beam': {
        'description': 'Carrega Solar Beam: na próxima batalha ganha +3 BP',
        'allowed_phases': ['roll', 'action'],
        'requires_target': False,
        'target_type': None,
        'implemented': False,
        'notes': 'Requer flag "solar_beam_charged" no estado do turno; '
                 'battle_effect=solar_beam já aplicado em mechanics._score_with_effect',
    },
    'swords_dance': {
        'description': 'Dobra o BP do Pokémon na próxima batalha deste turno',
        'allowed_phases': ['action'],
        'requires_target': False,
        'target_type': None,
        'implemented': False,
        'notes': 'Precisa de flag temporária no estado do turno',
    },
    'growth': {
        'description': 'Compra 1 carta de Pokémon adicional para captura',
        'allowed_phases': ['action'],
        'requires_target': False,
        'target_type': None,
        'implemented': False,
    },
    'minimize': {
        'description': 'Esquiva do próximo duelo recebido neste turno',
        'allowed_phases': ['roll', 'action'],
        'requires_target': False,
        'target_type': None,
        'implemented': False,
        'notes': 'Requer flag "minimize_active" no estado do turno',
    },
    'tail_whip': {
        'description': 'Reduz BP de um oponente em 1 até o fim do turno dele',
        'allowed_phases': ['roll', 'action'],
        'requires_target': True,
        'target_type': 'player',
        'implemented': False,
        'notes': 'Requer debuff temporário no estado do oponente',
    },
    'thunder_wave': {
        'description': 'Paralisa um oponente: ele perde a fase de ação no próximo turno',
        'allowed_phases': ['roll', 'action'],
        'requires_target': True,
        'target_type': 'player',
        'implemented': False,
        'notes': 'Requer status "paralyzed" no estado do jogador alvo',
    },
    'smokescreen': {
        'description': 'Oponente rola dado com -2 no próximo turno',
        'allowed_phases': ['roll', 'action'],
        'requires_target': True,
        'target_type': 'player',
        'implemented': False,
        'notes': 'Requer debuff "smokescreen_turns" no estado do jogador alvo',
    },
    'attract': {
        'description': 'Oponente não pode desafiar você para duelo até o seu próximo turno',
        'allowed_phases': ['roll', 'action'],
        'requires_target': True,
        'target_type': 'player',
        'implemented': False,
        'notes': 'Requer flag "infatuated_by" no estado do jogador alvo',
    },
    'heal': {
        'description': 'Recupera 1 Full Restore',
        'allowed_phases': ['action'],
        'requires_target': False,
        'target_type': None,
        'implemented': False,
    },
    'recover': {
        'description': 'Recupera 2 Pokébolas',
        'allowed_phases': ['action'],
        'requires_target': False,
        'target_type': None,
        'implemented': False,
    },
}


# ── Habilidades Passivas ──────────────────────────────────────────────────────
# Sempre ativas; nenhuma ação do jogador é necessária.
# Verificadas em pontos específicos do engine (campo "checked_in").

PASSIVE_ABILITY_METADATA: dict[str, dict] = {
    'Water Veil': {
        'trigger': 'post_battle_loss',
        'description': 'Imune a perder Full Restore como resultado de batalha',
        'implemented': True,
        'checked_in': 'state._apply_post_battle_effects → loser_immune_fr',
    },
    'Rock Head': {
        'trigger': 'post_battle_loss',
        'description': 'Imune a recuar por efeitos de movimento pós-batalha (hyper_voice)',
        'implemented': True,
        'checked_in': 'state._apply_post_battle_effects → loser_immune_pushback',
    },
    'Synchronize': {
        'trigger': 'post_battle_loss',
        'description': 'Copia o battle_effect do Pokémon oponente por uma rodada',
        'implemented': False,
        'checked_in': None,
        'notes': 'Precisa de flag "synchronized_effect" no estado do turno',
    },
    'Flame Body': {
        'trigger': 'post_battle_winner_effect',
        'description': 'Já implementado como battle_effect: earthquake + perdedor perde 1 FR',
        'implemented': True,
        'checked_in': 'mechanics._score_with_effect + state._apply_post_battle_effects',
        'notes': 'Funciona via battle_effect="flame_body" — não precisa de lógica passiva separada',
    },
    'Static': {
        'trigger': 'post_battle_loss',
        'description': 'Quando perde batalha, paralisa o vencedor por 1 turno',
        'implemented': False,
        'checked_in': None,
        'notes': 'Requer verificação do PERDEDOR em _apply_post_battle_effects',
    },
    'Intimidate': {
        'trigger': 'pre_battle',
        'description': 'Já implementado como battle_effect: dado do oponente -1',
        'implemented': True,
        'checked_in': 'mechanics.resolve_duel → pré-batalha',
        'notes': 'Funciona via battle_effect="intimidate"',
    },
    'Thick Fat': {
        'trigger': 'pre_battle',
        'description': 'Já implementado como battle_effect: BP do oponente -2',
        'implemented': True,
        'checked_in': 'mechanics.resolve_duel → pré-batalha',
    },
    'Shed Skin': {
        'trigger': 'post_battle_win',
        'description': 'Já implementado como battle_effect: vencedor recupera 1 FR',
        'implemented': True,
        'checked_in': 'state._apply_post_battle_effects',
    },
    'Poison Point': {
        'trigger': 'post_battle_loss',
        'description': 'Quando perde batalha, o vencedor perde 1 FR (contato com veneno)',
        'implemented': False,
        'checked_in': None,
        'notes': 'Verifica o PERDEDOR — efeito reverso (raro, implementar depois de Static)',
    },
    'Cute Charm': {
        'trigger': 'post_capture',
        'description': 'Pokémon adjacentes do mesmo tipo têm custo de captura reduzido',
        'implemented': False,
        'checked_in': None,
        'notes': 'cute_charm_battle já implementado como pré-batalha; este é o efeito de captura',
    },
    'Hustle': {
        'trigger': 'pre_roll',
        'description': 'Uma vez por partida: rola 2 dados e usa o maior',
        'implemented': False,
        'checked_in': None,
    },
    'Run Away': {
        'trigger': 'on_event',
        'description': 'Já implementado como habilidade ativa: foge de eventos negativos',
        'implemented': True,
        'checked_in': 'state.use_ability (run_away handler) + state.resolve_event',
    },
    'Compound Eyes': {
        'trigger': 'on_capture',
        'description': 'Já implementado como habilidade ativa: captura sem gastar Pokébola',
        'implemented': True,
        'checked_in': 'state.use_ability (compound_eyes handler)',
    },
}


# ── Efeitos de Batalha ────────────────────────────────────────────────────────
# Aplicados automaticamente quando o Pokémon batalha.
# Ver engine/mechanics.py para a implementação de cada fase.
#
# Fases:
#   score   — modifica o cálculo de score do próprio Pokémon
#   pre     — modifica dado ou BP do OPONENTE antes do cálculo
#   post    — efeito aplicado APÓS a batalha (vencedor sobre perdedor)

BATTLE_EFFECT_METADATA: dict[str, dict] = {
    # ── Score effects ─────────────────────────────────────────────────────
    'critical_hit': {
        'phase': 'score',
        'description': 'Rola dado extra; usa o maior resultado',
        'implemented': True,
    },
    'earthquake': {
        'phase': 'score',
        'description': '+1× BP de bônus ao score final (score = BP×roll + BP)',
        'implemented': True,
    },
    'swift': {
        'phase': 'score',
        'description': '+2 pontos flat ao score final',
        'implemented': True,
    },
    'shadow_ball': {
        'phase': 'score+post',
        'description': 'critical_hit + perdedor perde 1 Full Restore',
        'implemented': True,
    },
    'flame_body': {
        'phase': 'score+post',
        'description': 'earthquake + perdedor perde 1 Full Restore',
        'implemented': True,
    },
    'multiscale': {
        'phase': 'score+pre',
        'description': 'earthquake + ignora habilidades/efeitos do oponente',
        'implemented': True,
    },
    'solar_beam': {
        'phase': 'score',
        'description': '+3 BP de bônus (score = (BP+3)×roll), requer ativação prévia',
        'implemented': True,
        'notes': 'O bonus já está em mechanics._score_with_effect; a ativação via use_ability está pendente',
    },
    # ── Pre-battle effects ────────────────────────────────────────────────
    'intimidate': {
        'phase': 'pre',
        'description': 'Dado do oponente -1 (mínimo 1)',
        'implemented': True,
    },
    'thick_fat': {
        'phase': 'pre',
        'description': 'BP do oponente -2 (mínimo 1)',
        'implemented': True,
    },
    'pressure': {
        'phase': 'pre',
        'description': 'Oponente re-rola dado e usa o menor dos dois',
        'implemented': True,
    },
    'pressure_max': {
        'phase': 'pre',
        'description': 'Dado do oponente fixo em 1',
        'implemented': True,
    },
    'cute_charm_battle': {
        'phase': 'pre',
        'description': 'Oponente usa o menor de 2 rolls',
        'implemented': True,
    },
    'transform': {
        'phase': 'pre',
        'description': 'Copia o BP do oponente para este Pokémon',
        'implemented': True,
    },
    # ── Post-battle effects ───────────────────────────────────────────────
    'poison_sting': {
        'phase': 'post',
        'description': 'Vencedor: perdedor perde 1 Full Restore',
        'implemented': True,
    },
    'super_fang': {
        'phase': 'post',
        'description': 'Vencedor rouba 1 Pokébola do perdedor',
        'implemented': True,
    },
    'curse': {
        'phase': 'post',
        'description': 'Perdedor perde 5 Master Points extras',
        'implemented': True,
    },
    'shed_skin': {
        'phase': 'post',
        'description': 'Vencedor recupera 1 Full Restore',
        'implemented': True,
    },
    'wing_attack': {
        'phase': 'post',
        'description': 'Vencedor avança 1 casa extra no tabuleiro',
        'implemented': True,
    },
    'hyper_voice': {
        'phase': 'post',
        'description': 'Perdedor recua 2 casas no tabuleiro (bloqueado por Rock Head)',
        'implemented': True,
    },
    'dynamic_punch': {
        'phase': 'post',
        'description': 'Perdedor perde 1 item aleatório',
        'implemented': False,
        'notes': 'Depende do sistema de itens (ItemCard) — pendente',
    },
    'synchronize': {
        'phase': 'post',
        'description': 'Copia o battle_effect do Pokémon adversário por 1 rodada',
        'implemented': False,
        'notes': 'Precisa de flag "synchronized_effect" no estado do turno',
    },
}


# ── Helpers de consulta ───────────────────────────────────────────────────────

def is_ability_implemented(ability_action: str) -> bool:
    """Retorna True se a habilidade ativa tem handler registrado."""
    meta = ACTIVE_ABILITY_METADATA.get(ability_action)
    return bool(meta and meta.get('implemented', False))


def get_allowed_phases(ability_action: str) -> list[str]:
    """Retorna as fases em que a habilidade pode ser usada."""
    meta = ACTIVE_ABILITY_METADATA.get(ability_action)
    return meta.get('allowed_phases', []) if meta else []


def requires_target(ability_action: str) -> bool:
    """Retorna True se a habilidade requer target_id ou target_position."""
    meta = ACTIVE_ABILITY_METADATA.get(ability_action)
    return bool(meta and meta.get('requires_target', False))


def get_pending_abilities() -> list[str]:
    """Lista habilidades ativas declaradas mas ainda não implementadas."""
    return [k for k, v in ACTIVE_ABILITY_METADATA.items() if not v.get('implemented', True)]
