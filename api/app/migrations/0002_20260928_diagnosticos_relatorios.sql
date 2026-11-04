-- Sessão recebida de uma carreta, já normalizada para o contrato atual (ADR-018).
-- Uma linha por POST /v1/relatorio aceito, inclusive quando a IA falha depois.
CREATE TABLE diagnosticos (
    id INTEGER PRIMARY KEY,
    carreta TEXT NOT NULL,
    token_id INTEGER NOT NULL REFERENCES carretas_tokens (id),
    hostname TEXT NOT NULL,
    sessao_id TEXT NOT NULL,
    projeto TEXT,
    sub_perfil TEXT,
    versao_schema TEXT NOT NULL,
    dados TEXT NOT NULL,
    resumo TEXT NOT NULL,
    -- Código interno quando a IA falhou (ia_timeout, ia_cota...); NULL com relatório gerado.
    falha TEXT,
    recebido_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX diagnosticos_hostname ON diagnosticos (hostname, id);
CREATE INDEX diagnosticos_carreta ON diagnosticos (carreta, recebido_em);

-- Relatório gerado pela IA. Sem linha aqui, o diagnóstico ficou sem relatório.
CREATE TABLE relatorios (
    id INTEGER PRIMARY KEY,
    diagnostico_id INTEGER NOT NULL UNIQUE REFERENCES diagnosticos (id),
    modelo TEXT NOT NULL,
    tokens_entrada INTEGER,
    tokens_saida INTEGER,
    duracao_ms INTEGER NOT NULL,
    maior_confianca TEXT CHECK (maior_confianca IN ('ALTA', 'MÉDIA', 'BAIXA')),
    relatorio_md TEXT NOT NULL,
    chamado_titulo TEXT NOT NULL,
    chamado_descricao TEXT NOT NULL,
    -- Espelho no NocoDB (ADR-005), tratado no Módulo 04.
    espelho_status TEXT NOT NULL DEFAULT 'pendente' CHECK (espelho_status IN ('pendente', 'ok', 'desligado')),
    gerado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
