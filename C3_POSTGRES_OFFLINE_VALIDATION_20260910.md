# C3 — adaptador PostgreSQL exclusivamente de laboratório

Data: 2026-09-10. Escopo autorizado: implementar e testar o adaptador PostgreSQL
com dados sintéticos, sem contratar infraestrutura ou integrar produção.

## Alterações

- `trade_registry_c3_postgres_consumption_offline_v1.py`: consumidor default-off,
  sem importação do driver, DSN, credenciais, provisionamento ou chamada runtime.
  Conexão fresca, assinatura e relógio são dependências explicitamente injetadas.
  Recusa autocommit/transação previamente aberta; usa objetos SQL qualificados,
  valida estrutura, primary key imediata, tabelas persistentes sem RLS, triggers
  ou regras, papel sem privilégios destrutivos e identidade esperada do banco.
  Usa INSERT parametrizado com conflito sem atualização e RETURNING; somente
  assina após commit confirmado. Não repete, apaga ou compensa consumo confirmado.
  Exige fsync, força synchronous_commit e aplica limites de statement, lock e
  transação. Os deadlines das dependências externas permanecem cooperativos.
- `tests/test_c3_postgres_consumption_offline_v1.py`: cenários sintéticos de
  concorrência, falha/ambiguidade de commit, morte real de processo cliente,
  recuperação do servidor temporário, prazos, assinatura, privilégios, schema,
  composição assinada com ledger local restaurado e controles de backup.
- `tests/helpers/c3_postgres_fixture.py`: inicializa e encerra exclusivamente
  clusters sintéticos sob `/scratch`, usuário não-root, socket Unix privado,
  listener TCP desabilitado, credencial sintética restrita e administrador de teste.
- `tests/helpers/c3_postgres_lab.py`: perfil explícito, pacotes apenas extraídos
  em diretório temporário, exportação seletiva e execução isolada. Não instala
  serviços globais, não altera dependências de produção ou arquivos de ambiente.
- `tests/helpers/c3_linux_lab.py`: reutilização da verificação de isolamento e
  parâmetros opcionais para o novo perfil; perfil anterior preservado.
- Este relatório.

`main.py`, requirements e demais arquivos operacionais não foram alterados
nesta etapa. Alterações preexistentes na worktree foram preservadas.

## Ambiente

Ubuntu/WSL, PostgreSQL 18.6 e psycopg 3.3.2, obtidos dos repositórios oficiais
Ubuntu. Dez pacotes extraídos sem executar scripts de instalação, total de
download aproximadamente 19,7 MB. Ferramentas preservadas em
`/var/tmp/cq-c3-pg-tools-7lj3eong`; hashes dos pacotes em `packages.json`.

Isolamento reutilizado: bubblewrap, usuário UID 999, namespaces privados,
zero rotas externas, ausência de discos Windows e diretórios pessoais,
capabilities zeradas, NoNewPrivs, fontes somente leitura e área ext4 sintética.
O novo `/etc/passwd` contém somente a identidade fictícia necessária ao initdb.
Driver aponta explicitamente para libpq/libc locais; nenhum processo auxiliar
de descoberta de bibliotecas foi liberado. Testes não conectam a serviços reais.

Cada teste de integração cria seu próprio cluster; o launcher tem limite total
de 900 segundos, comandos de preparação/encerramento 25 segundos, conexão no
máximo dois segundos no fixture e orçamento de consumo no máximo cinco segundos.
Os arquivos do laboratório são preservados; servidores temporários são encerrados.

## Evidência de execução

**198 testes aprovados em 249,20 segundos, sem falhas, erros ou ignorados.**
São 39 testes da nova suíte (33 cenários com PostgreSQL temporário e seis
checagens sem I/O) e os 159 testes anteriores de regressão. A primeira rodada
completa anterior teve 192 aprovados em 236,05 segundos; não somar as rodadas.

Laboratório final: `/var/tmp/cq-c3-lab-pg-rd54rn6q`.
JUnit: `scratch/results-postgres.xml` nesse diretório.
JUnit conferido: 198 testes, zero falhas/erros/ignorados, 249,050 segundos
(249,20 segundos no resumo do pytest). Nenhum `postmaster.pid` permaneceu nos
clusters da rodada após o encerramento bem-sucedido dos fixtures.
Manifesto: `manifest.json`, SHA-256
`8bf646829270ad5bbbdc497afb38c04eeb472628d8cb3ffee20262e9b14bf3f3`.
Os 76 arquivos Python exportados foram comparados com os fontes atuais:
nenhuma divergência de hash. A aplicação principal permaneceu somente como
texto para verificações AST, sem importar/iniciar a Central.

O perfil padrão anterior também executou seus 159 testes nesta rodada, sem
ignorar os cenários Linux. Não houve novos avisos de whitespace no diff/check
dos arquivos desta etapa; apenas avisos Git sobre conversão LF/CRLF no Windows.
O diff sem índice contra NUL retorna 1 por haver arquivos novos, não por falha
de teste. A suíte integral do repositório não foi executada.

As primeiras tentativas recusaram corretamente processos auxiliares de descoberta
de bibliotecas; o fixture passou a fornecer caminhos locais explícitos, sem
remover o bloqueio de rede/processos. Essas tentativas não contam como aprovação
dos cenários PostgreSQL. A primeira executou os 159 testes anteriores e o novo
default-off, com erros de preparação nos demais cenários.

## Limites de segurança e de evidência

O controle negativo restaura um dump PostgreSQL anterior ao consumo em outro
banco, mantendo a mesma identidade, e demonstra que a autorização pode voltar
a ser consumida. A aprovação desse teste comprova a LIMITAÇÃO, não proteção
anti-rollback. Alterar a identidade do banco restaurado é recusado pelo pin;
isso tampouco autentica quem controla essa identidade.

A restauração apenas do ledger SQLite local, mantendo intacto o PostgreSQL,
é testada na composição de autorização assinada existente e deve ser recusada.
Os dois bancos continuam no mesmo computador: não constituem domínios reais
independentes de confiança, administração ou backup.

Assinaturas são HMAC com chaves públicas fictícias de teste. Não foi implementado
serviço autenticado, chave privada isolada, rotação/revogação operacional,
recuperação confiável do provedor ou proteção contra administrador comprometido.
O conector e o signer injetados são portas confiáveis, não fronteiras de segurança
contra código hostil no mesmo processo. A instância restaurada não pode ser
promovida automaticamente em produção com base apenas no hash contido no banco.

Não testados: queda física de energia, alta disponibilidade gerenciada, falhas
multirregião, restauração de infraestrutura externa, startup completo da Central,
suíte integral, preflight real e trading. Nenhuma readiness Live é emitida.

## Próximo passo

Auditar e fechar autenticação do emissor e recuperação da autoridade independente,
usando o controle negativo de restauração como critério obrigatório. Provisão de
serviço pago, credenciais, configuração Render e integração runtime continuam
fora desta autorização de laboratório.

Nenhum secret ou `.env` acessado, nenhuma chamada à BingX/Render ou serviço
operacional, nenhuma ordem, commit, push, deploy ou alteração de flags reais.
Houve somente consulta à documentação pública e download preparatório Ubuntu;
os testes foram executados depois, sem rede externa.

Modelo/esforço recomendado: GPT-6 Astra — Alto. Percentual restante para Live:
ainda não mensurável com segurança.

## Referências técnicas consultadas

- [Transações psycopg](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)
- [Durabilidade PostgreSQL](https://www.postgresql.org/docs/current/runtime-config-wal.html)
- [Inicialização de cluster](https://www.postgresql.org/docs/current/app-initdb.html)
