# C3 — Candidato isolado do preflight read-only

Data local: 2026-09-10, America/Sao_Paulo; execução de testes em 2026-09-11 UTC.

## Resultado

**CANDIDATO OFFLINE PREPARADO E VALIDADO: 145 testes aprovados, zero falhas, erros ou skips. Sem commit, publicação, deploy ou ativação.**

A cópia contém somente a correção funcional pretendida e a reatestação diretamente necessária de sua cadeia de integridade, além das ferramentas de teste identificadas abaixo. As alterações anteriores de manutenção foram preservadas na origem e não entraram no candidato.

Este é um subconjunto de fontes para validação e extração de delta, **não uma aplicação completa pronta para implantar**. O sucesso dos testes não autoriza produção, reparo real, readiness ou Live.

## Identidade e evidências

- Worktree de origem: `C:/Users/giuli/OneDrive/Documentos/GitHub/8---Central-Quant/.worktrees/c3_final_release_promote_20260910`.
- Base Git local fixa: `d9e12e9daa8f606c3649370bbbf1551650979eb6`; confirmada sem fetch.
- Diretório candidato: `.offline_candidates/preflight_ro_20260910`, dentro dessa worktree.
- Fontes em `src`: **59 arquivos, 4.510.203 bytes**; nenhum arquivo de dados reais exportado.
- SHA-256 do inventário de fontes: `d58db12422a197d238f2a2f797446fe2b03e70483cfea8cdba7164648b20be01`.
- Canonicalização do inventário: linhas UTF-8 ordenadas por caminho, `<sha256 dos bytes brutos> <bytes> <caminho relativo>\n`.
- SHA-256 da prova de proveniência: `98c6ba530013571f795a6cb538f8580de7820ab3c61bef67120e447157998d31`.

Arquivos de evidência, todos sob o diretório candidato:

| Arquivo | Conteúdo |
|---|---|
| `export_manifest.json` | Base, seleção explícita, dependências importadas e fontes usadas somente como dados AST; hashes antes das edições. |
| `candidate_provenance.json` | Verificação do delta exato, hashes de todas as fontes e diff por arquivo alterado. |
| `candidate_manifest.json` | Inventário final, digests, resultados por suíte, ferramentas e limites de autorização. |
| `evidence/lab_manifest.json` | Hashes dos 59 arquivos efetivamente exportados ao laboratório Linux. |
| `evidence/candidate-results.xml` | Resultado JUnit integral da execução, preservado sem reescrita. |

Esses hashes identificam os artefatos desta validação; não são uma autoridade autenticada de produção nem substituem seus interlocks.

## Delta exato

O único delta funcional em `main.py`, dentro de `_frpp_v1_get_trade_registry_storage`, é:

```diff
-        storage = fn(force=False) or {}
+        storage = fn(force=False, read_only=True) or {}
```

O caminho anterior podia instalar patches e atualizar estado durante a consulta. O novo argumento seleciona o ramo de leitura já existente, sem fabricar readiness ou executar bootstrap. Não torna a rota inteira sem I/O: uma execução runtime ainda pode ler o Registry e o preflight mantém sua própria auditoria.

A verificação de proveniência comprovou igualdade textual com a base mais essa substituição única, mesma quantidade de linhas e igualdade de toda a AST fora do coletor. As 21 linhas anteriores de manutenção em `main.py` e as quatro linhas anteriores em `runtime_seam_v1.py` não foram exportadas da worktree suja: os arquivos-base vieram do commit fixo.

O prefixo dos nomes abreviados `runtime_*` na tabela abaixo é `trade_registry_closed_identity_conflict_repair_`. Os caminhos são relativos ao `src` do candidato.

