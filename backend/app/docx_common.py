"""Helpers de localização de marcador, compartilhados por docx_lista.py e
docx_comentada.py."""

from docx import Document
from docx.shared import RGBColor

# Cor de destaque da identidade visual (Estratégia Concursos), extraída dos
# exemplos em Templates_padrão/*.docx — mesmo valor usado em
# scripts/build_templates.py para os títulos/labels do template.
COR_MARCA = RGBColor(0x42, 0x31, 0xA4)


def find_paragraph_with(doc: Document, token: str):
    for p in doc.paragraphs:
        if token in p.text:
            return p
    return None


def cabecalho_inline(questao) -> str:
    """Prefixo '(banca / orgao - ano)' para abrir a linha do enunciado,
    substituindo o antigo parágrafo separado 'Questão N — Matéria/Assunto'.
    Trata nulos: sem orgao -> '(banca - ano)'; sem ano -> omite o ano."""
    texto = f"{questao.banca} / {questao.orgao}" if questao.orgao else questao.banca
    if questao.ano:
        texto = f"{texto} - {questao.ano}"
    return f"({texto})"
