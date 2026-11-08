FROM python:3.12.14-slim-trixie

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
# Lock com hash (TA-ADR-032): pacote com hash diferente do lock não instala.
RUN pip install --no-cache-dir --root-user-action=ignore --require-hashes -r requirements.txt

COPY app ./app

# /data is owned by the app user so a new named volume inherits that ownership.
RUN useradd --system --uid 10001 app && mkdir /data && chown app /data
USER app

CMD ["sh", "-c", "exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port \"$APP_PORT\""]
