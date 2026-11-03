# Módulo 05 — CI/CD

**Branch:** `module/05-ci-cd` (a partir da `module/04-nocodb-ntfy`) · **Data:** 2026-09-28 ·
**Escopo:** `PROMPT_CLAUDE_CODE.md` §12, §15 (Módulo 05) e §16

Cria o pipeline que compensa a falta de branch protection e de secret scanning no GitHub
Free (TA-ADR-012): testes e gitleaks em todo PR e push na `develop`/`main`, e deploy por SSH
no glpi-srv só depois dos testes verdes. Nenhum código da API nem do pendrive mudou.

## O que foi implementado

| Arquivo | Conteúdo |
|---|---|
| `.github/workflows/ci.yml` | Gatilhos `pull_request`, `push` em `develop`/`main` e `workflow_call`. Job `test`: `actions/checkout` e o pytest oficial do `CLAUDE.md` dentro de `python:3.12.14-slim-trixie`; passo que compara `pendrive/config/eventlog-conhecidos.json` e `api/app/eventlog-conhecidos.json` como JSON (TA-ADR-022). Job `gitleaks`: checkout com `fetch-depth: 0`, download do `gitleaks_8.30.1_linux_x64.tar.gz` da release oficial com `sha256sum -c` e `gitleaks git . --redact --verbose --exit-code 1` |
| `.github/workflows/deploy.yml` | Gatilhos `push` na `main` com `paths: ["api/**"]` e `workflow_dispatch`. Job `test` = `uses: ./.github/workflows/ci.yml`; job `deploy` com `needs: test`, `if: github.ref == 'refs/heads/main'`, `concurrency: deploy-glpi-srv` sem cancelamento. SSH com a chave e o `known_hosts` vindos de secrets, script remoto por heredoc (ver `docs/DEPLOY.md`) |
| `.github/dependabot.yml` | `pip` em `/api` e `github-actions` em `/`, semanal, PRs para a `develop`, prefixos `chore`/`ci` |
| `docs/DEPLOY.md` | Pipeline, servidor, secrets, rollback e verificação pós-deploy (§16) |

### Versões e SHAs

| Item | Valor | Como foi conferido |
|---|---|---|
| `actions/checkout` | `3d3c42e5aac5ba805825da76410c181273ba90b1` (`v7.0.1`, 2026-07-20) | `gh api repos/actions/checkout/releases/latest` e `gh api repos/actions/checkout/git/ref/tags/v7.0.1` → objeto `commit` com esse SHA |
| gitleaks | `8.30.1` (2026-03-21), tarball `linux_x64` com SHA-256 `551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb` | `gh release download v8.30.1 -R gitleaks/gitleaks`: a linha do `gitleaks_8.30.1_checksums.txt` e o `sha256sum` do tarball baixado são iguais |
| Runner | `ubuntu-24.04` | Fixo, em vez de `ubuntu-latest` |
| Imagem dos testes | `python:3.12.14-slim-trixie` | A mesma tag do `api/Dockerfile` e do `CLAUDE.md` |

### Escolhas feitas no caminho

- **Sem `setup-python`.** Os testes rodam na mesma imagem do `Dockerfile` pelo mesmo
  comando do `CLAUDE.md`: o CI e a máquina de desenvolvimento executam a mesma coisa, e
  há uma action a menos para fixar.
- **Sem action de SSH.** O `ssh` do runner resolve, e a chave do servidor fica fixada
  pelo `DEPLOY_KNOWN_HOSTS`, com `StrictHostKeyChecking=yes`.
- **gitleaks pelo binário.** A `gitleaks-action` v2 exige `GITLEAKS_LICENSE` em
  repositório de organização. O binário é conferido por SHA-256 fixado no workflow.
- **Deploy reusa o `ci.yml`** por `workflow_call`, em vez de repetir os passos. Um push
  na `main` roda o `ci.yml` duas vezes (pelo próprio `push` e pelo deploy); é aceito.
- **O deploy confere o commit.** Depois do `git pull`, o script compara `HEAD` com o
  `GITHUB_SHA` testado e para se forem diferentes. Um run atrasado não publica código que
  ele não testou; o run do commit mais novo faz o deploy.
- **Sem `environment:`.** Environments em repositório privado exigem plano pago; os
  secrets ficam no nível do repositório.
- **Sem job do pendrive.** O `Testar-Ferramenta.ps1` precisa de runner Windows, que custa
  o dobro de minutos no plano gratuito. Fica como pendência, não como parte deste módulo.

