# C3 — instalação local do WSL para laboratório

Data: 2026-09-10. Autorização: instalação do WSL neste computador, sem alterar
Render nem reiniciar automaticamente o Windows.

Atualização posterior: `C3_LINUX_ISOLATED_VALIDATION_20260910.md` registra a
preparação do laboratório isolado e os resultados Linux. O restante deste arquivo
preserva o estado observado ao concluir apenas a instalação do WSL.

## Resultado verificado

- WSL instalado: 2.7.13.0.
- Distribuição registrada: Ubuntu, versão WSL 2.
- Kernel respondeu: `Linux 6.18.33.2-microsoft-standard-WSL2`.
- Python respondeu: `Python 3.14.4`.
- Serviço WslService observado em execução.
- Instalador inicial encerrou; a distribuição estava parada antes da verificação.
- Linux iniciado somente para `uname -sr` e `python3 --version`, como root,
  sem executar a Central. Essas verificações funcionaram sem reinício do Windows.

O comando inicial sem elevação não instalou o componente. A instalação ocorreu
após invocação explícita do instalador Windows com `RunAs`, usando `--install
--no-launch`. Não foram encerrados processos do usuário nem realizado reboot.

Referências oficiais consultadas:
- https://learn.microsoft.com/en-us/windows/wsl/install
- https://learn.microsoft.com/en-us/windows/wsl/basic-commands

## Limites e próximo passo

Instalação do Linux não equivale a isolamento validado. Não foram alteradas as
configurações padrão de rede, montagem de discos Windows, interoperabilidade ou
usuário da distribuição. Não foram copiados código, bancos, `.env` ou secrets
para o Linux. Não foi instalado pytest nem executada a suíte da Central em Linux.

Próximo passo: preparar usuário e diretório próprios de laboratório, dependências
de teste e bloqueio efetivo de rede durante os ensaios; transferir somente fontes
necessárias e usar dados sintéticos em filesystem Linux, sem dados operacionais.
Depois executar as cinco suítes registradas no relatório de autoridade persistente,
incluindo os dois testes anteriormente ignorados por ausência de Linux.

O serviço de autoridade realmente independente, a validação de backup/recovery
externo e a integração de startup continuam pendentes. WSL na mesma máquina não
constitui domínio independente de confiança por si só e não habilita Live.

## Escopo preservado

Mudança desta etapa: instalação autorizada de WSL e Ubuntu no Windows, mais este
registro. Houve acesso à documentação oficial e download pelo instalador.
Não houve acesso a secrets reais, alteração de código operacional, chamada à
BingX ou Render, ordem, commit, push, deploy ou mudança de flags de trading.
