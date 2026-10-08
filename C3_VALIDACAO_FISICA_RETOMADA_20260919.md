# Retomada da validação C3 — proposta de 19/09/2026

## Decisão proposta

Executar uma nova sessão sintética delimitada de **qualificação do alvo AL2023,
build nativo e processos/locks**, reutilizando os cinco pacotes existentes.
Não chamar essa sessão de homologação física completa do C3: o pacote disponível
não contém a preparação do daemon e a coleta PHC/VMClock necessárias para isso.
A recomendação é limitar a primeira sessão ao que tem executor preparado e
entregar evidência exportada antes do desligamento. A etapa temporal completa
fica explicitamente separada; nenhuma aprovação desta proposta libera Live.

Esta é uma proposta, sem lançamento, instalação, teste ou nova despesa executada.
A autorização anterior era para a instância removida e uma janela já encerrada.

## Base preservada e mudança desde o plano anterior

O plano de 13/09, a receita CLOCK_DEPENDENCIES.md e os documentos LAB_TRANSPORT.md
e PROCESS_PROBES_TRANSPORT.md foram reaproveitados. Não foram refeitos estudos
temporais, testes concluídos, inventários de pacotes ou cotações.

Em 19/09, as listas EC2/EBS de Oregon estavam vazias. Os cinco objetos S3,
seu bucket e a política temporária foram excluídos com confirmação AWS. Os
cinco originais locais permanecem preservados e tiveram os hashes conferidos.
Não há evidência apresentada de instalação, build ou ensaio na antiga EC2;
as saídas de download e SHA-256 não substituem essa evidência.

Fontes congeladas, ferramentas, Python 3.11.9, aquisição ClockBound 2.0.3 e
probes são reutilizados sem reconstruir arquivos. Os caminhos e hashes estão
na atualização de 19/09 do registro de continuidade. Evidências WSL continuam
válidas no escopo original; não são resultados AL2023.

## Sessão A: sequência e critérios de aceite

| Passo | Trabalho ainda sem evidência no alvo | Aceite obrigatório / recusa |
| --- | --- | --- |
| A1. Encerramento e identidade | Nova instância e seus dois volumes, conta/região, horários e agendas externas | IDs reais, DeleteOnTermination nos dois discos e agendas vinculadas ao ARN exato antes de ensaios. Falha: encerrar sem testar. |
| A2. Sistema e runtime | Resolver transação RPM sem aceite; conferir versões/assinaturas/dependências; qualificar loader, libcrypt.so.1 e Python 3.11.9 | Revisar a transação antes de instalar somente pacotes faltantes previstos. Não mudar release, libc, kernel ou Python de sistema por conveniência. Loader/import/pin incompatível: abortar. |
| A3. Isolamento e scratch | Identificar o EBS sintético de 10 GiB e preparar ext4; validar conta sem privilégios e sandbox | Identidade por volume/serial, nunca por ordem NVMe; raiz de 20 GiB intocada. Testes sem rede, IMDS, credenciais, diretórios operacionais ou capabilities. Guard falhou: nenhum import de teste. |
| A4. Regressão no alvo | Executar o launcher portátil sobre o candidato congelado | 101 testes sem skips, orçamento existente de 600 s, resultados e hashes registrados. Esta repetição só se justifica pela mudança WSL → AL2023; não repetir localmente. |
| A5. FFI/coletor nativos | inspect/build com fonte e vendor pinados | Inspect até 60 s e build até 330 s, Cargo frozen/offline, sem binários/rlibs WSL. Registrar versões, linkagem e hashes; incompatibilidade ou timeout reprova, sem ampliar orçamento. |
| A6. Processos sintéticos | Probes preparados de contenção e encerramento da árvore | Exclusão mútua efetiva entre processos, recusa da segunda posse e ausência de filhos após timeout, conforme oráculos existentes. Limites 600 s e 10 s preservados. Não chamar isso de restart do host ou cobertura dos 19 writers. |
| A7. Entrega | Exportar resultados sanitizados e conferir cópias locais | Evidências fora da VM antes de T0+7h30; resultado parcial também é exportado. Falhas e passos não executados permanecem explícitos. |

Instalação administrativa é distinta dos testes sem rede. Fonte/runner/runtime
entram somente por transporte temporário autenticado delimitado. O processo de
teste nunca herda acesso AWS. Nenhum comando executável de provisionamento foi
incluído nesta proposta para evitar usar IDs antigos por engano.

