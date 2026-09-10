# Central Quant — Manifesto do release C3 CLOSED repair

Data de corte: 2026-09-10
Branch: `codex/c3-closed-repair-preview-only`
Base: `15d612971b585d9867e67a65dd68cee305193053`
Estado: **CANDIDATO LOCAL — DEFAULT-OFF — NÃO APROVADO PARA LIVE**

## Identidade do payload

- Arquivos do payload: 258
- Bytes totais: 6910419
- Linhas totais: 158496
- SHA-256 do inventário canônico: `99479cc3e244fe4178abcf96944c35971a1e38235c40079295ec452adf147101`
- Formato do inventário canônico: uma linha UTF-8 por arquivo, ordenada por caminho, no formato `<sha256> <bytes> <linhas> <caminho>\n`.
- Este manifesto não integra o digest do payload para evitar autorreferência.

## Evidência validada

- 258 arquivos analisados sintaticamente.
- 1138 testes aprovados.
- 56 subtestes aprovados.
- Um aviso não bloqueante.
- Preflight estático aprovado.
- 19 de 19 writers coordenados; zero divergências de assinatura ou âncora.
- Controller binding sintético aprovado.
- Plano de patch somente leitura aprovado.
- `git diff --check` aprovado.

## Invariantes obrigatórias

- `ENABLE_REAL_TRADING` deve permanecer desativado durante release, deploy, provisionamento, bootstrap e preflight.
- Nenhuma ordem pode ser enviada durante essas etapas.
- C3 permanece default-off até existir recibo autenticado e persistente de produção.
- Runtime binding, startup recovery, activation e Live devem falhar fechados sem o vetor completo de readiness.
- Os 19 writers devem usar a mesma coordenação, o mesmo backend de lock e a mesma maintenance lease.
- Autoridade raiz, revogação e stores de recuperação devem compartilhar o binding de armazenamento esperado.
- Toda divergência de hash, geração, instância, WAL ou transação pendente bloqueia readiness.

## Bloqueios atuais para produção

1. O payload e este manifesto ainda não possuem commit isolado.
2. Nenhum push ou deploy deste candidato foi realizado.
3. Autoridade raiz autenticada, estado de revogação e referências de recovery não foram provisionados em produção.
4. Caminhos físicos e garantias de atomic replace/fsync não foram verificados em produção.
5. O runtime binding permanece deliberadamente não satisfeito.
6. Startup recovery de produção não foi executado para este candidato.
7. O preflight controlado de produção não foi executado após o futuro deploy.
8. Live e envio de ordens permanecem proibidos.

## Ordem controlada do release

1. Confirmar no staging que os 258 arquivos do payload e este manifesto pertencem ao commit isolado.
2. Criar commit isolado, preservando todos os gates default-off.
3. Fazer push e deploy com trading real desativado e sem execução de ordens.
4. Confirmar o artefato implantado pelo commit e pelos hashes de fonte.
5. Provisionar autoridade e referências persistentes sob janela de manutenção, sem ativar trading.
6. Executar bootstrap/recovery idempotente e confirmar zero transações pendentes.
7. Executar preflight somente leitura e arquivar seu relatório.
8. Exigir todos os campos do vetor de readiness antes de qualquer rearmamento.
9. Separar a autorização do piloto Live da autorização de release/deploy.

## Rollback obrigatório

- Manter trading real desativado.
- Interromper o avanço ao primeiro hash, geração, assinatura ou receipt divergente.
- Reverter o artefato implantado ao commit anterior sem aplicar reparo CLOSED.
- Não reaproveitar receipts, leases, nonces ou atestados da tentativa abortada.
- Reexecutar recovery e preflight somente leitura após qualquer rollback.
- Preservar Registry, WAL, histórico, backups e evidência de auditoria.

## Inventário completo

## 01 — Entrada, gates e readiness

Arquivos: 13 · bytes: 3324742 · linhas: 74999

| SHA-256 | Bytes | Linhas | Caminho |
|---|---:|---:|---|
| `f9752365930c34237d6e9829e66f3f31337e7fd93e66b50f656eab7d69bf8549` | 3051506 | 68700 | `main.py` |
| `d70988283c7359d6f2c3f653331952eb577983f25d4b5978c324b685cd940847` | 10011 | 241 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_invocation_seam_harness_v1.py` |
| `a810914c6dd95a69a28bba012996699cb744c1ecd62f9f7207c2c2ebdb0f90f8` | 44039 | 1032 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_invocation_seam_v1.py` |
| `6995a7542a268d9c07ac3519c2f7fe99776dd925e4d5a392ecc710a0419c6d99` | 26834 | 611 | `trade_registry_closed_identity_conflict_repair_runtime_installation_preflight_projection_harness_v1.py` |
| `ed86ec184ebe77fc3110420caaa9649333a1aa5df87828f1eba6f00cc0b05055` | 16761 | 426 | `trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_contract_v1.py` |
| `b4b79e8913c987d25e358f9248afd67ceb209f241e51a78acef459f74d0f23e2` | 8298 | 194 | `trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_harness_v1.py` |
| `deb0bb59235f02b6427725ced7e03411f8b140bd55fc5505435fce6f6b07beb3` | 21441 | 517 | `trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_contract_v1.py` |
| `8f36da4774d34aacadcc9a440209ca21f68a85798f5560c432eb74d63db842ea` | 10268 | 241 | `trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_harness_v1.py` |
| `ec7a3caecf86f68dd5422ccf1aa2471ff28c58e0c0543379b63ca664eb6a6668` | 26334 | 662 | `trade_registry_closed_identity_conflict_repair_runtime_seam_v1.py` |
| `47123e749373e23c46fe240d8f2189742bf00c889fe744a2096b31e9655ee18a` | 46651 | 1164 | `trade_registry_closed_identity_conflict_repair_runtime_static_preflight_v1.py` |
| `566dbf502630a80b94d529c8595028e6b1cd50cd2f81c1547f04de1c00f5cbc6` | 19779 | 405 | `trade_registry_closed_identity_conflict_repair_runtime_writer_source_anchor_contract_v1.py` |
| `304d7e453037b947d5efb3518bbf148f32093db14f67effa028da6513f55cb90` | 21683 | 382 | `trade_registry_closed_identity_conflict_repair_runtime_writer_transaction_placement_contract_v1.py` |
| `5d7a19d634d00183f580785858a7c7625ed6c910e6664aaff77c8005170a0ad1` | 21137 | 424 | `trade_registry_closed_identity_conflict_repair_writer_seam_binding_contract_v1.py` |

## 02 — Reparação, autorização e composição

Arquivos: 30 · bytes: 556397 · linhas: 13773

