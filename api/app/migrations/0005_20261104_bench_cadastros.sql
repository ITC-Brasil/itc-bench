-- Bench cadastros (ADR-014): who downloaded which version, one row per 200 (not per 304).
-- No cadastro value is stored; versao keeps only the first 12 characters of the HMAC.
-- Retention: 90 days, cleaned on each delivery.
CREATE TABLE bench_cadastros_entregas (
    id INTEGER PRIMARY KEY,
    sessao_id INTEGER NOT NULL,
    usuario TEXT NOT NULL,
    unidade TEXT,
    quando TEXT NOT NULL,
    versao TEXT NOT NULL
);

CREATE INDEX bench_cadastros_entregas_quando ON bench_cadastros_entregas (quando);
