"""API falsa da atualização para o teste no runner (ADR-026). Só stdlib; nunca em produção.

    python -I api_falsa.py --porta 8443 --cert c.pem --chave k.pem --pasta <dir> --modo ok

<dir> tem manifesto.json, manifesto.sig e o instalador (setup.exe). Aceita qualquer sessão
(a do `--teste-atualizacao`). Modos de recusa: `hash` (serve bytes trocados), `redireciona`
(302 no arquivo para outro host). O modo é relido de <dir>/modo.txt a cada requisição, para o
teste trocar sem reiniciar o servidor.
"""

import argparse
import base64
import hashlib
import json
import re
import ssl
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ARGS = argparse.Namespace()


class Handler(BaseHTTPRequestHandler):
    def _enviar(self, status: int, corpo: bytes, tipo: str, extra: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(corpo)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self) -> None:  # noqa: N802 — nome do http.server
        pasta = Path(ARGS.pasta)
        modo = (pasta / "modo.txt").read_text("ascii").strip() if (pasta / "modo.txt").exists() else "ok"
        partes = urlsplit(self.path)
        cru = (pasta / "manifesto.json").read_bytes()
        if partes.path == "/v1/bench/versao":
            corpo = {
                "versao": json.loads(cru)["versao"],
                "manifesto": base64.b64encode(cru).decode(),
                "assinatura": base64.b64encode((pasta / "manifesto.sig").read_bytes()).decode(),
            }
            self._enviar(200, json.dumps(corpo).encode(), "application/json")
            return
        if partes.path == "/v1/bench/versao/arquivo":
            if modo == "redireciona":
                self._enviar(302, b"", "text/plain", {"Location": "https://outro.exemplo.invalid/setup.exe"})
                return
            dados = (pasta / "setup.exe").read_bytes()
            sha = parse_qs(partes.query).get("sha256", [""])[0]
            if sha != hashlib.sha256(dados).hexdigest() and modo != "hash":
                self._enviar(404, b'{"erro":"versao_indisponivel"}', "application/json")
                return
            if modo == "hash":
                dados = bytes(b ^ 0xFF for b in dados[:16]) + dados[16:]
            inicio = 0
            if m := re.match(r"bytes=(\d+)-", self.headers.get("Range", "")):
                inicio = int(m.group(1))
            if inicio:
                extra = {"Content-Range": f"bytes {inicio}-{len(dados) - 1}/{len(dados)}"}
                self._enviar(206, dados[inicio:], "application/octet-stream", extra)
            else:
                self._enviar(200, dados, "application/octet-stream")
            return
        self._enviar(404, b'{"erro":"nao_encontrado"}', "application/json")


def main() -> None:
    p = argparse.ArgumentParser()
    for nome in ("porta", "cert", "chave", "pasta"):
        p.add_argument(f"--{nome}", required=True)
    p.parse_args(namespace=ARGS)
    servidor = ThreadingHTTPServer(("127.0.0.1", int(ARGS.porta)), Handler)
    contexto = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    contexto.load_cert_chain(ARGS.cert, ARGS.chave)
    servidor.socket = contexto.wrap_socket(servidor.socket, server_side=True)
    servidor.serve_forever()


if __name__ == "__main__":
    main()
