# C3 — Validação dirigida no Python 3.11.9

Data: 2026-09-11. Resultado: **145 testes aprovados no Python 3.11.9 exato, exclusivamente offline. Publicação e Live não liberados.**

Este relatório complementa o checklist `C3_PREFLIGHT_READ_ONLY_PY311_PUBLICATION_CHECKLIST_20260911.md`. O registro histórico de indisponibilidade do interpretador foi preservado; a lacuna de execução das seis suítes no interpretador-alvo foi resolvida nesta etapa, após autorização para provisionamento local isolado.

## Ambiente e preparação

- Diretório Linux dedicado: `/var/tmp/cq-c3-lab-py3119-3sd162jx`.
- Interpretador portátil: CPython **3.11.9**, build `Apr 15 2024, 18:24:23`, Clang 17.0.6. Dentro do isolamento: `/opt/c3-py311/bin/python3.11`.
- Distribuição: [Astral python-build-standalone, release 20240415](https://github.com/astral-sh/python-build-standalone/releases/tag/20240415), asset `cpython-3.11.9+20240415-x86_64-unknown-linux-gnu-install_only.tar.gz`.
- Arquivo de 29.812.587 bytes, SHA-256 conferido contra o checksum publicado: `78b1c16a9fd032997ba92a60f46a64f795cd18ff335659dfdf6096df277b24d5`.
- Pacotes exclusivos do laboratório: pytest **8.3.5**, pluggy **1.5.0**, packaging **24.2**, iniconfig **2.0.0**. Wheels Python puro, tamanhos e SHA-256 conferidos contra metadados do PyPI. URLs, hashes e requisitos constam em `evidence/provenance.json`.
- Os downloads públicos ocorreram antes do isolamento, mediante autorização. A instalação usou somente os wheels locais, sem índice e sem rede, como usuário não privilegiado.
- O Python do sistema permaneceu **3.14.4**, confirmado novamente após a execução. Não houve instalação global, alteração de PATH persistente, atualização de pacotes do sistema, alteração de `requirements.txt` ou de `runtime.txt`.

A escolha de 3.11.9 atende à reprodução do patch declarado no projeto, não constitui recomendação de segurança para produção. O runtime portátil não é uma reprodução completa da imagem/build do Render. Hashes publicados no mesmo canal comprovam correspondência dos downloads, não uma auditoria independente da cadeia de fornecimento.

## Isolamento efetivamente verificado

O launcher novo ficou fora da árvore da aplicação. O entrypoint de testes e seu verificador de isolamento existentes foram reutilizados sem alteração.

- Linux, UID **999**, sem capacidades efetivas e com `NoNewPrivs`.
- Namespace de rede diferente do hospedeiro e **zero rotas**.
- Sem mounts Windows, home, root ou diretórios operacionais do hospedeiro visíveis ao teste.
- Fontes em `/work` somente leitura; runtime portátil também somente leitura durante os testes.
- Scratch sintético em ext4; ambiente limpo e autocarregamento de plugins pytest desativado.
- Bloqueio explícito de sockets, subprocessos e imports de runtime, broker e bots antes de carregar os testes.
- `main.py` permaneceu dado-fonte para inspeção AST; a Central não foi iniciada.

## Resultado das mesmas seis suítes

| Suíte dirigida | Aprovados |
|---|---:|
| Preflight fail-closed | 54 |
| Storage readiness | 3 |
| Readiness binding | 37 |
| Preflight patch plan | 20 |
| Preflight estático | 29 |
| Integridade do candidato | 2 |
| **Total** | **145** |

Zero falhas, erros ou testes ignorados. Duração JUnit: **81,389 segundos**. Timestamp da suíte: `2026-09-11T09:51:34.474186+00:00`. Processo concluído com código zero.

JUnit SHA-256: `804708bc44e920b7e3be89c5bda3b98240c2bf2f2206d4bb09000e28dfee151b`.

Os **557 arquivos** da árvore offline e suas cópias sintéticas foram conferidos antes e depois dos testes. Inventário preservado: `80461db78d76143b30ec99c67875823e094aa7f057848cd3b731d0691e30b9d8`. Os oito artefatos vinculados pelo manifesto da validação anterior também foram recalculados e permaneceram intactos.

Não foi executada a suíte global, instalação das sete dependências da aplicação, build/start do serviço, consulta a configuração atual, Registry real, recovery real, reparo CLOSED ou preflight de produção. A sintaxe do novo launcher foi analisada com gramática Python 3.11; seu provisionamento e execução isolada foram exercitados neste fluxo. Os caminhos de erro do próprio provisionador não receberam uma suíte específica de injeção de falhas.

## Arquivos criados e resumo do diff

Nenhum arquivo existente da Central, teste, contrato, pin ou evidência histórica foi editado. Foram criados somente este relatório e os oito arquivos abaixo, todos em `.offline_validation/py3119_20260911/`:

| Arquivo novo | SHA-256 |
|---|---|
| `validate.py` | `cef3b03bf42ec8ab484821e263436cbfd59f2529a8caa367b0f0b59858d5ad0e` |
| `evidence/environment.json` | `73233dc05d2cb4d2d44c44aff31a9909ccdb76979021d5b8a92018ec50ee955d` |
| `evidence/installation.txt` | `e3f24131e2946028fce744df363ac8e70bd38e435b3ce175ccfe099de7a8a7c3` |
| `evidence/location.json` | `7b765132f4860348d0554cd4f5e9874fc953d33cb655c187020e214e139a84d2` |
| `evidence/provenance.json` | `4f0c6da96153da25b3aa20e553d35e2d853271df2f42696f992062ff55238410` |
| `evidence/results.xml` | `804708bc44e920b7e3be89c5bda3b98240c2bf2f2206d4bb09000e28dfee151b` |
| `evidence/run_summary.json` | `94d55111a75d0c7ec9a58ce6fc29fa96d16445a7813541c0df3e291d1e7e81a0` |
| `evidence/tests.txt` | `e94029416bedca76c26f6549899c173a39c2752fd4e5150afe6b29d05fe0f092` |

O launcher novo valida a identidade das fontes, limita hosts/tamanhos dos downloads e verifica hashes; extrai a distribuição com filtro de segurança; instala apenas no runtime portátil e executa o harness existente com isolamento explícito. Diretório de evidências é exclusivo: não sobrescreve resultados de execução anterior. Não deve ser incluído no payload de produção.

Também foram gerados, exclusivamente no laboratório temporário identificado acima, o runtime, archive baixado, quatro wheels, cópias verificadas das fontes e scratch dos testes. Nada foi apagado. O laboratório temporário foi preservado para auditoria, mas não é infraestrutura persistente de produção.

## Pendências e próximo passo

A validação do interpretador-alvo das seis suítes está concluída. Permanecem as outras condições do checklist: dependências da aplicação sem pins e build não validados, artefato publicável/delta autorizado, configuração efetiva e bloqueio de trading, preservação de dados/watchlists, rollback e verificações operacionais pós-deploy. A árvore offline não é substituta integral do diretório de produção.

Próximo passo seguro: revisar a preparação do artefato publicável e as dependências de build a partir das fontes locais, sem modificar produção nem transportar o laboratório. Commit, push, deploy ou consulta operacional não foram executados por esta autorização de ambiente local. Nenhum percentual confiável para retorno a Live pode ser deduzido de 145 testes sintéticos: **percentual restante indeterminado**.

Nenhum secret, `.env`, token, chave, Registry ou dado operacional foi acessado. Houve acesso externo exclusivamente à documentação e aos downloads públicos autorizados; **nenhuma chamada externa durante instalação ou testes**, nem chamada a Render, BingX, Redis ou Telegram. Nenhum commit, push ou deploy, alteração de trading real ou envio de ordem. Nenhum automatismo foi criado, reativado ou alterado nesta etapa.

Modelo recomendado para a próxima revisão: **GPT-6 Astra — Alto**.
