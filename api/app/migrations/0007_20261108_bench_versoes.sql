-- Bench versions for the automatic update (ADR-026, TA-ADR-033). Written only by the CLI
-- app.bench_versao; the route serves the newest row not revoked. manifesto and assinatura are
-- the exact bytes signed by the owner (base64), checked by the Bench, never by the API.
CREATE TABLE bench_versoes (
    versao TEXT PRIMARY KEY,
    -- (major, minor, patch) as one sortable integer: major * 1e6 + minor * 1e3 + patch.
    ordem INTEGER NOT NULL UNIQUE,
    minima TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    tamanho INTEGER NOT NULL,
    notas TEXT NOT NULL,
    manifesto TEXT NOT NULL,
    assinatura TEXT NOT NULL,
    publicado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    publicado_por TEXT NOT NULL,
    revogado_em TEXT,
    revogado_por TEXT
);

-- Fixed one-hour UTC window per technician and kind: consulta, download (from byte 0) and
-- retomada (Range from byte > 0), same upsert as bench_relatorio_uso.
CREATE TABLE bench_versao_uso (
    usuario TEXT NOT NULL,
    tipo TEXT NOT NULL,
    janela TEXT NOT NULL,
    contagem INTEGER NOT NULL,
    PRIMARY KEY (usuario, tipo)
);
