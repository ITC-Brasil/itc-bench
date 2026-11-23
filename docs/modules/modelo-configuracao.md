# Modelo de configuração (ADR-076)

Tela Sistema › Importar configurações: salva as marcações num `.itcbench` e carrega em outra
máquina, pelo arquivo ou pela pasta `%ProgramData%\ITC\Bench\modelos`.

Arquivos: `servicos/modelo.py`, `ui/modelo.py`, `nucleo/caminhos.modelos()`, ganchos
`marcacoes()`/`aplicar_modelo()` em `ui/preparacao.py`, `ui/identificacao.py`, `ui/wifi.py`,
`ui/programas.py` (Programas e Remover), `ui/politicas.py`, `ui/inicializacao.py`; `tests/test_modelo.py`.

## Verificação

| Cenário | Resultado |
|---|---|
| Salvar e ler devolve as mesmas marcações; arquivo sem senha | ok (teste) |
| Não-JSON, outro formato, versão nova, arquivo grande | recusados com motivo (teste) |
| Perfil com caractere estranho, turno fora da lista, sufixo inválido, itens de tipo errado | descartados (teste) |
| Seção ausente não mexe na tela | ok (teste) |
| Pasta: o mais novo vence; arquivo ruim é pulado; pasta inexistente | ok (teste) |
| Janela: aplicar e coletar devolvem o mesmo; perfil fora do cadastro vira aviso | ok (teste) |
| Remover: marca só o removível do modelo; removido na sessão entra no modelo | ok (teste) |
| Programas: marca pelo id do cadastro, pula o bloqueado; instalado na sessão entra no modelo; perfil da tela vai junto (ADR-077) | ok (teste) |
| Wi-Fi: perfil da tela vai junto e é reaplicado (ADR-079) | ok (teste) |
| Usar sempre: cópia na pasta vence as antigas; Parar de usar tira só as cópias; desmarcado não copia (ADR-078) | ok (teste) |
| Duas máquinas reais da mesma unidade | pendente: roteiro 10.31 |
