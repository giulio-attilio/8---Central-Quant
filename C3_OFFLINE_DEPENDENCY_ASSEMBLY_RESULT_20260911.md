# C3 — montagem offline das dependências, 11/09/2026

## Resultado

Montagem dormente implementada, sem ligação ao startup publicado. Foram aprovados
120 testes locais: 31 novos e 89 de regressão. Isso comprova a montagem e suas
recusas; não comprova readiness de produção nem autoriza Live.

## Escopo e diff resumido

Somente quatro arquivos novos de código/documentação nesta etapa:

- `c3_runtime_dependency_assembly_offline_v1.py`: reúne as classes existentes de
  coordenador, autoridade, interlock, gate e composição, com todas as configurações
  desativadas. Os providers são apenas retidos, nunca chamados pela montagem.
- `tests/test_c3_runtime_dependency_assembly_offline_v1.py`: dados e dependências
  sintéticos, traps de chamada, recusa de startup/recuperação/lease, integridade
  de cada vínculo, configuração trocada, DTOs protegidos e fronteira de produção.
- `tests/helpers/c3_dependency_assembly_lab.py`: execução explícita sem downloads,
  com namespaces Linux sem rede, usuário sem privilégios, fontes somente leitura,
  bloqueio de importação de main/broker/bots/Registry e de processos filhos.
- Este relatório.

Trechos relevantes da montagem: o interlock recebe exatamente o coordenador e
a autoridade criados; gate e composição recebem a mesma instância de lock e
startup_state. O snapshot compara cada referência capturada e a configuração
original desativada. Não há instalação global, registro de writers, método de
ativação ou chamada de recuperação. O interlock não instalado rejeita uso.

Nenhum arquivo existente foi editado. As sete alterações rastreadas que já estavam
no worktree foram preservadas e não incluídas na validação desta montagem.
O índice Git permaneceu sem diferenças.

## Validação

Base: inventário imutável de 557 fontes do release publicado, SHA-256
`80461db78d76143b30ec99c67875823e094aa7f057848cd3b731d0691e30b9d8`.
Sobreposição: apenas os três novos arquivos Python acima. Nenhum snapshot antigo
de release foi alterado. Runtime de laboratório já existente: Python 3.11.9.

- Montagem offline: 31 aprovados.
- Composição startup existente: 32 aprovados.
- Binding de portas existente: 19 aprovados.
- Fronteira de autoridade existente: 5 aprovados.
- Gate de admissão existente: 33 aprovados.
- Total: 120 aprovados, zero falhas, 0,71 s na execução do pytest.
- Sintaxe dos três arquivos novos validada também sem importá-los no Windows.

A primeira execução teve 88 testes aprovados; a execução final acrescentou a suíte
da composição e a verificação de recusa de maintenance lease. O aviso de sessão
systemd emitido pelo WSL não impediu o laboratório: isolamento confirmado e saída 0.

Evidência final nesta árvore:
`.offline_validation/c3_dependency_assembly_20260911/cq-c3-lab-assembly-rom6j4v3/`.
JUnit SHA-256:
`fa02eadda22076c40df13f1a3f2da4adb78d5bc4733a20bb0262be181efd5ba7`.
O result.json contém hashes dos três arquivos executados, inventário e saída.
Os diretórios temporários e as evidências de ambas as execuções foram preservados.

## Limites e riscos residuais

Esta montagem não executa a cadeia completa de recuperação: os testes da montagem
exigem que nenhum provider seja chamado. A suíte existente da autoridade exercita
seus próprios cenários sintéticos, separadamente. Não foi executado novo preflight,
teste de produção, suíte integral da Central ou ensaio sobre Registry real.

Os providers recebidos são injetados e declarados sintéticos, não autenticados por
esta montagem. Identidade de objeto não comprova autenticidade de produção.
O adapter de portas de produção continua rejeitando esses DTOs sintéticos; não
foram reclassificados como runtime. O snapshot é diagnóstico local, nunca uma
permissão de startup. Ele não torna imutáveis objetos externos nem substitui os
interlocks existentes.

A montagem verifica atributos internos das classes existentes. Mudança nesses
atributos deve exigir atualização explícita e nova regressão; não há fallback
que silencie vínculo rompido. O runtime Python/local é reutilizado, não novamente
provisionado. A execução final validou as fontes publicadas mais os arquivos novos,
não as outras mudanças ainda não publicadas do worktree.

O coordenador dormente mantém sua semântica existente, inclusive a passagem de
writers legados: este módulo não é um bloqueio operacional de writers. Readiness,
recuperação durável autenticada e ativação permanecem fora desta entrega.

## Segurança e próximo passo

Nenhum secret, token, chave ou arquivo .env foi acessado. Nenhuma chamada externa
foi feita. Nenhum commit, push, merge ou deploy foi executado. Nenhuma configuração
de trading real foi alterada, nenhuma ordem foi enviada e nenhum dado real foi
lido ou modificado. main.py e a instalação global do coordenador não foram tocados.

Próximo passo técnico: definir e testar a passagem de evidências de recuperação
entre as portas sintéticas desta montagem, preservando a recusa de produção.
Isso deve reutilizar os contratos existentes, sem habilitar o runtime. Integração
ou operação em produção permanece uma etapa distinta, com autorização específica.

Percentual restante para Live: indeterminado. Aprovação desta etapa offline não
remove, por si só, nenhum dos dois bloqueios observados no último preflight.
