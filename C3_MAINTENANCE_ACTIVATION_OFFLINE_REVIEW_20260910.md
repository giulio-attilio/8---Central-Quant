# C3 — composição executável de manutenção offline

Data: 2026-09-10. Base local: `d9e12e9`.

Registro da etapa de composição offline. A preparação posterior do binding no
`main.py` e do verificador assinado está documentada em
`C3_STARTUP_AUTHORITY_PREPARATION_REVIEW_20260910.md`; as afirmações abaixo sobre
ausência de alteração no `main.py` referem-se à etapa anterior.

## Resultado e escopo

Composição de referência implementada, desligada por padrão e sem importação
pelo `main.py`. Reutiliza o construtor físico existente, registra o inventário
canônico de 19 writers e executa bootstrap sintético, recuperação sintética e
postflight sintético sob a mesma instância de permissão de manutenção.
Não é uma entrada operacional de ativação em produção.

O modo `maintenance_only` agora bloqueia a admissão diretamente no coordenador,
inclusive depois de liberar a lease. O instalador de ativação controlada recusa
esse coordenador. Desligar um binding de manutenção não restaura o passthrough.
O comportamento dos bindings legados, cujo modo de manutenção é falso, permanece.

Foi corrigida também a liberação da trava quando a geração do identificador ou
a leitura do relógio falha imediatamente após adquirir o lock de manutenção.

## Arquivos

- `trade_registry_c3_maintenance_activation_offline_v1.py`: composição de uma
  tentativa, com verificador de autorização injetado, controles estritos, kill
  switch, prazo e validação dos resultados de cada etapa e da liberação da lease.
- `trade_registry_closed_identity_conflict_repair_writer_runtime_coordinator_v1.py`:
  modo exclusivo de manutenção propagado pelo construtor e correção da liberação
  da trava na falha de geração do identificador.
- `trade_registry_closed_identity_conflict_repair_runtime_seam_v1.py`: rejeição
  explícita da promoção de um coordenador exclusivo de manutenção.
- `tests/test_trade_registry_c3_maintenance_activation_offline_v1.py`: testes
  sintéticos, com rede e criação de subprocessos bloqueadas antes das importações.
- Este relatório.

## Verificação

A rodada ampliada terminou com **149 testes aprovados em 22,75 s**, abrangendo
a composição nova, defaults de produção, seam, superfície CAS e adaptadores de
manutenção existentes. Depois da última proteção do binding desligado, a rodada
final terminou com **121 testes aprovados em 439,94 s**, incluindo o preflight
estático e o contrato de ativação controlada. As rodadas têm testes em comum;
esses números não devem ser somados como testes distintos.

Última execução:

```powershell
python -m pytest -q -p no:cacheprovider --basetemp=.pytest_tmp_maintenance_activation_20260910_v3 tests/test_trade_registry_c3_maintenance_activation_offline_v1.py tests/test_trade_registry_closed_identity_conflict_repair_production_defaults_v1.py tests/test_trade_registry_closed_identity_conflict_repair_runtime_static_preflight_v1.py tests/test_trade_registry_closed_identity_conflict_repair_runtime_controlled_activation_v1.py
```

`git -c core.longpaths=true diff --check` passou. A suíte integral do repositório,
testes em Linux/Render, testes de crash entre processos e testes sobre dados reais
não foram executados nesta etapa.

Os testes usam somente diretórios temporários sintéticos. Os locks do sistema,
a gravação de arquivos de lease, fsync de arquivo e troca de arquivo são reais.
A confirmação de fsync do diretório é uma dependência simulada para executar a
suíte no Windows: esses resultados não atestam durabilidade no Linux do Render.

Casos cobertos: default-off sem chamadas, autorização negada ou ausente, replay,
controles inseguros ou com tipos incorretos, prazo, kill switch, relógio regressivo,
permissão copiada, operações pendentes, exceções sanitizadas, falhas de persistência,
lease residual, concorrência na mesma instância, disputa entre coordenadores sobre
a mesma trava física e bloqueio de todos os 19 identificadores de writer.

## Limites e condições para a próxima integração

1. **Composição no startup:** registrar nomes no coordenador não instala os 19
   writers do serviço nessa instância. É necessário conectar a composição antes
   de iniciar workers e atender requisições, vinculando explicitamente o status
   e a lease à mesma instância. O runtime atual continua dormente.
2. **Autoridade operacional:** `consume_authorization` é uma dependência confiável
   injetada, não uma implementação de autenticação. A implementação de produção
   deve autenticar e consumir duravelmente a autorização, vinculando escopo,
   armazenamento, nonce e prazo. Os hashes de um pedido não concedem autoridade.
   A proteção local de tentativa única não substitui replay protection no reinício.
3. **Persistência e recuperação em Linux:** validar fsync de diretório, disputa
   entre processos, interrupção abrupta e recuperação de lease/transações pendentes.
   Lease residual não é liberada automaticamente por esta composição.
4. **Operações reais:** os callbacks deste escopo são sintéticos. Não houve
   bootstrap real, reparo CLOSED nem nova execução do preflight em produção.

O prazo é cooperativo: é verificado antes e depois de cada etapa, mas não interrompe
um callback bloqueado. Cada futuro coletor/operação deve impor seu próprio timeout.
Falhas após uma etapa impedem as seguintes; não há rollback automático do Registry
real nem declaração de readiness. Se o relógio regride ou a liberação não pode ser
confirmada, a lease pode permanecer `QUIESCED`, exigindo reconciliação explícita.

A conclusão offline não permite `coordination_ready`, `runtime_activation_allowed`,
`production_ready` ou `live_allowed`. Não existe base mensurável para converter
essas pendências em um percentual restante para Live; a estimativa anterior de
0,01% não deve ser usada para uma decisão operacional.

## Segurança da execução realizada

Nenhum secret, token ou arquivo `.env` acessado. Nenhuma chamada externa feita.
Nenhum servidor, bot ou worker operacional iniciado. Nenhuma ordem enviada.
Nenhum dado do Registry real, flag de trading ou configuração do Render alterado.
Nenhum commit, push ou deploy executado. `main.py` não foi alterado.