| SHA-256 | Bytes | Linhas | Caminho |
|---|---:|---:|---|
| `c86d8f20c09ec8a45f6df23b1f6cd17519b50ec2e6ac58002c9530f76de6eceb` | 5071 | 131 | `trade_registry_closed_identity_conflict_repair_runtime_apply_schema_static_conformance_harness_v1.py` |
| `6c836dd95a36ed549b2738f5e9ef70e5be16884bb820503e761182dbc63e2756` | 20492 | 536 | `trade_registry_closed_identity_conflict_repair_runtime_apply_schema_static_conformance_v1.py` |
| `1741269be7ae534ba97d30634f3592f5f3e2ced959fce8441a52c0670cacc402` | 7249 | 176 | `trade_registry_closed_identity_conflict_repair_runtime_controlled_authorization_harness_v1.py` |
| `d6c6d764b1cde570fcc0b1ee8f4e56015b16f57850162801e75b1d5878008a98` | 17186 | 424 | `trade_registry_closed_identity_conflict_repair_runtime_controlled_authorization_validator_v1.py` |
| `31247eadff430faed11240c04486749562a659a59170712d5713ae6d6890ecdb` | 9732 | 240 | `trade_registry_closed_identity_conflict_repair_runtime_controlled_repair_package_harness_v1.py` |
| `60a6af207088b8335bb90a5d04ba3d93fac26dd8b2a3dc040576dd02ef1f2e49` | 25738 | 632 | `trade_registry_closed_identity_conflict_repair_runtime_controlled_repair_package_v1.py` |
| `5172c3e8f6e2c9ede0c3749be3c2c72f1909203308a945fd311ea64a36a4f99a` | 15700 | 434 | `trade_registry_closed_identity_conflict_repair_runtime_controller_binding_contract_v1.py` |
| `ee7d03085f9604525b2d22983320175a8810495f56bf76ce1b705c050904ee65` | 8882 | 218 | `trade_registry_closed_identity_conflict_repair_runtime_controller_binding_harness_v1.py` |
| `798cd78420048a9604531ae6a75c71e5272667e8e669a3377c7c5841aef5b50d` | 12121 | 282 | `trade_registry_closed_identity_conflict_repair_runtime_dormant_invocation_gateway_harness_v1.py` |
| `3991d41d11489c58f143ac1f6f97ba4d3249b3cd9813081950edc729439dec2f` | 31562 | 783 | `trade_registry_closed_identity_conflict_repair_runtime_dormant_invocation_gateway_v1.py` |
| `eead2837b484b429dfb395ad68ca64fa2944555f661d2a66cb3de9d07d61d9af` | 37437 | 876 | `trade_registry_closed_identity_conflict_repair_runtime_operation_v1.py` |
| `1703e2bb0ee9e53b0b873f6699ebc93c88037c64a369040797dbf769027843c1` | 8322 | 200 | `trade_registry_closed_identity_conflict_repair_runtime_package_apply_request_adapter_harness_v1.py` |
| `9758566634c3051d83dc1673641e9d06091aa789ed133717fc19f13529d3aa2c` | 23048 | 590 | `trade_registry_closed_identity_conflict_repair_runtime_package_apply_request_adapter_v1.py` |
| `da181da0f95525e281eed665fd2b1698b0b12e21ca2dd5205037cc538144d452` | 15794 | 361 | `trade_registry_closed_identity_conflict_repair_runtime_patch_plan_harness_v1.py` |
| `4a7822dabcbb6e972fdbe1a3048aef865f92a782c22191ac9d2135e45d347a93` | 58271 | 1376 | `trade_registry_closed_identity_conflict_repair_runtime_production_backend_boundary_contract_v1.py` |
| `730611428ef21b20a3e4258f9db0895f32b6c18a9779a584e51b0eda6800188f` | 12677 | 307 | `trade_registry_closed_identity_conflict_repair_runtime_production_backend_boundary_harness_v1.py` |
| `e688f12eb06857ebb3dfe71e2e8a78a795c2bc5a73fbb80c44673fc2842b6ea4` | 41032 | 972 | `trade_registry_closed_identity_conflict_repair_runtime_production_backend_store_adapter_contract_v1.py` |
| `2527b6cbb0c67c2e54815751456e64b556349538ed6f3095484c6e45ea901955` | 9231 | 229 | `trade_registry_closed_identity_conflict_repair_runtime_production_backend_store_adapter_harness_v1.py` |
| `ea037c3ce37cc151792da1df33780221c59615925c0eb3acb940c4655065cc41` | 26032 | 646 | `trade_registry_closed_identity_conflict_repair_runtime_production_backend_terminal_receipt_port_contract_v1.py` |
| `48fcef04d66e10bdbdfd01e4d79f1d36eadd24bba4efb0238f03a51532779a90` | 10131 | 252 | `trade_registry_closed_identity_conflict_repair_runtime_production_backend_terminal_receipt_port_harness_v1.py` |
| `a389917f71ff156a475fa964686bbe004b631a79fefe92fcb5a2c5e196265f76` | 36067 | 905 | `trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_contract_v1.py` |
| `82a5897e1c1bfc6b78fc3c775e0327d48510ad7cd163971d9b0e01684eef1fe3` | 13651 | 338 | `trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_harness_v1.py` |
| `a259b65ed43195a013d62eaab7e77a8511b18feda598a4bb80f195c80a12d007` | 26730 | 644 | `trade_registry_closed_identity_conflict_repair_runtime_production_provider_store_adapter_binding_contract_v1.py` |
| `df61da5345974ac2dfd931abfca4c1aedb3e217e491a3674cb746bcecd40c977` | 9611 | 222 | `trade_registry_closed_identity_conflict_repair_runtime_production_provider_store_adapter_binding_harness_v1.py` |
| `fe0b6eabab5c4ccec23c30ca7744bfb4d39f661a91f5043014ccd80ec70b489c` | 19498 | 519 | `trade_registry_closed_identity_residual_repair_offline_contract_v1.py` |
| `187be6dfd8335598664d1a246395c57f69b1425a9c996594b432c7c82968a70d` | 8280 | 235 | `trade_registry_closed_identity_residual_repair_offline_harness_v1.py` |
| `0a83d8e2445068d6643dcd68e648c734d009d0ccf640bcf86be800f1487b7692` | 16257 | 479 | `trade_registry_closed_identity_residual_timestamp_evidence_extractor_offline_contract_v1.py` |
| `a955118c952e8dbea7f1dfd12699a4dc1f0c7bced8081e39018c5b68d69db9f6` | 5267 | 130 | `trade_registry_closed_identity_residual_timestamp_evidence_extractor_offline_harness_v1.py` |
| `088286bf08eb51c64097cd7f5a564b2f9fdcb78c4ab77f86cd5b6e74159cc1d9` | 19784 | 507 | `trade_registry_closed_identity_residual_timestamp_selection_offline_contract_v1.py` |
| `4d6690c74a58908400e0df61b9c49c06477e7d8e9eded8da3906e356de01c479` | 5544 | 129 | `trade_registry_closed_identity_residual_timestamp_selection_offline_harness_v1.py` |

