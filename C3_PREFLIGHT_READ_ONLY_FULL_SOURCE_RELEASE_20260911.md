# C3 — Árvore completa de fontes do preflight read-only

Data: 2026-09-11, America/Sao_Paulo.

## Resultado

**ÁRVORE DE FONTES PREPARADA E VERIFICADA OFFLINE. 145 testes dirigidos aprovados no novo contexto, sem falhas, erros ou skips. Nenhuma publicação ou ativação.**

Foram reunidas todas as fontes Python rastreadas na base, os arquivos de dependências e as instruções do projeto, com somente os dez caminhos aprovados sobrepostos. “Completa” refere-se às fontes Python da base, não a uma cópia do ambiente operacional: dados, watchlists e outros itens excluídos não foram lidos nem exportados. O diretório não deve substituir uma instalação de produção.

Permanece uma lacuna explícita: os testes executaram em Python 3.14.4, enquanto `runtime.txt` declara 3.11.9. A validação sintática para 3.11 não comprova comportamento sob esse interpretador.

## Identidade e inventário

Worktree: `C:/Users/giuli/OneDrive/Documentos/GitHub/8---Central-Quant/.worktrees/c3_final_release_promote_20260910`.

Novo diretório: `.offline_releases/preflight_ro_full_20260911`, relativo à worktree. Fontes em `src/`; ferramentas e evidências fora de `src/`.

- Base Git local: `d9e12e9daa8f606c3649370bbbf1551650979eb6`, sem fetch, branch ou alteração de index.
- Base: 609 entradas rastreadas, classificadas primeiro por metadados.
- Selecionadas: 553 entradas da base — 550 fontes Python, `agents.md`, `requirements.txt` e `runtime.txt`.
- Excluídas sem leitura de conteúdo: 56 entradas, incluindo quatro arquivos de histórico em `data/`, oito watchlists, documentos históricos, relatórios, diagramas e arquivos sem extensão não classificados como fontes necessárias. Nenhuma exclusão significa apagamento na origem.
- Adicionadas quatro fontes de teste/helpers aprovadas: **557 arquivos finais**, sendo **554 Python**, total **15.900.933 bytes**.
- Inventário SHA-256: `80461db78d76143b30ec99c67875823e094aa7f057848cd3b731d0691e30b9d8`.
- Canonicalização: UTF-8, caminhos ordenados ordinalmente, linhas `<sha256 bruto> <bytes> <caminho>\n`.

O inventário completo de arquivos criados em `src/`, com hashes brutos, normalizados e origem, está em `source_manifest.json`. A seleção e todas as exclusões estão em `selection_manifest.json`. `final_evidence_manifest.json` vincula os hashes das ferramentas, manifestos e evidências desta rodada. Esses arquivos identificam o trabalho offline; não são autoridade autenticada de produção.

## Delta comprovado

A conferência independente dos bytes como blobs Git confirmou **547 arquivos idênticos à base, seis modificados e quatro adicionados**, exatamente os dez caminhos da revisão de promoção.

Seis modificados:

1. `main.py` — somente a chamada abaixo.
2. `tests/test_falcon_real_pilot_preflight_fail_closed_v1.py` — regressões da consulta observacional e falha fechada.
3. `trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_contract_v1.py` — hash/tamanho do main candidato.
4. `tests/test_trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_v1.py` — expectativas correspondentes.
5. `trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_contract_v1.py` — pin transitivo do binding.
6. `tests/test_trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_v1.py` — expectativa correspondente.

Quatro adicionados: `tests/helpers/c3_linux_lab.py`, `tests/helpers/c3_preflight_lab.py`, `tests/helpers/c3_candidate_lab.py` e `tests/test_c3_preflight_candidate_integrity.py`. Os dois últimos continuam exclusivamente de validação. Nenhum helper foi integrado à aplicação.

```diff
-        storage = fn(force=False) or {}
+        storage = fn(force=False, read_only=True) or {}
```

