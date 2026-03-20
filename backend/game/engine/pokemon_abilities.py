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
    if effect_kind == 'battle_reroll':
        return 'Rerrolar batalha'
    if effect_kind == 'capture_reroll':
        return 'Rerrolar captura'
    if effect_kind == 'heal_other':
        return 'Curar outro Pokémon'
    if effect_kind == 'draw_victory':
        return 'Comprar vitória'
    if effect_kind == 'draw_event':
        return 'Comprar evento'
    if effect_kind == 'event_peek':
        return 'Espiar evento'
    if effect_kind == 'evolve_other':
        return 'Evoluir outro Pokémon'
    if effect_kind == 'targeted_move':
        return 'Movimento direcionado'
    if effect_kind == 'move_roll_choice':
        return 'Escolher resultado do dado'
    if effect_kind == 'capture_choice':
        return 'Modificar captura'
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
        ('you may always move one tile forward', 1),  # Mew: "instead of throwing ... you may always move one tile forward"
    )
    for phrase, steps in fixed_distance_matchers:
        if phrase in normalized:
            add(
                'fixed_move',
                activation_mode='manual_before_roll',
                implemented=True,
                params={'steps': steps},
            )

    if 'ao capturar, não gasta pokébola' in normalized or 'ao capturar, nao gasta pokebola' in normalized:
        add(
            'capture_free_next',
            activation_mode='manual_action',
            implemented=True,
            limit_scope='turn',
        )

    if 'heal one of your other pok' in normalized:
        add('heal_other', activation_mode='manual_action', implemented=True, limit_scope='turn')
    if 'draw a card from the victory pile' in normalized or 'take a victory card' in normalized:
        add('draw_victory', activation_mode='manual_action', implemented=False)
    if 'draw a card from the event pile' in normalized or 'top card of the event discard pile' in normalized:
        add('draw_event', activation_mode='manual_action', implemented=False)
    if 'look at the top card of the event pile' in normalized or 'take two cards at once' in normalized:
        add('event_peek', activation_mode='event_prompt', implemented=False)
    if 'evolve one of your other pok' in normalized or 'cause one of your pok' in normalized:
        add('evolve_other', activation_mode='manual_action', implemented=False)
    if 'increases the battle points of all pokémon in your team by 2' in normalized or 'increases the battle points of all pokemon in your team by 2' in normalized:
        add('team_bonus', activation_mode='automatic_passive', implemented=False)
    if 'extra battle point' in normalized and 'for each other' in normalized:
        # Beedrill: +1 BP and +10 MP for each other same-named pokemon in team
        ally_name = str(pokemon.get('current_name') or pokemon.get('real_name') or '').strip()
        add('team_bonus', activation_mode='passive', implemented=True, params={
            'bonus_bp_per_ally': 1,
            'bonus_mp_per_ally': 10,
            'ally_name': ally_name,
        })
    if 'instead of throwing the move dice, you may teleport' in normalized or 'move forward to a player on another tile within 5 tiles' in normalized or 'move forward to a tile no further than five ahead' in normalized:
        add('targeted_move', activation_mode='manual_before_roll', implemented=False)
    if 'you may decide the outcome of the move dice' in normalized:
        add('move_roll_choice', activation_mode='prompt_after_move_roll', implemented=True)
    if 'you may decide the outcome of the capture dice' in normalized or 'throw 2 dice at once, and choose the outcome you desire' in normalized:
        add('capture_choice', activation_mode='capture_prompt', implemented=True)

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

            action = {
                'action_id': _slug(f"{effect['effect_kind']}"),
                'effect_kind': effect['effect_kind'],
                'label': effect['label'],
                'params': copy.deepcopy(effect.get('params') or {}),
                'supported': True,
                'can_activate_now': False,
                'disabled_reason': None,
            }

            if no_charges_left:
                action['disabled_reason'] = 'Sem cargas restantes'
            elif runtime_entry.get('used_this_turn'):
                action['disabled_reason'] = 'Já usada neste turno'
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
                elif effect['effect_kind'] == 'heal_other' and is_owner_turn and current_phase in ('roll', 'action') and can_interact:
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
