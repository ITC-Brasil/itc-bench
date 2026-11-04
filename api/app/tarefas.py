"""Work that runs off the request path: NocoDB mirror and ntfy alerts (§6.6, §6.7).

Everything goes through app.state.em_segundo_plano, a daemon thread in production and a
direct call in the tests. None of it can change or delay the response.
"""

import logging
import threading

from app import db
from app.services import nocodb, ntfy

log = logging.getLogger("tecnico.tarefas")

TITULOS_IA = {
    "ia_cota": "OpenCode Go recusou por cota",
    "ia_autenticacao": "OpenCode Go recusou a chave",
}


def em_thread(funcao) -> None:
    def executar():
        try:
            funcao()
        except Exception:
            log.exception("tarefa em segundo plano falhou")

    threading.Thread(target=executar, daemon=True).start()


def transporte(app, nome):
    return app.state.transports.get(nome)


def espelhar(app) -> None:
    settings = app.state.settings
    app.state.em_segundo_plano(lambda: nocodb.espelhar_pendentes(settings, transporte(app, "nocodb")))


def token_revogado(app, carreta: str) -> None:
    settings = app.state.settings
    app.state.em_segundo_plano(
        lambda: ntfy.alertar(
            settings,
            f"token_revogado:{carreta}",
            f"Token revogado em uso ({carreta})",
            f"Chegou requisição com o token revogado da carreta {carreta}. A API recusou com 401. "
            "Se o pendrive foi perdido ou roubado, alguém está tentando usá-lo (docs/TOKENS.md, cenário 5).",
            transporte(app, "ntfy"),
        )
    )


def falha_ia(app, codigo: str) -> None:
    settings = app.state.settings

    def executar():
        if codigo in TITULOS_IA:
            ntfy.alertar(
                settings,
                f"ia:{codigo}",
                TITULOS_IA[codigo],
                f"O OpenCode Go respondeu {codigo}. Os pendrives estão usando o relatório determinístico.",
                transporte(app, "ntfy"),
            )
        conn = db.connect(settings.database_path)
        try:
            falhas = conn.execute(
                "SELECT count(*) FROM diagnosticos WHERE falha IS NOT NULL AND recebido_em >= datetime('now', '-1 hour')"
            ).fetchone()[0]
        finally:
            conn.close()
        if falhas >= settings.ntfy_failure_threshold_per_hour:
            ntfy.alertar(
                settings,
                "ia:taxa",
                "Falhas da IA acima do limiar",
                f"{falhas} diagnósticos sem relatório na última hora (limiar "
                f"{settings.ntfy_failure_threshold_per_hour}). Último código: {codigo}.",
                transporte(app, "ntfy"),
            )

    app.state.em_segundo_plano(executar)
