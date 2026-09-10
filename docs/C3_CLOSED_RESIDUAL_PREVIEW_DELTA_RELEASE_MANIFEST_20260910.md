# Central Quant — Manifesto suplementar do delta C3 CLOSED residual preview

Data de corte: 2026-09-10
Branch: `codex/c3-closed-repair-preview-only`
Base: `5d461c981149d140b0f6b87970770950c3b05bfb`
Payload commit: `db34f3fa9b65e4bbc11b00089714cb5a1730f420`
Estado: **DELTA REMOTO — DEFAULT-OFF — VALIDAÇÃO AMPLIADA BLOQUEADA — NÃO APROVADO PARA LIVE**

Este documento complementa, sem substituir, `C3_CLOSED_REPAIR_RELEASE_MANIFEST_20260910.md`. O manifesto suplementar não integra o digest do payload para evitar autorreferência.

## Identidade do delta

- Arquivos: 17 (12 adicionados e 5 modificados).
- Diff: 3.612 inserções e 17 remoções.
- Bytes totais no payload: 193.621.
- Linhas totais no payload: 4.831.
- SHA-256 do inventário canônico: `70fbc8ca8738032ccc4da981e933d6511d31ced7d4793e193efef8a888d78122`.
- Formato canônico: uma linha UTF-8 por arquivo, ordenada por caminho, no formato `<sha256> <bytes> <linhas> <caminho>\n`.

## Escopo e invariantes

- O delta implementa somente contratos, harnesses e testes offline do reparo residual e de sua cadeia de preview protegida.
- A leitura física aceita exclusivamente o arquivo sintético `synthetic_trade_registry.json` em diretório temporário dedicado.
- Não existe superfície de apply, integração com `main.py`, integração com `trade_registry.py`, autoridade de produção ou chamada ao broker.
- O legado permanece autoritativo; toda divergência, expiração, assinatura inválida ou quebra de preservação falha fechada.
- `ENABLE_REAL_TRADING`, shadow, canário, FAST e Live permanecem desativados e fora do escopo.
- Nenhum conteúdo deste manifesto autoriza deploy, bootstrap, reparo real, alteração de flags ou envio de ordens.

## Evidência local

- Suíte direcionada do delta: **70 testes aprovados**.
- `git diff --check 5d461c981149d140b0f6b87970770950c3b05bfb..db34f3fa9b65e4bbc11b00089714cb5a1730f420`: aprovado.
- Inventário: 17 de 17 arquivos presentes e vinculados ao payload por SHA-256.
- Integração runtime: busca estática confirmou que os módulos novos não são importados por `main.py` nem por `trade_registry.py`.

### Validação CLOSED ampliada

A seleção exata encontrou 1.510 testes em 122 arquivos. A execução ampliada não pode ser declarada aprovada:

1. A tentativa por coleta global foi inválida antes dos testes C3 por três módulos legados que importam a dependência opcional ausente `ccxt`.
2. Com seleção exata, 209 testes passaram antes de o pytest falhar ao acessar o diretório temporário padrão do Windows.
3. Com diretório temporário isolado no worktree e cache desativado, 249 testes passaram; a primeira falha real foi `pinned source drifted: runtime_seam`.
4. O atestado esperado para `runtime_seam` é `928b2472e9a76bd5d2c0daa27b2ea354f11747045e4e1035853a5f9e69dc5698` / 26.270 bytes normalizados; o arquivo atual produz `c5bb7d157d5a77061bd2395ba5fe83dcf7450885c856ff40cdc6664bfa3c5d87` / 37.093 bytes.
5. A auditoria dos quatro pins também encontrou `main.py` divergente: esperado `fcb4cc495221db6f293c201648d69d1b498788167cb128c2ce2e7bb13ae7a1a7` / 2.983.543 bytes; atual `6bb4b7881839f15123e0f27b176d01d638070633d792c6ccdae9c4d9aee5bbb3` / 2.988.537 bytes.
6. `runtime_seam` e `main.py` não foram modificados entre a base e o payload deste manifesto. Portanto, o bloqueio é preexistente ao delta de 17 arquivos, mas continua sendo bloqueio real de release.

## Decisão de readiness

O delta está íntegro e sua suíte direcionada está aprovada, porém o candidato agregado **não está pronto para deploy nem Live** enquanto os pins de readiness não forem reconciliados e a suíte CLOSED ampliada não terminar integralmente verde. Não é permitido atualizar pins apenas para silenciar a falha: os arquivos atuais devem ser auditados e o novo binding precisa refletir uma revisão explícita de segurança.

## Próxima etapa controlada

