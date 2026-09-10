# Central Quant — Manifesto final do candidato C3 CLOSED residual preview

Data de corte: 2026-09-10
Branch: `codex/c3-closed-repair-preview-only`
Base do delta cumulativo: `5d461c981149d140b0f6b87970770950c3b05bfb`
Payload commit: `65946040a3398c5f1d9eaa4bbe9f4341ed55a090`
Payload tree: `0bcee2cdb27bf56de41f8312245468db7a03e381`
Estado: **PAYLOAD REMOTO VALIDADO — MANIFESTO LOCAL — DEFAULT-OFF — NÃO APROVADO PARA LIVE**

Este manifesto atesta o candidato remoto `6594604`. Ele não integra o digest do payload para evitar autorreferência e precisa ser versionado separadamente antes de qualquer decisão de deploy.

## Identidade do payload cumulativo

- Arquivos: 22.
- Diff: 3.741 inserções e 22 remoções.
- Bytes totais: 261.289.
- Linhas totais: 6.443.
- SHA-256 do inventário canônico: `39ac7123adfb6c027e82143ba086641a17be459c5146cf81f51072bd896db651`.
- Formato canônico: uma linha UTF-8 por arquivo, ordenada por caminho, no formato `<sha256> <bytes> <linhas> <caminho>\n`.
- Delta final `db34f3f → 6594604`: 5 arquivos, 129 inserções e 5 remoções.

## Evidência validada

- Git local e remoto coincidem exatamente em `65946040a3398c5f1d9eaa4bbe9f4341ed55a090`.
- Conectividade dos objetos Git aprovada.
- `git diff --check` aprovado para o delta final e para o delta cumulativo.
- Suíte direcionada do residual preview: 70 testes aprovados.
- Suíte do endurecimento dormente que originou os pins: 321 testes aprovados.
- Suíte conjunta de readiness binding e patch plan: 57 testes aprovados.
- Suíte CLOSED final: **1.512 testes e 56 subtestes aprovados** em ambiente local sem rede.
- Os hashes de `runtime_seam`, `main.py` e do contrato transitivo de readiness foram reatestado após auditoria de proveniência.
- Nenhum módulo novo do residual preview é importado por `main.py` ou `trade_registry.py`.

## Escopo de segurança

- O residual preview permanece exclusivamente offline, sintético, default-off e sem superfície de apply.
- A porta física aceita somente `synthetic_trade_registry.json` dentro de diretório temporário dedicado.
- O legado permanece autoritativo.
- O contrato de readiness continua declarativo e não concede autoridade runtime ou de produção.
- O vetor de readiness exige 19 writers, zero mutações em andamento, recovery concluído, kill switch pronto, hashes verificados e todos os interlocks positivos.
- `ENABLE_REAL_TRADING` deve permanecer desativado.
- Shadow, canário, FAST, Live, reparo real e envio de ordens permanecem proibidos por este manifesto.

## Decisão de release

O payload `6594604` está tecnicamente validado para ser considerado em um futuro deploy controlado com trading real desativado. Este documento não autoriza deploy: antes disso, o próprio manifesto deve ser versionado e enviado, o artefato precisa ser novamente conferido e deve existir autorização operacional separada.

Após eventual deploy, continuam obrigatórios:

1. confirmar o commit e a árvore implantados;
2. manter trading real desativado e dry-run ativo;
3. executar somente preflight de produção autorizado e somente leitura;
4. confirmar zero transações pendentes e todos os campos do vetor de readiness;
5. preservar o Registry, WAL, histórico e evidência de auditoria;
6. exigir autorização separada antes de qualquer rearmamento ou piloto Live.

## Critérios de aborto

- Divergência de commit, árvore, inventário ou hash de fonte.
- Qualquer tentativa de acesso a Registry real pelo residual preview.
- Qualquer superfície de apply, ordem, ativação, shadow, canário, FAST ou Live.
- Menos de 19 writers coordenados ou qualquer mutação em andamento.
- Recovery incompleto, WAL pendente, kill switch indisponível ou recibo inválido.
- Trading real habilitado ou dry-run desabilitado durante release e preflight.

## Inventário exato

| SHA-256 | Bytes | Linhas | Caminho |
|---|---:|---:|---|
| `80d06776de58947da12c870e2b010ef5490ab7250f09e741700c2cc53d2631dc` | 7.515 | 79 | `docs/C3_CLOSED_RESIDUAL_PREVIEW_DELTA_RELEASE_MANIFEST_20260910.md` |
| `3657340791fe04689c050a25e740fa59cfdaeae9025d20bd2f9b89620a90dc33` | 10.997 | 306 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_v1.py` |
| `bb9bfca85daa0027e3b3c20c09f34b071c16f31e55cc51d3f9713ded21f50104` | 10.954 | 284 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_v1.py` |
| `435ed4afc95688d060d6fe0b6ae82e64087942b0072036b8f28a216b9e97f8ac` | 8.405 | 218 | `tests/test_trade_registry_closed_identity_residual_repair_offline_v1.py` |
| `cc813bbe475b4f879d1501772676379d7f8f8fc9e4e7d604e4dbc39eeb6238de` | 7.024 | 174 | `tests/test_trade_registry_closed_identity_residual_repair_physical_preview_bridge_offline_v1.py` |
| `47b50b8c6ba1343d321372f6e01940ac40a0b61d74260d2f10115653ea2fb88f` | 7.934 | 214 | `tests/test_trade_registry_closed_identity_residual_repair_physical_read_only_snapshot_port_offline_v1.py` |
| `f035f30ce7f16cc41e8aaf630bdfec6cd655ba1c3a55dd28224b3d71577c710c` | 7.843 | 195 | `tests/test_trade_registry_closed_identity_residual_repair_protected_preview_offline_v1.py` |
| `c3dec8964ac930d1e2dadeb63586caf5ee0110a86410c888da9fe23026af4709` | 8.318 | 208 | `tests/test_trade_registry_closed_identity_residual_repair_runtime_read_only_preview_adapter_offline_v1.py` |
| `6c214821def3de0dbe04b525163f223404b588a3f54f4c2b9294f5c0115a4500` | 6.621 | 172 | `tests/test_trade_registry_closed_identity_residual_timestamp_selection_offline_v1.py` |
| `f55f6503330f2395f72545c6a5985f0e528671bfbcebe3211fa66be4d8c1410e` | 16.761 | 426 | `trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_contract_v1.py` |
| `d256ec4d0d272d86e4a2390c638ad5227ffbd2828daffc6e166298829950bf1c` | 21.441 | 517 | `trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_contract_v1.py` |
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
