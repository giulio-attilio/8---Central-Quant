# C3 — resultado da sessão A, 20/09/2026

## Implementação V2 local concluída após aprovação humana

O "sim" posterior à revisão autorizou somente implementar e testar offline.
Esta seção supera a decisão pendente no histórico abaixo, sem alterar o
resultado da sessão AWS: A5 e A7 continuam reprovados no alvo.

Arquivos de autoria afetados em .offline_releases/aws_synthetic_lab_20260913:

- test_clock_real.py: valida cadeia fixa de links, donos root e permissões;
  constrói somente diretório/link virtuais no sandbox do modo build. Não altera
  links do host nem adiciona mounts. Recibo futuro identifica RECIPE_VERSION V2.
- evidence_frames_v2.py (novo): codificação/montagem puras em memória; limite
  total1MiB, blocos1024bytes, frames2048bytes, JSON canônico, identidade esperada
  externa, índices/offsets/comprimentos/digests estritos e marcador final.
  Nenhuma leitura/gravação de arquivo ou chamada de transporte. Só retorna bytes
  após validação completa; hashes não autenticam o emissor.
- test_session_a_revision_v2.py (novo):21 testes novos e agregação dos17 testes
  existentes do launcher e13 do oráculo. Bloqueios de rede/processos/imports
  operacionais antes dos imports dos sujeitos. Nenhum compilador é executado.

Também atualizados este relatório e C3_OFFLINE_CONTINUITY_20260911.md. Nenhum
arquivo operacional/main/bots ou alteração alheia foi editado. Fontes soltas
representam a nova revisão de autoria, não uma substituição do ZIP congelado.
Nenhum novo pacote foi gerado; os cinco artefatos originais não foram editados.
Teste verificou SHA256 do ZIP tools V1 e igualdade byte-a-byte do launcher
compartilhado com seu membro congelado.

Execução local com Python fornecido pelo ambiente, -I -B:
`test_session_a_revision_v2.py`: **51 testes,0falhas,0erros,exit0**.
Primeira execução detectou um erro no próprio auxiliar mutate (nome index
colidindo com campo mutado); nome corrigido e suíte completa passou na segunda.
Verificações incluem vetor integral de cada modo, cadeia de linker inválida,
alvo ausente/inseguro, tamanho máximo e fronteiras de blocos,7426bytes sintéticos,
truncamentos, blocos duplicados/reordenados/misturados, corrupção, tipos booleanos
em campos inteiros, JSON duplicado e digest global independente do digest local.
Os testes existentes usam somente diretórios temporários sintéticos; o codec
trabalha exclusivamente em memória. Sem import/execução de código operacional.

Não executados: compilação nativa, bwrap real, SSM, exportação remota, daemon ou
preflight. A inspeção do linker ainda precisa ser confirmada no alvo sob uma
futura autorização; não é proteção atômica contra troca por administrador root.
O protocolo detecta saída incompleta, mas não comprova a correção do canal que
truncou a sessão anterior. Não há recuperação dos recibos remotos neste trabalho.

Nesta implementação: nenhum secret acessado, nenhuma chamada externa,
nenhum commit/push/deploy e nenhuma configuração de trading real alterada.
Próximo passo técnico depende de ensaio nativo e transporte em sessão remota
delimitada separadamente autorizada; não reiniciar ou prolongar a VM parada.
Automatismo não precisa de OK genérico para a futura checagem já autorizada de
encerramento, mas não pode iniciar novo laboratório com a autorização local.

## Resultado

Sessão **parcialmente aprovada, sem readiness de produção**. Regressão e probes
de processos passaram. O build nativo falhou fechado: o linker do AL2023 depende
de um link em `/etc/alternatives`, ausente no sandbox previsto. Não houve retry,
troca de compilador, abertura de `/etc`, alteração do runner ou extensão de prazo.

| Critério | Evidência | Resultado |
| --- | --- | --- |
| A1 Identidade/encerramento | Instância i-0bafbafe5535e036b, conta899845009758, us-west-2; agendas verificadas | Configurado; entrega futura ainda não comprovada |
| A2 Sistema/runtime | AL2023 2023.12.20260909, Python3.11.9, libcrypt.so.1, pytest8.3.5 | Passou |
| A3 Isolamento | uid993, CapEff0, NoNewPrivs1, netns separado sem rotas, fontes ro, scratch ext4 | Passou |
| A4 Regressão | 101 passed, 0 failed, 0 skipped; exit0, sem timeout, budget600s | Passou |
| A5 Build nativo | inspect exit0; build exit101, sem timeout, verified=false | Reprovou |
| A6 Processos/timeout | process_probe_verified=true; timeout_tree_verified=true, exit124 esperado,10.002048878s | Passou |
| A7 Exportação | Duas transferências truncadas, sem marcador final; validação recusou ambas | Reprovou; pacote completo não exportado |

## Identidade e proteção de custo

