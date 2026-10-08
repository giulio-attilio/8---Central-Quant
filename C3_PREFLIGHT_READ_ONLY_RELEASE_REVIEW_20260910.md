# C3 — Revisão offline do coletor read-only do preflight

Data: 2026-09-10, America/Sao_Paulo (retomada em 2026-09-11 UTC).

Worktree examinada: `C:/Users/giuli/OneDrive/Documentos/GitHub/8---Central-Quant/.worktrees/c3_final_release_promote_20260910`.

Base Git local: `d9e12e9daa8f606c3649370bbbf1551650979eb6`.

## Parecer

**APTO PARA PREPARAR um candidato isolado offline, com as condições abaixo. NÃO APTO para considerar o release validado, fazer deploy ou liberar Live.**

A correção funcional é pertinente, pequena e coberta por evidência sintética verificável. Entretanto, o diretório atual contém alterações anteriores que não pertencem à correção. Além disso, mesmo a alteração isolada de uma linha invalida o pin de `main.py` usado pelo readiness binding. O pacote isolado, suas dependências de teste e a cadeia de hashes ainda precisam de validação própria.

Este parecer não autoriza essa preparação nem executa release. Não foram criados branch, worktree, commit, push, pull, merge ou deploy. Nenhum hash, contrato, teste ou código foi alterado nesta revisão. A única escrita de projeto desta etapa é este relatório.

## 1. Causa e fluxo revisado

Em `main.py`, `_frpp_v1_get_trade_registry_storage` chamava `trade_registry_persistent_storage_fix_v1_status` apenas com `force=False`. O parâmetro `read_only` dessa função tem default `False`; por isso, o coletor podia instalar patches de persistência e atualizar `_TRPSF_V1_STATE["last_status"]` durante uma consulta.

Não se conclui que a chamada antiga sempre gravasse o Registry: `force=False` não solicita bootstrap. O problema comprovado é a entrada no caminho de instalação e mutação de estado em memória.

Delta pretendido, em uma única linha:

```diff
-        storage = fn(force=False) or {}
+        storage = fn(force=False, read_only=True) or {}
```

Âncora atual: `main.py:56399`; na base isolada sem as adições anteriores: linha 56378. Selecionar a função e o conteúdo exatos, não somente o número da linha.

No caminho corrigido:

- O status é uma cópia do cache, ou `BOOTSTRAP_STATUS_NOT_AVAILABLE` quando não há cache.
- Não são chamados `_trpsf_v1_apply_patch`, bootstrap ou gravadores por esse ramo.
- O coletor preserva o resultado do provider `falcon_live_entry_storage_readiness`; não fabrica readiness a partir de um status textual.
- Provider ausente, inválido ou com exceção conserva a falha fechada existente. Um provider legado sem o argumento `read_only` resulta em `ERROR`, sem nova tentativa no caminho mutante.
- A leitura de status não promove um Registry não preparado nem invalida artificialmente a prova de um Registry já preparado.

Foram inspecionados também `_trpsf_v1_active_file`, `_trpsf_v1_read_json`, `_trpsf_v1_registry_counts`, `_trpsf_v1_iter_trades` e `_trpsf_v1_falcon_live_entry_storage_readiness`. O contador utiliza projeções/cópias e não persiste dados.

Limite importante: `read_only=True` não significa `no_io=True`. O status ainda pode ler o arquivo ativo e consultar sua existência quando executado no runtime. Nesta revisão isso não ocorreu. O preflight completo também conserva sua própria gravação de relatório de auditoria; a correção não transforma toda a rota em uma operação sem I/O.

## 2. Inventário do delta pretendido e dependências

Os caminhos desta seção são relativos à worktree identificada acima.

| Arquivo | Tratamento no futuro candidato isolado |
|---|---|
| `main.py` | Somente a substituição de uma linha do coletor; +16 bytes UTF-8 normalizados, sem acrescentar linha. |
| `tests/test_falcon_real_pilot_preflight_fail_closed_v1.py` | Delta atual: 106 inserções e 3 remoções; atualização dos fakes e novos controles de regressão. |
| `tests/helpers/c3_preflight_lab.py` | Novo executor de testes, 40 linhas; atualmente não rastreado pelo Git. Não é dependência runtime. |
| `tests/helpers/c3_linux_lab.py` | Dependência preexistente do executor, 160 linhas; também não rastreada. Precisa integrar o pacote de validação reproduzível ou ser fornecida por um artefato de teste identificado. Não omitir silenciosamente. |
| `tests/test_trade_registry_live_entry_storage_readiness_v1.py` | Dependência de teste já rastreada, sem delta; integra os cinco arquivos exportados ao laboratório. |

