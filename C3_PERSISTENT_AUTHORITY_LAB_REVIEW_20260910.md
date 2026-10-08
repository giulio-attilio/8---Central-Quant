# C3 — autoridade persistente de referência em laboratório

Data: 2026-09-10. Escopo: testes sintéticos offline; nenhuma instalação operacional.

## Resultado

Implementada referência persistente de consumo independente, exclusivamente nos
auxiliares de teste. O histórico de consumo agora pode sobreviver à morte do
processo, sem depender do conjunto em memória usado na etapa anterior.

A referência reutiliza `SQLiteMaintenanceAuthorizationLedgerV1` para o consumo
atômico, em arquivo temporário separado do ledger local. O comprovante só é
assinado depois de confirmar esse consumo. O autorizador real do módulo offline
verifica a assinatura e os bindings antes de registrar o consumo local.

**Não é um serviço pronto para produção.** Os dois arquivos estão no mesmo
laboratório. O teste que restaura somente o ledger local comprova a preservação
do consumo independente; o controle negativo que restaura ambos comprova que
esta referência não protege contra rollback conjunto.

## Arquivos desta etapa e diff resumido

- `tests/helpers/c3_independent_authority_child.py`: consumidor persistente
  sintético, default-off; chaves públicas de teste, namespace fixo de laboratório,
  assinatura após commit e construção da cadeia completa de autorização.
  Não provisiona banco ao autorizar, não carrega credenciais, não inicia serviço
  nem importa `main.py`. Recusa banco ausente, schema inválido, prazo vencido
  ou banco da autoridade apontando ao mesmo arquivo físico do ledger local.
- `tests/test_c3_maintenance_ledger_process_probe.py`: o fixture existente agora
  admite também o auxiliar fixo da autoridade, por parâmetro explícito. Mantém
  argumentos e ambiente restritos, rede bloqueada e cleanup somente dos processos
  criados pelo próprio teste. Os testes anteriores do ledger não foram removidos.
- `tests/test_c3_persistent_independent_authority_process_v1.py`: processos novos,
  concorrência, quatro pontos de crash real, restauração local, falha ao assinar,
  pedido inválido, default-off, banco ausente, schema inválido, alias por hardlink,
  deadline e controle negativo de restauração conjunta.
- `C3_INDEPENDENT_CONSUMPTION_OFFLINE_REVIEW_20260910.md`: nota do ensaio posterior,
  preservando o resultado histórico da etapa em memória.
- Este relatório.

Nenhum arquivo de runtime ou módulo operacional foi alterado nesta etapa.
Alterações anteriores já presentes no worktree foram preservadas.

## Evidências e limites de interpretação

| Cenário | Resultado exigido e observado |
| --- | --- |
| Dois processos simultâneos com o mesmo pedido | Exatamente uma autorização |
| Repetição em um processo novo | Recusada |
| Morte antes do commit independente | Nenhum consumo confirmado; tentativa posterior pode autorizar |
| Morte após commit independente, antes de devolver comprovante | Consumo retido; tentativa posterior recusada |
| Morte antes do commit local | Consumo independente retido; tentativa posterior recusada |
| Morte após commit local | Ambos os consumos retidos; tentativa posterior recusada |
| Restauração apenas do banco local | Tentativa repetida recusada pelo consumo independente |
| Falha ao emitir assinatura após commit | Sem autorização; consumo independente permanece |
| Pedido com assinatura inválida | Nenhum dos bancos é consumido |
| Banco independente ausente ou incompatível | Recusa sem recriar banco ou escrever no ledger local |
| Os dois caminhos apontam ao mesmo arquivo | Recusa |
| Deadline vencido antes/depois do consumo | Sem comprovante; consumo confirmado não é desfeito |
| **Controle negativo: restauração dos dois bancos** | **A repetição volta a autorizar; fora da garantia da referência** |

O controle negativo passa porque confirma explicitamente a limitação do modelo;
não deve ser interpretado como aprovação de segurança para restauração conjunta.
Não há mecanismo mágico de detecção de rollback externo dentro de dois arquivos
restauráveis na mesma máquina.

Os crashes usam `os._exit` na fronteira do `commit()` SQLite do banco escolhido,
executando o restante do fluxo real de `consume_once`. Não existe rollback de
limpeza após essa saída. Cada tentativa subsequente reconstrói os componentes
em outro processo. Isso não simula queda de energia ou falha física do disco.

A referência tem chaves de teste conhecidas e revogação sintética. Não fornece
autenticação de transporte, administração de chaves, monitoramento de serviço
nem isolamento de privilégios de um backend externo. Seu uso deve permanecer
limitado a testes. Nenhum desafio, assinatura ou dado de produção foi usado.

## Testes

Primeira rodada dirigida: 16 aprovados e 1 ignorado por depender de Linux, em
10,38 s. A rodada final reúne as cinco suítes abaixo, com `--runxfail`; resultado
final: **157 aprovados e 2 ignorados por ausência de Linux, em 51,38 s**.
Nenhuma falha nem `xfail`. Entre os aprovados está o controle negativo que
confirma a limitação de restauração conjunta; aprovação da suíte não é readiness
operacional. Não somar as rodadas como testes distintos.

```text
tests/test_c3_persistent_independent_authority_process_v1.py
tests/test_c3_maintenance_ledger_process_probe.py
tests/test_c3_maintenance_independent_consumption_v1.py
tests/test_trade_registry_c3_maintenance_authority_startup_v1.py
tests/test_trade_registry_c3_maintenance_activation_offline_v1.py
```

Não executados: Linux isolado (indisponível nesta máquina), queda de energia,
backend externo independente, startup completo, suíte integral do repositório,
recovery multistore ou preflight de produção.

## Próximo passo concreto

A referência offline de persistência está implementada. O próximo requisito não
é outro contrato dormente: é disponibilizar um laboratório Linux e definir o
domínio de persistência confiável da autoridade, independente do backup local.

Antes de integração operacional, a implementação selecionada precisa demonstrar:

1. Consumo único autenticado e persistente entre processos e reinícios.
2. Histórico preservado em rotação de chave e recovery; nenhuma recriação vazia
   ou troca de namespace para permitir retry.
3. Backup e recuperação que não revertam o histórico independente junto com o
   ledger local; falha fechada quando essa atualidade não puder ser comprovada.
4. Respostas assinadas com desafio novo, deadline e revogação verificáveis.
5. Testes no armazenamento alvo e auditoria da composição de startup completa.

Disponibilizar esse ambiente ou serviço exige uma decisão de infraestrutura
separada. Não foi instalado WSL, criado recurso externo ou alterado o Render.
Este ensaio não libera Live nem permite reparar o Registry real.

Nenhum secret real ou `.env` acessado; nenhuma chamada externa, ordem, commit,
push ou deploy. Nenhuma flag de trading ou configuração de produção alterada.
Percentual restante para Live: ainda não mensurável com fundamento.
