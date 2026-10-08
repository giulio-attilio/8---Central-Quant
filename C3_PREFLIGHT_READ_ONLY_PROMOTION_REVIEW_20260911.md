# C3 — Revisão offline de promoção do preflight read-only

Data: 2026-09-11, America/Sao_Paulo.

## Parecer e limite

**APTO PARA PREPARAR UMA ÁRVORE COMPLETA DE RELEASE OFFLINE, com o inventário e as condições abaixo. NÃO APTO, por esta evidência, para publicar, implantar ou ativar Live.**

A revisão não identificou drift nas fontes ou evidências do candidato. A correção é compatível com a assinatura do provider presente na mesma base. Não há justificativa para repetir agora os 145 testes sobre os mesmos bytes. Ainda não existe uma árvore completa nova identificada e validada: o candidato é um subconjunto de teste, não um pacote de aplicação implantável.

Esta etapa não preparou a árvore completa, não promoveu arquivos e não alterou código. Sua única escrita no projeto é este relatório. A gestão do automatismo ocorre separadamente no aplicativo.

Worktree examinada: `C:/Users/giuli/OneDrive/Documentos/GitHub/8---Central-Quant/.worktrees/c3_final_release_promote_20260910`.

## 1. Evidência conferida nesta revisão

- HEAD e base local: `d9e12e9daa8f606c3649370bbbf1551650979eb6`, consultados sem fetch.
- Candidato: `.offline_candidates/preflight_ro_20260910` nessa worktree.
- Recalculados os hashes e tamanhos dos **59 arquivos** do manifesto: todos coincidem, total declarado e conferido individualmente de **4.510.203 bytes**.
- Inventário canônico: `d58db12422a197d238f2a2f797446fe2b03e70483cfea8cdba7164648b20be01`.
- Proveniência: `98c6ba530013571f795a6cb538f8580de7820ab3c61bef67120e447157998d31`.
- JUnit: `2f12641906393accf6a67b05239ffd63e8e8d0451300da93b545234c4d9555ee`.
- Os 59 hashes também coincidem com `evidence/lab_manifest.json`; as quatro ferramentas externas a `src` coincidem com seus hashes no manifesto.
- Comparação independente com Git confirmou os **49 arquivos-base sem delta**, em texto normalizado para LF, e confirmou `main.py` igual à base mais a substituição única pretendida.
- Relidos `candidate_manifest.json`, a prova de proveniência, os relatórios anteriores, os runners de validação e o teste de drift. Nenhum módulo da aplicação foi importado.

O inventário usa linhas UTF-8 `<sha256> <bytes> <caminho>\n`, ordenadas por caminho com comparação ordinal. A primeira tentativa de recomposição nesta revisão utilizou a ordenação cultural padrão do PowerShell e divergiu; a correção do cálculo para ordenação ordinal reproduziu exatamente o hash existente. Nenhuma fonte, evidência ou expectativa foi alterada para obter essa igualdade.

O JUnit existente registra **145 testes, zero falhas, erros ou skips, 74,955 segundos**, timestamp `2026-09-11T02:39:52.917584+00:00`. Distribuição: preflight 54, storage 3, binding 37, patch plan 20, preflight estático 29, drift 2. São resultados anteriores revalidados por leitura, não uma nova execução de testes.

## 2. Inventário exato da promoção proposta

Caminhos relativos à futura raiz completa. A origem dos bytes é o `src` candidato, nunca o arquivo sujo correspondente da worktree.

