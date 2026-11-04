import os

# Widgets sem abrir janela (ADR-010).
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
