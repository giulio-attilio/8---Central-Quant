# C3 — ensaio de interrupção e preparação de provisionamento

Data: 2026-09-10. Escopo: testes locais sintéticos e plano; nenhuma instalação operacional.

Atualização posterior: `C3_INDEPENDENT_CONSUMPTION_OFFLINE_REVIEW_20260910.md`
registra a correção do protocolo com consumo independente simulado. O diagnóstico
e os resultados abaixo são históricos; a autoridade persistente real continua pendente.

## Decisão

**Integração em produção ainda bloqueada.** O histórico de consumo resiste à
reconstrução de objetos e à interrupção de processos, mas não à restauração de
um backup antigo no mesmo caminho. O pin atual identifica o caminho, não a
atualidade do conteúdo. Uma assinatura válida não resolve esse rollback.

WSL está disponível como comando do Windows, mas informou que o subsistema não
está instalado. Docker e Podman não foram encontrados. Não houve instalação,
download de imagem nem tentativa de usar o Render como laboratório.

## Alterações desta etapa

- `tests/helpers/c3_maintenance_ledger_child.py`: processo auxiliar de teste,
  restrito a banco com nome fixo e marcador sintético. Bloqueia rede e processos
  adicionais antes de importar os componentes C3. Não recebe chave ou token.
- `tests/test_c3_maintenance_ledger_process_probe.py`: provisiona apenas SQLite
  temporário; permite somente o auxiliar fixo com argumentos controlados e
  ambiente mínimo, sem herdar credenciais. Dois processos competem pelo mesmo
  consumo. Há interrupção abrupta imediatamente antes e depois do commit real.
  O cleanup encerra somente processos criados pelo próprio fixture.
- `tests/test_trade_registry_c3_maintenance_authority_startup_v1.py`: reprodução
  da restauração no mesmo caminho com assinatura sintética, continuidade do
  histórico após mudança de época e ensaio Linux da composição assinada com
  fsync de diretório real, mesma barreira de startup e bloqueio dos 19 writers.
- `C3_STARTUP_AUTHORITY_PREPARATION_REVIEW_20260910.md`: esclarece que o teste
  anterior recusava troca para outro caminho, não restauração no mesmo caminho.
- Este relatório e plano.

Nenhum módulo operacional, rota ou configuração foi alterado nesta etapa.
As alterações já existentes no worktree foram preservadas.

## O que os testes comprovam e o que não comprovam

1. Dois processos concorrentes: exatamente um consumo confirmado; o registro
   permanece íntegro e um novo processo não consegue repetir o consumo.
2. Saída abrupta antes do commit: nenhuma autorização foi devolvida e a transação
   não fica confirmada. Um pedido posterior pode consumir a autorização. Não
   ocorreu manutenção antes da confirmação do consumo.
3. Saída abrupta depois do commit, antes da resposta: registro persiste e o pedido
   posterior é recusado. A falta de resposta não se transforma em autorização.
4. Mudança de época com o mesmo ledger: o nonce consumido continua recusado;
   um nonce novo, devidamente assinado para a época nova, pode ser consumido.
   Este caso não atesta rotação de chaves reais nem revogação operacional.
5. Backup anterior ao consumo restaurado no mesmo caminho: o pedido assinado
   volta a ser aceito. O teste está marcado `xfail(strict=True)` como bloqueador
   conhecido. Não deve ser contado como aprovação de segurança. A aceitação
   operacional deve usar `--runxfail`, tornando essa lacuna uma falha normal.

Os ensaios de processo usam `os._exit` no commit de `consume_once`; não simulam
queda de energia, falha de hardware, filesystem remoto ou restauração coordenada
de todos os stores. O ensaio de startup continua extraindo somente a barreira por
AST: não executa o aplicativo completo, HTTP ou workers. As operações de
bootstrap/recovery/postflight continuam sintéticas. Não constitui validação
completa do startup em produção.

## Plano de provisionamento — preparado, não executado

Reutilizar o manifesto já existente em
`trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authority_provisioning_manifest_contract_v2.py`.
Não criar outro contrato equivalente nem transformar referências em secrets.
O manifesto é uma especificação dormente, não uma autorização operacional.

### Dependências que precisam de origem confiável

- Provedor da chave raiz e identificador/época fixados fora do pedido; manter
  apenas referências como `C3_ROOT_AUTHORITY_KEY_PROVIDER_REF` no manifesto.
  Material de chave real fica fora do repositório, relatórios e testes.