## Verificação realizada

| Cenário | Como foi verificado | Resultado |
|---|---|---|
| YAML e scripts | Os três arquivos lidos com `yaml.safe_load` e cada `run:` passado a `bash -n`, na imagem `python:3.12.14-slim-trixie` | ✅ gatilhos e jobs como na tabela; `bash -n` 0 em todos os 7 passos |
| gitleaks no histórico atual | Binário 8.30.1 conferido, `gitleaks git <repo> --redact --exit-code 1`, local | ✅ 59 commits, `no leaks found`, saída 0 |
| Comparação das bases | O comando do passo, local | ✅ saída 0 com os arquivos atuais |
| Script remoto: commit certo | Simulação num container: clone de um repositório bare no caminho real, `docker` e `sleep` substituídos, `curl` que só responde na 3ª tentativa | ✅ `git pull --ff-only`, `docker compose up -d --build`, `healthy after 3 attempt(s)`, saída 0 |
| Script remoto: `main` andou | Mesma simulação, com um commit a mais na origem | ✅ `main is at ..., this run tested ...: stopping`, saída 1, sem `docker compose` |
| Script remoto: sem saúde | `curl` sempre com erro | ✅ `no 200 from /v1/saude in 60 s`, `ps` e `logs`, saída 1 |
| CI no GitHub | PR ITC-Brasil/tecnico-assistente#7, run `36487430328` (`pull_request`, commit `f1d51d0`) | ✅ job `test`: `142 passed, 1 warning`, comparação das bases ok (25 s); job `gitleaks`: `gitleaks_8.30.1_linux_x64.tar.gz: OK`, 62 commits, `no leaks found` (6 s) |
| Deploy real | — | **Não executado** — depende do servidor, dos secrets e do merge na `main` (Módulo 06) |
| Dependabot | — | **Não executado** — só abre PRs depois que o arquivo estiver na branch padrão (`develop`) |

## Decisões

Nenhum ADR novo. As escolhas acima seguem o TA-ADR-012 e não têm alternativa com
consequência real além do que está registrado.

## Dependências entre módulos

- **Módulo 06:** criar o usuário `<usuário de deploy>`, o clone por PAT, o `.env`, os seis
  secrets e o `known_hosts`; o primeiro deploy é o merge `develop` → `main`.
- **Módulo 07:** mudanças só em `pendrive/` não disparam o deploy (`paths: api/**`), mas
  passam pelo CI.

## Pontos de atenção

- **A base de Event Log agora quebra o CI** se as duas cópias divergirem (TA-ADR-022).
- **O gitleaks varre todo o histórico** em cada run. Um falso positivo antigo exige um
  `.gitleaksignore` com a impressão digital do achado, nunca reescrever o histórico.
- **Atualizar o gitleaks** exige trocar `GITLEAKS_VERSION` e `GITLEAKS_SHA256` juntos, com
  o SHA-256 lido do `checksums.txt` da release. O Dependabot não cuida disso.
- **Um push na `main` sem mudança em `api/**`** (só docs ou pendrive) roda o `ci.yml`, mas
  não faz deploy. `workflow_dispatch` força o deploy do commit atual da `main`.
- **Transitivas fixadas com `==` geram PRs do Dependabot que não resolvem.** O
  `api/requirements.txt` fixa diretas e transitivas, e o Dependabot abre um PR por pacote.
  Em 2026-09-28, o ITC-Brasil/tecnico-assistente#10 subiu só o `pydantic_core` para
  2.49.0, e o `pip install` do CI falhou com `ResolutionImpossible`, porque o
  `pydantic==2.13.5` exige uma versão exata do `pydantic_core`. O CI barrou corretamente.
  O grupo `pydantic` (#11) não resolveu: o #12 saiu pelo grupo, mas de novo só com o core. A correção foi estrutural
  (TA-ADR-025): `api/requirements.in` com as 5 diretas e o `requirements.txt` gerado por
  `pip-compile`. O Dependabot passa a atualizar o `.in` e recompilar o lock, e o grupo
  saiu do `.github/dependabot.yml`. Nenhum lock é editado à mão; o comando está no
  `CLAUDE.md`.

## Commits

```
8c96ed5 ci: add pytest, event base check and gitleaks workflow
396f5c6 ci: add SSH deploy to glpi-srv with pinned host key and health check
f1d51d0 ci: add dependabot for pip and github actions
```

O commit `docs: document module 05 ci cd` fecha a lista.