## 03 — Durabilidade e transações

Arquivos: 10 · bytes: 185057 · linhas: 3890

| SHA-256 | Bytes | Linhas | Caminho |
|---|---:|---:|---|
| `fb1c3c65a10df715531f9146d5597cee2d7bfc1ac7e6cab28e8e8a378ca39c78` | 27813 | 563 | `trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_contract_v2.py` |
| `1d0af0b0b59de1c30a6c9531d3d56f064927d7ef5332954cabccf815f839d9f1` | 16188 | 347 | `trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_harness_v2.py` |
| `683dcdfce3ffd995d8d3efdcb968a97c31e9d9420adf8c7212ec717770ec8772` | 7302 | 162 | `trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_harness_v2.py` |
| `e7d99225bee556614f7c52994a36e56637fd355e0c7ee492c71130aa3591b034` | 27032 | 553 | `trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2.py` |
| `7a1aad314a4dcad60e3692aa4f6e3e157f4fe115266320b96fa2b2c85feabbdf` | 19449 | 420 | `trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_terminal_evidence_contract_v2.py` |
| `a1c278bc170cf1b2ac99aa2bbed7472186b648544c8499f90b98963fad955e0b` | 6865 | 152 | `trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_terminal_evidence_harness_v2.py` |
| `b74e7276688d3258cceba408e73394600e48453180ce08b4e6f589f21a808aa4` | 31327 | 595 | `trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_provider_store_projection_contract_v2.py` |
| `dc40f306b1a46e1f856b602de6b25756bc3c3fa061b99ce7b1f56a2dc1b665d5` | 4995 | 119 | `trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_provider_store_projection_harness_v2.py` |
| `7050f0824363c04732df494a74b5146565b537e3cbbd2414d2803bb0a175e607` | 31666 | 676 | `trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_writer_coordination_compatibility_contract_v2.py` |
| `1dbd53672d4bdab2afe53171eebb754395b52056b8107adc59ff3e09f3fda428` | 12420 | 303 | `trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_writer_coordination_compatibility_harness_v2.py` |

## 04 — Handoff e reconciliação protegida

Arquivos: 38 · bytes: 888178 · linhas: 18956

