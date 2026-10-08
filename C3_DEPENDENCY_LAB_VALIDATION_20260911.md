# C3 — Validação das dependências em laboratório isolado

Data: 2026-09-11. **Instalação conjunta e verificações sintéticas aprovadas no Python 3.11.9. Não constitui liberação de build, deploy ou Live.**

## Resultado

Os sete requisitos originais foram resolvidos com pip 24.0 em um novo ambiente Linux x86_64 descartável. Foram obtidos **40 wheels**, incluindo dependências transitivas, totalizando **49.984.719 bytes**. Todos foram verificados por SHA-256, instalados sem rede e submetidos a verificação de consistência. Nenhum pacote precisou ser compilado e nenhum requisito da Central foi alterado.

| Requisito direto | Versão efetivamente validada |
|---|---|
| flask | 3.1.3 |
| gunicorn | 26.2.0 |
| requests | 2.34.2 |
| pandas | 3.0.5 |
| numpy | 2.4.6 |
| ccxt | 4.5.78 |
| upstash-redis | 1.8.0 |

Essas são versões resolvidas nesta consulta pública, **não versões confirmadas da produção nem recomendação de atualização**. Foram registradas todas as versões, URLs, nomes de wheels e hashes em `evidence_attempt2/wheels.json`, e um requirements resolvido exclusivo do laboratório em `evidence_attempt2/requirements.resolved.txt`.

SHA-256 desse requirements resolvido: `44b6e731a9605cda2fc411cb6feea5d35d08ec61247eeb182e8b55196d94ca29`. Não foi copiado para o requirements da aplicação, nem promovido a lock de produção. Ele representa somente os wheels selecionados para este ambiente; não é um lock universal entre plataformas.

## Procedimento e isolamento

O CPython portátil foi extraído novamente do archive previamente verificado, sem reutilizar ou modificar a instalação do laboratório anterior. A consulta de metadados e downloads públicos ocorreu em etapa separada; o resolvedor tinha rede, usuário sem privilégios, ambiente limpo e runtime somente leitura, sem fontes da aplicação, homes, credenciais ou dados montados. Aceitou apenas wheels, sem builds de fontes.

A primeira tentativa sofreu timeout de leitura dos metadados de aiohttp no PyPI. Foi preservada integralmente em `evidence/` e no laboratório `/var/tmp/cq-c3-lab-dependencies-u51bg928`. Não houve instalação nessa tentativa. Uma única nova tentativa, com deadline de leitura de 45 segundos em lugar de 30, concluiu a resolução sem alterar os sete requisitos. Não foi necessário forçar versões ou ignorar conflitos.

Laboratório bem-sucedido: `/var/tmp/cq-c3-lab-dependencies-0duryfjg`.

Antes da instalação foi verificado o isolamento: UID 999, zero rotas, namespace de rede distinto do hospedeiro, fontes de teste somente leitura, scratch ext4, ausência de mounts Windows/homes e capacidades efetivas zeradas. A instalação usou índice desabilitado, wheels locais e hashes obrigatórios. As verificações posteriores mantiveram também o runtime portátil somente leitura.

As opções de resolução sem instalação, wheels e hashes seguem a documentação do [pip install](https://pip.pypa.io/en/stable/cli/pip_install/) e de [instalações com hashes](https://pip.pypa.io/en/stable/topics/secure-installs/). A versão efetivamente usada foi 24.0, registrada separadamente; não houve atualização do pip.

## Verificações executadas

- Python exato 3.11.9 confirmado.
- `pip check`: **No broken requirements found**.
- Versões instaladas dos 40 pacotes conferidas contra a resolução.
- Importação dos sete pacotes principais concluída sem erro.
- Operação NumPy e DataFrame pandas com valores sintéticos aprovados.
- Requisição ao cliente de testes Flask, inteiramente em memória, aprovada; nenhum servidor foi iniciado.
- Teste negativo de criação de socket: bloqueado por AssertionError antes das importações dos pacotes. O mesmo audit hook proíbe rede e subprocessos nas verificações.
- Nenhuma instância de exchange, cliente Redis ou envio de requisição HTTP foi usada nos testes.
- Sintaxe dos dois novos scripts verificada com gramática Python 3.11.
- Os 557 arquivos da árvore offline foram conferidos antes e depois; inventário preservado: `80461db78d76143b30ec99c67875823e094aa7f057848cd3b731d0691e30b9d8`.
- Os oito artefatos históricos, o JUnit dos 145 testes anteriores e os 14 artefatos vinculados pelo novo `artifact_hashes.json` foram conferidos.

Não executados: 145 testes C3 novamente neste novo conjunto de dependências, suíte global, inicialização da Central, build/start do Render, chamadas de broker/Redis, preflight real ou testes completos das APIs das bibliotecas. Importar pacotes e verificar seus metadados não demonstra compatibilidade de todos os caminhos da aplicação, nem equivale a auditoria de vulnerabilidades. Em especial, a disponibilidade dos wheels neste Linux não prova compatibilidade com a imagem efetiva do Render, ainda não inspecionada.

## Arquivos criados e diff resumido

Nenhum arquivo existente de produção, requisito, contrato, teste ou evidência anterior foi editado. Somente este relatório e os seguintes arquivos novos, sob `.offline_validation/dependencies_20260911/`:

- `validate_dependencies.py`: provisionamento separado, resolução, hashes, instalação offline e registro de resultados. SHA-256 final: `110a19239b522d534f1fb56e2d4c83e5eb67b0aac3dec5e78fff38c5755c2e21`.
- `check_inside.py`: controles de isolamento e testes sintéticos dos pacotes. SHA-256: `f07bfc607c2cde3917b497d00a0b13dad9fa4351a0fb665ea13d0ce8aa8d04f0`.
- `evidence/`: `failure.json`, `location.json`, `pip-version.txt`, `python-version.txt`, `resolution.txt`.
- `evidence_attempt2/`: `artifact_hashes.json`, `installation.json`, `installation.txt`, `isolation.txt`, `location.json`, `pip-check.txt`, `pip-version.txt`, `python-version.txt`, `requirements.resolved.txt`, `resolution.json`, `resolution.txt`, `smoke.json`, `smoke.txt`, `summary.json`, `wheels.json`.

O launcher novo recebeu um modo explícito para a segunda tentativa, com diretório exclusivo, após a falha de rede. Evidências nunca foram sobrescritas. Os dois laboratórios temporários foram preservados; nada foi apagado. Não devem ser transportados ao release de produção. Não houve suíte específica cobrindo todos os caminhos de falha do provisionador.

## Próximo passo e limites

Próximo passo seguro: executar as seis suítes C3 já revisadas com esse conjunto de dependências, reutilizando dados sintéticos e isolamento, para verificar se a presença das bibliotecas altera o resultado. Os 145 testes anteriores continuam válidos para o ambiente anterior, não podem ser reetiquetados como executados neste novo laboratório.

Mesmo que essa etapa passe, ainda serão necessárias evidências próprias de artefato publicável, ambiente efetivo, bloqueio de trading, preservação de dados, rollback e verificações pós-deploy. Não foi ativado ou alterado automatismo nesta etapa.

Nenhum secret, .env, token, chave, Registry ou dado operacional foi acessado. Houve somente consultas à documentação e downloads públicos autorizados; **nenhuma chamada externa durante instalação ou testes**, nenhuma chamada a Render/BingX/Redis/Telegram. Nenhum commit, push, deploy, alteração de trading real ou envio de ordem.

Modelo recomendado para a próxima etapa: **GPT-6 Astra — Alto**. Percentual restante para Live: **indeterminado**; não há base objetiva para atribuir um número.