LaunchTime: 2026-09-19T23:46:35Z. Uma m7i-flex.large, AMI
ami-03db3415e6524c5d2. Raiz20GiB vol-0895f06c8cb68e8bd e scratch10GiB
vol-024a047eaac92ff2e, ambos DeleteOnTermination. Somente o scratch, confirmado
vazio e identificado por serial, foi formatado ext4 e montado /srv/cq-c3-lab.

Grupo externo cq-c3-synthetic-lab-20260919-shutdown, role
CentralQuantC3SyntheticLabShutdownRole20260919, acesso somente stop/terminate
no ARN desta instância, com expiração20/09 23:46:35Z. As agendas novas ENABLED,
UTC, janela flexívelOFF, retry1/120s são:

- cq-c3-lab-i0bafbafe5535e036b-stop:20/09 07:30Z.
- cq-c3-lab-i0bafbafe5535e036b-terminate:20/09 23:40Z.

Exportação limite07:16Z; sem reinício/extensão. Preço Linux exibido US$0.09576/h;
verba de planejamento US$5, não teto técnico. Encerramento antecipado após
exportação é preferível a manter compute sem ensaio pendente autorizado.

Após os ensaios e duas falhas de exportação, stop antecipado solicitado e
`describe-instances` confirmou **stopped** para o ID exato. Sessão SSM encerrada.
Os discos permanecem preservados, com custo de armazenamento, até a terminação
agendada em **20/09/2026 23:40 UTC**. A configuração de DeleteOnTermination implica
perda do pacote completo ainda não exportado nesse encerramento. Não foi feita
extensão da retenção, reinício, snapshot ou terminação antecipada dos discos.

## Preparação e integridade

Os cinco pacotes preservados foram enviados ao bucket privado
cq-c3-synthetic-transfer-20260919-899845009758, SSE-S3, bloqueio público completo,
BucketOwnerEnforced, sem versionamento habilitado. Upload5sucessos/0falhas.
Grant C3SyntheticTransferReadUntil20260920: apenas GetObject dos cinco nomes
exatos por HTTPS até20/09 23:40Z. Nenhum PutObject foi concedido à instância.
Após a parada, o grant temporário foi removido; list-role-policies confirmou
somente CentralQuantC3SyntheticLabSessionRole20260913Policy. Role e política
SSM basal preservadas. Bucket e cinco objetos novos ainda não foram excluídos;
a limpeza não está concluída. Os originais locais permanecem preservados.

Recepção /var/tmp/cq-c3-transfer-20260919-ROmwMEFI: cinco tamanhos/SHA256
coincidem com os originais registrados. Manifestos de candidato e ferramentas
ficaram separados;6membros do tools e3do probes verificados, sem sobrescrita.
O manifesto de563fontes mantém o pin
d8aa8bdc2c76a83bdc59e2f297c768c459133b27e4efe7606b5b37828ef2e2a4.
Hash não é, isoladamente, prova de autenticidade do emissor.

Transação DNF previamente revisada com --assumeno:19instalações,166MBdownload,
597MBinstalados, sem upgrades/removals. Release pinada, gpgcheck e
localpkg_gpgcheck ativos. gcc11.5.0, rust/cargo1.97.0, bubblewrap0.10.0;
glibc2.34-231.amzn2023.0.5 preservada. Não foi iniciado daemon ClockBound.

## Diagnóstico da falha nativa

O log JSON do Cargo contém `collect2: fatal error: cannot find 'ld'` durante
o build script de proc-macro2 v1.0.78. Inspeção somente leitura no alvo confirmou:

```
/usr/bin/ld -> /etc/alternatives/ld -> /usr/bin/ld.bfd
```

O launcher monta `/usr` somente leitura, mas cria `/etc` vazio. Assim, o link
intermediário não resolve dentro do sandbox. A inspeção da árvore de dependências
não precisou linkar e passou; o build reprovou. Esta é uma incompatibilidade
concreta da receita de build com o alvo, não evidência de falha do algoritmo C3.
Não há biblioteca/coletor nativos qualificados, nem casos negativos pós-build
executados nesta sessão. Os modos valid/markers WSL não foram chamados.

Próximo trabalho técnico: revisar offline o encaminhamento explícito do linker
já instalado, preservando o isolamento e pins; testar essa alteração com dados
sintéticos antes de propor novo ensaio nativo. Não montar `/etc` inteiro, mudar
links do sistema ou baixar outro toolchain como contorno automático.

## Evidências geradas

Diretórios em /srv/cq-c3-lab/work:

- cq-c3-lab-portable-u7vrx8v1/evidence: regressão, JUnit e receipt.
- cq-c3-lab-portable-_369bvuh/evidence: inspect, árvore e versões.
- cq-c3-lab-portable-1d80_qav/evidence: build recusado e diagnóstico JSON.
- cq-c3-lab-portable-wbd9o92u/evidence: processo, sete checks e receipt.
- cq-c3-lab-portable-7k6vf6xj/evidence: árvore de timeout e receipt.

