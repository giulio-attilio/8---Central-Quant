# C3 — Compatibilidade Python 3.11 e checklist de publicação

Data: 2026-09-11, America/Sao_Paulo.

## Resultado

**INVESTIGAÇÃO LOCAL E CHECKLIST CONCLUÍDOS. COMPATIBILIDADE PYTHON 3.11 NÃO VALIDADA: nenhum interpretador 3.11 utilizável foi encontrado nos locais delimitados examinados. Publicação e Live não liberados.**

Há um atalho Chocolatey para Python 3.11, mas seu executável de destino não existe. O laboratório Linux disponível usa Python 3.14.4; o Python auxiliar de análise usa 3.12.14. Nenhum deles substitui a validação no 3.11.9 declarado pelo projeto.

Não foram instalados, baixados, compilados ou atualizados interpretadores ou pacotes. Não foram repetidos os 145 testes sob 3.14. A lacuna do ambiente foi documentada sem alterar runtime.txt, fontes, pins ou expectativas.

## Escopo e identidade preservada

Worktree: `C:/Users/giuli/OneDrive/Documentos/GitHub/8---Central-Quant/.worktrees/c3_final_release_promote_20260910`.

Árvore offline: `.offline_releases/preflight_ro_full_20260911/src`.

- Base/HEAD local confirmado: `d9e12e9daa8f606c3649370bbbf1551650979eb6`.
- Inventário da árvore: `80461db78d76143b30ec99c67875823e094aa7f057848cd3b731d0691e30b9d8`.
- Recalculados nesta etapa os hashes dos **557 arquivos**: todos coincidem com source_manifest.json.
- Recalculados os hashes dos **oito artefatos** vinculados por final_evidence_manifest.json: todos coincidem.
- O delta permanece aquele comprovado na preparação: seis modificados, quatro adicionados e 547 arquivos idênticos à base. Não houve alteração nesta revisão.
- Evidência preservada: 145 testes aprovados sob Python 3.14.4; JUnit SHA-256 `c0822a00ace28e4a0097e1266d2eac30a552eaa13497a049b7a65a0e69399352`. Isso não é um resultado 3.11.

## 1. Busca delimitada do interpretador

Foram consultados apenas comandos disponíveis, metadados de instalações pertinentes, registros de instalação Python e versões. Não houve busca recursiva no disco nem leitura de diretórios de dados pessoais.

### Windows

| Local/verificação | Evidência |
|---|---|
| `C:/ProgramData/chocolatey/bin/python3.11.exe` | Shim presente. Chamada com `-I -S --version` informou que não encontra `c:/python311/python.exe`. Não forneceu versão utilizável. |
| `C:/Python311` | Diretório residual com `Lib`; nenhum executável no nível superior. |
| `C:/ProgramData/chocolatey/lib/python311/tools` | Somente scripts de instalação/desinstalação/helpers e arquivo `python-3.11.3-amd64.exe.ignore`; não foi encontrado instalador ou interpretador nesse nível. Os scripts não foram lidos ou executados. O nome 3.11.3 não comprova instalação dessa versão nem de 3.11.9. |
| `C:/Users/giuli/AppData/Local/Programs/Python`, `C:/Program Files/Python311`, `C:/Program Files/Python 3.11` | Ausentes. |
| `C:/Users/giuli/AppData/Local/Python` | Diretórios `_cache`, `bin` e `pythoncore-3.14-64`. Não há diretório 3.11 no nível examinado; não foi vasculhado o cache. |
| `C:/Users/giuli/AppData/Local/Python/pythoncore-3.11-64` e `pythoncore-3.11.9-64` | Ausentes. |
| `C:/Users/giuli/.pyenv/pyenv-win/versions`, `.local/share/uv/python` e `AppData/Roaming/uv/python` | Ausentes. |
| PythonCore em HKCU, HKLM e HKLM/WOW6432Node | Chaves de registro ausentes nos três caminhos consultados. Nenhuma outra chave foi lida. |
| Python auxiliar do Codex | `C:/Users/giuli/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`: **3.12.14**, por `-I -S --version`. |

Os comandos python/python3/py encontrados em WindowsApps não foram usados para iniciar instalação, abrir loja ou baixar runtime. A presença de aliases não foi tratada como prova de Python 3.11 instalado.

