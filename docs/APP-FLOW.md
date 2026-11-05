# APP-FLOW — ITC Bench

Fluxo de telas conforme `docs/design/itc-bench-identidade-telas.html`. Implementação: planejada
a partir do Módulo 01 (navegação) e 04 (Entrar).

## Abertura

```
Atalho → UAC (admin do Windows) → Entrar
  ├─ online:  usuário/senha GLPI → API valida → sessão → baixa cadastros (Módulo 05) → Início
  ├─ offline: técnico logou nesta máquina há ≤ 7 dias → hash DPAPI confere → Início (cadastros do cache)
  └─ falha:   mensagem; limite de tentativas aplicado pela API
Parado 15 min → volta para Entrar
```

Rodapé da tela Entrar: hostname, unidade, versão do Windows, versão do Bench, estado da API.

## Navegação (ADR-004)

Barra lateral fixa com 7 grupos, na ordem de trabalho no notebook:

| Grupo | Itens |
|---|---|
| Início | Início · Preparação completa |
| Preparar | Identificação · Contas · Wi-Fi · Acesso remoto |
| Software | Programas · Remover programas |
| Segurança | Políticas · Proteção do login · USB |
| Aparência e periféricos | Tela e papel de parede · Mouse e teclado · Energia |
| Diagnóstico | Coleta e laudo · Histórico · Limpeza |
| Sistema | Registro · Ajuda · Configurações |

Selos na barra: progresso da preparação (ex.: `6/9`) e contagem de alertas críticos.

## Fluxos principais

**Início** — estado da máquina (modelo, série, Windows, unidade, disco, bateria), etapas da
preparação (feito / pendente / não iniciado), último diagnóstico, alertas com atalho para a tela
que resolve, atalhos (forçar inventário GLPI, limpar temporários).

**Preparação completa** — escolhe perfil (ex.: Sala de aula), lista etapas, "Rodar N etapas",
"Pausar". Log ao vivo. Se uma etapa pede reinício, agenda retomada e continua depois do boot.

**Tela de cadastro (Wi-Fi como modelo)** — abas filtro (esta unidade / todas / instaladas no
Windows), tabela com situação no Windows (igual, senha antiga, ausente), ações "Testar conexão",
"Instalar N redes". Dados vêm do cache dos cadastros.

**Acesso remoto** — mostra servidor, tag, instalador, SHA-256 conferido e o comando antes de
instalar. Se um campo obrigatório estiver vazio em Configurações › Servidores, a instalação não
começa e diz qual falta. Senha permanente nunca exibida.

**Diagnóstico** — "Nova coleta" roda os coletores, mostra resultado por área, envia à API e exibe
o laudo da IA com aviso "revise antes de abrir chamado". Histórico da máquina ao lado
(`GET /v1/historico/{hostname}` já existe na API).

**Ajuda (ADR-007)** — "?" ao lado do título de cada tela abre painel lateral com as instruções;
"Ver toda a ajuda" leva à tela Ajuda, com índice na ordem do menu e busca.

## Ações destrutivas

Confirmação com resumo antes de executar; para exclusão de conta, digitar o nome. Regras do
ADR-017 (herdadas de `backend/contas.py`): não mexer no Administrador nativo nem em conta
Microsoft/domínio; a conta Suporte só muda por "Aplicar conta Suporte"; a conta logada não é
rebaixada, excluída nem tem a senha trocada (exceto em "Remover administrador de todos", que a
rebaixa); não rebaixar nem excluir o último administrador ativo; não excluir conta com sessão
aberta.
