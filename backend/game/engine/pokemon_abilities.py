"""
Camada canônica de habilidades de Pokémon derivada do cards_metadata.json.

Objetivos:
  - separar definição estática da habilidade do estado runtime
  - permitir reconstrução idempotente em save/load/normalize
  - oferecer snapshots prontos para o frontend
  - expor grupos genéricos de habilidade suportados pela engine atual

Esta camada NÃO consome cargas nem aplica efeitos por si só.
Ela apenas sincroniza definição/runtime e oferece helpers para
os fluxos do engine decidirem quando e como resolver a habilidade.
"""
from __future__ import annotations

import copy
import re
from typing import Any

ABILITY_RUNTIME_VERSION = 1
PRIMARY_ABILITY_ID = 'primary'

_OPPOSITE_DICE_FACE = {1: 6, 2: 5, 3: 4, 4: 3, 5: 2, 6: 1}


def _slug(value: Any) -> str:
    normalized = re.sub(r'[^a-z0-9]+', '_', str(value or '').strip().lower())
    return normalized.strip('_')


def _to_int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _effect_label(effect_kind: str, params: dict[str, Any] | None = None) -> str:
    params = params or {}
    if effect_kind == 'move_roll_reroll':
        return 'Rerrolar movimento'
    if effect_kind == 'move_roll_delta':
        return 'Ajustar resultado do movimento'
    if effect_kind == 'move_roll_set':
        return 'Alterar resultado do movimento'
    if effect_kind == 'move_roll_multiplier':
        return 'Dobrar movimento'
    if effect_kind == 'move_roll_opposite_side':
        return 'Lado oposto do dado'
    if effect_kind == 'move_roll_divide':
        return 'Dividir movimento'
    if effect_kind == 'fixed_move':
        steps = params.get('steps')
        return f'Mover {steps} casas' if steps is not None else 'Movimento fixo'
    if effect_kind == 'capture_free_next':
        return 'Captura gratuita'
    if effect_kind == 'cannot_battle':
        return 'Não pode batalhar'
    if effect_kind == 'occupies_extra_slot':
        return 'Ocupa slot extra'
    if effect_kind == 'team_bonus':
        return 'Bônus de equipe'
    if effect_kind == 'battle_score_bonus':
        return 'Bônus no resultado da batalha'
    if effect_kind == 'battle_auto_win_threshold':
        return 'Vitória automática por BP'
    if effect_kind == 'battle_reroll':
        return 'Rerrolar batalha'
    if effect_kind == 'capture_reroll':
        return 'Rerrolar captura'
    if effect_kind == 'event_copy':
        return 'Copiar carta de evento'
    if effect_kind == 'knockout_redirect':
        return 'Redirecionar nocaute'
    if effect_kind == 'knockout_counter_roll':
        return 'Contra-atacar nocaute'
    if effect_kind == 'recharge_all_other_abilities':
        return 'Recarregar habilidades do time'
    if effect_kind == 'team_rocket_protection':
        return 'Proteção contra Equipe Rocket'
    if effect_kind == 'bonus_victory_on_gym_or_league_win':
        return 'Vitória extra em ginásio ou Liga'
    if effect_kind == 'market_tile_item_copy':
        return 'Copiar item do Poké-Mart'
    if effect_kind == 'repeat_previous_move':
        return 'Repetir movimento do jogador anterior'
    if effect_kind == 'event_tile_double_draw_choice':
        return 'Escolher entre 2 cartas de evento'
    if effect_kind == 'clone_in_game_pokemon':
        return 'Clonar Pokémon em jogo'
    if effect_kind == 'heal_other':
        return 'Curar outro Pokémon'
    if effect_kind == 'draw_victory':
        return 'Comprar vitória'
    if effect_kind == 'draw_event':
        return 'Comprar evento'
    if effect_kind == 'event_peek':
        return 'Espiar evento'
    if effect_kind == 'area_capture_free':
        return 'Capturar Pokémon da área'
    if effect_kind == 'evolve_other':
        return 'Evoluir outro Pokémon'
    if effect_kind == 'targeted_move':
        return 'Movimento direcionado'
    if effect_kind == 'move_roll_choice':
        return 'Escolher resultado do dado'
    if effect_kind == 'capture_choice':
        return 'Modificar captura'
    if effect_kind == 'battle_bp_swap':
        return 'Trocar Battle Points'
    if effect_kind == 'tile_type_override':
        to_type = params.get('to', '?')
        from_type = params.get('from')
        if from_type:
            return f'Tratar {from_type} como {to_type}'
        return f'Tratar casa como {to_type}'
    if effect_kind == 'revive_after_knockout':
        return 'Reviver após nocaute'
    if effect_kind == 'mutual_knockout':
        return 'Nocaute mútuo'
    if effect_kind == 'team_rocket_theft_copy':
        return 'Receber o que Team Rocket rouba'
    if effect_kind == 'duel_extra_victory_card':
        return 'Vitória extra em duelo'
    if effect_kind == 'conditional_team_bonus':
        return 'Bônus condicional de equipe'
    if effect_kind == 'battle_bp_per_team_ko':
        return 'BP por nocaute na equipe'
    if effect_kind == 'battle_predict_victory':
        return 'Prever vitória em batalha'
    if effect_kind == 'market_dice_reroll':
        return 'Rerrolar dado de mercado'
    if effect_kind == 'item_slot_increase':
        return 'Aumentar slots de item'
    if effect_kind == 'battle_two_dice_best':
        return 'Dois dados de batalha (melhor)'
    if effect_kind == 'battle_two_dice_worst_opponent':
        return 'Oponente: dois dados (pior)'
    if effect_kind == 'battle_bp_decrease_opponent':
        return 'Reduzir BP do oponente'
    if effect_kind == 'battle_bp_increase_self':
        return 'Aumentar BP próprio'
    if effect_kind == 'stay_put_extra_turn':
        return 'Ficar parado turno extra'
    if effect_kind == 'move_backward_dig':
        return 'Cavar de volta no tabuleiro'
    if effect_kind == 'battle_team_up':
        return 'Batalha em dupla'
    if effect_kind == 'battle_bp_random':
        return 'BP aleatório em batalha'
    if effect_kind == 'battle_bp_two_dice':
        return 'BP determinado por dois dados'
    if effect_kind == 'battle_double_bp_before_roll':
        return 'Dobrar BP antes de rolar'
    if effect_kind == 'nugget_on_battle_six':
        return 'Nugget ao tirar 6 em batalha'
    if effect_kind == 'two_hit_knockout':
        return 'Resistência: dois nocautes'
    if effect_kind == 'battle_loss_give_to_left':
        return 'Ao perder, jogador à esquerda pode capturar'
    if effect_kind == 'no_pokeball_needed':
        return 'Captura sem Pokébola'
    if effect_kind == 'victory_peek':
        return 'Espiar pilha de vitória'
    if effect_kind == 'capture_from_any_area':
        return 'Capturar de qualquer área'
    if effect_kind == 'item_discard_for_capture':
        return 'Descartar itens para capturar'
    if effect_kind == 'evolve_only_through_battle':
        return 'Evolução apenas por batalha'
    if effect_kind == 'nugget_on_release':
        return 'Nugget ao soltar Pokémon'
    if effect_kind == 'receive_item_used_in_duel':
        return 'Receber item usado no duelo'
    if effect_kind == 'move_two_dice_pick':
        return 'Movimento: dois dados, escolha'
    if effect_kind == 'random_gift_roll':
        return 'Presente aleatório'
    if effect_kind == 'move_backward_immune':
        return 'Imune a mover para trás'
    if effect_kind == 'event_immune_negative':
        return 'Imune a eventos negativos'
    if effect_kind == 'transform_clone':
        return 'Transformar e copiar Pokémon'
    if effect_kind == 'evolve_to_highest_stage':
        return 'Evoluir ao estágio final'
    if effect_kind == 'evolve_on_move_roll':
        return 'Evoluir ao tirar número'
    if effect_kind == 'evolve_on_team_add':
        return 'Evoluir ao adicionar Pokémon à equipe'
    if effect_kind == 'evolve_on_teammate_release':
        return 'Evoluir ao soltar parceiro'
    if effect_kind == 'random_evolution_roll':
        return 'Evolução aleatória por dado'
    if effect_kind == 'conditional_evolution':
        return 'Evolução condicional'
    if effect_kind == 'evolve_victory_card_draw':
        return 'Comprar vitórias ao evoluir'
    if effect_kind == 'master_points_on_evolve':
        return 'Pontos Mestre ao evoluir'
    if effect_kind == 'master_points_random_roll':
        return 'Chance de Pontos Mestre'
    if effect_kind == 'pair_required_to_battle':
        return 'Parceiro necessário para batalhar'
    if effect_kind == 'nidoran_find_partner':
        return 'Encontrar parceiro Nidoran'
    if effect_kind == 'choose_no_evolve':
        return 'Escolher não evoluir'
    if effect_kind == 'team_bonus_unevolved':
        return 'Bônus por Pokémon não evoluído'
    if effect_kind == 'add_self_copy_to_team':
        return 'Adicionar cópia ao time'
    if effect_kind == 'fossil_trade_roll':
        return 'Trocar fóssil por Pokémon'
    if effect_kind == 'choose_opponent_pokemon':
        return 'Escolher Pokémon do oponente'
    if effect_kind == 'item_full_restore_enhanced':
        return 'Cura total aprimorada'
    if effect_kind == 'instant_event_battle_win':
        return 'Vitória instantânea em batalha de evento'
    if effect_kind == 'forced_pokemon_immune':
        return 'Imune a Pokémon forçado'
    if effect_kind == 'draw_from_bottom':
        return 'Comprar de baixo da pilha'
    if effect_kind == 'capture_battle_choice':
        return 'Batalhar ao capturar'
    if effect_kind == 'battle_bp_double_if_last':
        return 'Dobrar BP se último Pokémon vivo'
    if effect_kind == 'area_capture_free':
        return 'Capturar da área atual'
    if effect_kind == 'text_rule':
        return 'Regra textual'
    return effect_kind.replace('_', ' ').title()