Pacote /srv/cq-c3-lab/session-a-evidence-20260920.tar.gz,7426bytes,
SHA256138794109ce1d9a62509bc6454a8c62ea59bdc64bad08e97d2662a82f6ce53f0.
Contém somente os cinco diretórios evidence; não inclui dados operacionais,
credenciais, fontes completas ou ambientes.

Exportação via SSM AWS-StartInteractiveCommand para CloudShell recusada duas
vezes: tentativa1 com5185bytes; tentativa2 com5119caracteres,69linhas. Ambas
tinham um marcador inicial e nenhum final; decoder abortou antes de gravar um
arquivo tar local validado. Não houve terceira tentativa. A causa de truncamento
do transporte não foi determinada; não confundir com a causa conhecida do build.

Somente a saída parcial da tentativa1 foi baixada e copiada, sem remover o
original de Downloads, para
`.offline_releases/aws_synthetic_lab_20260913/session_a_evidence_20260920/partial-export-attempt1.txt`.
SHA25688b9ef84a698037abcd31ae6e8ad4bf3452bb522e406dd05f56bdf0b7e734bb1.
Esse arquivo é evidência da transferência incompleta, não substitui os recibos
integrais. Os resultados acima foram observados no terminal; não declarar um
pacote completo local ou cadeia de evidência exportada qualificada.

## Fronteira preservada

Sem acesso a secrets, .env, Registry real, Render, Redis, BingX ou Telegram.
Chamadas externas foram administrativas à AWS e instalação oficial no laboratório;
os ensaios executaram sem rede, com guards antes dos imports de teste.
Sem main/bots/broker/Registry operacional importados, sem flags reais alteradas,
commit, push, deploy ou ordens. Fontes/runner congelados não foram alterados.

Sessão A não comprova PHC/VMClock, reinício de host, coordenação dos19writers,
autoridade autenticada de produção, recuperação durável ou readiness Live.
Percentual total restante para Live: indeterminado, sem base para estimativa.

## Revisão local concluída — 20/09/2026 00:25 UTC

Somente leitura de código, sem imports, execução de testes, rede ou AWS.
Registro desta revisão é a única alteração, junto à continuidade. Receita e
pacotes congelados permanecem intactos. Nenhum secret, flag, commit ou deploy.

O ajuste candidato mínimo fica no `command_for` nativo de
`.offline_releases/aws_synthetic_lab_20260913/test_clock_real.py:363`, não no
launcher compartilhado `run_regression.py:42`. Proposta: criar apenas o diretório
virtual `/etc/alternatives` e um link virtual `ld -> /usr/bin/ld.bfd` no namespace
do build. Não montar o `/etc` do host, copiar configurações ou alterar seus links.
Validar antes que o alvo instalado é arquivo regular executável dentro do `/usr`
já somente leitura; rejeitar alvo ausente, link inesperado ou escape. Limitar o
ajuste ao modo build, sem alterar regressão, processos, sample, valid ou markers.
É uma proposta ainda não implementada/validada; não garante compilação completa.

Isso mantém GCC como driver tanto no RUSTFLAGS existente (linha20) quanto no
COMPILE do coletor C (linha27). Substituir diretamente o driver GCC por ld.bfd
não é o ajuste proposto. Preservar source manifest, versões, aquisição, helper
e sampler pinados; uma eventual revisão da ferramenta deverá receber novo
artefato/recibo, nunca sobrescrever os cinco pacotes da sessão A.

Verificação sintética necessária antes de novo laboratório: comparar vetores
completos de comando; permitir só os dois argumentos de construção virtual
esperados no build; rejeitar destinos/links arbitrários; preservar todos os
mounts, unshare, env, UID, capacidades e budgets; verificar que outros modos
não mudaram. Testar validação de arquivo com fakes e guards antes de imports,
sem chamar bwrap, GCC, Cargo ou aplicação. Esses testes NÃO foram executados.
Uma compilação nativa futura continua exigindo sessão remota separadamente
autorizada e confirmação de resultado, não aprovação automática por teste fake.

Transporte: o launcher atual grava logs/recibos locais; não oferece protocolo
de exportação. As duas saídas truncadas não identificam a causa (processo,
plugin, terminal ou canal). Espera adicional não comprovou correção. Proposta
para futura revisão: leitura de evidência em blocos limitados, índice/offset,
comprimento e digest por bloco, digest/tamanho totais e marcador final; montagem
local exclusiva após validação integral. Rejeitar bloco faltante/duplicado,
troca de ordem, mistura de arquivos/sessões, tamanho excessivo, base64 inválido,
digest incorreto e saída sem encerramento. Validar primeiro com bytes sintéticos
em memória, incluindo um arquivo de7426bytes e cortes em qualquer bloco. Isso
não autoriza nova tentativa na VM parada nem comprova canal remoto corrigido.

Decisão necessária: implementar e testar SOMENTE essas correções locais numa
revisão nova das ferramentas, sem modificar os pacotes congelados, acessar AWS,
reiniciar VM ou executar compilação real. Não refazer esta revisão em heartbeats.
