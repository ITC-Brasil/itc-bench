import sqlite3

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import db

router = APIRouter()


@router.get("/v1/saude")
def saude(request: Request):
    # No version and no error detail: the endpoint is reachable through the tunnel.
    try:
        db.check(request.app.state.settings.database_path)
    except sqlite3.Error:
        return JSONResponse(status_code=503, content={"status": "erro"})
    return {"status": "ok"}
