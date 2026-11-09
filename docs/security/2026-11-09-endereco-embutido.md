# Auditoria de segurança — Endereço da API embutido no instalador de release — 2026-11-09

Escopo: ADR-027. `instalador/itc-bench.iss` (padrão `ApiUrlPadrao`), `instalador/endereco-padrao.ps1`,
`instalador/testar-endereco.ps1` e `app-build.yml` (environment `release`, passo do instalador de
release). Branch `feat/instalador-endereco-embutido`. Sem mudança no app nem na API.

## Resumo

| Severidade | Quantidade |
|---|---|
| Crítica | 0 |
| Alta | 0 |
| Média | 0 |
| Baixa | 0 |
| Informativa | 3 (decisão do responsável e limites, no ADR-027) |

## O que muda

### [INFORMATIVA, decisão do responsável] Endereço legível no instalador de release

O endereço fica no script compilado do Inno, dentro do `setup.exe` de release. Quem tiver o arquivo
consegue lê-lo. O ADR-008 já previa que só o endereço vai no instalador, e ele não é credencial:
o acesso continua exigindo o login do técnico e o Cloudflare Access. O instalador de release é
tratado como interno (`docs/BUILD.md`).

### [INFORMATIVA] Instalador adulterado

Trocar o endereço embutido exige alterar o `setup.exe`, o que muda o hash: o `SHA256SUMS` da Release
continua cobrindo. Sem assinatura de código (ADR-025), conferir o hash antes de instalar segue
sendo o controle.

### [INFORMATIVA] Para onde vai o login do técnico

Sem `/APIURL` e sem valor gravado, o login vai para o endereço embutido. A validação
(`https://`, host, sem credencial, query, fragmento e aspas) roda no CI antes do ISCC e de novo no
`.iss`; o app valida ao abrir (`validar()`).

## Segredo no CI

- `BENCH_API_URL` só no environment `release`, que só o build de tag usa. PR e push não têm acesso.
- O GitHub mascara o segredo no log. Nenhum passo imprime o valor, o tamanho ou parte dele; a
  mensagem de erro do `endereco-padrao.ps1` é fixa.
- O pacote (`dist`) nunca recebe o endereço: `varrer.py` e gitleaks rodam sobre ele sem exceção
  nova. O instalador de release é recompilado depois dos testes e da varredura.
- Testes só com endereços `.invalid`; as variantes de teste nunca são enviadas como artefato.
- `git log -p develop..HEAD`: sem endereço real.
