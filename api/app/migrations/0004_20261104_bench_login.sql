-- Bench login (ADR-013). No column holds a password; usuario is the GLPI login only when GLPI
-- recognized it, otherwise an HMAC of the typed value.
CREATE TABLE bench_sessoes (
    id INTEGER PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    usuario TEXT NOT NULL,
    nome TEXT NOT NULL,
    glpi_id INTEGER NOT NULL,
    maquina TEXT NOT NULL,
    ip TEXT NOT NULL,
    criada_em TEXT NOT NULL,
    expira_em TEXT NOT NULL,
    revogada_em TEXT,
    ultimo_uso TEXT
);

-- Fixed 15-minute window, one row per key (u:<hmac> or ip:<ip>), same upsert as tokens_uso.
CREATE TABLE bench_login_tentativas (
    chave TEXT PRIMARY KEY,
    janela TEXT NOT NULL,
    contagem INTEGER NOT NULL
);

CREATE TABLE bench_login_auditoria (
    id INTEGER PRIMARY KEY,
    quando TEXT NOT NULL,
    usuario TEXT,
    maquina TEXT,
    ip TEXT,
    resultado TEXT NOT NULL
);

CREATE INDEX bench_login_auditoria_quando ON bench_login_auditoria (quando);