| Arquivo | Delta em relação à base |
|---|---|
| `main.py` | 1 inserção, 1 remoção: argumento read-only. |
| `tests/test_falcon_real_pilot_preflight_fail_closed_v1.py` | 106 inserções, 3 remoções: regressão de consulta observacional, preservação e falha fechada. |
| `tests/helpers/c3_linux_lab.py` | 160 linhas novas para a base; cópia exata do helper local preexistente, ainda não rastreado. |
| `tests/helpers/c3_preflight_lab.py` | 40 linhas novas para a base; cópia exata do runner já utilizado na validação anterior. |
| `runtime_readiness_binding_contract_v1.py` | Somente hash e tamanho de `main.py`: 2 inserções, 2 remoções. |
| `tests/test_trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_v1.py` | Somente as duas expectativas correspondentes. |
| `runtime_readiness_preflight_patch_plan_contract_v1.py` | Somente o hash transitivo do binding: 1 inserção, 1 remoção. |
| `tests/test_trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_v1.py` | Somente a expectativa do hash transitivo. |

São **8 arquivos de delta, 313 inserções e 10 remoções**. Os demais arquivos provenientes da base permaneceram iguais, além da normalização de leitura usada na comparação. As cópias locais dos dois helpers e do teste de preflight foram verificadas também byte a byte.

Acrescentados exclusivamente à validação do candidato:

- `tests/helpers/c3_candidate_lab.py`: seleção das seis suítes, isolamento e bloqueio explícito de importação do runtime/rede/processos externos.
- `tests/test_c3_preflight_candidate_integrity.py`: dois controles que alteram somente a projeção em memória da leitura de `main.py` e comprovam rejeição por ambos os harnesses, sem escrever o arquivo.

Fora de `src`, as ferramentas novas são `prepare_sources.py`, `audit_candidate.py`, `launch_candidate.py` e `seal_manifest.py`. Servem apenas à exportação, verificação e documentação do candidato. Nenhuma foi integrada à aplicação.

## Reatestação com proveniência

A reatestação foi feita somente depois da prova do delta exato. O contrato funcional dos gates não foi enfraquecido. Hashes normalizados UTF-8/LF:

| Fonte | SHA-256 final | Bytes normalizados |
|---|---|---:|
| `main.py` | `4472fa4da21793b67a2c0e5ee846950d94d52ec6be9c5d794dd08345c229ffb9` | 2988553 |
| Readiness binding | `3eaedf291600cf7a680ed6e23ea8ece0d1cae27b17d26a8a5af2c9c38fbb74fd` | 16761 |
| Readiness preflight patch plan | `f0cf7223b0c8fc91d6a24f3fed52120e5efe44cad0baec70d9b5c2e0d1061ca6` | 21441 |
| Runtime seam, igual à base | `c5bb7d157d5a77061bd2395ba5fe83dcf7450885c856ff40cdc6664bfa3c5d87` | 37093 |

Os contratos de ativação controlada e de preflight estático não foram alterados. A prova compara todos os arquivos-base, permitindo apenas as substituições listadas. Os pins da worktree de origem e os manifestos históricos não foram tocados.

## Testes executados

Laboratório: `/var/tmp/cq-c3-lab-candidate-vnzyjkaq`.

JUnit: **145 aprovados em 74,955 s**, timestamp `2026-09-11T02:39:52.917584+00:00`. SHA-256 do XML: `2f12641906393accf6a67b05239ffd63e8e8d0451300da93b545234c4d9555ee`.

| Suíte | Testes aprovados |
|---|---:|
| Preflight fail-closed | 54 |
| Interlock de storage | 3 |
| Readiness binding | 37 |
| Readiness preflight patch plan | 20 |
| Preflight estático e semântica C3 | 29 |
| Drift da fonte efetivamente lida por ambos os harnesses | 2 |
| **Total** | **145** |

Cobertura relevante: consulta repetida sem instalação/bootstrap/escrita; estados preparado e não preparado; provider legado sem retry mutante; nove lacunas do interlock; vetor completo de 14 condições C3; 19 writers e suas âncoras estáticas; rejeição de marcador literal, condição OR, `ok` genérico, status cacheado/condicional e fontes/recibos adulterados. Os controles de fonte rejeitam drift mesmo quando estruturas derivadas são recalculadas.

O laboratório confirmou UID 999, zero rotas IPv4, namespace de rede separado, ausência dos mounts Windows, fontes somente leitura e scratch ext4. O runner bloqueia sockets, DNS, subprocessos e importação de `main`, `trade_registry`, bots e módulos runtime usados apenas como dados. As dependências executáveis foram identificadas por AST e inspecionadas quanto a importações e superfícies de I/O. Os harnesses de leitura de fonte usam somente os caminhos delimitados no candidato. A aplicação não foi importada nem iniciada.

