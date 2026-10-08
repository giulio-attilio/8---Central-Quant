# C3 — Publicação isolada do preflight read-only

Data: 2026-09-11. Autorização: resposta “Sim” ao pedido explícito de commit,
push e deploy exclusivamente do pacote validado, mantendo trading desativado.

## Resultado

Commit criado e enviado sem force para `origin/main`:
`17e767c14b7c90c97a01bc5173f4fd94985672cc`.

Pai: `d9e12e9daa8f606c3649370bbbf1551650979eb6`.
Árvore: `b0a21ccaee737b7de412c61505d23ba9b5b12ccd`.
Referência local nova: `codex/c3-preflight-read-only-release-20260911`.

**Deploy não acionado nem confirmado.** Após o push, o painel Render ainda
apresentou `d9e12e9` como última versão implantada com sucesso, deployment
`dep-dahi5gks728c73b7bls0`, sem uma nova implantação na lista consultada.
Isso é observação pontual, não prova do valor da configuração auto-deploy.

A conexão de navegador disponível nesta sessão expõe consulta/navegação, mas
não forneceu uma operação documentada para clicar em Manual Deploy. Não havia
conector Render disponível nem comando `render` instalado no Windows.
Não foram procurados tokens, cookies ou deploy hooks como alternativa.

## Conteúdo exato

O ZIP preservado tem SHA-256
`bea041d619c7c2983b6f80c5b0ece711d3313a698ae36e642c941d529baed112`.
Manifesto: `8e66a16a9426e4581533661c368f9dfe446d9e06b256251e45da34c16d4d0090`.

Dez arquivos incorporados, sem exclusões:

- `main.py`: somente `fn(force=False)` para `fn(force=False, read_only=True)` no coletor de storage do preflight.
- `trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_contract_v1.py`: hash/tamanho correspondentes.
- `trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_contract_v1.py`: hash transitivo correspondente.
- `tests/test_falcon_real_pilot_preflight_fail_closed_v1.py`: regressões read-only e falha fechada.
- `tests/test_trade_registry_closed_identity_conflict_repair_runtime_readiness_binding_v1.py`: expectativas correspondentes.
- `tests/test_trade_registry_closed_identity_conflict_repair_runtime_readiness_preflight_patch_plan_v1.py`: expectativa correspondente.
- `tests/helpers/c3_linux_lab.py`: helper de validação, novo.
- `tests/helpers/c3_preflight_lab.py`: helper de validação, novo.
- `tests/helpers/c3_candidate_lab.py`: adição exclusiva de validação, nova.
- `tests/test_c3_preflight_candidate_integrity.py`: adição exclusiva de validação, nova.

As duas últimas adições continuam exclusivamente de teste, agora incluídas
explicitamente na publicação autorizada dos dez arquivos. Nenhum helper é
conectado ao startup/runtime.

Diff ignorando apenas diferenças de finais de linha: 399 inserções, 10 remoções.
Os bytes CRLF já testados de um arquivo de teste foram preservados. A primeira
checagem de whitespace rejeitou CRLF como espaços finais; a checagem foi
ajustada apenas no script de publicação para reconhecer CR como fim de linha,
mantendo verificações de espaços e linhas em branco. Nenhum payload foi alterado.
Não houve commit nem push na tentativa que falhou nessa checagem.

## Isolamento e verificações

Foi usado índice temporário exclusivo, nunca `git add` sobre a worktree suja.
Somente os dez blobs do delta foram escritos. As 603 entradas fora do delta
foram preservadas por identidade de objeto/modo Git, sem leitura de seu conteúdo.
A árvore resultante tem 613 entradas. Nenhum checkout foi criado/substituído;
o índice e HEAD existentes da worktree de origem foram conferidos intactos.

Foram conferidos ZIP, manifesto, seis evidências, dez hashes/tamanhos/blobs do
delta, seis blobs anteriores e substituição exata única de main. A árvore Git
criada e o commit foram comparados integralmente por metadados com a projeção.
O remoto estava no pai esperado antes da publicação e foi confirmado no commit
novo após o push. Não houve force, merge, pull ou inclusão de arquivos alheios.

Evidência anterior preservada: 145 testes aprovados, zero falhas/erros/skips,
Python 3.11.9 com dependências, JUnit
`de5a4b2c9b436fde86289b0ccd275c57dbbf4443df54e0a382db455e79046483`.
Não foram repetidos testes sobre os mesmos bytes, nem iniciada a aplicação.
Não foi executado preflight real. Não foi verificado o build/start do novo commit
em produção, pois o deploy está pendente.

Arquivos locais novos desta etapa: este relatório e
`.offline_releases/preflight_ro_publication_20260911/publish.py`, `commit.json`,
`push.json` e índices temporários exclusivos. Esses artefatos não foram enviados
ao GitHub. O script tem fases separadas de verificação, commit e push; não é
aplicador de produção. Índices e objetos da tentativa inicial foram preservados;
nada foi apagado.

## Flags, riscos e próximo passo

Valores informados pelo usuário, não relidos do processo em produção:
`ENABLE_REAL_TRADING=false`, `BROKER_DRY_RUN=true`, `EXECUTION_MODE=LIVE`,
`FALCON_MODE=VERIFY`. Nenhum desses valores foi alterado.

A consulta anterior ao Render confirmou build `pip install -r requirements.txt`,
start `python main.py` e branch `main`. Não confirmou a versão exata do Python
ou das bibliotecas em produção. Requirements sem pins é risco preexistente;
o pacote não altera requirements/runtime.txt nem fixa dependências.

Para concluir o deploy: no serviço `central-robos-bingx`, usar Manual Deploy →
Deploy latest commit somente enquanto o commit mais recente de main for
`17e767c14b7c90c97a01bc5173f4fd94985672cc`. Se houver outro commit, não publicar
uma versão diferente por inferência. Não limpar cache, alterar flags nem usar
Deploy a specific commit sem considerar seu efeito sobre auto-deploy.
Referência: https://render.com/docs/deploys .

Após o deploy, conferir o SHA implantado, resultado do build/start e indicadores
sanitizados. O preflight real e eventual bootstrap/reparo não foram executados
por esta publicação. A versão anterior `d9e12e9`/deployment
`dep-dahi5gks728c73b7bls0` identifica a referência anterior para análise de
rollback; não autoriza restauração de dados ou disco.

Nenhum secret foi revelado, copiado ou modificado; autenticação existente do Git
foi utilizada pelo próprio Git. Houve chamadas ao GitHub, navegação no Render e
consulta à documentação pública Render. Nenhuma chamada operacional à BingX,
Redis ou Telegram, acesso ao Registry real, ordem, stop ou alteração de flag.
Commit e push foram executados conforme autorização; deploy permanece pendente.
Automatismo não foi pausado. Este bloqueio é de capacidade de execução do deploy,
não falta de um novo OK.

Modelo recomendado: GPT-6 Astra — Alto. Percentual restante para Live:
indeterminado; testes sintéticos e push não comprovam prontidão de produção.
