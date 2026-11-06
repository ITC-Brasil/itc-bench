# BACKEND-SCHEMA — ITC Bench

O Bench não tem banco próprio. Lê cadastros da API do Técnico Assistente, que lê da base
"ITC Bench" no NocoDB (ADR-006), e guarda cópia local cifrada.

## Base "ITC Bench" no NocoDB

Colunas lidas em 03/11/2026 pela API de metadados do NocoDB (só esquema, nenhum registro lido).
Todas as tabelas têm também as colunas de sistema do NocoDB (`Id`, `CreatedAt`, `UpdatedAt`,
`nc_created_by`, `nc_updated_by`, `nc_order`, `__nc_deleted`, `nc_row_meta`). Nenhuma coluna está
marcada como obrigatória nem única: validação fica na API.

### Servidores

| Coluna | Tipo NocoDB | Observação |
|---|---|---|
| `Servico` (`servico`) | SingleLineText, display | Ex.: GLPI, RustDesk, AnyDesk |
| `Papel` (`papel`) | SingleLineText | Ex.: servidor de ID, relay, API, chave pública, senha |
| `Valor` | LongText | **Sensível**: endereços, chaves, senhas |
| `Versao` | SingleLineText | |
| `Ativo` | Checkbox | |
| `Observacao` | LongText | Segredo quando `Publico` não é `true` (ADR-014) |
| `Publico` | Checkbox | Coluna nova (ADR-014): só `true` sai como público; vazio ou coluna ausente = segredo |

### Instaladores

| Coluna | Tipo NocoDB | Observação |
|---|---|---|
| `Programa` | SingleLineText, display | |
| `Versao` | SingleLineText | |
| `Arquivo` | SingleLineText | Nome do arquivo baixado |
| `SHA256` | SingleLineText | Conferido antes de executar |
| `Link` | URL | Origem do download |
| `Ativo` | Checkbox | |
| `Observacao` | LongText | |
| `Tipo` | SingleSelect: `instalador`, `winget`, `webapp` | Vazio = `instalador` (ADR-020) |
| `Categoria` | SingleSelect: `Programas`, `Jogos` | Vazio = `Programas`; dá as abas da tela |
| `Identificador` | SingleLineText | winget: ID do pacote; webapp: URL `https://` |
| `Argumentos` | LongText | Só instalador: um argumento por linha (MSI: `PROPRIEDADE=valor`). Vazio em `.exe` = instalação interativa |
| `Deteccao` | SingleLineText | Opcional: começo do nome em "Aplicativos instalados" quando é diferente de `Programa` |
| `Modo` | SingleSelect: `quiosque`, `app` | Só webapp; vazio = `quiosque` |

Contrato de Programas (ADR-020, TA-ADR-029):
- **instalador:** `Programa`, `Versao`, `Arquivo` `.msi`/`.exe`, `SHA256`, `Link` `https://`.
  Cadastre `Programa` com o nome que aparece em "Aplicativos instalados" do Windows (o Bench o
  usa como prefixo para dizer se está instalado; MSI é achado pelo `ProductCode` do arquivo).
- **winget:** `Programa` e `Identificador` (ID exato do repositório `winget`). `Versao` é só
  referência. `Link`, `SHA256` e `Arquivo` vazios.
- **webapp:** `Programa` (vira o nome do atalho), `Identificador` (`https://`), `Modo`. Ícone
  opcional: `Link` `https://` do `.ico`, `SHA256` e `Arquivo` `.ico`.
- Linhas `GLPI Agent`, `RustDesk` e `AnyDesk` do tipo instalador são do Acesso remoto e não
  aparecem em Programas. Duplicada (mesmo tipo e ID/URL, ou mesmo `Programa` entre
  instaladores): nenhuma das duas instala.

### WiFi

| Coluna | Tipo NocoDB | Observação |
|---|---|---|
| `SSID` | SingleLineText, display | **Sensível para log**: visível na tela, nunca no log (o log usa `Id`) |
| `Senha` | SingleLineText | **Sensível**, nunca exibida na UI. Obrigatória: WPA2-Personal, 8–63 caracteres comuns ou 64 hexadecimais; vazia ou fora disso, o Bench não instala (ADR-018) |
| `Unidade` | SingleLineText | Texto livre, casa com `Unidades.Codigo` (sem link) |
| `categoria` | SingleLineText | Ex.: Carreta, Roteador 4G, Parceiro local |
| `Ativo` | Checkbox | |
| `AtualizadoPor` | SingleLineText | Técnico |
| `AtualizadoEm` | DateTime | |

### Unidades

| Coluna | Tipo NocoDB | Observação |
|---|---|---|
| `Codigo` | SingleLineText, display | Sigla do programa + número da UM com dois dígitos: `^[A-Z]{1,6}[0-9]{2}$`, até 8 (ex. fictício: `ABC01`). ADR-018 |
| `Nome` | SingleLineText | |
| `Cidade` | SingleLineText | |
| `UF` | SingleLineText | |
| `TagGLPI` | SingleLineText | Tag do GLPI Agent |
| `PerfilPadrao` | SingleLineText | Perfil da Preparação completa |
| `Ativo` | Checkbox | |