### Linux/WSL Ubuntu

- `/usr/bin/python3`: **3.14.4**, executado com `-I -S`, sem imports de projeto.
- Ausentes: `/usr/bin/python3.11`, `/usr/local/bin/python3.11`, `/usr/local/bin/python3`, `/opt/python/cp311-cp311/bin/python3.11` e `/opt/conda/bin/python3.11`.
- Nenhuma entrada `python3.11*` no nível superior de `/usr/bin` ou `/usr/local/bin`.
- Ausentes no usuário padrão examinado: `/root/.pyenv/versions` e `/root/.local/share/uv/python`; também `/opt/python` e `/opt/conda/bin`.

A primeira tentativa de consulta Linux com laço de shell perdeu os argumentos de caminho no transporte entre shells; não foi usada como evidência de ausência. A consulta foi refeita com caminhos literais via biblioteca padrão e forneceu os resultados acima.

Conclusão delimitada: não foi encontrado Python 3.11 funcional nos caminhos relevantes consultados. Isso não é uma alegação de varredura exaustiva de toda a máquina. Não há motivo para repetir essa mesma busca em cada despertar sem instalação ou caminho novo informado.

## 2. Testes e ambiente necessário

Sem interpretador 3.11 utilizável, não foi possível verificar pytest sob esse interpretador nem executar a suíte-alvo. Pacotes que existam para 3.12/3.14 não devem ser assumidos compatíveis ou copiados indiscriminadamente para 3.11. Não foi reduzido o isolamento para tentar contornar a falta do ambiente.

**Nenhum teste de projeto novo foi executado nesta etapa.** As verificações foram de versão, presença de caminhos, metadados e integridade dos artefatos existentes. Não foram importados main.py, runtime, broker ou bots. Não foi criado runner alternativo nem alterado o launcher existente.

A providência mínima seguinte é disponibilizar um ambiente Linux de teste isolado com **Python 3.11.9** e dependências de teste compatíveis, preservando rede bloqueada na execução, usuário sem privilégios, fontes somente leitura e dados sintéticos. Pode ser um ambiente já existente com caminho fornecido ou um provisionamento local dedicado, este último mediante autorização específica para obtenção/instalação dos componentes. Não é necessário alterar o Render para resolver esta lacuna local.

Se apenas outro 3.11.x for disponibilizado, registrar o patch real e manter explícita a diferença para 3.11.9; não apresentar automaticamente esse resultado como teste da versão exata declarada. Não mudar runtime.txt para 3.14 apenas porque essa versão está disponível no laboratório.

## 3. Checklist único de publicação

Os itens abaixo distinguem o que está comprovado do que permanece pendente. Nenhuma ação operacional foi executada.

| Item | Estado | Condição para encerramento |
|---|---|---|
| Identidade do pacote offline | Comprovado | Inventário dos 557 arquivos e oito artefatos conferido; qualquer drift exige nova análise. |
| Delta delimitado | Comprovado offline | Somente seis modificados/quatro novos; manter a correção read-only e as reatestações correspondentes, sem transportar a manutenção anterior da worktree. |
| Testes funcionais e de integridade | Comprovado em 3.14.4 | 145 aprovados nessa versão; preservar evidência sem reetiquetá-la como 3.11. |
| Compatibilidade do interpretador-alvo | **Pendente — ambiente indisponível** | Disponibilizar 3.11.9 isolado e testar os mesmos seis módulos, com resultados e hashes novos. |
| Dependências da aplicação | Pendente | requirements.txt contém sete pacotes sem pins; instalação/build real não validado. Não inventar versões resolvidas ou alterar dependências neste delta. |
| Artefato publicável e commit | Pendente | Identidade própria do pacote/commit autorizado, diff exato e preservação do conteúdo da base que não pertence ao delta. Nenhum commit foi criado. |
| Configuração efetiva do serviço | Pendente, não consultada | Confirmar versão de Python, comandos de build/start e configuração não secreta do serviço mediante escopo operacional próprio. Não inferir configuração atual de screenshots antigos. |
| Dados e watchlists no destino | Pendente de garantia operacional | A árvore offline exclui dados/watchlists; nunca usá-la para substituir integralmente produção nem remover os arquivos excluídos. Transportar apenas o delta aprovado. |
| Bloqueio de trading e proteção operacional | Pendente de evidência atual | Confirmar trading real impedido e preservação dos interlocks/proteções existentes antes de publicação. Nenhuma flag foi lida ou alterada nesta tarefa. |
| Rollback e verificações pós-deploy | Plano proposto, não ensaiado | Identificar release anterior recuperável, critérios de aborto e escopo somente leitura autorizado; não assumir rollback seguro sem evidência atual. |
| Autorização de publicação | Ausente nesta etapa | Commit, push, deploy, consulta operacional e preflight real requerem autorização aplicável; o checklist não a concede. |
| Liberação Live | **Não comprovada** | Requer evidência operacional própria; testes sintéticos não comprovam Registry, concorrência, recuperação, ownership ou disaster stops em produção. |