def _build_effect(
    effect_kind: str,
    *,
    activation_mode: str,
    implemented: bool,
    params: dict[str, Any] | None = None,
    limit_scope: str | None = None,
) -> dict[str, Any]:
    resolved_params = copy.deepcopy(params or {})
    return {
        'effect_kind': effect_kind,
        'label': _effect_label(effect_kind, resolved_params),
        'activation_mode': activation_mode,
        'implemented': bool(implemented),
        'limit_scope': limit_scope,
        'params': resolved_params,
    }


def _infer_effects_from_description(pokemon: dict[str, Any]) -> list[dict[str, Any]]:
    description = str(pokemon.get('ability_description') or '').strip()
    normalized = description.lower()
    pokemon_name = str(
        pokemon.get('current_name')
        or pokemon.get('real_name')
        or pokemon.get('name')
        or ''
    ).strip().lower()
    effects: list[dict[str, Any]] = []

    def add(effect_kind: str, *, activation_mode: str, implemented: bool, params: dict[str, Any] | None = None, limit_scope: str | None = None) -> None:
        effect = _build_effect(
            effect_kind,
            activation_mode=activation_mode,
            implemented=implemented,
            params=params,
            limit_scope=limit_scope,
        )
        signature = (
            effect['effect_kind'],
            effect['activation_mode'],
            effect['implemented'],
            repr(effect['params']),
            effect['limit_scope'],
        )
        if signature not in {
            (
                item['effect_kind'],
                item['activation_mode'],
                item['implemented'],
                repr(item['params']),
                item.get('limit_scope'),
            )
            for item in effects
        }:
            effects.append(effect)

    if 'cannot battle' in normalized:
        add('cannot_battle', activation_mode='automatic_passive', implemented=True)
    if 'takes up two pokéball slots' in normalized or 'takes up two pokeball slots' in normalized:
        add('occupies_extra_slot', activation_mode='automatic_passive', implemented=True)

    if 'rethrow the move dice' in normalized:
        add('move_roll_reroll', activation_mode='prompt_after_move_roll', implemented=True, limit_scope='turn')
    if 'rethrow the battle dice' in normalized:
        add('battle_reroll', activation_mode='battle_prompt', implemented=True, limit_scope='battle')
    if 'rethrow the capture dice' in normalized or 'rethrow the capture or move dice' in normalized:
        add('capture_reroll', activation_mode='capture_prompt', implemented=True, limit_scope='turn')

    if 'whenever your move dice outcome is 4 or 6, you may divide the outcome by 2' in normalized:
        add(
            'move_roll_set',
            activation_mode='prompt_after_move_roll',
            implemented=True,
            params={'absolute_map': {4: 2, 6: 3}},
        )

    if (
        'whenever the outcome of the move dice is 1 / 3 you may move one tile further' in normalized
        and 'when the outcome is 4 / 6 you may move one tile less' in normalized
    ):
        add(
            'move_roll_delta',
            activation_mode='prompt_after_move_roll',
            implemented=True,
            params={'delta_map': {1: 1, 3: 1, 4: -1, 6: -1}},
        )

    if 'whenever the outcome of the move dice is 6, you may change the outcome to 1' in normalized:
        add(
            'move_roll_set',
            activation_mode='prompt_after_move_roll',
            implemented=True,
            params={'absolute_map': {6: 1}},
        )

    if 'you may increase the outcome of the move dice by one' in normalized:
        add(
            'move_roll_delta',
            activation_mode='prompt_after_move_roll',
            implemented=True,
            params={'delta': 1},
        )

    if 'you may decrease the outcome of the move dice by one (not below zero)' in normalized:
        add(
            'move_roll_delta',
            activation_mode='prompt_after_move_roll',
            implemented=True,
            params={'delta': -1, 'min_result': 0},
        )

    if 'you can divide the move dice outcome by 2 (rounded up)' in normalized:
        add(
            'move_roll_divide',
            activation_mode='prompt_after_move_roll',
            implemented=True,
            params={'rounding': 'up', 'divisor': 2},
        )

    if 'you may double the move dice outcome' in normalized:
        add(
            'move_roll_multiplier',
            activation_mode='prompt_after_move_roll',
            implemented=True,
            params={'multiplier': 2},
        )

    if 'you may change the outcome of the move dice to the outcome on the opposite side of the dice' in normalized:
        add(
            'move_roll_opposite_side',
            activation_mode='prompt_after_move_roll',
            implemented=True,
            params={'mapping': copy.deepcopy(_OPPOSITE_DICE_FACE)},
        )

    fixed_distance_matchers = (
        ('you may always move 3 tiles instead of throwing the move dice', 3),
        ('instead of throwing the move dice, you may move 4 tiles', 4),
        ('you may move two tiles instead of throwing the move dice', 2),
        ('you may move one tile instead of throwing the move dice', 1),
    )
    for phrase, steps in fixed_distance_matchers:
        if phrase in normalized:
            add(
                'fixed_move',
                activation_mode='manual_before_roll',
                implemented=True,
                params={'steps': steps},
            )

    if pokemon_name == 'mew' and 'you may always move one tile forward' in normalized:
        add(
            'fixed_move',
            activation_mode='manual_before_roll',
            implemented=True,
            params={'steps': 1},
        )

    if 'ao capturar, não gasta pokébola' in normalized or 'ao capturar, nao gasta pokebola' in normalized:
        add(
            'capture_free_next',
            activation_mode='manual_action',
            implemented=True,
            limit_scope='turn',
        )

    if 'heal one of your other pok' in normalized:
        if 'knocked out in battle' in normalized:
            # Vaporeon: triggered reactively when this pokémon is KO'd in battle
            add(
                'heal_other',
                activation_mode='automatic_passive',
                implemented=True,
                params={'on_ko_in_battle': True},
            )
        else:
            add(
                'heal_other',
                activation_mode='manual_action',
                implemented=True,
                limit_scope='turn',
                params={'heal_limit': 3 if pokemon_name == 'blissey' else 1},
            )
    if 'draw a card from the victory pile' in normalized or 'take a victory card' in normalized:
        _after_duel_loss = 'after losing a duel' in normalized
        add(
            'draw_victory',
            activation_mode='automatic_passive' if _after_duel_loss else 'manual_action',
            implemented=True,
            params={'after_duel_loss': True} if _after_duel_loss else None,
        )
    if 'draw a card from the event pile' in normalized or 'top card of the event discard pile' in normalized:
        _from_discard = 'event discard pile' in normalized
        add(
            'draw_event',
            activation_mode='manual_action',
            implemented=True,
            params={'from_discard': True, 'event_tile_only': True} if _from_discard else None,
        )
    if 'look at the top card of the event pile' in normalized or 'take two cards at once' in normalized:
        add('event_peek', activation_mode='manual_action', implemented=True)
    if 'evolve one of your other pok' in normalized:
        add(
            'evolve_other',
            activation_mode='manual_action',
            implemented=True,
            params={'exclude_self': True},
        )
    if 'cause one of your pok' in normalized:
        add(
            'evolve_other',
            activation_mode='manual_action',
            implemented=True,
            params={'exclude_self': False},
        )
    if 'increases the battle points of all pokémon in your team by 2' in normalized or 'increases the battle points of all pokemon in your team by 2' in normalized:
        add(
            'team_bonus',
            activation_mode='automatic_passive',
            implemented=True,
            params={'flat_bonus': 2},
        )
    if 'recharge all of your pokémon' in normalized or "recharge all of your pokemon's abilities" in normalized:
        add(
            'recharge_all_other_abilities',
            activation_mode='manual_action',
            implemented=True,
            params={'exclude_self': True, 'self_recharge_blocked': True},
        )
    if 'extra battle point' in normalized and 'for each other' in normalized:
        # Beedrill: +1 BP and +10 MP for each other same-named pokemon in team
        ally_name = str(pokemon.get('current_name') or pokemon.get('real_name') or '').strip()
        add('team_bonus', activation_mode='passive', implemented=True, params={
            'bonus_bp_per_ally': 1,
            'bonus_mp_per_ally': 10,
            'ally_name': ally_name,
        })
    if 'whenever another player takes a card from the event pile, you may choose to execute it too' in normalized:
        add('event_copy', activation_mode='event_prompt', implemented=True)
    if 'total battle outcomes are always increased by 8' in normalized:
        add(
            'battle_score_bonus',
            activation_mode='automatic_passive',
            implemented=False,
            params={'score_bonus': 8},
        )
    if 'all opposing pokémon with less than 8 battle points automatically lose' in normalized or 'all opposing pokemon with less than 8 battle points automatically lose' in normalized:
        add(
            'battle_auto_win_threshold',
            activation_mode='automatic_passive',
            implemented=True,
            params={'opponent_bp_lte': 7},
        )
    if 'is knocked out, you may choose to knock out one of your other pok' in normalized:
        add('knockout_redirect', activation_mode='battle_knockout_prompt', implemented=True)
    if 'when wobbuffet loses in battle, throw the dice' in normalized and 'enemy is knocked out instead' in normalized:
        add('knockout_counter_roll', activation_mode='battle_knockout_prompt', implemented=True)
    if 'all assaults from team rocket to fail miserably' in normalized:
        add('team_rocket_protection', activation_mode='automatic_passive', implemented=True)
    if 'whenever you win a gym or league battle with raikou still alive' in normalized:
        add(
            'bonus_victory_on_gym_or_league_win',
            activation_mode='automatic_passive',
            implemented=True,
        )
    if 'whenever any other player receives an item at a market, you receive it too' in normalized:
        add(
            'market_tile_item_copy',
            activation_mode='automatic_passive',
            implemented=True,
            params={'exclude_reward_keys': ['pokeball', 'master_ball']},
        )
    if 'you may move the same amount of tiles as the previous player' in normalized:
        add(
            'repeat_previous_move',
            activation_mode='manual_before_roll',
            implemented=True,
        )
    if 'when landed on an event tile' in normalized and 'take two cards at once and choose which cards to execute' in normalized:
        add(
            'event_tile_double_draw_choice',
            activation_mode='automatic_passive',
            implemented=True,
        )
    if 'you can clone a pkmn currently in game' in normalized and 'no starters or legendaries' in normalized:
        add(
            'clone_in_game_pokemon',
            activation_mode='manual_action',
            implemented=True,
            params={'exclude_starters': True, 'exclude_legendaries': True},
        )
    if 'move forward to a tile no further than five ahead' in normalized:
        add(
            'targeted_move',
            activation_mode='manual_before_roll',
            implemented=True,
            params={'mode': 'choose_forward_steps', 'max_steps': 5},
        )
    elif 'instead of throwing the move dice, you may teleport' in normalized:
        if 'another player' in normalized:
            add('targeted_move', activation_mode='manual_before_roll', implemented=True,
                params={'mode': 'player_teleport'})
        elif 'nearest event tile behind' in normalized:
            add('targeted_move', activation_mode='manual_before_roll', implemented=True,
                params={'mode': 'backward_event_tile'})
        else:
            add('targeted_move', activation_mode='manual_before_roll', implemented=False)
    elif 'move forward to a player on another tile within 5 tiles' in normalized:
        add('targeted_move', activation_mode='manual_before_roll', implemented=True,
            params={'mode': 'player_teleport', 'forward_only': True, 'max_steps': 5})
    if 'you may decide the outcome of the move dice' in normalized:
        add('move_roll_choice', activation_mode='prompt_after_move_roll', implemented=True)
    if 'you may decide the outcome of the capture dice' in normalized:
        add('capture_choice', activation_mode='capture_prompt', implemented=True)
    if 'throw 2 dice at once, and choose the outcome you desire' in normalized:
        add('capture_choice', activation_mode='capture_prompt', implemented=True, params={'two_dice': True})
    if 'switch battle points with the opponent' in normalized:
        add('battle_bp_swap', activation_mode='battle_prompt_before_roll', implemented=True, limit_scope='battle')
    if 'when landed on a tile, you can choose to also execute the next tile' in normalized:
        add('advance_after_landing', activation_mode='manual_action', implemented=True, limit_scope='turn')

    # --- Batch 3: sem parser ---

    # natu / xatu: event_tile_double_draw_choice (different wording from Articuno)
    if 'look at the top two cards of the event pile, and pick one of them' in normalized:
        add('event_tile_double_draw_choice', activation_mode='automatic_passive', implemented=True)

    # hitmontop: auto-win vs low BP opponents (opponent_bp < 7 = lte 6)
    if 'has less than 7 battle points' in normalized and 'automatically wins' in normalized:
        add('battle_auto_win_threshold', activation_mode='automatic_passive', implemented=True,
            params={'opponent_bp_lte': 6})

    # kabuto / kabutops / omanyte / omastar: rethrow any dice
    if 'rethrow any dice throw' in normalized:
        add('move_roll_reroll', activation_mode='prompt_after_move_roll', implemented=True, limit_scope='turn')
        add('battle_reroll', activation_mode='battle_prompt', implemented=True, limit_scope='battle')
        add('capture_reroll', activation_mode='capture_prompt', implemented=True, limit_scope='turn')

    # arbok: move forward to opponent's tile within 5
    if 'move forward to an opponent on another tile within 5 tiles' in normalized:
        add('targeted_move', activation_mode='manual_before_roll', implemented=False,
            params={'mode': 'forward_to_player', 'max_steps': 5})

    # lapras: choose move dice outcome but only on Ocean Route
    if 'decide the outcome of the move dice while on the ocean route' in normalized:
        add('move_roll_choice', activation_mode='prompt_after_move_roll', implemented=False,
            params={'zone_restriction': 'ocean'})

    # tile_type_override: any grass tile → duel (machop / machoke / machamp)
    if 'treat any grass tile as a duel tile' in normalized:
        if 'you may always' in normalized or 'always treat' in normalized:
            add('tile_type_override', activation_mode='automatic_passive', implemented=False,
                params={'from': 'grass', 'to': 'duel'})
        else:
            add('tile_type_override', activation_mode='manual_action', implemented=False,
                params={'from': 'grass', 'to': 'duel'}, limit_scope='turn')

    # tile_type_override: landed tile → duel (tentacool / tentacruel)
    if 'treat the tile you landed on as if it were a duel tile' in normalized:
        add('tile_type_override', activation_mode='manual_action', implemented=False,
            params={'to': 'duel'}, limit_scope='turn')

    # tile_type_override: landed tile → grass (bellsprout / weepinbell)
    if 'treat the tile you landed on as a grass tile' in normalized:
        add('tile_type_override', activation_mode='manual_action', implemented=False,
            params={'to': 'grass'}, limit_scope='turn')

    # tile_type_override: landed tile → event (houndour, one charge)
    if 'treat the tile you landed on as if it were an event tile' in normalized:
        add('tile_type_override', activation_mode='manual_action', implemented=False,
            params={'to': 'event'}, limit_scope='turn')

    # tile_type_override: all grass tiles → event (houndoom, always)
    if 'treat grass tiles as if it were event tiles' in normalized:
        add('tile_type_override', activation_mode='automatic_passive', implemented=False,
            params={'from': 'grass', 'to': 'event'})

    # revive_after_knockout: magcargo / slugma
    if 'is ever knocked out, he will be revived after the battle' in normalized:
        add('revive_after_knockout', activation_mode='automatic_passive', implemented=False)

    # mutual_knockout: koffing / weezing
    if 'is knocked out in battle, the opposing pok' in normalized and 'is knocked out too' in normalized:
        add('mutual_knockout', activation_mode='automatic_passive', implemented=False)

    # team_rocket_theft_copy: meowth / persian
    if 'whenever team rocket steals from another player, you receive what is stolen' in normalized:
        add('team_rocket_theft_copy', activation_mode='automatic_passive', implemented=False)

    # duel_extra_victory_card: girafarig
    if 'winning a duel always grants you two victory cards' in normalized:
        add('duel_extra_victory_card', activation_mode='automatic_passive', implemented=False)

    # conditional_team_bonus: geodude / graveler / golem
    if 'additional battle point' in normalized and 'most knocked out pok' in normalized:
        _m = re.search(r'have (\d+) additional battle point', normalized)
        _bonus = int(_m.group(1)) if _m else 1
        add('conditional_team_bonus', activation_mode='automatic_passive', implemented=False,
            params={'condition': 'most_knocked_out', 'flat_bonus': _bonus})

    # battle_bp_per_team_ko: primeape
    if 'every knocked out pok' in normalized and "battle points are increased by 1" in normalized:
        add('battle_bp_per_team_ko', activation_mode='automatic_passive', implemented=False)

    # battle_predict_victory: jigglypuff / wigglytuff
    if 'at the start of any duel or event battle, you may guess who will be victorious' in normalized:
        add('battle_predict_victory', activation_mode='battle_prompt', implemented=False)

    # market_dice_reroll: starmie / staryu
    if 'rethrow the market dice' in normalized:
        add('market_dice_reroll', activation_mode='manual_action', implemented=False, limit_scope='turn')

    # item_slot_increase: starmie / staryu
    if 'items at a time, up from 8' in normalized:
        _m2 = re.search(r'have (\d+) items at a time', normalized)
        _slots = int(_m2.group(1)) if _m2 else 10
        add('item_slot_increase', activation_mode='automatic_passive', implemented=False,
            params={'max_items': _slots})

    # battle_two_dice_best: hitmonchan
    if 'throw two dice at once (the highest outcome counts)' in normalized:
        add('battle_two_dice_best', activation_mode='automatic_passive', implemented=False)

    # battle_two_dice_worst_opponent: hitmonlee
    if 'throw two dice at once (the lowest outcome counts)' in normalized:
        add('battle_two_dice_worst_opponent', activation_mode='automatic_passive', implemented=False)

    # battle_bp_decrease_opponent: slowbro
    if 'decreases the battle points of every pok' in normalized and 'in battle by 2' in normalized:
        add('battle_bp_decrease_opponent', activation_mode='automatic_passive', implemented=False,
            params={'bp_decrease': 2})

    # battle_bp_increase_self: slowking
    if 'during battle, you can increase the battle point of one of your pok' in normalized:
        add('battle_bp_increase_self', activation_mode='battle_prompt', implemented=False,
            params={'bp_increase': 2})

    # stay_put_extra_turn: cubone / marowak
    if 'you can stay put on a tile for' in normalized and 'additional turn' in normalized:
        add('stay_put_extra_turn', activation_mode='manual_action', implemented=False, limit_scope='turn')

    # move_backward_dig: diglet / dugtrio
    if 'dig back to a tile no more than five tiles away' in normalized:
        add('move_backward_dig', activation_mode='manual_before_roll', implemented=False,
            params={'max_steps_back': 5})

    # battle_team_up: kangaskhan / nidorina / nidorino
    if 'in battle, combining their battle points' in normalized:
        add('battle_team_up', activation_mode='battle_prompt', implemented=False)

    # battle_bp_random: krabby
    if 'throw a dice to decide its battle points for the duration of the battle' in normalized:
        add('battle_bp_random', activation_mode='automatic_passive', implemented=False)

    # battle_bp_two_dice: kingler
    if 'throw 2 dice to decide its battle points for the duration of the battle' in normalized:
        add('battle_bp_two_dice', activation_mode='automatic_passive', implemented=False)

    # battle_double_bp_before_roll: scizor
    if 'double' in normalized and 'battle points for one dice throw' in normalized:
        add('battle_double_bp_before_roll', activation_mode='battle_prompt_before_roll', implemented=False,
            limit_scope='battle')

    # battle_score_bonus activated (manual): gyarados
    if 'may increase his total battle outcome by' in normalized:
        _m3 = re.search(r'by (\d+) once per battle', normalized)
        _score = int(_m3.group(1)) if _m3 else 10
        add('battle_score_bonus', activation_mode='battle_prompt', implemented=False,
            params={'score_bonus': _score}, limit_scope='battle')

    # nugget_on_battle_six: magnemite / magneton
    if 'throws a 6 in battle, you receive a nugget' in normalized:
        add('nugget_on_battle_six', activation_mode='automatic_passive', implemented=False)

    # two_hit_knockout: shellder / cloyster
    if 'has to lose twice before he is knocked out' in normalized:
        add('two_hit_knockout', activation_mode='automatic_passive', implemented=False)

    # battle_loss_give_to_left + no_pokeball_needed: abra
    if 'loses in battle, the player to your left may add it to his team' in normalized:
        add('battle_loss_give_to_left', activation_mode='automatic_passive', implemented=False)
    if 'does not need to be put in a pok' in normalized and 'ball' in normalized:
        add('no_pokeball_needed', activation_mode='automatic_passive', implemented=False)

    # no_pokeball_needed: voltorb / electrode
    if "doesn't need to be put in a pok" in normalized and 'ball' in normalized:
        add('no_pokeball_needed', activation_mode='automatic_passive', implemented=False)

    # victory_peek: umbreon
    if 'you may always look at the top card of the victory pile' in normalized:
        add('victory_peek', activation_mode='automatic_passive', implemented=False)

    # capture_from_any_area: victreebel
    if 'you may try to catch a pok' in normalized and 'from an area of choice' in normalized:
        add('capture_from_any_area', activation_mode='manual_action', implemented=False)

    # item_discard_for_capture: grimer / muk
    if 'discard 2 items in order to throw the capture dice' in normalized:
        add('item_discard_for_capture', activation_mode='manual_action', implemented=False)

    # evolve_only_through_battle: magikarp
    if 'can only evolve through battle' in normalized:
        add('evolve_only_through_battle', activation_mode='automatic_passive', implemented=False)

    # nugget_on_release: exeggcute
    if 'you receive a nugget if you release' in normalized:
        add('nugget_on_release', activation_mode='automatic_passive', implemented=False)

    # receive_item_used_in_duel: forretress
    if 'an opponent uses an item during a duel with you, you receive the item after the duel' in normalized:
        add('receive_item_used_in_duel', activation_mode='automatic_passive', implemented=False)

    # move_two_dice_pick: gligar
    if 'throw 2 dice at once and pick the outcome you want' in normalized:
        add('move_two_dice_pick', activation_mode='prompt_after_move_roll', implemented=False)

    # random_gift_roll: delibird
    if 'throw the dice for a present' in normalized:
        add('random_gift_roll', activation_mode='manual_action', implemented=False)

    # move_backward_immune: metapod (Portuguese)
    if 'nenhum efeito negativo te move para trás' in normalized:
        add('move_backward_immune', activation_mode='automatic_passive', implemented=False)

    # event_immune_negative: caterpie (Portuguese)
    if 'imune a efeitos negativos de eventos' in normalized:
        add('event_immune_negative', activation_mode='automatic_passive', implemented=False)

    # transform_clone: ditto
    if 'transform into any in-game pok' in normalized and 'copying its battle points and ability' in normalized:
        add('transform_clone', activation_mode='manual_action', implemented=False)

    # evolve_to_highest_stage: dragonair
    if 'evolve it directly to the highest stage possible' in normalized:
        add('evolve_to_highest_stage', activation_mode='manual_action', implemented=False)

    # evolve_on_move_roll: dratini
    if 'if the outcome of your move dice is ever 6' in normalized and 'evolves' in normalized:
        add('evolve_on_move_roll', activation_mode='automatic_passive', implemented=False,
            params={'trigger_roll': 6})

    # random_evolution_roll: eevee
    if 'when evolving eevee, throw the dice' in normalized:
        add('random_evolution_roll', activation_mode='automatic_passive', implemented=False)

    # evolve_on_team_add: weedle
    if 'will evolve when you add another pok' in normalized:
        add('evolve_on_team_add', activation_mode='automatic_passive', implemented=False)

    # evolve_on_teammate_release: mankey
    if 'if you release another pok' in normalized and 'evolve mankey' in normalized:
        add('evolve_on_teammate_release', activation_mode='automatic_passive', implemented=False)

    # conditional_evolution: slowpoke / tyrogue
    if 'when evolving slowpoke' in normalized or 'when evolving tyrogue' in normalized:
        add('conditional_evolution', activation_mode='automatic_passive', implemented=False)

    # evolve_victory_card_draw: scyther
    if 'when scyther evolves, draw victory cards equal to the amount of players' in normalized:
        add('evolve_victory_card_draw', activation_mode='automatic_passive', implemented=False)

    # master_points_on_evolve: kakuna
    if 'master points when' in normalized and 'evolves' in normalized:
        _m4 = re.search(r'receive (\d+) master points', normalized)
        _mp = int(_m4.group(1)) if _m4 else 20
        add('master_points_on_evolve', activation_mode='automatic_passive', implemented=False,
            params={'mp': _mp})

    # master_points_random_roll: pineco
    if 'throw 4 to 6, you receive 10 master points' in normalized:
        add('master_points_random_roll', activation_mode='manual_action', implemented=False)

    # pair_required_to_battle: nidoking / nidoqueen
    if "don't have a nidoqueen" in normalized and "won't battle" in normalized:
        add('pair_required_to_battle', activation_mode='automatic_passive', implemented=False,
            params={'required_partner': 'nidoqueen'})
    if "don't have a nidoking" in normalized and "won't battle" in normalized:
        add('pair_required_to_battle', activation_mode='automatic_passive', implemented=False,
            params={'required_partner': 'nidoking'})

    # nidoran_find_partner: nidoran_female / nidoran_male
    if 'nidoran has no male partner' in normalized and 'you receive nidoran' in normalized:
        add('nidoran_find_partner', activation_mode='manual_action', implemented=False,
            params={'gender': 'male'})
    if 'nidoran has no female partner' in normalized and 'you receive nidoran' in normalized:
        add('nidoran_find_partner', activation_mode='manual_action', implemented=False,
            params={'gender': 'female'})

    # choose_no_evolve + team_bonus_unevolved: venonat
    if 'you may always choose not to evolve your pok' in normalized:
        add('choose_no_evolve', activation_mode='automatic_passive', implemented=False)
    if 'master points bonus for each pok' in normalized and 'not evolved' in normalized:
        add('team_bonus_unevolved', activation_mode='automatic_passive', implemented=False)

    # add_self_copy_to_team: wooper
    if 'you may add a wooper to your team' in normalized:
        add('add_self_copy_to_team', activation_mode='manual_action', implemented=False)

    # fossil_trade_roll: mysterious_fossil
    if 'trade this fossil at a pok' in normalized:
        add('fossil_trade_roll', activation_mode='manual_action', implemented=False)

    # choose_opponent_pokemon: mr_mime
    if 'you may decide which pok' in normalized and 'the opponent uses' in normalized:
        add('choose_opponent_pokemon', activation_mode='automatic_passive', implemented=False)

    # item_full_restore_enhanced: golduck
    if 'when using a full restore, you may choose to heal up to four' in normalized:
        add('item_full_restore_enhanced', activation_mode='automatic_passive', implemented=False)

    # instant_event_battle_win + forced_pokemon_immune: pinsir
    if 'you may instantly win an event battle' in normalized:
        add('instant_event_battle_win', activation_mode='manual_action', implemented=False, limit_scope='turn')
    if 'can no longer force you to use a specific pok' in normalized:
        add('forced_pokemon_immune', activation_mode='automatic_passive', implemented=False)

    # draw_from_bottom: psyduck
    if 'you may always choose to draw from the bottom instead' in normalized:
        add('draw_from_bottom', activation_mode='automatic_passive', implemented=False)

    # capture_battle_choice: sneasel
    if 'whenever you capture a pok' in normalized and 'you may battle it instead of adding it to your team' in normalized:
        add('capture_battle_choice', activation_mode='automatic_passive', implemented=False)

    # battle_bp_double_if_last: snubbull
    if 'last pok' in normalized and 'battle points are doubled' in normalized:
        add('battle_bp_double_if_last', activation_mode='automatic_passive', implemented=False)

    # area_capture_free: aerodactyl
    if 'receive a pok' in normalized and 'from the area you are in' in normalized:
        add('area_capture_free', activation_mode='manual_action', implemented=True)

    if description and not effects:
        add('text_rule', activation_mode='descriptive_only', implemented=False, params={'summary': description})

    return effects


