# C3 — integração do vínculo dormente no startup

## Escopo e resultado de código

Autorização: resposta `sim` à proposta de integrar as correções ao código de
startup, mantendo tudo desativado por padrão, sem dados reais, commit, push,
deploy ou Live. Não autoriza provisionamento ou execução operacional.

O startup agora constrói uma única instância de coordenador desativado antes
dos adaptadores. A mesma instância é entregue à recuperação multistore e ao
instalador dos interlocks. A factory dormente grava somente um pin de identidade
local. O instalador valida a identidade, os tipos exatos e `enabled is False`
antes de criar/instalar capacidades. Falha nessa validação interrompe a montagem.

Não foi usado o harness sintético como implementação de produção. Nenhum backend
físico, caminho, raiz autenticada, chave, lease ou porta de recuperação operacional
é inferido. Eles continuam ausentes. O vínculo NÃO comprova autenticação,
durabilidade, posse de locks ou readiness operacional. A operação de recuperação,
o gate e a composição permanecem default-off. As cinco fontes DORMANT e o
autostart existente não foram alterados.

O preflight estático foi ajustado ao novo fluxo: exige construção única sem
argumentos de habilitação, passagem explícita do mesmo global, ordem de
construção e guarda canônica anterior à instalação. Não aceita somente nomes de
builders. A checagem é de uma forma AST restrita; não é prova geral de todos os
possíveis efeitos de um programa Python, nem autorização de produção.

## Arquivos modificados nesta etapa

- `main.py`: construção única, injeção explícita e guarda antes da instalação.
- `trade_registry_closed_identity_conflict_repair_runtime_production_startup_recovery_authenticated_persistent_authority_production_adapters_v2.py`:
  factory dormente com coordenador opcional e validação de vínculo sem I/O;
  chamada antiga sem argumentos continua suportada e desativada.
- `trade_registry_closed_identity_conflict_repair_runtime_static_preflight_v1.py`:
  validação estática do novo fluxo e das duas passagens do coordenador.
- `tests/test_c3_dormant_startup_same_coordinator_v2.py`: novo teste de fragmentos
  AST revisados, montagem e falha fechada; nenhum import de main.
- `tests/test_trade_registry_closed_identity_conflict_repair_runtime_static_preflight_v1.py`:
  caso com somente shapes/builders passa a exigir rejeição do vínculo.
- `tests/helpers/c3_dependency_assembly_lab.py`: overlays explícitos e suítes novas.
- Este relatório e `C3_OFFLINE_CONTINUITY_20260911.md`: resultado e continuidade.
- Evidências geradas em subdiretórios novos de
  `.offline_validation/c3_dependency_assembly_20260911/`.

Alterações preexistentes em main (binding de manutenção e preflight read-only),
coordenador, adapters e demais arquivos foram preservadas. Nenhum dado operacional
ou pacote histórico foi apagado/sobrescrito; nenhum pacote anterior contém esta etapa.

## Validação

Primeira rodada: 230 aprovados e 1 falha em teste novo. O namespace do fragmento
sintético não definia `__name__`, deixando a identidade do verificador indisponível.
O gate recusou corretamente. Corrigido o namespace do teste, sem relaxar o gate.
Evidência preservada: `cq-c3-lab-assembly-vc5stj60`.

Segunda rodada: 261 aprovados e 6 falhas, `cq-c3-lab-assembly-k5g_qlpk`.
Três mutações AST sintéticas omitiam `ctx=ast.Load()`; corrigidas apenas no teste.
As outras três detectaram 11 referências antigas de linhas no laboratório:
o overlay de main já continha as alterações preexistentes, mas o contrato de
seams ainda vinha da base histórica. Incluído explicitamente o contrato local
`trade_registry_closed_identity_conflict_repair_writer_seam_binding_contract_v1.py`
após revisar suas 11 mudanças exclusivamente de números de linha. Este contrato
NÃO foi editado nesta etapa. A checagem de linhas exatas não foi relaxada.
O limite do processo de testes passou de 180 para 300 segundos devido à suíte
AST ampliada (a segunda rodada demorou 168,78 s); nenhum deadline operacional mudou.

Resultado final: **267 aprovados, zero falhas, erros ou skips**, em 165,00 s.
Evidência: `cq-c3-lab-assembly-o88wfn4u/result.json` e `results.xml`.
Os 18 overlays foram conferidos novamente após a execução: todos os hashes
coincidem com os arquivos atuais. JUnit SHA-256:
`725f31c0b7314b5d9eb8a164f813bbdeb26ea3b58f9e6f395be5f16670397a23`.
`git -c core.longpaths=true diff --check` passou; índice Git permanece vazio.
Inclui 211 regressões anteriores, 20 casos novos, 7 testes existentes de startup
dormente e 29 de preflight estático. O preflight de fontes passou sem promover
readiness operacional: `production_ready=False` e `live_allowed=False`.

Ambiente: Python 3.11.9 já existente, usuário sem privilégios, fontes somente
leitura, namespace sem rede/rotas, sem mounts Windows/home e sem processos filhos
nos testes. Importação de main/trade_registry/broker/bots bloqueada. Fragmentos
dormentes específicos de main são extraídos via AST; o módulo inteiro nunca é
executado. A instalação da seam nos testes novos é um fake em memória.

Não executados: startup integral, Windows nativo, crash/restart real, serviços,
preflight operacional, bootstrap, reparo real ou suíte integral do repositório.

## Riscos residuais e próximo marco

A nova assinatura privada do instalador exige coordenador explícito. Um chamador
antigo fora do fluxo auditado falhará fechado. Refatorar a forma canônica da guarda
exige atualizar e testar a checagem AST. Pins são locais por instância/processo,
não assinaturas. As dependências persistentes/autenticadas de produção ainda não
estão provisionadas nem conectadas. Não basta ligar uma flag para concluir isso.

Próximo marco: revisar o conjunto consolidado para preparação controlada das
dependências de produção, separando planejamento de qualquer execução operacional.
Não voltar a registrar esta montagem dormente como pendente após sua validação.

Nenhum secret foi acessado; nenhuma chamada externa foi feita; nenhum commit,
push ou deploy foi executado; nenhuma configuração de trading real foi alterada.
Não houve acesso ao Registry real, envio de ordens ou ativação de Live.
Automação não modificada nesta etapa. Percentual restante para Live: indeterminado.
