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

### WiFi

| Coluna | Tipo NocoDB | Observação |
|---|---|---|
| `SSID` | SingleLineText, display | **Sensível para log**: visível na tela, nunca no log (o log usa `Id`) |
| `Senha` | SingleLineText | **Sensível**, nunca exibida na UI |
| `Unidade` | SingleLineText | Texto livre, casa com `Unidades.Codigo` (sem link) |
| `categoria` | SingleLineText | Ex.: Carreta, Roteador 4G, Parceiro local |
| `Ativo` | Checkbox | |
| `AtualizadoPor` | SingleLineText | Técnico |
| `AtualizadoEm` | DateTime | |

### Unidades

| Coluna | Tipo NocoDB | Observação |
|---|---|---|
| `Codigo` | SingleLineText, display | Ex.: `UM-07` |
| `Nome` | SingleLineText | |
| `Cidade` | SingleLineText | |
| `UF` | SingleLineText | |
| `TagGLPI` | SingleLineText | Tag do GLPI Agent |
| `PerfilPadrao` | SingleLineText | Perfil da Preparação completa |
| `Ativo` | Checkbox | |

**Regra `WiFi.Unidade`:** continua texto, sem relação no NocoDB, com o mesmo código de
`Unidades.Codigo` (ex.: `UM-07`). A API descarta a rede cuja unidade não é uma Unidade ativa; o
Bench não confia em código que a API não validou. Sem `?unidade=`, a API entrega todo o Wi-Fi;
com `?unidade=`, só o daquela unidade (ADR-014, que substitui a regra de 03/11/2026 de filtrar
sempre).

`Servidores.Valor` misturava público e segredo: resolvido pela coluna `Publico` (ADR-014). Linhas
com `Ativo` diferente de `true` são filtradas na API.

## API (rotas)

Existentes na API (`docs/api/API.md`): `GET /v1/saude`,
`POST /v1/relatorio`, `GET /v1/historico/{hostname}`, autenticadas por token de carreta
`Authorization: Bearer itcta_...`.

Do Bench, com sessão `Authorization: Bearer itcbs_...`: `/v1/bench/login|logout|sessao|saude`
(ADR-013) e `GET /v1/bench/cadastros[?unidade=<codigo>]` (ADR-014). Formato em `docs/api/API.md`.

## Guardado localmente pelo Bench (planejado)

| O quê | Onde | Proteção | Módulo |
|---|---|---|---|
| Cache dos 4 cadastros + data da sincronização | `%ProgramData%\ITC\Bench` | DPAPI | 04 |
| Hash do último login por técnico + data (validade 7 dias) | `%ProgramData%\ITC\Bench` | DPAPI | 03 |
| Sessão da API (token) | Memória; persistência a decidir | DPAPI se persistida | 03 |
| Estado da Preparação completa (etapas, retomada após reinício) | `%ProgramData%\ITC\Bench` | ACL de admin | migração do Master |
| Log rotativo | `%ProgramData%\ITC\Bench\logs` | ACL de admin | 01 |
| Preferências de UI (sem senha) | `%LOCALAPPDATA%\ITC\Bench` | — | 01 |
| Token da carreta (`itcta_`) | `%ProgramData%\ITC\Bench` | DPAPI, escopo máquina | 05 |
| Sessões de diagnóstico | a definir no módulo de Diagnóstico | — | Diagnóstico |

Escopo DPAPI (usuário ou máquina): a definir no Módulo 04, considerando que vários técnicos usam
a mesma máquina e o app roda elevado.
