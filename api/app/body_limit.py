from starlette.responses import JSONResponse


class BodyLimit:
    """Refuse bodies over max_bytes before any route or dependency runs.

    Content-Length is checked up front; without it (chunked) the body is counted as it
    arrives. The body is buffered (at most max_bytes) and replayed to the app, so the
    size check always comes before the token check.
    """

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        length = dict(scope["headers"]).get(b"content-length")
        if length is not None:
            # bytes.isdigit is ASCII only: rejects "", "-1", "+1" and " 1".
            if not length.isdigit():
                await JSONResponse({"erro": "requisicao_invalida"}, 400)(scope, receive, send)
                return
            if int(length) > self.max_bytes:
                await JSONResponse({"erro": "corpo_grande"}, 413)(scope, receive, send)
                return

        body = bytearray()
        more = True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body += message.get("body", b"")
            if len(body) > self.max_bytes:
                await JSONResponse({"erro": "corpo_grande"}, 413)(scope, receive, send)
                return
            more = message.get("more_body", False)

        replayed = False

        async def replay():
            nonlocal replayed
            if replayed:
                return await receive()
            replayed = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)
