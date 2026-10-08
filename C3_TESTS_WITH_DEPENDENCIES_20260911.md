# C3 — Suítes dirigidas com dependências da aplicação

Data: 2026-09-11. **145 testes aprovados no Python 3.11.9, com as dependências da aplicação presentes. Zero falhas, erros ou testes ignorados.**

## Ambiente e resultado

Foi criado um novo laboratório: `/var/tmp/cq-c3-lab-combined-pp9exaaf`. O CPython portátil e todos os wheels vieram dos laboratórios anteriores, com hashes conferidos; **nenhum download ou acesso à rede nesta etapa**.

Foram instalados offline 40 pacotes da aplicação/transitivos, nas mesmas versões anteriormente validadas, e quatro de teste: pytest 8.3.5, pluggy 1.5.0, packaging 24.2 e iniconfig 2.0.0. As 44 versões esperadas foram conferidas por metadados. `pip check` não encontrou requisitos quebrados.

Versões diretas da aplicação: flask 3.1.3, gunicorn 26.2.0, requests 2.34.2, pandas 3.0.5, numpy 2.4.6, ccxt 4.5.78 e upstash-redis 1.8.0. São versões deste laboratório; não foram confirmadas como versões do Render ou incorporadas ao requirements da Central.

| Suíte existente, sem alteração | Testes aprovados |
|---|---:|
| Preflight fail-closed | 54 |
| Storage readiness | 3 |
| Readiness binding | 37 |
| Preflight patch plan | 20 |
| Preflight estático | 29 |
| Integridade do candidato | 2 |
| **Total** | **145** |

Duração JUnit: **79,93 segundos**. Timestamp: `2026-09-11T10:06:49.989129+00:00`. Saída do processo: zero.

JUnit SHA-256: `de5a4b2c9b436fde86289b0ccd275c57dbbf4443df54e0a382db455e79046483`.

O resultado anterior de 145 testes sem esse conjunto de dependências continua separado e intacto. Não houve mudança de expectativas, seleção, mocks ou harness para obter aprovação.

## Segurança e integridade

A instalação usou somente wheels locais, hashes obrigatórios e índice desabilitado, sob usuário não privilegiado. Antes da instalação e novamente no início dos testes, o verificador existente confirmou UID 999, zero rotas, namespace de rede separado, scratch ext4, fontes somente leitura, ausência dos mounts Windows e homes, capacidades zeradas e NoNewPrivs.

Durante os testes, o runtime portátil também permaneceu somente leitura, plugins pytest automáticos ficaram desativados e o harness original bloqueou sockets, processos filhos e imports de runtime/broker/bots. `main.py` permaneceu fonte para inspeção AST, não aplicação iniciada. O launcher externo também recebeu bloqueio explícito de eventos de rede; nenhuma função de download foi chamada.

Foram conferidos antes e depois os 557 arquivos originais e suas cópias. Inventário preservado: `80461db78d76143b30ec99c67875823e094aa7f057848cd3b731d0691e30b9d8`. Também foram conferidos os oito artefatos históricos, os 14 artefatos vinculados da validação de dependências, o JUnit Python 3.11 anterior e os 11 artefatos vinculados da execução atual.

## Arquivos criados e diff

Nenhum arquivo existente da aplicação, contrato, teste, pin, configuração ou evidência anterior foi editado. Foram criados somente este relatório e, em `.offline_validation/c3_with_dependencies_20260911/`:

- `run.py`: launcher externo que recria o ambiente com wheels locais verificados, copia a árvore delimitada, instala offline, confere versões e executa o entrypoint existente. SHA-256: `0aba4fac84886deb24d85560602335eb0534d5cec79ba5e6d4e51b654c66ecbe`.
- `evidence/environment.json`, `environment.txt`, `installation.txt`, `isolation.txt`, `location.json`, `pip-check.txt`, `requirements.test-environment.txt`, `results.xml`, `summary.json`, `tests.txt`, `wheels.json` e `artifact_hashes.json`.

SHA-256 de `requirements.test-environment.txt`: `86e0539cc5977d13080c78fe14231f4e5e5310be84b67f75dfd03b5a502a2b88`. É uma lista exclusiva dos 44 pacotes do ambiente de teste, não um lock de produção.

O laboratório temporário contém uma nova extração do Python, cópias dos wheels, fontes verificadas e scratch sintético. Foi preservado; nada foi apagado. Não deve integrar o release de produção. A sintaxe do launcher foi verificada com gramática Python 3.11 e seu fluxo completo foi exercitado; não foi criada uma suíte específica para todos os erros do launcher.

## Limites e próximo passo

A presença das dependências não alterou o resultado das seis suítes dirigidas. Isso **não** significa que todos os caminhos da Central foram testados contra essas versões: a aplicação permaneceu bloqueada para importação/inicialização. Não foram executados suíte global, build/start do Render, inspeção de configuração operacional, acesso ao Registry, chamadas de broker/Redis, preflight real ou rearmamento.

Próximo passo seguro: preparar um pacote local do delta de release, com manifesto verificável e preservação dos arquivos da base que não pertencem à correção, sem copiar laboratórios, alterar dependências, criar commit ou publicar. As condições operacionais de ambiente efetivo, bloqueio de trading, rollback, dados e preflight pós-deploy continuam pendentes de evidência própria.

Nenhum secret, .env, token, chave ou dado operacional acessado. Nenhuma chamada externa, commit, push, deploy, alteração de configuração de trading real ou envio de ordem. Nenhum automatismo alterado.

Modelo recomendado: **GPT-6 Astra — Alto**. Percentual restante para Live: **indeterminado**; estes testes não autorizam Live.