| Classe | Caminho | Tratamento proposto |
|---|---|---|
| Runtime | `main.py` | Modificar somente uma chamada: +1/-1. |
| Contrato dormente | `trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_contract_v1.py` | Somente hash e tamanho de main: +2/-2. |
| Contrato dormente | `trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_contract_v1.py` | Somente hash transitivo do binding: +1/-1. |
| Teste | `tests/test_falcon_real_pilot_preflight_fail_closed_v1.py` | Regressões read-only e falha fechada: +106/-3. |
| Teste | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_v1.py` | Expectativas correspondentes: +2/-2. |
| Teste | `tests/test_trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_v1.py` | Expectativa transitiva: +1/-1. |
| Helper de teste | `tests/helpers/c3_linux_lab.py` | Novo em relação à base, 160 linhas; não é dependência runtime. |
| Helper de teste | `tests/helpers/c3_preflight_lab.py` | Novo em relação à base, 40 linhas; não é dependência runtime. |

São **8 arquivos de delta: 6 modificados e 2 novos, 313 inserções e 10 remoções**. A composição funcional pretendida é:

```diff
-        storage = fn(force=False) or {}
+        storage = fn(force=False, read_only=True) or {}
```

Para preservar integralmente a reprodução dos 145 testes, recomenda-se transportar também, como material de teste e sem importação no runtime:

- `tests/helpers/c3_candidate_lab.py`, SHA-256 `bf6eecaa1d55f18ae26bc8b39d5088c153f06aa08b4c63d46930b4beb04e635f`.
- `tests/test_c3_preflight_candidate_integrity.py`, SHA-256 `881d7ff30c63b059dfc39ba086acbac53db634ebce3f965723c3e9a2c60816ff`.

Assim, a proposta contém **10 caminhos de código/teste, sendo 4 novos**, além de eventual documentação nova do release. As duas adições acima continuam exclusivamente de validação; não ampliam a correção runtime.

`prepare_sources.py`, `audit_candidate.py`, `launch_candidate.py` e `seal_manifest.py` ficam fora desse delta de aplicação. Preservar o candidato e suas evidências como artefato de auditoria separado. Não despejar `.offline_candidates` na raiz do release. Esses scripts têm caminhos e premissas próprios do pacote atual; movê-los não torna sua execução automaticamente reproduzível em outra estrutura.

## 3. Integridade e exclusões

Hashes normalizados que a futura árvore deve preservar:

| Fonte | SHA-256 | Bytes |
|---|---|---:|
| main | `4472fa4da21793b67a2c0e5ee846950d94d52ec6be9c5d794dd08345c229ffb9` | 2988553 |
| Binding | `3eaedf291600cf7a680ed6e23ea8ece0d1cae27b17d26a8a5af2c9c38fbb74fd` | 16761 |
| Patch plan | `f0cf7223b0c8fc91d6a24f3fed52120e5efe44cad0baec70d9b5c2e0d1061ca6` | 21441 |
| Seam, sem delta | `c5bb7d157d5a77061bd2395ba5fe83dcf7450885c856ff40cdc6664bfa3c5d87` | 37093 |

A pesquisa dos três hashes históricos de main/binding/patch plan nas fontes Python da base encontrou somente as quatro referências já tratadas pelo delta; não encontrou referência Python literal adicional ao hash antigo do patch plan. Isso delimita as referências literais pesquisadas, não prova ausência de referências dinâmicas ou externas.

Excluir as 21 linhas anteriores de manutenção de `main.py` e as quatro linhas de `maintenance_only` na seam. O diff da origem permanece 22/1 em main, 106/3 no teste de preflight e 4/0 na seam. Os hashes de main, do teste e dos dois helpers locais permanecem iguais aos registrados na etapa anterior. Não usar cópia integral do main sujo.

Não reescrever manifestos históricos nem reutilizar recibos/atestados antigos como autoridade sobre o novo pacote. Normalização LF dos pins não é o mesmo que identidade dos bytes brutos: o teste de preflight tem CRLF no candidato. Um checkout que converta finais de linha exige inventário bruto próprio, ainda que os hashes normalizados coincidam.

## 4. Árvore completa e dependências

A listagem de metadados Git da base contém **609 caminhos rastreados**, contra 59 no subconjunto. A contagem não autoriza exportar todos eles indiscriminadamente. Uma preparação deve selecionar fontes/configurações não secretas da base fixa, sem transportar `.env`, chaves, dados, logs ou arquivos operacionais da worktree. Interromper antes de ler/exportar qualquer item sensível identificado pelo caminho.

Ausências concretas no candidato, presentes na base: `requirements.txt`, `runtime.txt`, `broker.py`, `execution_orchestrator.py` e `bots/falcon.py`. Em particular, main importa `execution_orchestrator` e outros módulos locais ausentes no subconjunto. Portanto, copiar os 59 arquivos sobre um diretório vazio não recompõe a aplicação.

Configurações versionadas lidas apenas como texto:

- `requirements.txt`: flask, gunicorn, requests, pandas, numpy, ccxt e upstash-redis, sem versões fixadas. Blob Git `54df30db71193ab1ebd59386df62c6de12701c23`.
- `runtime.txt`: `python-3.11.9`. Blob Git `546f3c8de171cfec01188be38bc1466f33545866`.
- Não foram encontrados na listagem da base README, Procfile, render.yaml/render.yml, Dockerfile ou configuração gunicorn pelos nomes convencionais pesquisados. Não se inferiu comando real de build/start do Render. Main contém `app.run`, mas sua presença não comprova como o serviço foi configurado.

Não há nova biblioteca de produção introduzida pelo delta. A assinatura existente `trade_registry_persistent_storage_fix_v1_status(force=False, read_only=False, no_io=False)` aceita a nova chamada. Um provider incompatível deve continuar falhando fechado, sem retry mutante.

A validação usa pytest e biblioteca padrão, incluindo `pwd` no helper Linux; não é um runner Windows portátil. Depende do laboratório Ubuntu/WSL existente, bubblewrap, runuser, conta `cq-c3-lab`, namespaces e scratch ext4. O runner padrão de `c3_linux_lab.py` seleciona outros testes: usar a seleção explícita de seis suítes de `c3_candidate_lab.py`. O XML não atesta compatibilidade de instalação de todas as dependências de produção nem, por si só, execução sob a versão de Python declarada em runtime.txt.

O arquivo de requisitos sem pins impede assumir builds futuros byte a byte idênticos. Esse é um risco preexistente; não alterar dependências ou introduzir lockfile neste delta sem análise própria.

## 5. Condições e próxima ação limitada

Próxima etapa proposta: **preparar e verificar offline uma árvore completa de fontes a partir da base fixa, incorporando somente os 10 caminhos acima e documentação nova identificada, sem commit/push/deploy**.

Critérios finitos para essa preparação:

1. Emitir inventário explícito de fontes/configurações selecionadas da base e suas exclusões, sem acessar dados ou secrets; não copiar a worktree suja.
2. Comprovar que o delta completo se limita aos caminhos e mudanças descritos, com os hashes de main/binding/patch plan/seam esperados. Se a base mudar, parar para reavaliar; não atualizar pins mecanicamente.
3. Verificar estaticamente as dependências e arquivos de build/start disponíveis, distinguindo módulos ausentes de imports opcionais, sem importar a aplicação ou instalar pacotes. Não fabricar configuração Render ausente.
4. Produzir manifesto novo da árvore e conferir que as fontes selecionadas para teste coincidem com o candidato já aprovado. Repetir testes somente se houver alteração relevante de bytes, contexto de resolução ou versão de interpretador; quando necessário, usar isolamento e evidência nova, sem sobrescrever o JUnit atual.
5. Documentar validações não realizadas, ambiente necessário e riscos residuais. Não declarar o artefato implantável ou pronto para Live apenas por passar testes sintéticos.

Commit/push/deploy, consulta de configuração operacional, preflight real e qualquer mudança em produção constituem etapas distintas, não executadas nem autorizadas por este parecer. O próximo pacote ainda precisa de identidade própria e revisão operacional aplicável antes de publicação.

## 6. Riscos residuais e encerramento

Read-only continua permitindo leitura de status/cache e do Registry quando chamado no runtime; não equivale a no-I/O. O preflight conserva sua auditoria. Esta correção não implementa bootstrap, integridade completa de dados, recuperação distribuída, controle de concorrência real, disaster stops ou liberação Live. O estado atual de produção não foi consultado.

Verificações executadas agora: leituras de fontes/configurações e Git local, recomposição dos hashes, comparação da base, leitura do JUnit e classificação do inventário. **Nenhum teste novo, build, servidor, worker, bot, scanner ou preflight operacional foi executado.**

Nenhum secret ou dado real foi acessado; nenhuma chamada a Render, Redis, BingX, Telegram ou outra API operacional foi feita; nenhum commit, push, pull, merge, fetch ou deploy; nenhuma alteração de trading/flags, infraestrutura ou ordens. Houve somente consulta à documentação oficial OpenAI e gestão do automatismo, separadas da Central.

Único arquivo criado no projeto nesta etapa: `C3_PREFLIGHT_READ_ONLY_PROMOTION_REVIEW_20260911.md`. Diff: relatório novo, sem alterações de código, testes, pins ou manifestos existentes. A automação deve ser pausada na conclusão deste objetivo finito, conforme seu contrato; não há promoção ou produção em andamento.

Modelo recomendado para a próxima etapa: **GPT-6 Astra — Alto**. Percentual restante para Live: **indeterminado**, sem evidência suficiente para um número confiável.
