# Prompt de análise — entrada de um novo usuário ou agente

Cole o bloco abaixo como primeira mensagem de uma conversa nova no ITC Bench. Ele não traz estado
do trabalho: o agente descobre pelo `docs/PROGRESS.md` e pelo `git`, e o texto continua valendo
depois que o ESTADO ATUAL mudar.

```text
Você vai trabalhar no ITC Bench (repositório itc-bench), app Windows do Grupo ITC Brasil para a
bancada do técnico (app/ em Python 3.13 + PySide6; api/ em FastAPI + SQLite). Antes de alterar
qualquer coisa, faça uma análise e me mostre o resultado.

1. Leia, nesta ordem:
   - AGENTS.md (regras invioláveis, stack, modo de execução, gate de módulo, commits);
   - .conversa/para-agent.md, se existir;
   - docs/PROGRESS.md, bloco ESTADO ATUAL e as últimas linhas do Registro;
   - docs/IMPLEMENTATION-PLAN.md;
   - docs/DECISIONS.md (do ADR-001 em diante; os mais recentes são os que mais importam);
   - docs/UI-UX-BRIEF.md e docs/design/README.md;
   - docs/modules/ (o mais recente primeiro);
   - docs/testes/maquina-real.md;
   - docs/security/AUDIT-PROMPT.md.

2. Confira o estado real, sem confiar só nos documentos:
   - git status --short, git branch -a e git log --oneline -10;
   - o código das áreas citadas no ESTADO ATUAL (app/src/itc_bench/ui/, servicos/, recursos/);
   - rode da pasta app/ (se o uv não estiver no PATH, use .venv\Scripts\):
     ruff check ., ruff format --check ., mypy e pytest -q.
   Duas falhas são conhecidas e vêm do ambiente local, não do código:
   test_papel_de_parede::test_trecho_aparencia_recusa_valor_e_caminho_fora (exige elevação) e
   test_paridade::test_gravacoes_anonimas (nome da conta do Windows num arquivo de teste).

3. Responda em português, curto, com:
   - o que o projeto é, em 3 linhas;
   - branch atual, último commit e o que está sem commit;
   - o que o ESTADO ATUAL diz que está pela metade e o próximo passo;
   - o resultado do lint, do mypy e dos testes;
   - qualquer divergência entre os documentos e o código.
   Não altere nada nesta primeira resposta.

Como eu trabalho (siga sempre):
- Português do Brasil nas respostas, documentos e telas; código, caminhos e commits em inglês.
- Não faça commit, push nem PR sem eu pedir. Quando eu liberar: git add arquivo por arquivo,
  nunca git add -A, mensagem tipo(escopo): descrição, PR para a develop. Merge é só comigo.
- Não mude a versão nem crie tag sem eu pedir.
- Decisão com consequência de produto: pergunte antes e registre como ADR em
  docs/DECISIONS.md (o próximo número livre depois do último).
- Mudança visual: mantenha a identidade de docs/design/ (cores, fontes, barra lateral, botão
  primário). Cor nova entra na Paleta de ui/tema.py, nos modos claro e escuro, nunca direto
  numa tela. Mostre o resultado com uma captura da tela (QWidget.grab() num script fora do
  repositório).
- Texto de tela é sempre puro (QLabel PlainText, ui/texto.py), nunca HTML.
- Regra de segurança vale em duas camadas, no Python e de novo no trecho PowerShell
  (recursos/*.ps1); dados só por ITC_*, sem shell=True.
- Log sem senha, token, SSID, host, SID, nome de conta ou caminho de perfil.
- Toda mudança ganha teste. Ao terminar uma entrega, siga o padrão das entregas pós-16:
  documento em docs/modules/, auditoria em docs/security/AAAA-MM-DD-<nome>.md com o
  AUDIT-PROMPT, linha no Registro e ESTADO ATUAL atualizados em docs/PROGRESS.md, passo novo no
  roteiro docs/testes/maquina-real.md quando precisar de máquina real.
- Antes de encerrar ou ao ficar sem contexto: reescreva o ESTADO ATUAL de docs/PROGRESS.md
  (branch, o que está sem commit, o que está pela metade, o próximo passo concreto).
- Nada de segredo no repositório nem nos documentos: endereço de servidor, chave, senha ou SSID
  real.
```