O main completo foi comparado com a base mais essa substituição única antes da escrita. A alteração seleciona o ramo read-only já existente, evitando entrar na instalação de patches durante a consulta. Não executa bootstrap, não fabrica readiness e não transforma a rota inteira em no-I/O.

Hashes normalizados preservados:

| Fonte | SHA-256 |
|---|---|
| main, 2988553 bytes | `4472fa4da21793b67a2c0e5ee846950d94d52ec6be9c5d794dd08345c229ffb9` |
| Binding | `3eaedf291600cf7a680ed6e23ea8ece0d1cae27b17d26a8a5af2c9c38fbb74fd` |
| Patch plan | `f0cf7223b0c8fc91d6a24f3fed52120e5efe44cad0baec70d9b5c2e0d1061ca6` |
| Seam, sem delta | `c5bb7d157d5a77061bd2395ba5fe83dcf7450885c856ff40cdc6664bfa3c5d87` |

Os 59 arquivos do candidato anterior estão byte a byte iguais na árvore nova. As 21 linhas anteriores de manutenção do main e as quatro linhas `maintenance_only` da seam foram excluídas do transporte, mas preservadas na origem. O diff original continua 22/1, 106/3 e 4/0 nos três arquivos correspondentes; os hashes originais conferidos também permanecem iguais. Nenhum pin original ou manifesto histórico foi editado.

## Dependências: análise estática, não execução

Todas as 554 fontes passaram em `ast.parse(feature_version=(3, 11))`, usando o Python 3.12.14 de análise. Não foram importadas para isso. A análise registrou 4926 ocorrências de imports em `static_dependency_audit.json`.

Não há import local obrigatório ausente demonstrado pela varredura de módulos. As oito ocorrências inicialmente pendentes foram examinadas:

- `strategy` e `telegram_utils`, em donkey/meme/trendpro: imports em `try/except` com implementações locais de fallback. São dependências ausentes já na base; não foi testada a equivalência funcional dos fallbacks nem feita chamada ao Telegram.
- `psutil`, em `memory_profiler_v1.py:127`: dependência não declarada, dentro de função e protegida por `try/except`, com fallback para `resource`. Não foi instalada nem executada.
- Import calculado em `executive_policy_learning.py:3318`: o laço usa cinco nomes literais — history_manager, paper_lifecycle, outcome_evaluator, paper_executor_integrated e trade_registry — todos presentes. Nenhum deles foi importado nessa inspeção, e nenhum caminho de dados por eles utilizado foi acessado.

A varredura verifica presença de módulos, não todos os atributos de `from ... import ...`, resolução dinâmica arbitrária, efeitos colaterais, APIs externas ou semântica da aplicação. O catálogo de biblioteca padrão é o do interpretador de análise; não substitui uma instalação validada para a versão-alvo.

`requirements.txt` foi preservado: flask, gunicorn, requests, pandas, numpy, ccxt e upstash-redis, sem versões fixadas. `runtime.txt` continua `python-3.11.9`. Não houve instalação, lockfile, atualização ou mudança de versão. Não foi inventado comando de build/start nem consultada configuração no Render.

## Testes desta etapa

A rodada nova foi justificada pela mudança de contexto: os seis módulos de teste agora foram executados com a árvore completa de fontes disponível em `/work`, não somente as 59 fontes do candidato. Os bytes desses testes e de suas dependências selecionadas permaneceram iguais.

- Laboratório novo: `/var/tmp/cq-c3-lab-full-release-u9lzcygt`.
- Python efetivo: **3.14.4**.
- JUnit: **145 aprovados, 0 falhas, 0 erros, 0 skips**, em **76,078 segundos**.
- Timestamp: `2026-09-11T08:57:29.362617+00:00`.
- SHA-256 do JUnit: `c0822a00ace28e4a0097e1266d2eac30a552eaa13497a049b7a65a0e69399352`.
- Seleção: preflight fail-closed 54, storage 3, binding 37, patch plan 20, preflight estático 29 e drift 2. Não foi usada a seleção padrão de manutenção do helper Linux.

