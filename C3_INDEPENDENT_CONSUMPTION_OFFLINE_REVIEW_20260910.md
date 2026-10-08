# C3 — consumo independente contra reutilização após restauração

Data: 2026-09-10. Escopo: implementação e testes exclusivamente offline.

Ensaio posterior: `C3_PERSISTENT_AUTHORITY_LAB_REVIEW_20260910.md` registra uma
referência com persistência sintética e processos reais. Este relatório preserva
a etapa anterior em memória; nenhum dos dois representa instalação de produção.

## Resultado e limite

O autorizador deixou de aceitar o ledger local como única prova de consumo.
Agora exige um comprovante assinado de uma autoridade de consumo independente,
antes de gravar o consumo local ou devolver autorização à composição.
Sem essa dependência, com assinatura inválida ou em qualquer falha intermediária,
o resultado é fechado. O padrão continua desligado.

O caso que antes falhava após restaurar o backup agora é um teste normal de
regressão, sem `xfail`. Isso comprova o protocolo com uma autoridade sintética
em memória preservada fora da restauração do SQLite temporário. **Não comprova
durabilidade ou proteção contra rollback de um serviço real.** Não foi criado,
configurado ou conectado um serviço externo. Produção continua pendente.

## Causa e alteração

O pin anterior identificava o caminho do banco; restaurar o conteúdo antigo no
mesmo caminho apagava o consumo sem mudar esse pin. A correção não usa outro
hash ou contador no mesmo backup.

O fluxo passou a ser:

1. Validar assinatura do pedido, configuração fixada, prazo e revogação.
2. Gerar desafio aleatório novo de 256 bits, fora do histórico restaurável.
3. Solicitar consumo atômico de `(namespace, claim)` na dependência independente.
4. Exigir comprovante assinado vinculado ao namespace, claim, payload, desafio,
   deadline e confirmação estrita de commit. Conferir assinatura pela chave
   fixada do consumidor, usando o verificador já existente.
5. Revalidar prazo e revogação, consumir o ledger local e revalidar novamente.
6. Somente então devolver autorização à composição offline.

A identidade do claim continua vinculada ao escopo, raiz e nonce, sem variar com
deadline ou época da chave. Namespace é configuração confiável, nunca escolhido
pelo pedido nem recriado automaticamente durante recovery.

Uma resposta perdida após consumo independente não permite retry. Falha no
registro local também não desfaz esse consumo. O pedido fica inutilizado mesmo
que nenhuma manutenção tenha sido executada; não há compensação automática.
Um comprovante antigo não serve para outra tentativa, pois o desafio muda.

## Arquivos desta etapa / diff resumido

- `trade_registry_c3_maintenance_authorization_v1.py`: DTO protegido do comprovante,
  digest com domínio próprio, pins do consumidor, verificação obrigatória do
  consumo independente e revogação das duas chaves. Reutiliza o verificador HMAC
  existente. Não adiciona caminho, credencial ou endpoint automático.
- `tests/test_trade_registry_c3_maintenance_authority_startup_v1.py`: provedor
  sintético com chave própria e consumo atômico em memória, compartilhado entre
  instâncias reconstruídas; remove `xfail` da regressão de restauração.
- `tests/test_c3_maintenance_independent_consumption_v1.py`: dependências ausentes,
  pins inválidos, respostas booleanas, bindings alterados mesmo assinados, assinatura
  inválida/chave errada, revogação, deadline, regressão do relógio, falha de entropia,
  perda de resposta, falha de commit local, comprovante antigo e crashes simulados.
- `C3_AUTHORITY_PROVISIONING_AND_CRASH_REVIEW_20260910.md`: nota de atualização
  preservando o resultado histórico do diagnóstico anterior.
- Este relatório.

`main.py`, coordenação, runtime, Registry e flags não foram modificados nesta
etapa. As alterações anteriores do worktree foram preservadas.

## Validação

Rodada inicial: 64 testes aprovados e 1 ignorado por depender de Linux.
Rodada final das quatro suítes, com `--runxfail`: **141 aprovados e 2 ignorados
por ausência de Linux, em 41,36 s**. Nenhum teste falho ou marcado como `xfail`.
Inclui os ensaios anteriores entre processos para o SQLite e a composição offline.
Não somar as duas rodadas como testes distintos. `git diff --check` passou nas
alterações rastreadas, com avisos de conversão de final de linha do Windows.

```text
python -m pytest -q -rs -p no:cacheprovider --runxfail
  tests/test_c3_maintenance_independent_consumption_v1.py
  tests/test_trade_registry_c3_maintenance_authority_startup_v1.py
  tests/test_trade_registry_c3_maintenance_activation_offline_v1.py
  tests/test_c3_maintenance_ledger_process_probe.py
```

Os argumentos acima pertencem a uma única chamada; a execução local utilizou
também um diretório temporário exclusivo para a rodada.

Os novos crashes usam uma exceção derivada diretamente de `BaseException`, para
sair sem passar pelo tratamento normal de erros, antes/depois do consumo local
ou depois do consumo independente. A autoridade sintética mantém o estado em
memória fora do ledger restaurado. Não é ensaio de morte de um serviço remoto.
Os ensaios anteriores com `os._exit` continuam limitados ao commit do SQLite local.

Rede é bloqueada. Apenas o auxiliar sintético fixo é permitido nos testes de
processos já existentes. Todos os bancos são temporários e as chaves são bytes
sintéticos. O desafio aleatório gerado não é uma credencial operacional.

## Riscos residuais e próximos passos

- Implementação confiável e persistente da autoridade independente ainda não
  existe nesta composição. Não substituir o fake por outro arquivo no mesmo
  domínio de backup e afirmar que isso resolve rollback.
- O consumidor futuro deve autenticar o acesso, consumir atomicamente, respeitar
  prazo, reter histórico entre reinícios/rotação e assinar somente o primeiro
  consumo. Se perder seu próprio histórico ou assinar repetição, este cliente não
  consegue provar que o serviço violou o contrato. Assinatura autentica o emissor,
  não a implementação correta de sua persistência.
- Pins, chaves, fonte de revogação, namespace estável e política de recuperação
  dependem de provisionamento confiável ainda não executado.
- A proteção é contra reutilização da autorização. Não reconstrói registros
  locais perdidos nem torna uma restauração do Registry apta para operação.
- Chamadas injetadas têm deadlines cooperativos; não há preempção de callbacks.
- Linux isolado, durabilidade do armazenamento alvo, startup completo, coordenação
  multistore e ensaio operacional seguem pendentes. Não foi executada a suíte
  integral do repositório nem qualquer preflight de produção.

Próximo passo: definir e validar o backend persistente independente em laboratório
isolado, incluindo autenticação, recuperação e falhas entre processos. Sem esse
backend provisionado, o autorizador deve continuar recusando execução. Essa
pendência não exige mudar o Render ou habilitar trading agora.

Nenhum secret real ou `.env` acessado; nenhuma chamada externa, ordem, commit,
push ou deploy. Nenhuma configuração do Render ou flag de trading real alterada.
Percentual restante para Live: ainda não mensurável com fundamento.