**Regra `WiFi.Unidade`:** continua texto, sem relação no NocoDB, com o mesmo código de
`Unidades.Codigo` (ex. fictício: `ABC01`). A API descarta a rede cuja unidade não é uma Unidade ativa; o
Bench não confia em código que a API não validou. Sem `?unidade=`, a API entrega todo o Wi-Fi;
com `?unidade=`, só o daquela unidade (ADR-014, que substitui a regra de 03/11/2026 de filtrar
sempre).

`Servidores.Valor` misturava público e segredo: resolvido pela coluna `Publico` (ADR-014). Linhas
com `Ativo` diferente de `true` são filtradas na API.

Contrato da conta Suporte (ADR-017): `Servico = "Conta Suporte"`, `Papel = "usuario"` (nome da
conta, `Publico` marcado) e `Papel = "senha"` (`Publico` desmarcado). Uma linha ativa de cada;
duplicada, o Bench recusa. Sem `usuario`, o nome é `Suporte`.

Contrato do acesso remoto (ADR-019), uma linha ativa por par: `GLPI Agent`/`servidor` (URL
`http(s)://`, público), `RustDesk`/`servidor` (host sem porta, público), `RustDesk`/`chave`,
`RustDesk`/`senha` e `AnyDesk`/`senha` (não públicos). Ausente, vazia, duplicada ou com
`Publico` trocado: o Bench recusa aquele programa e diz o par. Instaladores: `Programa` igual a
`GLPI Agent`, `RustDesk` ou `AnyDesk`, `SHA256` de 64 hexadecimais, `Link` `https://` e
`Arquivo` com `.msi`, `.msi`, `.exe`. `Unidades.TagGLPI` é opcional (sem ela, o agente vai sem
`TAG=`).

## API (rotas)

Existentes na API (`docs/api/API.md`): `GET /v1/saude`,
`POST /v1/relatorio`, `GET /v1/historico/{hostname}`, autenticadas por token de carreta
`Authorization: Bearer itcta_...`.

Do Bench, com sessão `Authorization: Bearer itcbs_...`: `/v1/bench/login|logout|sessao|saude`
(ADR-013), `GET /v1/bench/cadastros[?unidade=<codigo>]` (ADR-014), `POST /v1/bench/relatorio` e
`GET /v1/bench/historico/{hostname}` (ADR-016). Formato em `docs/api/API.md`.

## Guardado localmente pelo Bench

| O quê | Onde | Proteção | Módulo |
|---|---|---|---|
| Cache dos 4 cadastros (`formato`, versão, `sincronizado_em`, `por`, unidade, corpo da API com segredos); válido 7 dias | `%ProgramData%\ITC\Bench\protegido\cadastros.dpapi`; sem admin, só memória | DPAPI de máquina + ACL só SYSTEM e `S-1-5-32-544` (ADR-013, ADR-014) | 05 |
| Unidade da máquina (código de `Unidades`) | `HKLM\SOFTWARE\ITC\Bench`, valor `Unidade` | Escrita só por admin | 05 |
| Verificador do login offline por técnico (scrypt) + datas, validade 7 dias | `%ProgramData%\ITC\Bench\protegido\logins.dpapi` | DPAPI de máquina + ACL (ADR-013) | 04 |
| Sessão da API (`itcbs_`) | Só memória | — | 04 |
| Endereço da API | `HKLM\SOFTWARE\ITC\Bench`, valor `ApiUrl` | Escrita só por admin | 04 |
| Estado da Preparação completa (etapas, retomada após reinício) | `%ProgramData%\ITC\Bench` | ACL de admin | migração do Master |
| Log rotativo (sem segredo nem SSID; versão com 12 caracteres) | `%ProgramData%\ITC\Bench\logs` | ACL de admin | 01 |
| Preferências de UI (sem senha) | `%LOCALAPPDATA%\ITC\Bench` | — | 01 |
| Fila de diagnósticos não enviados (`formato`, `envio_id`, `criado_em`, `coletado_por`, hostname, corpo 1.3 já saneado); 10 itens, 14 dias | `%ProgramData%\ITC\Bench\protegido\fila-diagnostico.dpapi`; ilegível vira `fila-diagnostico.corrompida`; sem admin, só memória | DPAPI de máquina + ACL (ADR-015) | 06 |
| Token da carreta (`itcta_`) | Não vai aos notebooks: o envio usa a sessão (ADR-016) | — | 06 |
| Instaladores conferidos (nome = SHA-256 + extensão); apagados quando nenhuma linha ativa de Instaladores os usa | `%ProgramData%\ITC\Bench\protegido\instaladores\` | ACL só SYSTEM e `S-1-5-32-544` (ADR-019) | 09 |
| Ícones dos Web Apps (nome = SHA-256 + `.ico`); limpos com a mesma regra dos instaladores | `%ProgramData%\ITC\Bench\icones\` | ACL gravada pelo Bench: sem herança, SYSTEM e Administradores total, Usuários leitura (ADR-020) | 10 |
| Atalhos dos Web Apps (descrição "ITC Bench") | Desktop Público | ACL padrão do Windows (gravação só admin) | 10 |
| Configuração do RustDesk (servidor, chave; senha só cifrada pelo RustDesk) | `%WINDIR%\ServiceProfiles\LocalService\AppData\Roaming\RustDesk\config\` | Pasta do perfil do serviço (SYSTEM, LocalService, Administradores) | 09 |
| `batteryreport.html` do powercfg | Pasta temporária, apagado depois de lido | — | 06 |