Portanto, são quatro arquivos a incluir/revisar no delta funcional e de ferramentas de teste, com um quinto arquivo inalterado necessário à execução. Isso ainda não inclui as mudanças condicionais de integridade descritas na seção 4 nem um futuro manifesto novo. Não há pacote final fechado nesta revisão.

### Exclusões obrigatórias

Há 21 linhas anteriores adicionadas a `main.py`: a variável `C3_MAINTENANCE_STARTUP_BINDING_V1`, a função `_bind_c3_startup_maintenance_v1` e a guarda em `start_central_runtime_once`. Elas não fazem parte desta correção.

Há também quatro linhas anteriores em `trade_registry_closed_identity_conflict_repair_runtime_seam_v1.py`, rejeitando um coordenador `maintenance_only`. Não pertencem a este release. Preservá-las na worktree de origem; não removê-las nem promovê-las incidentalmente.

O diff total atual de `main.py` é 22 inserções e 1 remoção, enquanto o delta pretendido é 1 inserção e 1 remoção. Copiar o arquivo inteiro atual para um release levaria alterações não autorizadas para esse pacote.

### Reprodutibilidade do laboratório

Os dois helpers foram lidos integralmente. O launcher padrão de `c3_linux_lab.py` seleciona testes de manutenção diferentes; não reproduz automaticamente esta rodada de preflight.

A execução registrada utilizou, apenas em memória no processo exportador:

```python
lab.TESTS = [
    "tests/test_falcon_real_pilot_preflight_fail_closed_v1.py",
    "tests/test_trade_registry_live_entry_storage_readiness_v1.py",
]
lab.EXTRA = [
    "tests/helpers/c3_linux_lab.py",
    "tests/helpers/c3_preflight_lab.py",
]
```

O exportador acrescenta `main.py` como dado AST. O entrypoint foi `/work/tests/helpers/c3_preflight_lab.py`, com timeout de lançamento de 120 segundos. Uma futura instrução reproduzível deve preservar essa seleção explícita e não recorrer ao launcher padrão.

Dependências locais: WSL Ubuntu, Python 3, pytest, `bubblewrap`, `runuser` e usuário Linux `cq-c3-lab`. Nenhuma foi instalada nesta revisão. A reprodução depende dessas condições, não é uma garantia genérica para qualquer máquina/CI.

O laboratório verifica isolamento antes da execução dos testes: usuário não root, namespace de rede separado, zero rotas IPv4, fontes somente leitura, ausência dos mounts Windows e diretórios sensíveis, capabilities zeradas e scratch ext4. O entrypoint adicional bloqueia sockets, resolução DNS, `subprocess.Popen` e `os.system` antes de importar pytest; desabilita conftest e cache. O ambiente desabilita autoload de plugins. Isso é uma barreira proporcional a estes testes inspecionados, não uma alegação de sandbox universal para código arbitrariamente hostil.

## 3. Evidência dos testes e preservação

Foram relidos nesta revisão, sem reexecutar pytest:

- `/var/tmp/cq-c3-lab-preflight-wtt0d97z/manifest.json`.
- `/var/tmp/cq-c3-lab-preflight-wtt0d97z/scratch/preflight-results.xml`.

O JUnit registra **57 testes, zero falhas, zero erros, zero skips**, em **23,367 segundos**, com timestamp `2026-09-11T01:46:14.137940+00:00`. Os hashes brutos dos cinco arquivos atuais coincidem exatamente com o manifesto daquela execução:

| Arquivo | SHA-256 dos bytes efetivamente testados |
|---|---|
| `main.py` | `a6b3a4f6a7d6196eb30dfa98ac9d92c748b34baa9e39421b43f9fd7e8fb06295` |
| `tests/test_falcon_real_pilot_preflight_fail_closed_v1.py` | `41e6f8294defd39b93fd31f20486c9adbd52fa8a675fae98973504dae19ef533` |
| `tests/test_trade_registry_live_entry_storage_readiness_v1.py` | `87ee5082a8da146c55e9e1bca9c27223d705ad4e5383b95930fc0a3aec89dc04` |
| `tests/helpers/c3_linux_lab.py` | `bb903f1ffbc5188313c021515b327f77b7f126b843d3299514966d72cfb17073` |
| `tests/helpers/c3_preflight_lab.py` | `c52584488ce4d3d6612bf6e800c27c8fe8f9d21ec31bd60c9469f08768251ecb` |

