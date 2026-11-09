"""Assinatura do manifesto da atualização (ADR-026): ECDSA P-256 com SHA-256 pela CNG.

Sem dependência nova nem cripto escrita à mão: `BCryptVerifySignature` da `bcrypt.dll`. A
assinatura é IEEE P1363 (`r || s`, 64 bytes), o formato da CNG e do `ECDsa.SignData` do .NET;
DER é recusado pelo tamanho. A chave pública é um SubjectPublicKeyInfo DER de P-256 em base64
(o que `ExportSubjectPublicKeyInfo` gera), conferido byte a byte no prefixo.
"""

import base64
import ctypes
import hashlib
from ctypes import wintypes

from itc_bench.nucleo.log import log

# SEQUENCE { SEQUENCE { id-ecPublicKey, prime256v1 }, BIT STRING 0x00 0x04 }: 27 bytes fixos.
PREFIXO_SPKI = bytes.fromhex("3059301306072a8648ce3d020106082a8648ce3d03010703420004")
TAMANHO_SPKI = len(PREFIXO_SPKI) + 64
TAMANHO_ASSINATURA = 64
_MAGIC_ECS1 = 0x31534345  # BCRYPT_ECDSA_PUBLIC_P256_MAGIC
_STATUS_INVALID_SIGNATURE = 0xC000A000


class ChaveInvalida(ValueError):
    """Arquivo de chave pública fora do formato SPKI P-256."""


def chave_de_texto(texto: str) -> bytes:
    """`X || Y` (64 bytes) do SPKI em base64; levanta `ChaveInvalida`."""
    try:
        der = base64.b64decode("".join(texto.split()), validate=True)
    except ValueError as erro:
        raise ChaveInvalida("chave pública não é base64") from erro
    if len(der) != TAMANHO_SPKI or not der.startswith(PREFIXO_SPKI):
        raise ChaveInvalida("chave pública não é SPKI de P-256")
    return der[len(PREFIXO_SPKI) :]


def _bcrypt() -> ctypes.WinDLL:
    dll = ctypes.WinDLL("bcrypt")
    dll.BCryptOpenAlgorithmProvider.argtypes = (
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.ULONG,
    )
    dll.BCryptImportKeyPair.argtypes = (
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_char_p,
        wintypes.ULONG,
        wintypes.ULONG,
    )
    dll.BCryptVerifySignature.argtypes = (
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_char_p,
        wintypes.ULONG,
        ctypes.c_char_p,
        wintypes.ULONG,
        wintypes.ULONG,
    )
    dll.BCryptDestroyKey.argtypes = (ctypes.c_void_p,)
    dll.BCryptCloseAlgorithmProvider.argtypes = (ctypes.c_void_p, wintypes.ULONG)
    for nome in (
        "BCryptOpenAlgorithmProvider",
        "BCryptImportKeyPair",
        "BCryptVerifySignature",
        "BCryptDestroyKey",
        "BCryptCloseAlgorithmProvider",
    ):
        getattr(dll, nome).restype = ctypes.c_ulong
    return dll


def verificar(chave_xy: bytes, dados: bytes, assinatura: bytes) -> bool:
    """True só se `assinatura` (P1363) for de `dados` pela chave. Erro da CNG vira OSError."""
    if len(chave_xy) != 64 or len(assinatura) != TAMANHO_ASSINATURA:
        return False
    dll = _bcrypt()
    alg, chave = ctypes.c_void_p(), ctypes.c_void_p()
    status = dll.BCryptOpenAlgorithmProvider(ctypes.byref(alg), "ECDSA_P256", None, 0)
    if status:
        raise OSError(f"CNG: ECDSA_P256 indisponível (0x{status:08X})")
    try:
        blob = _MAGIC_ECS1.to_bytes(4, "little") + (32).to_bytes(4, "little") + chave_xy
        status = dll.BCryptImportKeyPair(
            alg, None, "ECCPUBLICBLOB", ctypes.byref(chave), blob, len(blob), 0
        )
        if status:
            raise OSError(f"CNG: chave pública recusada (0x{status:08X})")
        try:
            resumo = hashlib.sha256(dados).digest()
            status = dll.BCryptVerifySignature(
                chave, None, resumo, len(resumo), assinatura, len(assinatura), 0
            )
        finally:
            dll.BCryptDestroyKey(chave)
    finally:
        dll.BCryptCloseAlgorithmProvider(alg, 0)
    if status == 0:
        return True
    if status != _STATUS_INVALID_SIGNATURE:
        # Outros códigos (parâmetro inválido etc.) também são recusa; o motivo vai no log.
        log.warning("Atualização: CNG recusou a assinatura (0x%08X).", status)
    return False
