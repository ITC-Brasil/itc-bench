# Análise do código — ITC Configurador (03/11/2026)

Ponto de partida do ITC Bench. Escopo: `itc-config/configurador` (~7,8 mil linhas Python, sem contar instaladores), fora deste repositório. Leitura por varredura e grep dirigido; o programa não foi executado (exige Windows). O manual `Manual_Configurador_ITC.pdf` (31/10/2026) fica na mesma pasta de origem.

## Visão geral
- Duas interfaces convivendo: `main_moderno.py` + `ui/` (CustomTkinter, "v60.4") e `app_qt.py` + `interface_qt/` (PySide6, mais nova). O Qt já cobre mais abas (contas, limpeza, proteção, mouse, tela).
- `backend/` dividido em mixins por assunto e agregado em `AutomationBackend`. Boa separação UI/backend; o Qt usa `LogBus` com Signal para atualizar a UI a partir de threads.
- `backend/contas.py` é o padrão a seguir: PowerShell via lista de argumentos e dados por variável de ambiente (sem injeção, senha fora da linha de comando).
- Sem git, sem `requirements.txt`, sem `.spec` do PyInstaller, sem testes, sem lint.

## Crítico (segurança)
1. **`config/config.ini` com senhas em texto claro** (`senhaadminsuporte`, `lastsenha`). Valores omitidos aqui de propósito. Essas senhas devem ser trocadas nos notebooks; o Bench nunca persiste senha em preferência de UI.
2. **`config/segredos.json` ao lado do executável** (RustDesk, AnyDesk, conta Suporte), legível por qualquer usuário que abra a pasta. No Bench os segredos vêm da API (ADR a registrar) com cópia local protegida por DPAPI.
3. **`shell=True` com interpolação de strings** (~40 chamadas): `usuarios.py` (`net user "{user}" "{senha}"`), `remoto.py:165` (`echo {senha} | anydesk --set-password`), `sistema.py:21` (`Rename-Computer "{n}"` interpolado), `desinstalador.py:63` (UninstallString do registro executada com shell). Padrão alvo: o de `contas.py`.
4. **GPO gera `.bat` com `-ExecutionPolicy Bypass`** (`gpo.py:104`): verificar local de gravação e ACL; pasta gravável por usuário comum executada no logon é escalada de privilégio.
5. **GLPI em HTTP na porta 8888.** A migração para HTTPS já está no escopo da atualização para o GLPI 12.

## Alto (manutenção/robustez)
6. Duas UIs duplicadas: ficar só com o Qt.
7. `from config import *` e efeitos colaterais no import (`config.py` cria pastas, move arquivos e lê segredos).
8. Caminhos atrelados à pasta do EXE. Instalado: binários em `Program Files`, dados em `%ProgramData%\ITC\Bench`, preferências do usuário em `%LOCALAPPDATA%`.
9. 1,3 GB de instaladores dentro da pasta, com versões duplicadas do GLPI Agent. No Bench: download sob demanda com SHA-256 conferido (tabela Instaladores no NocoDB) ou winget.
10. ~40 `except:` / `except Exception: pass` silenciosos.
11. Mixins por herança múltipla (14 no backend, 13 na UI Tk): preferir composição.
12. Log só na tela; o Bench grava log rotativo em `%ProgramData%\ITC\Bench\logs`.

## Médio
13. `wmic` (`usuarios.py:20`) removido no Windows 11 recente: usar `Set-LocalUser -PasswordNeverExpires`.
14. Grupo "Administradores/Administrators" por idioma: usar SID `S-1-5-32-544`.
15. `time.sleep(10)` fixo esperando o serviço do AnyDesk: polling com timeout.
16. Lixo na pasta: `__pycache__`, ícones `4444444444.ico`, `sssssssssssssss.ico`, exemplos do MagicaVoxel em `instaladores/programas`.
17. Versão fixa no título: centralizar em `__version__`.
18. Comparação de versão como texto em `remoto.py` (1.10.0 < 1.4.5), apontada pelo manual.

## Pontos positivos
- Elevação via UAC com `ShellExecuteW runas` e modos `--dev`/`--teste`.
- `contas.py` e `protecao.py` bem escritos (SHA-256 contra troca do utilman/sethc, SPI para aplicar na sessão).
- Segredos já fora do código-fonte.
- Salvamento de preferências com debounce (QTimer 400 ms).