1. Auditar somente leitura a proveniência das alterações em `runtime_seam` e `main.py` desde os pins atuais.
2. Confirmar que o vetor completo de readiness e os interlocks não foram enfraquecidos.
3. Preparar offline uma atualização isolada dos pins, acompanhada de testes de falha fechada.
4. Reexecutar os 1.510 testes CLOSED com diretório temporário isolado.
5. Criar uma nova decisão de release somente após resultado integralmente verde.

## Inventário exato

| SHA-256 | Bytes | Linhas | Caminho |
|---|---:|---:|---|
| `435ed4afc95688d060d6fe0b6ae82e64087942b0072036b8f28a216b9e97f8ac` | 8.405 | 218 | `tests/test_trade_registry_closed_identity_residual_repair_offline_v1.py` |
| `cc813bbe475b4f879d1501772676379d7f8f8fc9e4e7d604e4dbc39eeb6238de` | 7.024 | 174 | `tests/test_trade_registry_closed_identity_residual_repair_physical_preview_bridge_offline_v1.py` |
| `47b50b8c6ba1343d321372f6e01940ac40a0b61d74260d2f10115653ea2fb88f` | 7.934 | 214 | `tests/test_trade_registry_closed_identity_residual_repair_physical_read_only_snapshot_port_offline_v1.py` |
| `f035f30ce7f16cc41e8aaf630bdfec6cd655ba1c3a55dd28224b3d71577c710c` | 7.843 | 195 | `tests/test_trade_registry_closed_identity_residual_repair_protected_preview_offline_v1.py` |
| `c3dec8964ac930d1e2dadeb63586caf5ee0110a86410c888da9fe23026af4709` | 8.318 | 208 | `tests/test_trade_registry_closed_identity_residual_repair_runtime_read_only_preview_adapter_offline_v1.py` |
| `6c214821def3de0dbe04b525163f223404b588a3f54f4c2b9294f5c0115a4500` | 6.621 | 172 | `tests/test_trade_registry_closed_identity_residual_timestamp_selection_offline_v1.py` |
| `e46ee389ae1f5d7d64feca869ffc903dae19b0f3c2aad93ac1c6a2266a7627e9` | 19.969 | 529 | `trade_registry_closed_identity_residual_repair_offline_contract_v1.py` |
| `20665d29b8282283410640bdba345fc2bbb2ded8f0639da962e0f59953eb2e7f` | 8.636 | 246 | `trade_registry_closed_identity_residual_repair_offline_harness_v1.py` |
| `e03c95a81798073c043a0dd6bad94bd26531b77844c2345bc2736b54dcff1c52` | 15.129 | 350 | `trade_registry_closed_identity_residual_repair_physical_preview_bridge_offline_contract_v1.py` |
| `359828e13e5f0d44534b27309c899353d215d6ce437da1fdcc9528d5e3cb134d` | 8.055 | 182 | `trade_registry_closed_identity_residual_repair_physical_preview_bridge_offline_harness_v1.py` |
| `c2f92fe148fa94b6fb86c4c1356698459d7f8fb43ec4d7adaac367f4bf0f127b` | 21.085 | 514 | `trade_registry_closed_identity_residual_repair_physical_read_only_snapshot_port_offline_contract_v1.py` |
| `3512150a5e97a03e46790a4f228213e9d34ff33a66cd44658f4c825ff9650771` | 6.475 | 152 | `trade_registry_closed_identity_residual_repair_physical_read_only_snapshot_port_offline_harness_v1.py` |
| `4fc21c6b7add6c4726cd6e37fd4ab279a01f10734cb9b9b2be5dd078cde105e0` | 21.923 | 575 | `trade_registry_closed_identity_residual_repair_protected_preview_offline_contract_v1.py` |
| `a48e2039ec4af0415e7c78c6c5cc8689ad90495161ddb89d0e6dac97e4b729b0` | 6.414 | 149 | `trade_registry_closed_identity_residual_repair_protected_preview_offline_harness_v1.py` |
| `9f5b04b7e94d7fd269d24e0baa43d00f2954c7b4200f4a671568c20c97808c02` | 25.412 | 624 | `trade_registry_closed_identity_residual_repair_runtime_read_only_preview_adapter_offline_contract_v1.py` |
| `b77d70bcf431cd2996d8cf83d67f77aa8222b413a0b7a690bf4489cf97bfbaa9` | 8.821 | 200 | `trade_registry_closed_identity_residual_repair_runtime_read_only_preview_adapter_offline_harness_v1.py` |
| `af83b3d26a85ef148bfd9340ead9b78ea5fabc8a77cad4cbbd76a52217d65595` | 5.557 | 129 | `trade_registry_closed_identity_residual_timestamp_selection_offline_harness_v1.py` |
