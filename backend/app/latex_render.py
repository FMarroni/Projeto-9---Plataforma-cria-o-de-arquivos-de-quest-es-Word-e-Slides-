"""V3: renderiza blocos de matemática `$$...$$` (display) como imagem local
via `matplotlib.mathtext` — em vez da conversão LaTeX->Unicode em linha usada
para `$...$` (formatting.tokenize_formula_unicode), que fica visualmente
confusa/desestruturada para estruturas 2D (frações aninhadas, integrais com
limites, somatórios). Reaproveita 100% o pipeline de injeção de imagem já
existente (Épico 1): uma equação renderizada vira só mais uma entrada no dict
`imagens`, indistinguível de uma imagem extraída do PDF para o resto do
código (docx_render.py / pptx_gen.py não precisam saber que isto existe).

Só cobre o subconjunto de LaTeX que o mathtext do matplotlib entende (sem
`\\begin{matrix}`/`\\begin{array}`, sem múltiplas linhas) — quando a
renderização falha, cai de volta para `tokenize_formula_unicode` (mesma
substituição por dicionário usada em `$...$`), nunca quebra a geração.

Fórmulas transcritas estruturadamente pela IA a partir de um recorte de
página (marcador `[FORMULA_NN]`, ver `pdf_extract.py`) passam primeiro pela
validação/cadeia de fallback de `app.formula_resolve` (que já tenta renderizar
aqui, entre outras checagens, ANTES de decidir se usa o LaTeX ou o recorte
original) — `resolver_tokens_equacao` abaixo continua sendo o ponto único de
resolução `$$...$$` -> imagem para os dois casos (fórmula digitada
manualmente pelo usuário em qualquer texto do sistema, ou já validada por
`formula_resolve`), sem duplicar a lógica de renderização."""

import hashlib
import io
import logging
from functools import lru_cache

import matplotlib

matplotlib.use("Agg")  # backend headless — sem isso, importar pyplot pode tentar abrir uma janela
import matplotlib.pyplot as plt

from app.formatting import Token, tokenize_formula_unicode

logger = logging.getLogger(__name__)

matplotlib.rcParams["mathtext.fontset"] = "cm"  # visual clássico de LaTeX (Computer Modern)

FONTSIZE = 26
DPI = 200


@lru_cache(maxsize=256)
def renderizar_formula(formula: str) -> bytes:
    """Renderiza `formula` (sem os `$$` delimitadores) como PNG transparente,
    recortado ao tamanho do texto. Cacheado por processo — a mesma fórmula
    repetida no documento (comum em provas) só é renderizada uma vez."""
    fig = plt.figure(figsize=(0.1, 0.1))
    fig.text(0, 0, f"${formula}$", fontsize=FONTSIZE, color="black")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, transparent=True, bbox_inches="tight", pad_inches=0.06)
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def _id_para_formula(formula: str) -> str:
    return "EQUACAO_" + hashlib.sha1(formula.encode("utf-8")).hexdigest()[:10]


def resolver_tokens_equacao(tokens: list[Token], imagens: dict[str, bytes]) -> list[Token]:
    """Devolve uma nova lista de tokens onde cada Token `is_equation` foi
    substituído por um Token `is_image` comum (a imagem renderizada é
    inserida em `imagens`, mutado in place). Se a renderização falhar para
    uma fórmula específica, cai de volta para `tokenize_formula_unicode`
    (substituição Unicode em linha) em vez de propagar o erro."""
    resultado: list[Token] = []
    for token in tokens:
        if not token.is_equation:
            resultado.append(token)
            continue

        formula = token.latex_formula or ""
        try:
            image_id = _id_para_formula(formula)
            if image_id not in imagens:
                imagens[image_id] = renderizar_formula(formula)
            resultado.append(Token(text="", is_image=True, image_id=image_id))
        except Exception:
            logger.warning(
                "Falha ao renderizar equação LaTeX %r como imagem — usando substituição Unicode em linha.",
                formula,
                exc_info=True,
            )
            resultado.extend(tokenize_formula_unicode(formula))

    return resultado