## Sessão B: lacunas da medição temporal física, fora da Sessão A

O código e os documentos existentes confirmam estes limites:

- test_clock_real.py ainda fixa PREVIOUS e os hashes de artefatos WSL nos
  modos valid/markers. Esses modos não devem ser chamados na AWS. Torná-los
  portáveis não é pré-condição da Sessão A nem prova de PHC; não abrir essa
  alteração só para repetir os cenários sintéticos já concluídos.
- CLOCK_DEPENDENCIES.md explicitamente não prepara nem inicia o daemon.
  O daemon pode solicitar ressincronização ao chronyd e, portanto, não é
  observador somente leitura. Uma receita administrativa revisada e autorização
  específica para o alvo sintético são necessárias antes de seu uso.
- clock_sample.c mantém source_qualified, disruption_support_verified e
  admission_allowed falsos. Compilar e ler uma amostra não remove essas limitações.
- Precisam ser identificados no alvo PHC, ENA, VMClock, interface/referência,
  versões e dependências; não inventar dispositivo ou drift a partir de exemplos.
- Aceite temporal requer intervalo completo de erro, vínculo monotônico,
  origem comprovada das amostras e recusa por ausência/estado inválido,
  descontinuidade ou deadline. Não adotar 100 ms de fixture como limite Live.

A Sessão A pode registrar disponibilidade dos dispositivos somente leitura,
mas não instalar daemon, ajustar relógio, provocar migração/restart do host ou
declarar qualificação temporal. Se A reprovar compatibilidade/isolamento, B não
começa. O plano de B deve usar a evidência de A, não presumir seu sucesso.

## Recursos e custo sujeitos a nova decisão

Proposta de uma única instância m7i-flex.large x86_64 em us-west-2, raiz gp3
20 GiB e scratch gp3 10 GiB, até 8 horas de compute e 24 horas de retenção.
Reutilizar rede, grupo e perfil dedicados somente após conferir os vínculos
exatos antes de lançar. Não presumir que recursos históricos ainda existem.
Não modificar as agendas antigas para outra instância.

Verba proposta: **US$ 5 para esta nova sessão**, incluindo transporte e
encerramento, não mensalidade. É um limite de planejamento, não trava técnica
da cobrança. As tarifas do plano de 13/09 são históricas e não foram recotadas
nesta proposta; confirmar preço/configuração antes de qualquer lançamento.
Se o escopo não couber nessa verba, parar e apresentar a diferença; não ampliar.
Nenhum uso de créditos, desconto, gratuidade ou saldo remanescente é presumido.

Escopo de aprovação necessário: uma nova sessão A; transporte temporário dos
cinco pacotes; concessão GetObject restrita e expirada por prazo; associação do
perfil dedicado; SSM; preparação somente do volume sintético; instalação dos
pacotes mínimos da receita após revisar a transação; testes delimitados; duas
agendas novas com permissão só no ID futuro; exportação e limpeza. Não inclui
daemon ClockBound, KMS, chaves, serviços permanentes ou produção.

Supervisor proposto: Giulio, confirmando disponibilidade antes do lançamento.
T0 é o lançamento; exportar até +7h30, parar +7h45, encerrar até +24h, sem
reinício ou extensão. O horário absoluto só será fixado quando houver T0.
As agendas têm de ser verificadas antes dos ensaios; sua configuração não prova
o desligamento, que será conferido separadamente. Não depender só do Codex.
Falha de exportação não autoriza estender a retenção. Remover transporte e
concessão ao concluir o uso e, no máximo, no prazo de 24 horas; preservar locais.

## Entrega e fronteira para Live

Entregar um relatório único A1–A7 com resultado por passo, versões, IDs,
hashes, tempos, falhas, não executados, evidência de isolamento, exportação e
encerramento. Não instalar a Central nem importar main/bots/Registry operacional.

Mesmo que A e B sejam aprovadas, permanecem fora dessa sessão a autoridade de
produção autenticada, revogação/anti-rollback, recuperação durável, coordenação
dos 19 writers, integração/release e novo preflight operacional. O preflight
antigo não comprova o estado atual. Percentual total restante para Live:
**indeterminado**. Esta proposta documental está concluída; falta 0% dela.

Verificação desta entrega: leitura das referências locais e inspeção dos pontos
de código citados, sem imports, execução de testes ou chamadas externas. Nenhum
secret, dado real, flag, ordem, commit, push ou deploy foi acessado/alterado.