O laboratório confirmou UID 999, namespace de rede separado, zero rotas IPv4, ausência de mounts Windows, fontes somente leitura e scratch ext4. Os bloqueios de rede/processos e de importação do runtime foram instalados antes dos testes. Main não foi importado ou iniciado. As funções exercitadas pelos testes usam extração AST e dependências sintéticas. O processo privilegiado externo apenas preparou permissões e exportação, executando os testes como usuário de laboratório sem privilégios.

Os 557 hashes foram conferidos depois dos testes tanto na origem nova quanto no laboratório; verificação final do pacote também aprovada. Evidências novas em `evidence/full-source-results.xml`, `evidence/lab_manifest.json` e `evidence/run_summary.json`. A rodada anterior e seus arquivos permaneceram intactos.

Não executados: testes sob Python 3.11.9, instalação/build das dependências de produção, suíte geral, import/startup de main, preflight real, bootstrap, reparo CLOSED, broker, recuperação ou trading. Não houve falha de teste funcional a corrigir.

## Arquivos novos e reprodução

Todos os arquivos desta etapa são novos: os 557 arquivos inventariados em `src/`, `package_sources.py`, `validate_full_tree.py`, `selection_manifest.json`, `source_manifest.json`, `static_dependency_audit.json`, `final_evidence_manifest.json`, as três evidências em `evidence/` e este relatório. Nenhum arquivo preexistente foi modificado ou apagado.

`package_sources.py` oferece modos explícitos: `plan`, `export`, `audit` e `verify`. Os três primeiros usam criação exclusiva de artefatos; não reexecutá-los sobre os destinos existentes. `verify` é somente leitura. A exportação seleciona blobs Git previamente classificados e verifica candidato/proveniência antes de escrever.

`validate_full_tree.py run` usa somente Linux/WSL e o laboratório já instalado, com a seleção explícita de `c3_candidate_lab.py`. A evidência é exclusiva: não sobrescrever esta rodada nem repetir cegamente em caso de falha. Uma nova execução requer diretório de evidência novo identificado. As ferramentas não iniciam a Central e não são parte do runtime.

## Próximo passo e limites operacionais

Próximo passo limitado: **fechar a compatibilidade com o Python 3.11 declarado e o checklist de publicação deste delta**, ainda offline quando possível. Primeiro verificar disponibilidade de um interpretador 3.11 isolado, sem instalar ou mudar produção; se disponível e dentro do escopo autorizado, validar os mesmos testes com evidência nova. Não atualizar runtime.txt apenas para acomodar o laboratório.

Antes de uma futura publicação, continuam pendentes: identidade de commit/artefato completo autorizada, preservação de arquivos operacionais no destino, comando de build/start efetivo, versão/ambiente de produção, critérios de rollback e autorização específica para commit/push/deploy. Reaproveitar apenas o delta aprovado; não substituir produção por este diretório que exclui dados e watchlists. Nenhuma nova compra de infraestrutura foi demonstrada como necessária por esta etapa.

O sucesso offline não comprova integridade do Registry real, readiness atual, recuperação, concorrência, ownership operacional, disaster stops ou segurança Live. O read-only ainda consulta status/cache e pode ler o Registry quando chamado em runtime. Percentual restante para Live: **indeterminado**.

Confirmações: nenhum secret, .env, token, chave ou dado operacional acessado; nenhuma chamada a Render, Redis, BingX, Telegram ou API operacional; nenhuma chamada externa pelos testes; nenhum commit, push, pull, merge, fetch, deploy, branch ou Git worktree; nenhuma alteração de flags ou trading real; nenhuma ordem. Consulta à documentação OpenAI e gestão do automatismo são ações separadas da Central.

Objetivo offline concluído. O automatismo deve ser pausado conforme seu escopo finito, sem publicar ou ativar nada. Modelo recomendado para a próxima etapa: **GPT-6 Astra — Alto**, sem alegação de troca efetuada.