## 4. Critérios propostos de aborto e rollback

Proposta para uma futura janela autorizada, não procedimento executado agora:

1. Abortar antes da publicação se houver divergência de base, fontes, pins ou inventário; delta inesperado; falta de validação do interpretador; ausência de caminho de rollback; ou impossibilidade de comprovar bloqueio de trading real.
2. Não publicar se o empacotamento puder apagar/substituir dados, Registry ou watchlists, ou se exigir alteração de credenciais, flags ou dependências fora do escopo aprovado.
3. Após um eventual deploy autorizado, não prosseguir para Live se houver falha de startup/health, erro de assinatura do provider, bootstrap inesperado, instalação/mutação inesperada provocada pelo coletor, evidência incompleta, timeout ou falha em qualquer gate obrigatório. Um resultado genérico `ok` não substitui o contrato completo de readiness.
4. Em regressão, interromper a sequência operacional e manter trading bloqueado. Reverter código apenas para um release anterior previamente identificado e validado, com autorização apropriada; não reverter dados como efeito colateral.
5. Não restaurar snapshot de disco/Registry, desfazer reconciliação, cancelar ordens/stops ou executar reparo CLOSED automaticamente. Qualquer divergência de dados ou proteção exige contenção e tratamento específico, preservando capital e histórico.

Não foram inventados SHA de release implantado, prazo numérico de health, comando de deploy ou valores atuais de flags. Esses parâmetros devem vir da configuração e evidência verificadas na janela operacional autorizada.

## 5. Verificações pós-deploy propostas, ainda não autorizadas/executadas

- Confirmar identidade do release e ambiente efetivamente ativo por evidência não secreta, comparando-os com o artefato aprovado.
- Consultar health/preflight existentes com deadlines definidos e falha fechada, sem bootstrap, reparo, ordens ou alteração de flags.
- Exigir o mesmo contrato de readiness do interlock e o vetor C3 completo; não aceitar apenas marcador textual ou `coordination_ready` isolado.
- Distinguir consulta read-only do coletor de uma eventual gravação do relatório de auditoria pelo preflight completo. Se a rota gravar esse relatório, a autorização deve permitir explicitamente essa única escrita; não descrevê-la como zero-I/O.
- Registrar falhas e abortar progressão, sem usar retentativas para modificar estado ou promover readiness. Nada disso constitui rearmamento Live.

## 6. Encerramento

Único arquivo criado/modificado no projeto nesta etapa: **este relatório novo**. Diff resumido: documentação de disponibilidade do interpretador, checklist, condições de aborto e rollback propostos. Nenhum arquivo de código, teste, pin, configuração ou evidência anterior foi alterado; nada foi apagado.

Nenhum secret, .env, token, chave, Registry, watchlist ou dado operacional foi acessado. Nenhuma chamada a Render, Redis, BingX, Telegram ou API operacional; nenhum commit, push, pull, merge, fetch, deploy, alteração de index, branch ou Git worktree; nenhuma alteração de trading real ou envio de ordem. Houve apenas consulta à documentação oficial OpenAI e gestão do automatismo, separadas da Central.

O objetivo desta etapa está concluído com uma lacuna concreta documentada. O automatismo deve ser pausado, sem repetir buscas ou testes em outra versão. Próximo passo: disponibilizar o ambiente 3.11.9 isolado e suas dependências, sem modificar produção, antes de retomar a validação de compatibilidade.

Modelo recomendado: **GPT-6 Astra — Alto**. Percentual restante para Live: **indeterminado**; não há base confiável para quantificá-lo.
