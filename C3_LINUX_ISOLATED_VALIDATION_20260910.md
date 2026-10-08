# C3 — validação sintética no Linux isolado

Data: 2026-09-10. Escopo: preparação de laboratório local e execução offline das
cinco suítes C3 previamente autorizadas. Nenhuma ativação operacional.

## Resultado

**159 testes aprovados em Linux; zero falhas, ignorados ou xfails.**
Rodada final: 22,52 s. A primeira rodada funcional teve os mesmos 159 aprovados
em 20,48 s; não somar as rodadas como testes distintos.

Os dois testes antes ignorados no Windows foram executados: fsync de diretório
Linux e composição assinada com armazenamento de lease real, mesma barreira de
startup e recusa dos 19 writers durante manutenção. Isso elimina a pendência de
Linux para estas suítes, não para todo o sistema.

O controle negativo de restauração conjunta permanece na suíte: ele confirma
que restaurar os dois bancos sintéticos pode permitir reutilização. Seu sucesso
como teste de caracterização não atesta segurança operacional desse cenário.

## Ambiente e isolamento verificados antes de importar a aplicação de teste

- Ubuntu no WSL 2; Python 3.14.4, pytest 9.0.2.
- Usuário de sistema `cq-c3-lab`, UID 999, sem diretório pessoal e com login
  desabilitado; nenhum teste foi executado como root.
- Bubblewrap: namespaces separados, incluindo rede, processos e usuário;
  criação de namespaces adicionais desabilitada e todas as capabilities removidas.
- Namespace de rede diferente do host, zero rotas; nenhuma rede compartilhada.
- `/mnt`, `/home`, `/root`, `/run` e `/etc/shadow` ausentes; variável de
  interoperabilidade WSL ausente. Discos e credenciais Windows não foram expostos.
- Fontes montadas somente para leitura em `/work`.
- Diretório sintético gravável em `/scratch`, em filesystem Linux **ext4**;
  `/tmp` privado. Não se usou NTFS/DrvFS para a evidência de fsync.
- Ambiente limpo, plugins pytest de terceiros sem carregamento automático,
  `NoNewPrivs=1`, capabilities efetivas zeradas.
- Limite total de 300 segundos no launcher; morte do launcher encerra o filho
  isolado. Nenhum timeout ocorreu nas rodadas aprovadas.

A primeira tentativa de iniciar o bubblewrap recusou a combinação sem
`--unshare-user` explícito. Esse argumento foi acrescentado, sem remover
nenhuma proteção. Nenhum teste executou nessa tentativa recusada.

## Fontes e evidências preservadas

Foram exportados **72 arquivos Python**: as cinco suítes, seus auxiliares e a
dependência transitiva de fontes identificada estaticamente por AST. `main.py`
foi incluído apenas como texto para os testes de AST; suas dependências não
foram percorridas nem o aplicativo completo importado.

Não foram copiados `.env`, bancos operacionais, secrets, logs, diretório `.git`
ou uma cópia ampla do repositório. As fontes foram verificadas por SHA-256
antes do lançamento. O usuário de teste não pode alterá-las.

Laboratório final no Ubuntu:
`/var/tmp/cq-c3-lab-q2yXQtep`.

Manifesto:
`/var/tmp/cq-c3-lab-q2yXQtep/manifest.json`.
SHA-256: `3f761135f94b1889d43d06dda5340bcb40a956675495038034f918fd8850b0f6`.

Resultado JUnit:
`/var/tmp/cq-c3-lab-q2yXQtep/scratch/results-7446f4c040a34c97891a9286a5538eb7.xml`.

O primeiro laboratório, `/var/tmp/cq-c3-lab-qhdKxHTC`, também foi preservado.
Todos esses bancos e resultados são sintéticos, sem dados reais.

## Arquivos e alterações desta etapa

- `tests/helpers/c3_linux_lab.py`: exportador explícito de fontes, manifesto,
  launcher isolado e verificações obrigatórias antes dos testes. Não contém
  instalação automática de dependências, comando de produção ou integração runtime.
- `C3_WSL_LAB_INSTALLATION_20260910.md`: nota para a validação posterior.
- Este relatório.

No Ubuntu, instalados `python3-pytest`, `python3-iniconfig` e `python3-pluggy`;
`bubblewrap` atualizado pelo repositório oficial. A preparação acessou os
repositórios Ubuntu. Os testes foram executados somente depois, sem rede.
Nenhuma configuração global de rede ou montagem do WSL foi alterada; o isolamento
é restrito aos processos do laboratório.

Comando aplicado às cinco suítes: pytest com `-q -rs --runxfail`, plugin de cache
desabilitado, base temporária e arquivo JUnit únicos por rodada. Suítes:

- `tests/test_c3_persistent_independent_authority_process_v1.py`.
- `tests/test_c3_maintenance_ledger_process_probe.py`.
- `tests/test_c3_maintenance_independent_consumption_v1.py`.
- `tests/test_trade_registry_c3_maintenance_authority_startup_v1.py`.
- `tests/test_trade_registry_c3_maintenance_activation_offline_v1.py`.

`git diff --check` passou nas alterações rastreadas, com avisos de conversão de
final de linha Windows. Os arquivos operacionais já modificados por etapas
anteriores foram preservados, sem novas alterações nesta execução.

## Pendências e próximo passo

Permanecem fora da validação: provedor de autoridade realmente independente,
backup/recovery autenticado desse provedor, perda de energia física, startup
completo/múltiplos workers, recuperação multistore, suíte integral, preflight e
operação de produção. Os bancos separados em um mesmo computador continuam
sendo uma simulação, não domínios independentes de confiança.

Próximo passo: auditoria consolidada dos requisitos da autoridade independente
e da composição de startup, usando esta evidência Linux para fechar somente os
itens efetivamente comprovados. Não habilitar Live nem alterar o Render com base
apenas na aprovação das suítes.

Nenhum secret real ou `.env` acessado; nenhuma chamada à BingX, Render ou outro
serviço operacional; nenhuma ordem, commit, push ou deploy. Nenhuma flag de
trading real foi alterada. Percentual restante para Live ainda não mensurável.