def _build_ability_definition(pokemon: dict[str, Any]) -> dict[str, Any] | None:
    description = str(pokemon.get('ability_description') or '').strip()
    if not description and not pokemon.get('ability_type'):
        return None

    effects = _infer_effects_from_description(pokemon)
    if not effects and not description:
        return None

    preferred_name = next(
        (
            effect['label']
            for effect in effects
            if effect['implemented']
        ),
        None,
    )
    fallback_name = preferred_name or 'Habilidade'
    charges_total = _to_int_or_none(
        pokemon.get('ability_charges_total')
        if pokemon.get('ability_charges_total') is not None
        else pokemon.get('ability_charges')
    )
    return {
        'id': PRIMARY_ABILITY_ID,
        'name': fallback_name,
        'description': description,
        'ability_type': pokemon.get('ability_type') or 'none',
        'charges_total': charges_total,
        'is_optional': ' may ' in f' {description.lower()} ' or (pokemon.get('ability_type') == 'active'),
        'effects': effects,
        'supported': any(effect['implemented'] for effect in effects),
        'engine_hints': {
            'engine_ability_name': pokemon.get('ability') or None,
            'engine_battle_effect': pokemon.get('battle_effect') or None,
        },
    }


def get_static_ability_definitions(pokemon: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(pokemon, dict):
        return []
    definition = _build_ability_definition(pokemon)
    return [definition] if definition else []


def _normalize_runtime_entry(entry: dict[str, Any] | None, *, charges_total: int | None, fallback_used: bool = False) -> dict[str, Any]:
    normalized = copy.deepcopy(entry) if isinstance(entry, dict) else {}
    charges_remaining = _to_int_or_none(normalized.get('charges_remaining'))
    if charges_total is not None:
        if charges_remaining is None:
            charges_remaining = charges_total
        charges_remaining = max(0, min(charges_total, charges_remaining))
    else:
        charges_remaining = None

    used_area_keys = [
        str(area_key)
        for area_key in (normalized.get('used_area_keys') or [])
        if str(area_key).strip()
    ]

    return {
        'charges_remaining': charges_remaining,
        'used_this_turn': bool(normalized.get('used_this_turn', fallback_used)),
        'used_this_battle': bool(normalized.get('used_this_battle', False)),
        'used_this_game': bool(normalized.get('used_this_game', False)),
        'used_area_keys': list(dict.fromkeys(used_area_keys)),
        'resolved_decision_ids': list(dict.fromkeys(str(item) for item in (normalized.get('resolved_decision_ids') or []) if str(item).strip())),
    }


def _previous_player_movement_value(turn: dict[str, Any] | None) -> int | None:
    if not isinstance(turn, dict):
        return None
    try:
        steps = int(turn.get('previous_player_move_steps'))
    except (TypeError, ValueError):
        return None
    return steps if steps > 0 else None


def _attach_ability_snapshots(pokemon: dict[str, Any], *, turn: dict[str, Any] | None = None, player_id: str | None = None, current_player_id: str | None = None, slot_key: str | None = None) -> dict[str, Any]:
    definitions = get_static_ability_definitions(pokemon)
    runtime = copy.deepcopy((pokemon.get('ability_runtime') or {}).get('abilities') or {})
    pending_action = (turn or {}).get('pending_action') or {}
    current_phase = (turn or {}).get('phase')
    is_owner_turn = bool(player_id and current_player_id and player_id == current_player_id)
    can_interact = is_owner_turn and not (
        pending_action
        and pending_action.get('player_id') == player_id
        and pending_action.get('type') != 'ability_decision'
    )

    snapshots: list[dict[str, Any]] = []
    for definition in definitions:
        runtime_entry = _normalize_runtime_entry(
            runtime.get(definition['id']),
            charges_total=definition.get('charges_total'),
            fallback_used=bool(pokemon.get('ability_used')),
        )
        charges_total = definition.get('charges_total')
        charges_remaining = runtime_entry.get('charges_remaining')
        no_charges_left = charges_total is not None and int(charges_remaining or 0) <= 0

        awaiting_decision = False
        if pending_action.get('type') == 'ability_decision' and pending_action.get('player_id') == player_id:
            awaiting_decision = any(
                option.get('slot_key') == slot_key and option.get('ability_id') == definition['id']
                for option in (pending_action.get('options') or [])
            )

        can_activate_now = False
        disabled_reason = None
        manual_actions: list[dict[str, Any]] = []
        supported_effects = [effect for effect in definition.get('effects') or [] if effect.get('implemented')]

        if not supported_effects:
            disabled_reason = 'Sem handler genérico implementado ainda'
        elif no_charges_left:
            disabled_reason = 'Sem cargas restantes'
        elif runtime_entry.get('used_this_turn'):
            disabled_reason = 'Já usada neste turno'

        for effect in supported_effects:
            activation_mode = effect.get('activation_mode')
            if activation_mode != 'manual_before_roll' and activation_mode != 'manual_action':
                continue

            action_variants: list[dict[str, Any]] = []
            params = copy.deepcopy(effect.get('params') or {})
            if effect.get('effect_kind') == 'targeted_move' and params.get('mode') == 'choose_forward_steps':
                max_steps = max(1, int(params.get('max_steps', 1) or 1))
                for steps in range(1, max_steps + 1):
                    action_variants.append({
                        'action_id': _slug(f'fixed_move_{steps}'),
                        'effect_kind': 'fixed_move',
                        'label': f'Mover {steps} casa{"s" if steps != 1 else ""}',
                        'params': {'steps': steps},
                        'supported': True,
                        'can_activate_now': False,
                        'disabled_reason': None,
                    })
            elif effect.get('effect_kind') == 'fixed_move' and params.get('steps_options'):
                available_steps = []
                for value in params.get('steps_options') or []:
                    normalized_step = _to_int_or_none(value)
                    if normalized_step is None or normalized_step <= 0:
                        continue
                    if normalized_step not in available_steps:
                        available_steps.append(normalized_step)
                for steps in available_steps:
                    action_variants.append({
                        'action_id': _slug(f'fixed_move_{steps}'),
                        'effect_kind': 'fixed_move',
                        'label': f'Mover {steps} casa{"s" if steps != 1 else ""}',
                        'params': {'steps': steps},
                        'supported': True,
                        'can_activate_now': False,
                        'disabled_reason': None,
                    })
            elif effect.get('effect_kind') == 'repeat_previous_move':
                previous_steps = _previous_player_movement_value(turn)
                action_variants.append({
                    'action_id': _slug('repeat_previous_move'),
                    'effect_kind': 'fixed_move',
                    'label': (
                        f'Mover {previous_steps} casa{"s" if previous_steps != 1 else ""} como o jogador anterior'
                        if previous_steps is not None
                        else 'Repetir movimento do jogador anterior'
                    ),
                    'params': {'steps': previous_steps},
                    'supported': True,
                    'can_activate_now': False,
                    'disabled_reason': None,
                })
            else:
                action_variants.append({
                    'action_id': _slug(f"{effect['effect_kind']}"),
                    'effect_kind': effect['effect_kind'],
                    'label': effect['label'],
                    'params': params,
                    'supported': True,
                    'can_activate_now': False,
                    'disabled_reason': None,
                })

            for action in action_variants:
                if no_charges_left:
                    action['disabled_reason'] = 'Sem cargas restantes'
                elif runtime_entry.get('used_this_turn'):
                    action['disabled_reason'] = 'Já usada neste turno'
                elif effect.get('effect_kind') == 'repeat_previous_move' and int((action.get('params') or {}).get('steps') or 0) <= 0:
                    action['disabled_reason'] = 'Ainda não há movimento válido do jogador anterior'
                elif not is_owner_turn:
                    action['disabled_reason'] = 'Aguardando sua vez'
                elif activation_mode == 'manual_before_roll':
                    if not can_interact or current_phase != 'roll':
                        action['disabled_reason'] = 'Use antes de rolar o dado'
                    else:
                        action['can_activate_now'] = True
                elif activation_mode == 'manual_action':
                    has_capture_flow = current_phase == 'action' and (
                        (turn or {}).get('pending_pokemon') is not None
                        or ((turn or {}).get('pending_action') or {}).get('type') == 'capture_attempt'
                    )
                    if effect['effect_kind'] == 'capture_free_next' and has_capture_flow and is_owner_turn:
                        action['can_activate_now'] = True
                    elif effect['effect_kind'] == 'advance_after_landing' and is_owner_turn and current_phase == 'action' and can_interact:
                        action['can_activate_now'] = True
                    elif effect['effect_kind'] in ('heal_other', 'evolve_other', 'recharge_all_other_abilities', 'clone_in_game_pokemon') and is_owner_turn and current_phase in ('roll', 'action') and can_interact:
                        action['can_activate_now'] = True
                    elif effect['effect_kind'] == 'draw_victory' and not (action.get('params') or {}).get('after_duel_loss') and is_owner_turn and current_phase in ('roll', 'action') and can_interact:
                        action['can_activate_now'] = True
                    elif effect['effect_kind'] == 'draw_event' and is_owner_turn and current_phase in ('roll', 'action') and can_interact:
                        if (action.get('params') or {}).get('from_discard'):
                            _cur_tile_type = ((turn or {}).get('current_tile') or {}).get('type')
                            if _cur_tile_type == 'event':
                                action['can_activate_now'] = True
                            else:
                                action['disabled_reason'] = 'Use em uma casa de evento'
                        else:
                            action['can_activate_now'] = True
                    elif effect['effect_kind'] == 'event_peek' and is_owner_turn and can_interact:
                        action['can_activate_now'] = True
                    elif effect['effect_kind'] == 'area_capture_free' and is_owner_turn and current_phase in ('roll', 'action') and can_interact:
                        action['can_activate_now'] = True
                    else:
                        action['disabled_reason'] = 'Use na fase de ação apropriada'

                if action['can_activate_now']:
                    can_activate_now = True
                    disabled_reason = None
                manual_actions.append(action)

        snapshots.append({
            **copy.deepcopy(definition),
            'slot_key': slot_key,
            'charges_remaining': charges_remaining,
            'has_charges': charges_total is not None,
            'is_spent': no_charges_left,
            'runtime': runtime_entry,
            'awaiting_decision': awaiting_decision,
            'can_activate_now': can_activate_now,
            'disabled_reason': disabled_reason,
            'actions': manual_actions,
        })

    pokemon['abilities'] = snapshots
    if snapshots:
        primary = snapshots[0]
        pokemon['ability_charges'] = primary.get('charges_remaining')
        pokemon['ability_used'] = bool(primary.get('runtime', {}).get('used_this_turn')) or bool(primary.get('is_spent'))
        pokemon['ability_status'] = {
            'name': primary.get('name'),
            'description': primary.get('description'),
            'charges_total': primary.get('charges_total'),
            'charges_remaining': primary.get('charges_remaining'),
            'can_activate_now': primary.get('can_activate_now', False),
            'disabled_reason': primary.get('disabled_reason'),
            'awaiting_decision': primary.get('awaiting_decision', False),
        }
    else:
        pokemon['ability_status'] = None
    return pokemon


def sync_pokemon_ability_state(pokemon: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(pokemon, dict):
        return pokemon

    definitions = get_static_ability_definitions(pokemon)
    runtime = copy.deepcopy(pokemon.get('ability_runtime')) if isinstance(pokemon.get('ability_runtime'), dict) else {}
    runtime_abilities = copy.deepcopy(runtime.get('abilities')) if isinstance(runtime.get('abilities'), dict) else {}

    normalized_runtime: dict[str, Any] = {
        'version': ABILITY_RUNTIME_VERSION,
        'abilities': {},
    }
    for definition in definitions:
        normalized_runtime['abilities'][definition['id']] = _normalize_runtime_entry(
            runtime_abilities.get(definition['id']),
            charges_total=definition.get('charges_total'),
            fallback_used=bool(pokemon.get('ability_used')),
        )

    pokemon['ability_runtime'] = normalized_runtime
    pokemon['ability_charges_total'] = (
        definitions[0].get('charges_total')
        if definitions
        else _to_int_or_none(pokemon.get('ability_charges_total'))
    )
    return _attach_ability_snapshots(pokemon)


def adjust_primary_ability_charges(pokemon: dict[str, Any] | None, delta: int) -> int | None:
    if not isinstance(pokemon, dict):
        return None
    sync_pokemon_ability_state(pokemon)
    primary = ((pokemon.get('ability_runtime') or {}).get('abilities') or {}).get(PRIMARY_ABILITY_ID)
    if not isinstance(primary, dict) or primary.get('charges_remaining') is None:
        return None
    primary['charges_remaining'] = max(0, int(primary.get('charges_remaining', 0) or 0) + int(delta))
    _attach_ability_snapshots(pokemon)
    return primary['charges_remaining']


def mark_primary_ability_used(
    pokemon: dict[str, Any] | None,
    *,
    scope: str = 'turn',
    consume_charge: bool = False,
    decision_id: str | None = None,
    area_key: str | None = None,
) -> None:
    if not isinstance(pokemon, dict):
        return
    sync_pokemon_ability_state(pokemon)
    primary = ((pokemon.get('ability_runtime') or {}).get('abilities') or {}).get(PRIMARY_ABILITY_ID)
    if not isinstance(primary, dict):
        return

    if scope == 'turn':
        primary['used_this_turn'] = True
    elif scope == 'battle':
        primary['used_this_battle'] = True
    elif scope == 'game':
        primary['used_this_game'] = True

    if area_key:
        used_area_keys = [str(item) for item in primary.get('used_area_keys') or [] if str(item).strip()]
        if area_key not in used_area_keys:
            used_area_keys.append(area_key)
        primary['used_area_keys'] = used_area_keys

    if decision_id:
        resolved = [str(item) for item in primary.get('resolved_decision_ids') or [] if str(item).strip()]
        if decision_id not in resolved:
            resolved.append(decision_id)
        primary['resolved_decision_ids'] = resolved[-50:]

    if consume_charge and primary.get('charges_remaining') is not None:
        primary['charges_remaining'] = max(0, int(primary.get('charges_remaining', 0) or 0) - 1)

    _attach_ability_snapshots(pokemon)


def reset_player_ability_runtime(player: dict[str, Any] | None, scope: str) -> None:
    if not isinstance(player, dict):
        return
    pokemons = list(player.get('pokemon') or [])
    if player.get('starter_pokemon'):
        pokemons.append(player['starter_pokemon'])

    for pokemon in pokemons:
        sync_pokemon_ability_state(pokemon)
        primary = ((pokemon.get('ability_runtime') or {}).get('abilities') or {}).get(PRIMARY_ABILITY_ID)
        if not isinstance(primary, dict):
            continue
        if scope == 'turn':
            primary['used_this_turn'] = False
        elif scope == 'battle':
            primary['used_this_battle'] = False
        _attach_ability_snapshots(pokemon)


def build_move_roll_prompt_options(pokemon: dict[str, Any] | None, roll_value: int) -> list[dict[str, Any]]:
    if not isinstance(pokemon, dict):
        return []
    sync_pokemon_ability_state(pokemon)
    ability = next(iter(pokemon.get('abilities') or []), None)
    if not isinstance(ability, dict):
        return []
    runtime = ability.get('runtime') or {}
    if runtime.get('used_this_turn'):
        return []
    if ability.get('has_charges') and int(ability.get('charges_remaining') or 0) <= 0:
        return []

    options: list[dict[str, Any]] = []
    for effect in ability.get('effects') or []:
        if not effect.get('implemented') or effect.get('activation_mode') != 'prompt_after_move_roll':
            continue

        effect_kind = effect.get('effect_kind')
        params = effect.get('params') or {}
        option: dict[str, Any] | None = None
        if effect_kind == 'move_roll_reroll':
            option = {
                'effect_kind': effect_kind,
                'label_suffix': 'rerrolar o dado',
                'resolution': {'mode': 'reroll'},
            }
        elif effect_kind == 'move_roll_delta':
            delta_map = {int(key): int(value) for key, value in (params.get('delta_map') or {}).items()}
            delta = delta_map.get(int(roll_value), params.get('delta'))
            if delta is None:
                continue
            min_result = int(params.get('min_result', 0))
            max_result = int(params.get('max_result', 999))
            next_value = max(min_result, min(max_result, int(roll_value) + int(delta)))
            if next_value == int(roll_value):
                continue
            option = {
                'effect_kind': effect_kind,
                'label_suffix': f'{roll_value} -> {next_value}',
                'resolution': {'mode': 'set', 'result': next_value},
            }
        elif effect_kind == 'move_roll_set':
            absolute_map = {int(key): int(value) for key, value in (params.get('absolute_map') or {}).items()}
            next_value = absolute_map.get(int(roll_value))
            if next_value is None or next_value == int(roll_value):
                continue
            option = {
                'effect_kind': effect_kind,
                'label_suffix': f'{roll_value} -> {next_value}',
                'resolution': {'mode': 'set', 'result': next_value},
            }
        elif effect_kind == 'move_roll_divide':
            divisor = max(1, int(params.get('divisor', 2) or 2))
            rounding = params.get('rounding')
            if rounding == 'up':
                next_value = -(-int(roll_value) // divisor)
            else:
                next_value = int(roll_value) // divisor
            if next_value == int(roll_value):
                continue
            option = {
                'effect_kind': effect_kind,
                'label_suffix': f'{roll_value} -> {next_value}',
                'resolution': {'mode': 'set', 'result': next_value},
            }
        elif effect_kind == 'move_roll_multiplier':
            multiplier = max(1, int(params.get('multiplier', 2) or 2))
            next_value = int(roll_value) * multiplier
            if next_value == int(roll_value):
                continue
            option = {
                'effect_kind': effect_kind,
                'label_suffix': f'{roll_value} -> {next_value}',
                'resolution': {'mode': 'set', 'result': next_value},
            }
        elif effect_kind == 'move_roll_opposite_side':
            mapping = {int(key): int(value) for key, value in (params.get('mapping') or {}).items()}
            next_value = mapping.get(int(roll_value))
            if next_value is None or next_value == int(roll_value):
                continue
            option = {
                'effect_kind': effect_kind,
                'label_suffix': f'{roll_value} -> {next_value}',
                'resolution': {'mode': 'set', 'result': next_value},
            }

        elif effect_kind == 'move_roll_choice':
            # Gera uma opção para cada valor 1-6, exceto o resultado atual (não mudaria nada)
            for val in range(1, 7):
                if val == int(roll_value):
                    continue
                options.append({
                    'ability_id': ability.get('id', PRIMARY_ABILITY_ID),
                    'ability_name': ability.get('name') or 'Habilidade',
                    'description': ability.get('description') or '',
                    'effect_kind': effect_kind,
                    'label_suffix': f'{roll_value} → {val}',
                    'resolution': {'mode': 'set', 'result': val},
                    'charges_remaining': ability.get('charges_remaining'),
                    'charges_total': ability.get('charges_total'),
                })
            continue  # já adicionou todas as opções; não cai no append padrão abaixo

        if option is None:
            continue

        options.append({
            'ability_id': ability.get('id', PRIMARY_ABILITY_ID),
            'ability_name': ability.get('name') or 'Habilidade',
            'description': ability.get('description') or '',
            'effect_kind': option['effect_kind'],
            'label_suffix': option['label_suffix'],
            'resolution': option['resolution'],
            'charges_remaining': ability.get('charges_remaining'),
            'charges_total': ability.get('charges_total'),
        })

    return options


def annotate_state_ability_snapshots(state: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(state, dict):
        return state

    turn = state.get('turn') or {}
    current_player_id = turn.get('current_player_id')
    for player in state.get('players') or []:
        for index, pokemon in enumerate(player.get('pokemon') or []):
            sync_pokemon_ability_state(pokemon)
            _attach_ability_snapshots(
                pokemon,
                turn=turn,
                player_id=player.get('id'),
                current_player_id=current_player_id,
                slot_key=f'pokemon:{index}',
            )
        starter = player.get('starter_pokemon')
        if isinstance(starter, dict):
            sync_pokemon_ability_state(starter)
            _attach_ability_snapshots(
                starter,
                turn=turn,
                player_id=player.get('id'),
                current_player_id=current_player_id,
                slot_key='starter',
            )

        # pokemon_inventory é uma lista de deepcopies usadas pelo frontend.
        # Propaga as anotações de habilidade dos originais para as cópias.
        for inv_item in player.get('pokemon_inventory') or []:
            slot_key = inv_item.get('slot_key')
            if not slot_key:
                continue
            if slot_key == 'starter' and isinstance(starter, dict):
                source = starter
            elif slot_key.startswith('pokemon:'):
                try:
                    idx = int(slot_key.split(':', 1)[1])
                    pokemon_list = player.get('pokemon') or []
                    source = pokemon_list[idx] if 0 <= idx < len(pokemon_list) else None
                except (ValueError, IndexError):
                    source = None
            else:
                source = None
            if isinstance(source, dict):
                inv_item['abilities'] = copy.deepcopy(source.get('abilities') or [])
                inv_item['ability_status'] = copy.deepcopy(source.get('ability_status'))

    return state
