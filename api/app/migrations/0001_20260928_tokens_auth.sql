-- Tokens das carretas (ADR-007): só o hash SHA-256 fica no banco.
CREATE TABLE carretas_tokens (
    id INTEGER PRIMARY KEY,
    carreta TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    descricao TEXT NOT NULL DEFAULT '',
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    criado_por TEXT NOT NULL,
    ultimo_uso TEXT,
    revogado_em TEXT,
    revogado_por TEXT,
    motivo TEXT,
    ativo INTEGER NOT NULL DEFAULT 1 CHECK (ativo IN (0, 1))
);

-- Um token ativo por carreta, garantido pelo banco.
CREATE UNIQUE INDEX carretas_tokens_um_ativo ON carretas_tokens (carreta) WHERE ativo = 1;

-- Toda operação da CLI, inclusive as recusadas. Nunca guarda token nem hash.
CREATE TABLE tokens_auditoria (
    id INTEGER PRIMARY KEY,
    em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    operacao TEXT NOT NULL,
    operador TEXT NOT NULL,
    carreta TEXT,
    token_id INTEGER REFERENCES carretas_tokens (id),
    resultado TEXT NOT NULL CHECK (resultado IN ('ok', 'recusado', 'falha')),
    detalhe TEXT
);

-- Append-only: a auditoria não se corrige, só recebe linhas novas.
CREATE TRIGGER tokens_auditoria_sem_update BEFORE UPDATE ON tokens_auditoria
BEGIN
    SELECT RAISE(ABORT, 'tokens_auditoria is append-only');
END;

CREATE TRIGGER tokens_auditoria_sem_delete BEFORE DELETE ON tokens_auditoria
BEGIN
    SELECT RAISE(ABORT, 'tokens_auditoria is append-only');
END;

-- Contagem de requisições por token em janela fixa de uma hora UTC (ADR-021).
-- Uma linha por token: a janela nova sobrescreve a anterior.
CREATE TABLE tokens_uso (
    token_id INTEGER PRIMARY KEY REFERENCES carretas_tokens (id),
    janela TEXT NOT NULL,
    contagem INTEGER NOT NULL
);