| SHA-256 | Bytes | Linhas | Caminho |
|---|---:|---:|---|
| `99c4fc7b30c3bc90ff695490b5486b217b868cf3bb54d3bb9420b9b44104e170` | 9383 | 225 | `trade_registry_closed_identity_conflict_repair_runtime_durable_handoff_harness_v1.py` |
| `3bcc9e1689a915b14d071b40b1c5043b0167f8b6e078e95865d025c9cfa9ba76` | 44845 | 1111 | `trade_registry_closed_identity_conflict_repair_runtime_durable_handoff_v1.py` |
| `bf5e4518c8ec0920324c6a92de5ee6b2a4816ee4100fa9db7f82cdc1aea114eb` | 7917 | 187 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_consumer_harness_v1.py` |
| `1820284996742548084c8a3cbcf6cb3270c26e3469cb3db1601a104f8b4874ef` | 25386 | 647 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_consumer_v1.py` |
| `98e9445e26fb54e707f1ef041290233c12d276cadc98f2c90db98dd04da63b73` | 10690 | 271 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_request_adapter_harness_v1.py` |
| `359e8d7ae7f56f5e0ba74d164f53ea0f77a34c37089e00f9367c7890ec9d6576` | 24428 | 611 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_request_adapter_v1.py` |
| `7fcd96ec44ff770116d61125e21daebf2655afe54a2645fbf1806d75c318b4e6` | 37134 | 714 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_dto_materialization_contract_v2.py` |
| `911cacb06578bdea888d82835fa96418b425e27968c7bb1da5c323b2adb92520` | 32033 | 644 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_dto_materialization_harness_v2.py` |
| `e580c52e4c89c0969491416e2c8db442ea0583164dbc1a64473deca25b282866` | 38350 | 857 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_closure_attestation_contract_v2.py` |
| `0246ed8813626dc1d42f470ee3fdefb39d28cc942d4063931221cd4fdeb90657` | 15900 | 270 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_closure_attestation_harness_v2.py` |
| `dcf87e7f034351b421350dd8b4c5f15fd0d92e5763beb2fc5c7379b4a38c8100` | 63392 | 1432 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2.py` |
| `bd311ea74ec9e96ef5c232651d1de6e5ee5c97746f64714e580915738f85aeef` | 25689 | 504 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_harness_v2.py` |
| `1f87356457d0c33c35ea26779a88a1113feab54578fe13e192fdd8be230e9d04` | 20513 | 418 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_commit_contract_v2.py` |
| `534df399e7c06e8aa55d50777145748661cdd422e4aed6913dcdf80611c94652` | 16236 | 278 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_commit_harness_v2.py` |
| `205b680c6cee0dc2aac55c28ab5e5f1714cc938dc536aa23d91be934435fe07d` | 19542 | 368 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_preparation_contract_v2.py` |
| `9c134a05e01aae82e5bdc49557d1bd8d20ab72e5b86bb5faaddf1c61eaf96808` | 13048 | 212 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_preparation_harness_v2.py` |
| `f4cfa76e54ab547c169f85140c15615ea506ef4fb6834738e9111b9d7f00496d` | 20577 | 377 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_restart_admission_contract_v2.py` |
| `8ceddcb3b70033c8a8a812a98cfd4c3f703feadf77edb41e1eb2dab9ba0f420d` | 14664 | 254 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_restart_admission_harness_v2.py` |
| `1ecb66bbab80e4ec16b675f5d56467c5bb1d4b27ffd77902f121f8ca20330e5d` | 23042 | 539 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_contract_v2.py` |
| `05c92083740053644d0e6508955494814394b086738d819cfe56fda01ac23c4e` | 18569 | 439 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_harness_v2.py` |
| `ac2e2ec98a1214d3f2db2345ad33b56c3dabf71fc52400f0a586c275bc06af17` | 14458 | 301 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_outcome_envelope_contract_v2.py` |
| `41439210f4df113fcc985266c84211f6d88364feb6314a05358c67c95cf60db6` | 10578 | 176 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_outcome_envelope_harness_v2.py` |
| `26b9b34151ec7c1c49bb901e141c6cee192791f06ba86525f563a37300c8550a` | 47288 | 1015 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_contract_v2.py` |
| `a40bd612eead852f9fc895ff1719c950263ebabb8732d8e3559f12b970c42d0b` | 31722 | 601 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_harness_v2.py` |
| `9b73852b895ea42c758044cf45fb7f0439e65e8010b55deaaf401d7df1b9a830` | 18401 | 396 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_barrier_contract_v2.py` |
| `0f60fb9e3b296800891d105c72335a63934a9ba76e2f4acaee8aff66fa14a0c4` | 18646 | 359 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_barrier_harness_v2.py` |
| `6cc18f1e0775433c52a0e99960cdee22f89eeb57f334f8fddd7dd0dc17aee379` | 10472 | 226 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_safe_resolution_composition_contract_v2.py` |
| `9efd0a035418008970547de86cb1586c172139f442f4989fb53de3288609c34e` | 20888 | 370 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_safe_resolution_composition_harness_v2.py` |
| `4629f5e84a902902b75fbaeb3b389902b74728c4ff5069d35e6c5dd3eac7f57e` | 31292 | 689 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_handoff_contract_v2.py` |
| `d313f6e5ec62c72a2dcf6dd0b9368fb53d2e8ea7597bb155d4464383766b09f8` | 21793 | 457 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_handoff_harness_v2.py` |
| `a98ae00be617f6d81dd84f06413ba013a15a562cc6c01778af8e7b298834c376` | 20105 | 458 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_contract_v2.py` |
| `9f44da0b24b5c79e082b62d9ff640a990cf2e50655b82a0925272c3e2c2f6382` | 29737 | 636 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_execution_harness_v2.py` |
| `1d8c44178b237c39430141d5b0563bcce6f756c769635b4b5ea4e1e8355e55aa` | 20184 | 447 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_harness_v2.py` |
| `e8ab17a0c5448b685b604f6bb6b44e238eaf877e82dc0d125b1aec5ac16dd5bf` | 23886 | 591 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_v2.py` |
| `4c861de21ed87f1b1bbd818dff26f6471cd1c8ded0b3c69ccd6f5d69c16ffb0a` | 23092 | 502 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_materializer_harness_v2.py` |
| `0ce823559d0b13cbb0605a1f2d66a40a7d81800f09eeb784ba876049d58912dd` | 21729 | 473 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_materializer_v2.py` |
| `7685c74dc6ebbeea09fa44b6211cf1833a38d6864bb399b2b006406f42625f61` | 28182 | 547 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_schema_bridge_contract_v2.py` |
| `ab70b5a53293c0701a431c73d667b90e7bf43e65e3177caa1bf6921bf5cf2742` | 14387 | 354 | `trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_schema_bridge_harness_v2.py` |

## 05 — Startup recovery e autoridade

Arquivos: 70 · bytes: 1132844 · linhas: 26674

| SHA-256 | Bytes | Linhas | Caminho |
|---|---:|---:|---|
| `437f5b15c2d176d355ff50f3322efe5eefeb2264c61911f1c2f43ab938e6276e` | 23025 | 504 | `trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_startup_recovery_contract_v2.py` |
| `9675d758f077dd28e06c14f0a2575b7240dfcfb92bfb391c09010cc732a21d8c` | 6919 | 146 | `trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_startup_recovery_harness_v2.py` |
| `c4ec65defe482ba0394e9453db8ce7e6180ca4774e75a0dcf9e7deb5dbbde67d` | 37034 | 916 | `trade_registry_closed_identity_conflict_repair_runtime_production_backend_startup_recovery_contract_v1.py` |
| `80651c49b1a4fe1bd54b497b1b3bc5a195af0c71614d6ccd660f64370743bd16` | 11341 | 279 | `trade_registry_closed_identity_conflict_repair_runtime_production_backend_startup_recovery_harness_v1.py` |
| `508751f55041ef3b009bcd1b58bde568d5b6b36bcef0866d67078d109061a987` | 12010 | 262 | `trade_registry_closed_identity_conflict_repair_runtime_production_provider_startup_recovery_bridge_offline_harness_v1.py` |
| `59a54da5cb0a63da17c6d9e9065439432e1c0bf547402fdf29ef54bd9efde35b` | 12102 | 289 | `trade_registry_closed_identity_conflict_repair_runtime_production_provider_startup_recovery_bridge_offline_v1.py` |
| `37027560dbe4799be241e7b5e41bddccb0cd6f7f3fbb7584fb8df5d84994fa17` | 27084 | 642 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_authority_binding_contract_v1.py` |
| `082c702b52a1b2c98aea85d82e588c23aa7c9b29ba74abc3d17e96f076f9abc2` | 14659 | 355 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_authority_binding_harness_v1.py` |
| `7de08f2343f40fca36ea11c97007e694c726980710fa1443a6e956fc28db9a76` | 13969 | 325 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_harness_v2.py` |
| `39b9c1197759e0e6b7dfd79698eacbfaed895050f5c9ad52ca2aea4d95afa0d8` | 21049 | 472 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_v2.py` |
| `623dc58a36e2ea568c0cf8002e79c06dd993e9eb7ca1be3f4f8c1d21543b4a9c` | 12305 | 289 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_harness_v2.py` |
| `8defcd409d5dea8470440aababa386eac978e12d95c49437d789645bf5a3e348` | 22419 | 532 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2.py` |
| `10144ed717fde0707c93a6bc6e5e7b41349885c19ac895a34f8e9a6f2b84639f` | 14878 | 342 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_manifest_contract_v2.py` |
| `5168480b815f6d05ec2f33a2aa280e63cfc897fcab92b575b34b204bc9e4f0c0` | 4102 | 89 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_manifest_harness_v2.py` |
| `a2163427672800590d33003c0f86c055a68368e111e35f16ede7a3a572aa38fa` | 30254 | 700 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_physical_binding_contract_v2.py` |
| `bb06b94a0f9ae98b3ca918ecc04bac225f66ee1ac8e2a342add52b5e6f694cbd` | 6468 | 149 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_physical_binding_harness_v2.py` |
| `84c53007944ea5013035b746be1be50b9dcad0cf9519d43b1cce7cd0bd82e7da` | 24524 | 571 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_authenticated_verifier_contract_v2.py` |
| `606dc5db7b516a8885c4ad43185c798584aba285ee6fa21d2d26ea56fec861e9` | 11549 | 281 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_authenticated_verifier_harness_v2.py` |
| `1ab9eb71c36b36e4235ade4d45822823b40eee4bcf7cfff235b8d0d2ffb7d36a` | 16882 | 398 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_contract_v2.py` |
| `284205153293e25416840e44fde3fbab6725f301780bdfb3e2e6b38411e20d76` | 5318 | 126 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_harness_v2.py` |
| `cb854810558e78c553180f8eaaa31e424452a7b2214fcdf550dbcf9de8043b6d` | 25272 | 596 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_evidence_scope_binding_contract_v1.py` |
| `ba767ee64073cc6ab7c5675ff7fa89d5d096722f10adab59383e30d85e38d81d` | 7990 | 178 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_evidence_scope_binding_harness_v1.py` |
| `5544f43067e78769e8e4f6ddcbde862cf548f04ec29bb7248788861b2203349d` | 36253 | 868 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_session_authority_contract_v1.py` |
| `53104d119bd1102e35ad33e6b976b23f321450a978fc75a26c4059c95e08c354` | 13401 | 293 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_session_authority_harness_v1.py` |
| `6cdbd0da1114bd95dc1d10bc785f5829f8c42f6f0a0d23a48f090d8761032f94` | 23431 | 594 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_builder_ports_contract_v1.py` |
| `7df52915185bec4e1dfa7d45c7eff1ed65c11ac67e2757864e56dc3d45f334ca` | 9128 | 223 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_builder_ports_harness_v1.py` |
| `e76e9f424f941868b48ec6386378909a6aa74eb128f80188f7e62f6524314542` | 29587 | 744 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_conformance_contract_v1.py` |
| `8e346d433e503e48635a227d1da8c683ec368e259a37e6322e05feddd08dda7b` | 19807 | 507 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_conformance_harness_v1.py` |
| `c34e8d84ef27aa01e1895b37cf11c2c38d19c222347ea8cf842dd645230005c4` | 24518 | 603 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_read_port_adapter_contract_v1.py` |
| `83345b26cd3f9e14c48b465ca40bf3aaf646241d081aaf2f8e9f826c74a8f65e` | 6949 | 149 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_read_port_adapter_harness_v1.py` |
| `7d4e1239a6210b280f95d66a9cee8eb9eb6941685ea836a7362a6cb0b179f8d3` | 8638 | 202 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_read_port_reference_adapter_offline_harness_v1.py` |
| `0e1708407ad192666921dfe9a6dafc2c80795fde0395223e358a017666619634` | 15052 | 372 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_read_port_reference_adapter_offline_v1.py` |
| `34e21409d9e15260d5ada51b32850b7a1180128714e43e2784fc71773e5cb93a` | 9098 | 205 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_reference_builder_offline_harness_v1.py` |
| `82ab57763bd29dd2ff380f0931f3dbfd295034b983d1c17516634ba288512a9e` | 25936 | 619 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_reference_builder_offline_v1.py` |
| `3f42e0ef317354f39a8f7eb40262fc22adfd5ce83bbc130b7c105c9fbe560658` | 23970 | 626 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_schema_contract_v1.py` |
| `e671173df0a69d30cba5227f0409f40c5ca3b4cd2aa4b62c2d3682288dac7c65` | 7761 | 169 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_schema_harness_v1.py` |
| `155851ab3315cf0035559e08abd59ad960cca7194e31d27f491c24defdda2626` | 16063 | 336 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_physical_conformance_adapter_offline_harness_v2.py` |
| `733dbf6a5b9054469d59796424e60eac2318ee6e010087a9e2a257d4888f6b55` | 22179 | 515 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_physical_conformance_adapter_offline_v2.py` |
| `a94c53b7fd5b671660efe505cd2e8855075906a9a1e10d92b915522fb790c714` | 31035 | 746 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_contract_v2.py` |
| `e87b96ff7946706fde652bf45453122ef3f23c188d58a14b20cc3d74880ae7c3` | 13402 | 341 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_harness_v2.py` |
| `3f80eccbb9c11733212810b092ee845eed530f86eda68478dedbfdc2a2f05cc9` | 5091 | 118 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_aggregate_audit_offline_harness_v2.py` |
| `884fe18e357e8e2892f25ec0a7a91496eecb5591b3c0baaf37818277be53af6b` | 16784 | 390 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_aggregate_audit_offline_v2.py` |
| `8d3dfc6455e4c203622e8b1ed55eca6d61568b3d55b8ccf3649d77bc958fd9dd` | 5630 | 123 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_locked_aggregate_collection_offline_harness_v2.py` |
| `9950336ea5cf3fab20f9ff6555f571655f78f16b9fafe4e306d0307a57afe71a` | 20908 | 454 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_locked_aggregate_collection_offline_v2.py` |
| `4a2e60347c448a93dac0cfb4c1c29e14af5d9c2a502ff2f87fb3be15e0c3b717` | 6655 | 154 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_multistore_observation_lease_offline_harness_v2.py` |
| `479a1752c957decff7c2a62abb63fe2b2f7cd21065698adc0b47a318a5686dfd` | 17555 | 416 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_multistore_observation_lease_offline_v2.py` |
| `ee050501bcf9d0efffee7e037dc5e3093e8788c6aaaf356d10e9c31d6b2a0918` | 7490 | 166 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_resolved_catalog_port_offline_harness_v2.py` |
| `543506f3ccce40b0285c8b55350a132b3276b72d5eca17ee72708bcbbfe19bf7` | 15217 | 408 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_resolved_catalog_port_offline_v2.py` |
| `c155ef199ddc3fe249231b7a7e15d1808b65a6311e3fd9f7241510a26992f088` | 7379 | 161 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_contract_offline_harness_v2.py` |
| `9fd8c8765a7eeb770f32beffd8b1a0b41a31592381ac80513ebcb48f65640da9` | 27248 | 672 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_contract_offline_v2.py` |
| `6d1734c4fd3530bbf9e2fca25c937c4bf74248843929b7c86716ce9f365efc26` | 7832 | 187 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_reference_executor_offline_harness_v2.py` |
| `419893292c0423eb3e4a78fdec0ea46b9d3914026b7bdf8929a861772df0bee1` | 24606 | 595 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_reference_executor_offline_v2.py` |
| `29dbd12a219aafb25f8cebf60fa4327ec3bbaaf3dae724ee437dd15f7a42a61a` | 11126 | 237 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_resolved_authority_store_contract_offline_harness_v2.py` |
| `32f64f45f27325acb23330cd9995ba8755eae3e91569d6373bf65c4af1bc6759` | 24444 | 550 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_resolved_authority_store_contract_offline_v2.py` |
| `061bd08bd743f33d035cafceb5ef4f34351207837dc1bc5c234a7b15a42d5633` | 10396 | 226 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_resolved_store_multistore_lease_composition_offline_harness_v2.py` |
| `d85101c77e8066d39c24c3120888ab98d2821e3c4ffe2dffb284f4c8958a80b8` | 24008 | 544 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_resolved_store_multistore_lease_composition_offline_v2.py` |
| `e3670cc04af882d794cd947837bc44bed01a46cbed6cce98d29d6b88b1b1e8dd` | 7197 | 163 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_bridge_harness_v2.py` |
| `19c32a2a0d5120f8f3d5ae121ccf821b552219534518b87a7498800bf71da7e9` | 15108 | 349 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_bridge_v2.py` |
| `463edee6d3256a30598b6b83f41244b514cf573e7a084bee635ee09b7d009a9c` | 15442 | 346 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_physical_store_reference_harness_v2.py` |
| `fbffa8afd41fed6701a59bc54c0f34b2f2a8e1d659f0d507cf3a71a0fba83a5d` | 19405 | 458 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_physical_store_reference_v2.py` |
| `719d833a15b9e4f3b6100402f1c8cb71dde6e554381ac88f80a231b35556d8fa` | 29153 | 690 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_scope_aware_evidence_conformance_adapter_contract_v1.py` |
| `07e4e3877c5cad6d7cbfd43283970baaf6bf811d548729ed46d510c97cebcce0` | 15227 | 356 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_scope_aware_evidence_conformance_adapter_harness_v1.py` |
| `d0e88593cd8b5e3473a68b54207cff4b85de58f7820c85c24bc59e266615273a` | 6648 | 143 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_six_port_evidence_builder_composition_offline_harness_v1.py` |
| `537da88eda6dc53d9a469eb6c64c898784101381748087f9d20be21ce7e18135` | 15668 | 363 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_six_port_evidence_builder_composition_offline_v1.py` |
| `276d76009d8052939cb6f786ab24f78dffd2e41f7cf09337781de4b36f372b75` | 6277 | 142 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_terminal_receipt_normalizer_reference_offline_harness_v1.py` |
| `b5506629b84bd4f15ec3121fa9523ad33004a6739fb714263c83ef41b2338576` | 11342 | 275 | `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_terminal_receipt_normalizer_reference_offline_v1.py` |
| `e7e3d4496a180a0030d93909e5fe69321737cc90a790712aee5502618c274feb` | 12747 | 299 | `trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_adapter_offline_harness_v1.py` |
| `0535304127885830f9ac7038e25c3aed73dac43ad26f6beeb4c971cd8c36734d` | 22568 | 522 | `trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_adapter_offline_v1.py` |
| `b13ca999551adada457ed551168e8ab2d6e68157c3d73d54ecde3b1cfe167847` | 20089 | 477 | `trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_production_provider_binding_contract_v1.py` |
| `3aed0d79962735c0be1e86465be97515e4fc0a6ad2fbc924f1216c6716e7596c` | 6243 | 137 | `trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_production_provider_binding_harness_v1.py` |

