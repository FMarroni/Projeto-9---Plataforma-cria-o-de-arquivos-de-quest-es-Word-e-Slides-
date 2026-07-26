"""Resolve `Questao.formulas` — as transcrições LaTeX estruturadas que a IA
devolveu para os marcadores `[FORMULA_NN]` inseridos por `pdf_extract.py`
(ver docstring daquele módulo para o porquê: a extração nativa de texto não
consegue reconstruir com confiança a estrutura 2D de frações/expoentes
empilhados de uma fórmula matemática).

Cadeia de fallback (nunca corrompe silenciosamente uma fórmula):
  1. `Formula` validada (id corresponde a um marcador real, confiança acima
     do limiar, `usar_recorte_original=False`, LaTeX sintaticamente válido e
     renderizável) -> substitui o marcador por `$$latex$$` (display) ou
     `$latex$` (inline), reaproveitando o mecanismo já existente
     (`formatting.tokenize_rich_text` / `latex_render.py`).
  2. LaTeX válido na sintaxe mas o matplotlib.mathtext rejeita -> tenta uma
     normalização sintática conservadora (nunca reordena/descarta símbolos,
     só ajusta variantes de comando) e tenta renderizar de novo.
  3. Qualquer falha de validação/confiança/renderização -> o marcador
     `[FORMULA_NN]` é deixado INTOCADO no enunciado. Isso não é um caminho de
     erro: `[FORMULA_NN]` resolve automaticamente, pelo mesmo mecanismo de
     `[IMAGEM_NN]`, como o recorte fiel da página original (bytes já em
     `imagens[formula_id]`, gerado por `pdf_extract.py`) — uma imagem nunca
     está "errada" da forma que uma transcrição de texto pode estar.

Nunca lança exceção: uma fórmula problemática apenas não é substituída."""

import logging
import re

from app.latex_render import renderizar_formula
from app.schemas import Formula, Questao

logger = logging.getLogger(__name__)

# Abaixo deste limiar, a própria IA não está confiante o bastante — mesmo que
# o LaTeX seja sintaticamente válido e renderize sem erro, preferimos o
# recorte fiel a arriscar uma transcrição "quase certa" (mesmo espírito da
# regra de cruzamento de gabarito em prompts.py: prefira null a arriscar).
LIMIAR_CONFIANCA_FORMULA = 0.75

_PADRAO_MARCADOR_FORMULA = re.compile(r"\[(FORMULA_\d+)\]")

# Comandos LaTeX que o matplotlib.mathtext não suporta e que indicam uma
# transcrição fora do subconjunto renderizável localmente (ambientes multi-
# linha, inclusão de arquivo) — rejeitados cedo, sem gastar uma tentativa de
# renderização que sabemos que vai falhar.
_COMANDOS_NAO_SUPORTADOS = ("\\begin{", "\\end{", "\\includegraphics")


def _chaves_balanceadas(latex: str) -> bool:
    saldo = 0
    for ch in latex:
        if ch == "{":
            saldo += 1
        elif ch == "}":
            saldo -= 1
            if saldo < 0:
                return False
    return saldo == 0


def normalizar_latex_seguro(latex: str) -> str:
    """Correções sintáticas conservadoras que NUNCA reordenam/descartam
    símbolos matemáticos — só trocam variantes de comando por equivalentes
    que o mathtext do matplotlib aceita (ex.: `\\dfrac` -> `\\frac`) ou
    removem modificadores puramente visuais sem efeito estrutural
    (`\\left`/`\\right`, espaçamentos finos)."""
    normalizado = latex.strip()
    for variante in (r"\dfrac", r"\tfrac"):
        normalizado = normalizado.replace(variante, r"\frac")
    normalizado = normalizado.replace(r"\left", "").replace(r"\right", "")
    for espaco in (r"\,", r"\;", r"\:", r"\!"):
        normalizado = normalizado.replace(espaco, " " if espaco != r"\!" else "")
    return normalizado


