-- Reenvio do espelho no NocoDB (Módulo 04): tentativas, último erro e quando espelhou.
ALTER TABLE relatorios ADD COLUMN espelho_tentativas INTEGER NOT NULL DEFAULT 0;
ALTER TABLE relatorios ADD COLUMN espelho_erro TEXT;
ALTER TABLE relatorios ADD COLUMN espelho_em TEXT;

CREATE INDEX relatorios_espelho_pendente ON relatorios (id) WHERE espelho_status = 'pendente';

-- Limitação de repetição dos alertas ntfy: uma linha por chave de alerta.
CREATE TABLE alertas (
    chave TEXT PRIMARY KEY,
    ultimo_envio TEXT NOT NULL,
    suprimidos INTEGER NOT NULL DEFAULT 0
);