## 06 — Testes

Arquivos: 97 · bytes: 823201 · linhas: 20204

| SHA-256 | Bytes | Linhas | Caminho |
|---|---:|---:|---|
| `730ef3c07381bc808efc26d4f96ab174623a3b4814ffb6ab1cda5c9c2f283eab` | 32449 | 911 | `tests/test_falcon_real_pilot_preflight_fail_closed_v1.py` |
| `561a9869f80ac7690b2fc37f7960f3bb880f313e3df37af94c4273dfeecfbc1b` | 9317 | 195 | `tests/test_trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_conformance_v2.py` |
| `651158a8bf7b55f17c1916a1ab815a0181f3d340e7973c5d19f78c500a7a19a5` | 5240 | 112 | `tests/test_trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_reference_v2.py` |
| `d935c4ef1ce0bbecdbcb6323564967d0e4b320379df8f941b2f64b72028e6951` | 3878 | 92 | `tests/test_trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_physical_terminal_evidence_v2.py` |
| `0f57353709676d45610f5fb0542841735fcf493b62e4f6ccd976115616f4a9d0` | 5382 | 115 | `tests/test_trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_provider_store_projection_v2.py` |
| `90588fec63a553f8cdfd9c8b33b8eaf072a81ab714e0014bb51f5ed76686ccd7` | 4047 | 94 | `tests/test_trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_startup_recovery_v2.py` |
| `5718f6d63772bdc76fc9f8e495613a70cf3ef28eb80ae9a91c6aea053bb482f5` | 5434 | 127 | `tests/test_trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_writer_coordination_compatibility_harness_v2.py` |
| `968440750be9524cba6eec5145c047359bdaa2101588f6354f63309e5c780fe0` | 10797 | 271 | `tests/test_trade_registry_closed_identity_conflict_repair_durable_raw_transaction_backend_writer_coordination_compatibility_v2.py` |
| `2a3dee7785e37553e6625b2f3d9776d954c0b5b3181a63f5d6fb10f46df13db0` | 10204 | 281 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_apply_schema_static_conformance_v1.py` |
| `39387e694b4376e90ae657c86d88a99a5e997716b7f96dc59ca48efadf0ff097` | 11156 | 319 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_controlled_authorization_v1.py` |
| `b84321aa0cccfc280749c5d016564be81f85338f30fd2ed2035c7ebb57830eea` | 12011 | 353 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_controlled_repair_package_v1.py` |
| `cd938fa07c3c19723e08f29e7015f13dd023820c55014bba47b8029565095c75` | 7845 | 215 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_controller_binding_v1.py` |
| `49da7af67e124b366ea8740561179568fdaad42765da91ea9b96f2980a3597e7` | 14304 | 397 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_dormant_invocation_gateway_v1.py` |
| `508eecbffb4b9ff1223f723e1a412a93f84d57c46e47d90396d8414df2947541` | 19099 | 493 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_durable_handoff_v1.py` |
| `ec73e576355a955a828cdcda22aff2e76c84a51ab9cea57e81d99bc1d7d090e4` | 15192 | 410 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_consumer_v1.py` |
| `2ab9abe4b5184691611d5ac12f0d9ecfbfcd87c648a4b297f0d54b4d63941f4e` | 20226 | 508 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_invocation_seam_v1.py` |
| `27f963df207968a957f6e291aa8cde08ccaf3abfebbc1812a65020e0f3e6a3e7` | 14091 | 388 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_raw_transaction_request_adapter_v1.py` |
| `0059501f970f015866e66f014f7767498b6d339100aad629eecef9f645abea68` | 6688 | 152 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_dto_materialization_contract_v2.py` |
| `b156b5fdd4909eb6fdd10781eb236b79d1bb1ed72b59f2dd7743f53a03ecc12d` | 2742 | 68 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_dto_materialization_harness_v2.py` |
| `c80feca0c48a4f2bde2c1f0031e4082d485360f9384f3c2289fc08e7ae0b09ab` | 929 | 19 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_closure_attestation_contract_v2.py` |
| `538ab8d7cd06a27e1f638c05baf8621301dcd50dc59ddf93ddbebf9b9fe40a9c` | 1665 | 29 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_closure_attestation_harness_v2.py` |
| `78d67ce9865f37e329fe19ea27f5623a4cb2e3a888b5b5d1e0ce00ed400bfcd8` | 2754 | 67 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_contract_v2.py` |
| `f7e3c825ce44327e32a4108a7377e7df45cd489cb32105f0a15895535946133d` | 2042 | 51 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_authority_harness_v2.py` |
| `e75a1f0d8904f1539c58dc0147bbfc38fbe29990b82b770e6848581d6682b6c4` | 1013 | 23 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_commit_contract_v2.py` |
| `7ee51c860af4a5461879af8ec1f8c8faf7e99940b0d845ba25af3d0ca76f605d` | 1579 | 30 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_commit_harness_v2.py` |
| `6fd27ea5fd0b6912db92a9c4db4f387c8cf2e5e3e10110abcccb833417b1339c` | 1158 | 24 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_preparation_contract_v2.py` |
| `02bb510146ab4deae3e2dbe6b0c37f9985952d1c5d0f04ea6716fb7140333450` | 1627 | 29 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_resolution_preparation_harness_v2.py` |
| `9c9f4e12a78bc4a5d6aa487d2af36ba65f99dac8c0b6292989eac040dfd05099` | 935 | 22 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_restart_admission_contract_v2.py` |
| `de3f73adf0c33cd44b6445346eada71b0be242b7a9f65971a672e23e6af2a876` | 1677 | 30 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_durable_restart_admission_harness_v2.py` |
| `31e6a5701add8871e031dce8094d89474d8ce181d8043504fe60a6d0bb14dadd` | 3571 | 82 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_contract_v2.py` |
| `702ead5bdab0a98a58d72030c4146bc91e18b5fae19f6dfffa652fddbcb8ba9a` | 2788 | 78 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_obligation_harness_v2.py` |
| `69cd676bb1e7edac5fcf3668a0ae81f34a4c80eb914b25a73337fdcebc236e88` | 974 | 20 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_outcome_envelope_contract_v2.py` |
| `9f6b1ec9d89fc233e0ae080d6a427e9762a34478553cb0a5616a62189a25ebdf` | 1651 | 29 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_outcome_envelope_harness_v2.py` |
| `45fa5397e32bb34b77314aed1fa522d5bd6dae2ef9aeee3a36b3ba03fc7dabea` | 7639 | 171 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_contract_v2.py` |
| `09e4c340e97a328f388c2a1fdbf52291be2a7a99876899e6e7119b6e213c3a18` | 2570 | 63 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_resolution_receipt_harness_v2.py` |
| `b26e96ce7821722ee890f99698ea53c6e33d02a8cdc1425235efe9fba4eec96e` | 4739 | 110 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_barrier_contract_v2.py` |
| `607b000e4933b503daf14d4cab6e9949e70e0fd713ed82f0b8c5d75a3dc93f99` | 2131 | 53 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_barrier_harness_v2.py` |
| `4d7ee7941cee58d020952b174e5c2007aef41092d9a85b03b6c3116021afc429` | 2653 | 56 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_safe_resolution_composition_contract_v2.py` |
| `78b6eb8553fbbbf2c726f732dda959a1d7dc56c421877b5e8d5a5373e42d5b7c` | 2345 | 55 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_reconciliation_restart_safe_resolution_composition_harness_v2.py` |
| `c1bea6167201fa89dc8003edf74448c296f8570b9ba3d52d70850e3892ea19b1` | 8049 | 196 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_handoff_contract_v2.py` |
| `aa166b3c24a7d3635262e4369f7eaa28d533208a04fc0c87a9451b2451ca98ae` | 3901 | 86 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_handoff_harness_v2.py` |
| `cc8d919091d43d02862b2a260c7082f97226640a795496ee7ef7325f7aec4015` | 3851 | 102 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_contract_v2.py` |
| `612be9095ac58f7eeddd46b50b415f0439eb8f344336de1cae29ed0c2bda3fa7` | 2349 | 58 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_execution_harness_v2.py` |
| `264709f84887e5da1cb40b2ee08a97f883c8862b0356456d0c560c7ab8154021` | 2711 | 76 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_harness_v2.py` |
| `3d5a892943385bf484723d74dd86af3b6ffda27504392298177589f9420dd29a` | 4447 | 114 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_held_lease_port_adapter_v2.py` |
| `b5d8af2e999ee97f3e01f661a6e32f9bbefc7ef479fac4b182f42860f5d73285` | 3191 | 87 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_materializer_harness_v2.py` |
| `d1c62944b549e8094a77e609f6e42e6a7b13caa0b8e6c89c9e9438d9d52ad8d8` | 10779 | 257 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_protected_request_materializer_v2.py` |
| `01ed3744b6902dcbed2a86ab7bb164be70deb686425a7f6969825a4cc3329dd1` | 7969 | 180 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_schema_bridge_contract_v2.py` |
| `eacf506646fff9ed56a5bf11bd7585ff2d131dc5bacae6ef64f6346b96b4b38f` | 7820 | 175 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_handoff_v1_backend_v2_schema_bridge_harness_v2.py` |
| `2eeae706b124ded5a1bc89de0f16c42d703a1ab60b879c75256d47b7db79a9c8` | 27588 | 716 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_operation_v1.py` |
| `2bd4259db262e349d0a116d3cdcd319d9cdc1ceebe586e44c90e4e44ed90dc4e` | 11045 | 311 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_package_apply_request_adapter_v1.py` |
| `0ea0be11d1e1fbcce322a61fa65ce9c0757c2641697fd8db0ab9b9b9612e8235` | 23398 | 516 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_backend_boundary_v1.py` |
| `e4f271181cfaae64b46ea999aae412324c8b81f9157c4b15edc75f2ae998f5ee` | 21881 | 539 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_backend_startup_recovery_v1.py` |
| `e46e362c8a32b01f7a4cfd121ffb457338a4634ed33bfd788a71847b6555fcc3` | 19022 | 411 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_backend_store_adapter_v1.py` |
| `e37df9526660b5cb3a8db13b7f04e25956f9c5dd6e12ae2fc60b22d04e1994f4` | 19773 | 479 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_backend_terminal_receipt_port_v1.py` |
| `d933e076e6b4f7409ec9b9426a75b19e4c5f6792522b7f09d3d6146f4bc803b9` | 20143 | 400 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_invocation_envelope_v1.py` |
| `0afdb7302dbe98c4339b514a3dbf4c8120cb9a138773a047a83ee86a7826855f` | 10002 | 228 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_provider_startup_recovery_bridge_offline_v1.py` |
| `ced689d6b168cf1430b78d80d591c3033ddb67c0ada1eb0fdf2c78f1a7137732` | 16936 | 410 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_provider_store_adapter_binding_v1.py` |
| `96690b65a51e22b2cd7b9922e4bf55b08bfc33c4487a50dc839ac4de3cc40f75` | 12115 | 302 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_authority_binding_v1.py` |
| `295cdd2731f963785f36315df1969fa4d17976f853b9f0dd6e52b03b98842123` | 4862 | 119 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_boundary_v2.py` |
| `a9f369e1301b7155725ecd26348fcd0d55733c5fb461bfaa05a5b06c0af7ea27` | 4667 | 110 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2.py` |
| `5e1c792e959abcefb1f6c38dd5e89f53d4ba1b386315c1dc079116279b0053a7` | 4668 | 100 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_manifest_v2.py` |
| `cb2569d2be2faaa5838fb348aa31054f0aa064c1d78eebef6aacd2c28704ce15` | 4549 | 105 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_physical_binding_v2.py` |
| `10ee5bb3aea6f6b72af8eb659f0a060b9ecf9a9b3dbcd6d9131883cac29e7447` | 4560 | 111 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_authenticated_verifier_v2.py` |
| `540996900ca7f1dc0f0df21140f4fcadcdf36e25bd84229d9544d2e30a0e0dc0` | 3840 | 97 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_receipt_v2.py` |
| `57f8dac0267cef8e08c16c5badc3e76fed552746fcb18d3e03ff4674ffc442bf` | 9608 | 231 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_evidence_scope_binding_v1.py` |
| `194ce7961cc7a9fe6a6d6f8a15ac72637cb301e83fe723f2102393ac0eeb4bbb` | 8420 | 210 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_batch_session_authority_v1.py` |
| `f27fd86c3355fed5923ef751805139fbc59b0e07f02d610f29b19c67442b3af5` | 8544 | 217 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_builder_ports_v1.py` |
| `d3eeb866fd06c730ac94f22e5a7a371e986f4e74198cb114591b135a0747cf2c` | 8351 | 199 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_conformance_v1.py` |
| `1725eb350f5100330218e39b15e5d9136d019e6a7c49f01b6e42b48d64486148` | 7644 | 186 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_read_port_adapter_v1.py` |
| `7785a1747334f25e4b4aaac270a8079569e8cfec28020541779a2ea3d64aea37` | 9096 | 207 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_read_port_reference_adapter_offline_v1.py` |
| `841e7dd3a4b0baa8778998bc0453b57b7f9723dd4d05b6d0becd0e38a741f691` | 8923 | 204 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_reference_builder_offline_v1.py` |
| `81e219ddbb5b3cb71096d8e344f195a78ab89dcb9e36b3a4a21e37c1dcfdfc4a` | 6659 | 166 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_schema_v1.py` |
| `53cb80098026a9c6955a023539c61fcab054025d89e04aa9c1500242a4a32605` | 9839 | 207 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_physical_conformance_adapter_offline_v2.py` |
| `dff026ca01ca9e974611a25f898d8c2787ebb0ff5d9c038e202a588995c80962` | 9779 | 236 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_evidence_source_ports_v2.py` |
| `9e2897d9e02dd652bccbaefdf10bd4ed294bb84c4dd8643cd63ade418a058fa7` | 8374 | 187 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_aggregate_audit_offline_v2.py` |
| `e7e047d61a9b31e33c77c6dea0729010ccb49eef809da4bed473f74a354c7038` | 7558 | 172 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_locked_aggregate_collection_offline_v2.py` |
| `d5fc5e2ddea5ce4ace96c802145707ebf7bbaeb75b6e9490aaa6f86865682ac3` | 10045 | 210 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_multistore_observation_lease_offline_v2.py` |
| `710f38470c4e5da4d569dcddb68c08a1388740ea2a875376e2531cdff1d1f4f3` | 7529 | 161 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_physical_resolved_catalog_port_offline_v2.py` |
| `6f5d4e11a0950a3c5539d6c13796f0df11ebdb92c3336ff0d8a4cfb841782891` | 10570 | 260 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_contract_offline_v2.py` |
| `7f5427098560cb05438da65095c58f141fac533481e92fb370a819931e12fa40` | 10214 | 248 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_multistore_observation_lease_reference_executor_offline_v2.py` |
| `956e6091ff5260a89675634ffb4e5c5262419082ee2742b4fdbe4c8d64504be1` | 12085 | 284 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_resolved_authority_store_contract_offline_v2.py` |
| `b9674ebfbf041c8eb7976d9ee586c0cb14bde1d8ec44a3f5c4e4764317ca261a` | 8063 | 208 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_production_resolved_store_multistore_lease_composition_offline_v2.py` |
| `6e15049408fd4429f39cb32bd3a722e66c9fcb050c792d8e2eebe0811618bbf9` | 1823 | 39 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_bridge_v2.py` |
| `54168aa47bf6b0b7841afeafdf540712d6756b98f45348ea78793db0f3883b00` | 4228 | 107 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_resolved_authority_physical_store_reference_v2.py` |
| `a28b70b4e48a038e04830e64c1d43a144cf7faaf89a626fecafe2388b8316cc0` | 8787 | 223 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_scope_aware_evidence_conformance_adapter_v1.py` |
| `743ff450f9d2162da991fb512825d7797456dce926a543ac74f7a82842f7f3d9` | 8150 | 200 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_six_port_evidence_builder_composition_offline_v1.py` |
| `5928d72054aeaab9d866e1cd36cc29b9209ef89f87931621df8b2235d8cc9717` | 10331 | 225 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_terminal_receipt_normalizer_reference_offline_v1.py` |
| `373c4c179e7921844202f5c44639eae651d0cd1fc4ea2a2467d12f9d111e2fbc` | 10070 | 277 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_v1.py` |
| `4396008e8d5db1b5cfaafccc7dd54c877a0095bb6edcb0fed9a339e320e011cb` | 10386 | 268 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_v1.py` |
| `234373ba1300e96ce96e4f9160f2eef5dfa7eae790b707367326275878b1f063` | 22021 | 613 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_seam_v1.py` |
| `2f183a6dd676d964d25d64fa5322a6c895a09f2ebf5eaf1cf31879c40c9b7788` | 9537 | 232 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_adapter_offline_v1.py` |
| `e5be52b6d3532471a829b40485d8399a5d0b98dc10dcc91f713cd7b9152beec8` | 8997 | 210 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_startup_recovery_production_provider_binding_v1.py` |
| `431bc37919868fd40c53b36f94032b8cdb99d76ea26554721409454660ca770f` | 26221 | 652 | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_static_preflight_v1.py` |
| `271f49302ee9fa98ff23a393a9af9557bc3ec7f8fe36e46f21e51de5141acdf9` | 6961 | 181 | `tests/test_trade_registry_closed_identity_residual_repair_offline_v1.py` |
| `9ca7b2832ae7419c05c9f33a48636cce5a953f4b02ab486827d738289c07eddc` | 7109 | 185 | `tests/test_trade_registry_closed_identity_residual_timestamp_evidence_extractor_offline_v1.py` |
| `667d264144b0adf5538b6d4098d7d80a88e24a8ae138a19683a28bcf6d1c56a5` | 6621 | 172 | `tests/test_trade_registry_closed_identity_residual_timestamp_selection_offline_v1.py` |