def validar_sintaxe_latex(latex: str) -> tuple[bool, str]:
    """Validações sintáticas rápidas antes de tentar renderizar — não
    substitui a renderização real (única prova definitiva de que o
    matplotlib.mathtext aceita a fórmula), mas descarta cedo os casos mais
    óbvios (vazio, chaves desbalanceadas, comando fora do subconjunto
    suportado)."""
    if not latex or not latex.strip():
        return False, "LaTeX vazio"
    if not _chaves_balanceadas(latex):
        return False, "chaves desbalanceadas"
    for comando in _COMANDOS_NAO_SUPORTADOS:
        if comando in latex:
            return False, f"comando não suportado localmente: {comando}"
    return True, ""


def _tenta_renderizar(latex: str) -> bool:
    try:
        renderizar_formula(latex)
        return True
    except Exception:
        return False


def _latex_renderizavel(latex: str) -> str | None:
    """Devolve o LaTeX pronto para uso (original ou normalizado) se algum dos
    dois renderiza com sucesso — None se nenhum renderiza."""
    if _tenta_renderizar(latex):
        return latex
    normalizado = normalizar_latex_seguro(latex)
    if normalizado != latex and _tenta_renderizar(normalizado):
        return normalizado
    return None


def _formula_aceitavel(formula: Formula, marcadores_presentes: set[str]) -> tuple[str | None, str]:
    """Devolve (latex_pronto_para_uso, motivo). `latex_pronto_para_uso` é
    None quando a fórmula deve ser rejeitada (o motivo explica por quê, só
    para log — nunca propagado ao usuário como erro)."""
    if formula.id not in marcadores_presentes:
        return None, f"id {formula.id!r} não corresponde a nenhum marcador [FORMULA_NN] presente no enunciado"
    if formula.usar_recorte_original:
        return None, "IA sinalizou usar_recorte_original=True"
    if formula.confidence < LIMIAR_CONFIANCA_FORMULA:
        return None, f"confiança {formula.confidence} abaixo do limiar {LIMIAR_CONFIANCA_FORMULA}"

    ok, motivo = validar_sintaxe_latex(formula.latex)
    if not ok:
        return None, motivo

    latex_pronto = _latex_renderizavel(formula.latex)
    if latex_pronto is None:
        return None, "falha ao renderizar (mesmo após normalização sintática segura)"
    return latex_pronto, ""


def resolver_formulas_questao(questao: Questao) -> Questao:
    """Substitui, no enunciado de `questao`, cada `[FORMULA_NN]` que tem uma
    entrada correspondente validada em `questao.formulas` por `$$latex$$`
    (display) ou `$latex$` (inline) — reaproveitando 100% o pipeline de
    imagem/tokenização já existente a partir daqui. Marcadores sem entrada
    correspondente (ou cuja entrada falhou a validação) são deixados
    intocados — resolvem automaticamente como o recorte fiel da imagem
    original (ver docstring do módulo). Não modifica `questao` in-place:
    devolve uma cópia (ou a mesma instância, se nada mudou)."""
    if not questao.formulas or "[FORMULA_" not in questao.enunciado:
        return questao

    marcadores_presentes = set(_PADRAO_MARCADOR_FORMULA.findall(questao.enunciado))

    novo_enunciado = questao.enunciado
    for formula in questao.formulas:
        latex_pronto, motivo = _formula_aceitavel(formula, marcadores_presentes)
        if latex_pronto is None:
            logger.info(
                "Questão %s: fórmula %r não aplicada (mantendo recorte de imagem original) — %s",
                questao.numero, formula.id, motivo,
            )
            continue

        substituto = f"$${latex_pronto}$$" if formula.display else f"${latex_pronto}$"
        novo_enunciado = novo_enunciado.replace(f"[{formula.id}]", substituto)

    if novo_enunciado == questao.enunciado:
        return questao
    return questao.model_copy(update={"enunciado": novo_enunciado})


def resolver_formulas(questoes: list[Questao]) -> list[Questao]:
    """Aplica `resolver_formulas_questao` a cada questão da lista."""
    return [resolver_formulas_questao(q) for q in questoes]
