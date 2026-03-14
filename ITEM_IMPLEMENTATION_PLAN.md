# Item Implementation Plan

## 1. Itens não-Pokébola identificados com confidence high ou medium
- `bill`
  Evidência: a carta diz explicitamente que aumenta o resultado do move dice em 2.
- `full_restore`
  Evidência: a carta diz explicitamente que cura um Pokémon e não pode ser usada durante batalha.
- `gust_of_wind`
  Evidência: a carta diz explicitamente que em um duelo decide qual Pokémon o inimigo usará.
- `pluspower`
  Evidência: a carta diz explicitamente que dá `+2` Battle Points a um Pokémon no início da batalha, pela duração da batalha.
- `prof_oak`
  Evidência: a carta diz explicitamente que reduz o resultado do move dice em 1 sem ir abaixo de zero.
- `miracle_stone`
  Evidência: a carta diz explicitamente que evolui um Pokémon, exceto quando ele requer outro método específico.
- `master_points_nugget`
  Evidência: o nome visual é legível, mas não há texto de uso.
  Tratamento: manter como ambíguo e sem lógica complexa.

## 2. Itens ambíguos que não devem receber lógica complexa
- `master_points_nugget`
  Motivo: a carta não está marcada como `ITEM` e não descreve comportamento jogável.
  Implementação segura: mapear no catálogo como placeholder `unimplemented`, sem efeito automático.

## 3. Onde integrar no código atual
- Representação e normalização de itens:
  [backend/game/engine/inventory.py](/home/kadu/Projetos/pokemon-life-web/backend/game/engine/inventory.py)
- Bootstrap/estado inicial da partida:
  [backend/game/engine/state.py](/home/kadu/Projetos/pokemon-life-web/backend/game/engine/state.py)
  [backend/game/state_schema.py](/home/kadu/Projetos/pokemon-life-web/backend/game/state_schema.py)
  [backend/game/consumers.py](/home/kadu/Projetos/pokemon-life-web/backend/game/consumers.py)
- Fluxo de ações e efeitos já existentes:
  [backend/game/engine/state.py](/home/kadu/Projetos/pokemon-life-web/backend/game/engine/state.py)
  [backend/game/engine/cards.py](/home/kadu/Projetos/pokemon-life-web/backend/game/engine/cards.py)
- UI de inventário e ações:
  [frontend/src/components/ui/InventoryModal.vue](/home/kadu/Projetos/pokemon-life-web/frontend/src/components/ui/InventoryModal.vue)
  [frontend/src/components/ui/ActionPanel.vue](/home/kadu/Projetos/pokemon-life-web/frontend/src/components/ui/ActionPanel.vue)
  [frontend/src/components/player/PlayerPanel.vue](/home/kadu/Projetos/pokemon-life-web/frontend/src/components/player/PlayerPanel.vue)
  [frontend/src/stores/gameStore.js](/home/kadu/Projetos/pokemon-life-web/frontend/src/stores/gameStore.js)

## 4. Estratégia de implementação mínima e segura
- Expandir o catálogo de itens existente em vez de criar outro sistema paralelo.
- Implementar apenas efeitos diretamente suportados pela evidência visual:
  - `bill`: modificador temporário do move dice em `+2`.
  - `prof_oak`: modificador temporário do move dice em `-1`, com piso em `0`.
  - `full_restore`: cura um Pokémon fora de batalha.
  - `gust_of_wind`: apenas em duelo; força a escolha do Pokémon do oponente.
  - `pluspower`: buff temporário de batalha `+2 BP` para um Pokémon escolhido no início da batalha.
  - `miracle_stone`: chamar o fluxo de evolução apenas quando houver evolução padrão disponível; se não houver evidência suficiente, bloquear com mensagem segura.
- Não implementar lógica complexa para `master_points_nugget`.
- Não implementar Pokébolas nesta task.

## 5. Estratégia do modo debug
- Adicionar painel dev-only no frontend, visível apenas em ambiente de desenvolvimento.
- Permitir:
  - selecionar item por chave do catálogo;
  - informar quantidade;
  - enviar ação websocket/backend isolada do fluxo normal.
- Limitar o modo debug a adição de itens ao inventário, sem interferir em regras normais de turno.

## 6. Como os itens iniciais serão aplicados na criação da partida
- Ao inicializar ou normalizar jogadores novos, aplicar os itens visuais confirmados nas regras:
  - `6` Pokébolas
  - `2` Full Restores
- Como o projeto já nasce com `6` Pokébolas e `2` Full Restores em parte do fluxo, consolidar isso em uma única fonte de verdade para reduzir divergência.
- Manter a documentação do conflito onde ainda existirem defaults antigos divergentes no código legado.