Depois dos testes, o manifesto do laboratório foi comparado com a prova e os 59 hashes de origem foram recalculados: nenhuma fonte do candidato mudou. Não houve repetição desnecessária da suíte. Pequenos ajustes ocorreram somente na seleção de arquivos do exportador, antes dos testes; não houve falha funcional a corrigir após a execução.

Não executados: aplicação completa, suíte geral do projeto, integração com broker, preflight de produção, bootstrap, reparo CLOSED real, teste de restart de produção ou ensaio de trading. O resultado não cobre essas operações.

## Reprodução delimitada

O candidato já contém a seleção completa. Não usar o launcher padrão de `c3_linux_lab.py`, que seleciona outros testes de manutenção.

Na máquina atual, com WSL Ubuntu e ferramentas existentes, a validação pode ser repetida pelo launcher abaixo. Ele verifica os hashes, cria um laboratório temporário novo e preserva os anteriores:

```powershell
wsl -d Ubuntu -u root -- /usr/bin/python3 -B /mnt/c/Users/giuli/OneDrive/Documentos/GitHub/8---Central-Quant/.worktrees/c3_final_release_promote_20260910/.offline_candidates/preflight_ro_20260910/launch_candidate.py run
```

Pré-condições: Python/pytest, `bubblewrap`, `runuser`, conta Linux `cq-c3-lab` e suporte aos namespaces já existentes. O processo de empacotamento usa root apenas para preparar permissões e baixar para a conta de laboratório; os testes rodam como UID 999. Não foram instaladas ferramentas.

Para reconstruir em outro diretório dedicado, seguir o inventário de exportação da base fixa, aplicar somente os diffs presentes na prova e conferir os digests finais. Os dois arquivos exclusivos de validação têm seus próprios hashes no manifesto. Não copiar a worktree inteira, não copiar dados e não reaproveitar os pins de uma árvore diferente.

O manifesto usa criação exclusiva: não sobrescrever as evidências desta rodada para registrar outra. Uma nova execução exige evidência nova, identificada separadamente.

## Preservação e riscos residuais

- A origem conserva o diff de 22/1 linhas em `main.py`, 106/3 no teste de preflight e 4/0 na seam. As alterações funcionais locais anteriores e seus hashes foram preservados.
- Não houve edição nos contratos, testes ou pins originais; somente no diretório candidato novo e neste relatório novo.
- O pacote é parcial e destinado à validação offline. Antes de qualquer release, o delta deve ser aplicado a uma árvore completa identificada, com revisão do pacote e autorização operacional própria.
- O modo read-only continua consultando status/cache e pode ler o arquivo ativo no runtime. Esta tarefa não introduz auditoria de corrupção do Registry, prova distribuída de autoridade ou recuperação de produção.
- Os 145 testes não comprovam latência de disco real, integridade de dados reais, concorrência de produção, readiness atual, disaster stops ou segurança de um piloto Live.
- A base Git é local; não se verificou qual versão está atualmente no Render.
- Nenhuma compra ou mudança de Render/Redis é necessária para esta conclusão offline.

## Próximo passo e encerramento

Próximo passo limitado: revisão final de promoção do delta identificado para uma árvore completa de release, confirmando escopo, inventário e autorização específica antes de commit/push/deploy. Não copiar o `src` parcial diretamente para produção.

O objetivo deste automatismo foi concluído. Ele deve ser pausado ao entregar o relatório; não há trabalho de produção em andamento.

Confirmações: nenhum secret, `.env`, token ou chave real acessado; nenhum dado operacional/Registry real acessado; nenhuma chamada externa durante testes; nenhum commit, push, pull, merge ou deploy; nenhuma alteração de flags de trading, Render ou Redis; nenhuma ordem ou ativação de shadow, readiness, canário, FAST ou Live.

Modelo recomendado para a próxima etapa: **GPT-6 Astra — Alto**, sem alegação de mudança efetuada. Percentual restante para Live: **indeterminado**; esta validação não fornece uma base para estimá-lo.