A suíte carrega funções selecionadas da AST; não importa `main.py` nem executa seu startup. O novo teste parametrizado combina o coletor, a função real de status e a função real de readiness com dependências sintéticas. Executa duas leituras para os estados pronto/não pronto, proíbe instalação/bootstrap/escrita, compara o estado antes/depois, a identidade do cache e os atributos do Registry fictício. Verifica ainda que o checklist preserva a decisão de readiness.

Há cobertura da chamada exata `(force=False, read_only=True)`, provider inválido/ausente/com exceção, incompatibilidade de assinatura sem retry, nove lacunas do interlock, deadline, evidência faltante e isolamento de posições manuais. Esses testes não comprovam a operação em produção nem o comportamento concorrente de todos os writers.

Os 57 testes foram executados sobre o `main.py` da worktree com as alterações anteriores, não sobre o candidato isolado. A extração AST limita o que foi executado, mas não elimina a necessidade de validar o pacote exato após isolamento.

Verificações feitas agora: leitura de fonte/diff, identificação do HEAD, comparação dos hashes, leitura do JUnit e `git diff --check` dos dois arquivos rastreados da correção, aprovado. Houve aviso de normalização LF/CRLF, sem erro de whitespace.

Não foram repetidos os 57 testes. Não foram executados a suíte C3 completa, o preflight estático completo, os harnesses de binding/patch plan, a aplicação ou um preflight de produção. Não há motivo para repetir a rodada funcional sobre bytes idênticos apenas nesta revisão.

## 4. Integridade: hashes que precisam de revalidação

O contrato de binding normaliza CRLF/CR para LF antes do SHA-256. Seus hashes não devem ser confundidos com os hashes brutos do manifesto do laboratório.

| Fonte | SHA-256 normalizado | Bytes normalizados |
|---|---|---:|
| `main.py` em HEAD, igual ao pin histórico | `6bb4b7881839f15123e0f27b176d01d638070633d792c6ccdae9c4d9aee5bbb3` | 2988537 |
| `main.py` candidato: HEAD mais somente `read_only=True`, construído apenas em memória | `4472fa4da21793b67a2c0e5ee846950d94d52ec6be9c5d794dd08345c229ffb9` | 2988553 |
| `main.py` atual com as 21 linhas anteriores | `c62cde295b5de4b97b1414f0541cc8df94790171fd3e446bbc9402a8dd9d7207` | 2989701 |
| `runtime_seam_v1.py` atual, com as quatro linhas anteriores | `a7341e1431065f037dad02c9da05fa39e470a6c7a68e3c1c666c1a509634e8c6` | 37270 |

O nome abreviado `runtime_seam_v1.py` nesta tabela corresponde a `trade_registry_closed_identity_conflict_repair_runtime_seam_v1.py`.

O pin esperado da seam continua `c5bb7d157d5a77061bd2395ba5fe83dcf7450885c856ff40cdc6664bfa3c5d87`, 37093 bytes. Sua divergência atual é anterior e não deve ser absorvida para acomodar a correção do coletor.

### Cadeia diretamente afetada

1. `trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_contract_v1.py` fixa `main.py` em `_SOURCE_ATTESTATION_PINS`. O hash do candidato isolado já difere do pin. O teste `test_source_pins_match_audited_dormant_hardening_payload`, em `tests/test_trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_v1.py`, também exige o valor histórico exato. O harness lê as fontes e rejeita divergências; não basta fornecer hashes arbitrários.
2. Se uma revisão futura aprovar reatestar esse binding para o novo payload, mudará o hash do próprio contrato. O valor atual, conferido, é `f55f6503330f2395f72545c6a5985f0e528671bfbcebe3211fa66be4d8c1410e`, 16761 bytes.
3. Esse valor é pin transitivo em `trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_contract_v1.py` e expectativa explícita em `tests/test_trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_v1.py`. A cadeia deve ser revalidada conjuntamente. O contrato de patch plan atual é `d256ec4d0d272d86e4a2390c638ad5227ffbd2828daffc6e166298829950bf1c`, 21441 bytes.
4. `trade_registry_closed_identity_conflict_repair_runtime_static_preflight_v1.py` gera atestados de fonte e verifica semântica/âncoras dos writers. Seu hash atual coincide com o pin: `e2808fbe9e746ee67fbf528af66fc5e240cd3555e0d17ef8c45f1b778f2e7575`, 46173 bytes. Não é necessário alterá-lo só porque `main.py` mudou; é necessário reexecutar sua validação dirigida sobre a árvore isolada e produzir evidência nova.
5. O contrato de ativação controlada também permanece igual ao pin: `ee4359680ee610ee2424271f4bd1552a2018b802b25d3c4396faeb9c17b572d1`, 15557 bytes. Recibos/propostas que incorporam atestados do payload não devem ser reutilizados como prova do candidato novo.
6. A seam inclui `main.py` no conjunto de fontes da evidência de ativação controlada. Uma eventual evidência runtime futura deve corresponder ao artefato efetivo. Atualizar um hash não concede autoridade nem readiness.

