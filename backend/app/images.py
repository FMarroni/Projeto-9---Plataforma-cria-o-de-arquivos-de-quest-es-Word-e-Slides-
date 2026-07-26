"""Helpers para preparar imagens extraídas do PDF (`pdf_extract.py`) para envio
multimodal aos LLMs: detecção de mime type e redimensionamento defensivo de
imagens excepcionalmente grandes (sem limite de quantidade — apenas de
dimensão por imagem)."""

import base64

import fitz

MAX_DIMENSAO_PX = 1600


def detectar_mime(dados: bytes) -> str:
    if dados[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if dados[:2] == b"\xff\xd8":
        return "image/jpeg"
    if dados[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def redimensionar_se_necessario(dados: bytes) -> bytes:
    """Reamostra a imagem se qualquer dimensão exceder MAX_DIMENSAO_PX. Em caso
    de qualquer erro de decodificação, devolve os bytes originais inalterados
    (melhor enviar a imagem original do que falhar a requisição inteira)."""
    try:
        pix = fitz.Pixmap(dados)
        maior_lado = max(pix.width, pix.height)
        if maior_lado <= MAX_DIMENSAO_PX:
            return dados
        fator = MAX_DIMENSAO_PX / maior_lado
        pix_redimensionado = fitz.Pixmap(pix, pix.width * fator, pix.height * fator)
        return pix_redimensionado.tobytes("png")
    except Exception:
        return dados


def para_base64(dados: bytes) -> str:
    return base64.b64encode(dados).decode("ascii")


def preparar_para_envio(dados: bytes) -> tuple[str, str]:
    """Devolve (mime_type, base64) prontos para uso nos content blocks multimodais."""
    dados_prontos = redimensionar_se_necessario(dados)
    mime = detectar_mime(dados_prontos)
    return mime, para_base64(dados_prontos)
