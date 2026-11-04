-- Bench diagnostics sent with the technician session (ADR-016, TA-ADR-028).
-- diagnosticos is rebuilt because token_id was NOT NULL: SQLite cannot drop a NOT NULL in
-- place. Ids, relatorios.diagnostico_id and every existing column are kept; nothing is renamed
-- or removed. carreta stays NOT NULL ('BANCADA' for the Bench). The runner wraps this file in
-- one transaction; foreign_keys is off on these connections, so the drop does not cascade.
CREATE TABLE diagnosticos_0006 (
    id INTEGER PRIMARY KEY,
    carreta TEXT NOT NULL,
    token_id INTEGER REFERENCES carretas_tokens (id),
    hostname TEXT NOT NULL,
    sessao_id TEXT NOT NULL,
    projeto TEXT,
    sub_perfil TEXT,
    versao_schema TEXT NOT NULL,
    dados TEXT NOT NULL,
    resumo TEXT NOT NULL,
    falha TEXT,
    recebido_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- GLPI login of the technician whose session sent it; NULL for a carreta.
    bench_usuario TEXT,
    bench_sessao_id INTEGER REFERENCES bench_sessoes (id),
    -- Code of the unit, checked against the active Unidades; NULL when unknown.
    unidade TEXT,
    envio_id TEXT UNIQUE,
    -- Set while the AI call runs; a resend within 120 s gets 409 em_processamento.
    processando_desde TEXT,
    CHECK (token_id IS NOT NULL OR bench_usuario IS NOT NULL)
);

INSERT INTO diagnosticos_0006 (id, carreta, token_id, hostname, sessao_id, projeto, sub_perfil,
    versao_schema, dados, resumo, falha, recebido_em)
SELECT id, carreta, token_id, hostname, sessao_id, projeto, sub_perfil,
    versao_schema, dados, resumo, falha, recebido_em
FROM diagnosticos;

DROP TABLE diagnosticos;
ALTER TABLE diagnosticos_0006 RENAME TO diagnosticos;
CREATE INDEX diagnosticos_hostname ON diagnosticos (hostname, id);
CREATE INDEX diagnosticos_carreta ON diagnosticos (carreta, recebido_em);

-- Fixed one-hour UTC window per technician, same upsert as tokens_uso (TA-ADR-021).
CREATE TABLE bench_relatorio_uso (
    usuario TEXT PRIMARY KEY,
    janela TEXT NOT NULL,
    contagem INTEGER NOT NULL
);