A divergência dos pins é demonstrada por leitura e cálculo, não por uma execução nova da suíte. Os harnesses e testes de integridade correspondentes não podem ser declarados aprovados sobre o candidato novo neste momento.

Não houve atualização de pins. A preparação futura deve primeiro revisar o delta e estabelecer sua proveniência, depois reatestar apenas o necessário e validar controles negativos de drift, gates incompletos e fontes alteradas. Não se deve trocar expectativas só para deixar os testes verdes.

### Manifestos históricos

`docs/C3_CLOSED_RESIDUAL_PREVIEW_FINAL_RELEASE_MANIFEST_20260910.md` atesta o payload `65946040a3398c5f1d9eaa4bbe9f4341ed55a090`, árvore `0bcee2cdb27bf56de41f8312245468db7a03e381`, com inventário `39ac7123adfb6c027e82143ba086641a17be459c5146cf81f51072bd896db651`. Sua suíte de 57 testes é a de binding/patch plan, não esta rodada de preflight de 57 testes.

As contagens de 321 e 1512 testes e 56 subtestes desse manifesto também são históricas. Não validam o novo delta. Preservar esse documento; se houver preparação futura, gerar identidade e manifesto próprios, sem reescrever o histórico.

## 5. Riscos residuais e condições para a próxima etapa

- A validação positiva usa dados em memória e I/O injetado. Não mede latência de disco, arquivos grandes, corrupção real, reinício de produção ou concorrência.
- O modo read-only ainda usa parte do status cacheado. `_trpsf_v1_read_json` pode devolver `None` em erro e o status projetar contagens vazias; esta correção não cria uma prova nova de integridade do arquivo nem altera o contrato de readiness existente. Não interpretar o resultado como auditoria integral do Registry.
- Um provider incompatível passará a falhar fechado, em vez de executar sem read-only. É um comportamento de segurança deliberado; verificar compatibilidade da função no pacote final.
- A ausência de bootstrap continua bloqueante; esta correção não pode ser usada como inicialização automática do Registry.
- Os gates C3 e a composição runtime continuam fora do escopo. Um release aprovado desta correção não comprovaria que a Central está pronta para Live.
- Ferramentas de teste não rastreadas e o conjunto de testes padrão diferente exigem instruções explícitas de reprodução.

Próximo passo limitado, ainda não executado: preparar um candidato somente offline a partir do HEAD identificado, transportando apenas o delta funcional e as dependências de teste necessárias; auditar/revalidar a cadeia de integridade; executar a suíte funcional e os testes dirigidos de binding, patch plan e semântica estática sobre os bytes exatos do candidato; emitir manifesto novo. Continuar sem commit, push, deploy, alterações de produção ou Live até autorização específica aplicável.

Não há necessidade demonstrada nesta etapa de mudar Render, Redis ou adquirir infraestrutura.

## 6. Encerramento e segurança

- Nenhum secret, `.env`, token ou chave real foi acessado.
- Nenhum Registry, dado operacional, painel, shell remoto ou API operacional foi acessado.
- Nenhuma chamada externa foi feita nos testes; nenhum teste novo foi executado nesta revisão. A gestão do automatismo é uma ação do aplicativo, separada da Central.
- Nenhum commit, push, pull, merge, deploy, branch ou worktree foi criado.
- Nenhuma configuração de trading real foi alterada; nenhuma ordem foi enviada e nenhuma ativação ocorreu.
- Código, testes, pins, alterações anteriores e manifestos históricos foram preservados.

Ao entregar este relatório, a automação deve ser pausada conforme seu objetivo finito, sem avançar automaticamente para release ou produção.

Modelo recomendado para a próxima revisão: **GPT-6 Astra — Alto**; não implica mudança de modelo realizada. Percentual restante para Live: **indeterminado**, por ausência de uma base mensurável e de evidência operacional atual.