- Fonte autenticada de revogação, com política de atualização e indisponibilidade.
  Resposta ausente, ambígua, revogada ou obsoleta deve impedir admissão.
- Raiz de armazenamento e caminho do ledger escolhidos explicitamente, com
  permissões restritas e persistência comprovada no filesystem alvo.
- Referência de atualidade independente do backup restaurável. Pode ser um
  serviço de consumo monotônico autenticado ou um checkpoint externo com
  protocolo crash-safe. A escolha e o protocolo ainda não estão implementados.
  Um hash ou contador guardado no mesmo backup não atende a esse requisito.
- Portas de recovery e catálogo resolvido provenientes da mesma composição
  auditada. Os nomes do manifesto não comprovam que essas portas sejam confiáveis.

### Ordem para um futuro ensaio de provisionamento

1. Preparar ambiente Linux descartável, sem rede, sem secrets, sem volume do
   Registry e sem processo operacional. Instalar dependências somente por um
   fluxo previamente aprovado; os comandos abaixo não as instalam.
2. Usar os fixtures sintéticos existentes: raiz temporária, ledger novo, provedor
   de chave sintética, fonte de revogação injetada e pins calculados desse fixture.
   Não copiar caminhos, pins, nonces ou assinaturas de produção.
3. Executar concorrência, interrupção, replay, deadline, revogação e composição
   com fsync real. Registrar também casos ignorados e falhas conhecidas.
4. Implementar e testar o protocolo independente contra rollback antes de
   considerar o provisionamento pronto. Cobrir checkpoint atrasado/indisponível,
   rollback do ledger, mudança de época e interrupção em cada fronteira de consumo.
5. Testar recuperação/restauração com admissão bloqueada. Não recriar banco vazio
   para eliminar erros; não admitir workers até reconciliar estado e atualidade.
6. Auditar startup completo e todos os processos separadamente. A barreira local
   atual não é uma prova de bloqueio global nem oferece promoção automática a Live.

### Execução de aceitação em Linux isolado

Executar na raiz deste worktree, com Python e pytest já disponíveis, sem plugins
de terceiros carregados automaticamente. Não executar no shell de produção.
O comando falhará enquanto o bloqueador de rollback persistir; isso é esperado.

```sh
python -c "import sys; assert sys.platform == 'linux', 'Linux isolado obrigatorio'" && \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONDONTWRITEBYTECODE=1 python -m pytest \
  -q -rs -p no:cacheprovider --runxfail \
  tests/test_c3_maintenance_ledger_process_probe.py \
  tests/test_trade_registry_c3_maintenance_authority_startup_v1.py \
  tests/test_trade_registry_c3_maintenance_activation_offline_v1.py
```

Critério de aceitação desta suíte: nenhum teste falho, ignorado ou xfailed.
Mesmo esse resultado não substitui os ensaios de recuperação multistore,
startup completo ou perda de energia no armazenamento alvo.

## Validação local

Rodada final das três suítes: **106 aprovados, 2 ignorados por ausência de Linux
e 1 xfailed de rollback em 41,14 s**. A primeira rodada dirigida teve 5 aprovados,
1 ignorado e 1 xfailed; não somar as rodadas.

O caso de rollback também foi executado isoladamente com `--runxfail`: **1 falha
em 0,64 s**, exatamente na asserção final que exige recusar a autorização após
restauração. O valor observado foi `True`. Isso confirma a lacuna sem escondê-la
atrás da marcação de falha conhecida. `git diff --check` passou nas alterações
rastreadas, com somente avisos de conversão de final de linha do Windows.

Não foram executados Linux, aplicativo completo, recuperação multistore,
perda de energia, suíte integral do repositório ou operações de produção.

## Segurança e próximo passo

Nenhum secret, `.env` ou dado real acessado. Nenhuma chamada externa ou ordem.
Nenhum commit, push, deploy, configuração do Render ou flag de trading alterado.
Não foi aplicado reparo CLOSED nem executado bootstrap/preflight de produção.

Próximo passo técnico: resolver offline o protocolo contra rollback com uma
dependência confiável independente e repetir a suíte de aceitação. A validação
Linux permanece pendente por falta de ambiente isolado. Não há percentual
fundamentado de trabalho restante para Live.
