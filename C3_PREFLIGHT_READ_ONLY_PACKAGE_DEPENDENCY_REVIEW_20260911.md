# C3 — Revisão local do pacote e das dependências

Data: 2026-09-11. Escopo: revisão estática local, sem instalação, rede, execução da aplicação ou publicação.

## Resultado

**Delta da correção conferido; nenhuma dependência nova introduzida. Build reproduzível e publicação ainda não comprovados.**

HEAD local e base do candidato: `d9e12e9daa8f606c3649370bbbf1551650979eb6`. Isso não comprova a versão atualmente implantada no Render.

Foram recalculados os hashes dos 557 arquivos do candidato e dos oito artefatos históricos: todos coincidem com os manifestos. Inventário: `80461db78d76143b30ec99c67875823e094aa7f057848cd3b731d0691e30b9d8`. Conferido também o JUnit da execução anterior no Python 3.11.9: 145 testes, zero falhas, erros ou ignorados; SHA-256 `804708bc44e920b7e3be89c5bda3b98240c2bf2f2206d4bb09000e28dfee151b`. Os testes não foram repetidos nesta revisão.

## Delta e limites de empacotamento

O overlay conferido contém seis arquivos modificados e quatro novos. Em `main.py`, a única alteração contra a base é, na função `_frpp_v1_get_trade_registry_storage`, a chamada `fn(force=False, read_only=True)` em lugar de `fn(force=False)`.

Os outros modificados são dois contratos de binding com atualização de hashes/tamanho e três arquivos de testes. Os quatro novos são três helpers de laboratório e o teste de integridade do candidato. O diff completo do teste de preflight foi lido: cobre observação repetida com readiness presente/ausente, ausência de bootstrap/escrita/mutação e recusa de provider legado incompatível sem retry inseguro.

A implementação do provider foi lida estaticamente em `main.py:51239`; sua assinatura aceita `read_only`. Esse caminho não instala o patch, não realiza bootstrap e não atualiza `last_status`. **Ainda lê o arquivo ativo para contagens**: read-only não significa no-I/O. Nesta revisão nenhuma dessas funções foi executada nem o arquivo real lido. A referência inicial a um possível módulo separado não existia; o provider foi localizado na própria fonte de main, sem importação.

Os 557 arquivos são uma árvore de validação, não uma substituição integral do diretório de produção. A base contém itens deliberadamente excluídos dessa árvore. Um futuro release deve preservar o restante da base e transportar apenas o delta explicitamente escolhido; não copiar a árvore offline sobre produção nem incluir `.offline_validation`, runtime portátil, wheels ou scratch. Não foi materializado nem aplicado um patch publicável nesta etapa.

## Dependências e build

`requirements.txt` e `runtime.txt` são byte a byte idênticos à base. O primeiro declara somente:

`flask`, `gunicorn`, `requests`, `pandas`, `numpy`, `ccxt`, `upstash-redis`.

Nenhum dos sete tem versão fixada. `runtime.txt` declara `python-3.11.9`. A consulta dos nomes rastreados da base não encontrou `uv.lock`, `poetry.lock`, `Pipfile.lock`, `requirements.lock`, `pyproject.toml`, `setup.py`, `setup.cfg`, `render.yaml`, `render.yml`, `Dockerfile`, `Procfile` ou `.python-version`. A inspeção delimitada dos nomes de arquivos no nível superior da worktree e da raiz também encontrou somente requirements/runtime entre esses nomes. Isso não é uma busca exaustiva por todo formato possível de configuração.

Consequências:

- Não há versão resolvida comprovada dos pacotes da aplicação, nem comandos efetivos de build/start do Render identificáveis nesses arquivos.
- Os 145 testes usaram pytest e dependências de teste, não validaram a instalação conjunta dos sete pacotes da aplicação.
- Não se deve inferir as versões da produção a partir de uma resolução nova ou escolher pins arbitrários neste delta.
- O problema de reprodutibilidade é preexistente; não foi causado pela correção read-only. Ele limita o que se pode afirmar sobre um novo build.

Os imports não resolvidos da auditoria anterior foram revistos nos trechos de fonte: `strategy` e `telegram_utils` têm implementações alternativas locais nos três bots; `psutil` tem fallback para `resource`. O import calculado em `executive_policy_learning.py` usa cinco nomes literais de módulos presentes na árvore. Isso não comprova equivalência funcional dos fallbacks nem segurança da inicialização. Nenhum bot ou import dinâmico foi executado; nenhuma dependência foi adicionada para mascarar esses casos.

## Próxima ação concreta e condições de saída

Validar a resolução das sete dependências em outro ambiente local descartável Python 3.11.9, obtendo os pacotes de fontes públicas, registrando versões e hashes e verificando consistência da instalação sem importar/iniciar a Central. Isso requer uma etapa de downloads; a instalação e os testes devem permanecer sem rede. Se não houver distribuição binária compatível ou surgir conflito, registrar a falha e parar, sem compilar ou alterar versões/configuração automaticamente.

Uma resolução bem-sucedida será apenas um candidato de dependências para laboratório, não prova das versões instaladas no Render e não autorização para alterar requirements ou publicar. A identidade do artefato final, configuração efetiva do serviço, bloqueio atual de trading, preservação de dados e rollback continuam exigindo evidência própria antes de deploy. Live não está liberado. Percentual restante: **indeterminado**.

## Alterações e segurança

Único arquivo criado nesta etapa: este relatório. Nenhum código, teste, contrato, pin, dependência ou evidência anterior foi modificado. Verificações executadas: hashes, metadados Git locais, diffs, leitura/AST de fontes e conferência do JUnit anterior. Não executados: testes de aplicação novos, resolução/instalação de dependências, build/start, preflight real e suíte global.

Nenhum secret, .env, token, chave ou dado operacional foi acessado. Nenhuma chamada externa, instalação, commit, push, deploy, alteração de configuração de trading real ou ordem. O automatismo não foi alterado.

Modelo recomendado: **GPT-6 Astra — Alto**.
