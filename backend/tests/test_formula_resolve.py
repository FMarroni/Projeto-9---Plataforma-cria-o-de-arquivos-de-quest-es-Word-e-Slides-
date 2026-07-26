from app.formula_resolve import (
    LIMIAR_CONFIANCA_FORMULA,
    normalizar_latex_seguro,
    resolver_formulas,
    resolver_formulas_questao,
    validar_sintaxe_latex,
)
from app.schemas import Alternativa, Formula, Questao

# LaTeX exato do bug relatado pelo usuário: G(t) = t³ - 23/2·t² + 55/4·t + 399/8.
LATEX_G_CORRETO = r"G(t)=t^{3}-\frac{23}{2}t^{2}+\frac{55}{4}t+\frac{399}{8},\ t\in[0,10]"
# Transcrição ERRADA já observada em produção: perde o termo cúbico "t^3"
# inteiro e reanexa o expoente "3" ao termo errado ("55/4 t^3" em vez de
# "55/4 t"). Corromper a fórmula desta forma NUNCA deve escapar sem detecção
# quando a confiança/validação está em jogo neste módulo.
LATEX_G_ERRADO = r"G(t)=-\frac{23}{2}t^{2}+\frac{55}{4}t^{3}+\frac{399}{8}"


def _questao(enunciado: str, formulas: list[Formula] | None = None, **overrides) -> Questao:
    base = dict(
        numero=1,
        banca="FCC",
        ano=2025,
        materia="Matemática",
        assunto="Funções",
        enunciado=enunciado,
        alternativas=[Alternativa(letra="a", texto="Certo"), Alternativa(letra="b", texto="Errado")],
        gabarito="A",
        comentario=None,
        formulas=formulas or [],
    )
    base.update(overrides)
    return Questao(**base)


# --- validar_sintaxe_latex / normalizar_latex_seguro -------------------------


def test_validar_sintaxe_rejeita_latex_vazio():
    ok, motivo = validar_sintaxe_latex("")
    assert not ok
    assert "vazio" in motivo


def test_validar_sintaxe_rejeita_chaves_desbalanceadas():
    ok, motivo = validar_sintaxe_latex(r"\frac{23}{2")
    assert not ok
    assert "desbalanceadas" in motivo


def test_validar_sintaxe_rejeita_chave_fechando_sem_abrir():
    ok, _motivo = validar_sintaxe_latex(r"\frac{23}2}")
    assert not ok


def test_validar_sintaxe_rejeita_ambiente_nao_suportado():
    ok, motivo = validar_sintaxe_latex(r"\begin{matrix}1&2\\3&4\end{matrix}")
    assert not ok
    assert "não suportado" in motivo


def test_validar_sintaxe_aceita_latex_bem_formado():
    ok, _motivo = validar_sintaxe_latex(LATEX_G_CORRETO)
    assert ok


def test_normalizar_troca_dfrac_e_tfrac_por_frac():
    assert normalizar_latex_seguro(r"\dfrac{1}{2}") == r"\frac{1}{2}"
    assert normalizar_latex_seguro(r"\tfrac{1}{2}") == r"\frac{1}{2}"


def test_normalizar_remove_left_right_sem_alterar_parenteses():
    assert normalizar_latex_seguro(r"\left(x+y\right)") == "(x+y)"


def test_normalizar_nunca_reordena_ou_descarta_termos():
    # a normalização só troca variantes de comando/espaçamento — nunca mexe
    # na ordem ou na presença dos termos/símbolos da fórmula.
    normalizado = normalizar_latex_seguro(LATEX_G_CORRETO)
    for termo in ("t^{3}", r"\frac{23}{2}", "t^{2}", r"\frac{55}{4}", r"\frac{399}{8}"):
        assert termo in normalizado


# --- resolver_formulas_questao: cadeia de aceitação/fallback -----------------


def test_formula_valida_e_confiante_substitui_marcador_display():
    questao = _questao(
        "Considere [FORMULA_01] para responder.",
        [Formula(id="FORMULA_01", latex=LATEX_G_CORRETO, display=True, confidence=0.95)],
    )
    resolvida = resolver_formulas_questao(questao)
    assert "[FORMULA_01]" not in resolvida.enunciado
    assert f"$${LATEX_G_CORRETO}$$" in resolvida.enunciado


def test_formula_valida_inline_usa_delimitador_simples():
    questao = _questao(
        "O valor de [FORMULA_01] é positivo.",
        [Formula(id="FORMULA_01", latex=r"x^{2}", display=False, confidence=0.9)],
    )
    resolvida = resolver_formulas_questao(questao)
    assert "$x^{2}$" in resolvida.enunciado
    assert "$$x^{2}$$" not in resolvida.enunciado


def test_formula_com_usar_recorte_original_mantem_marcador():
    questao = _questao(
        "Veja [FORMULA_01].",
        [Formula(id="FORMULA_01", latex=LATEX_G_CORRETO, display=True, confidence=0.99, usar_recorte_original=True)],
    )
    resolvida = resolver_formulas_questao(questao)
    assert "[FORMULA_01]" in resolvida.enunciado


def test_formula_com_confianca_abaixo_do_limiar_mantem_marcador():
    questao = _questao(
        "Veja [FORMULA_01].",
        [Formula(id="FORMULA_01", latex=LATEX_G_CORRETO, display=True, confidence=LIMIAR_CONFIANCA_FORMULA - 0.01)],
    )
    resolvida = resolver_formulas_questao(questao)
    assert "[FORMULA_01]" in resolvida.enunciado


def test_formula_no_limiar_exato_e_aceita():
    questao = _questao(
        "Veja [FORMULA_01].",
        [Formula(id="FORMULA_01", latex=r"x^{2}", display=False, confidence=LIMIAR_CONFIANCA_FORMULA)],
    )
    resolvida = resolver_formulas_questao(questao)
    assert "[FORMULA_01]" not in resolvida.enunciado


def test_formula_com_id_que_nao_corresponde_a_marcador_e_ignorada():
    questao = _questao(
        "Veja [FORMULA_01].",
        [Formula(id="FORMULA_99", latex=r"x^{2}", display=False, confidence=1.0)],
    )
    resolvida = resolver_formulas_questao(questao)
    # nada muda: o id da IA não corresponde a nenhum marcador real do enunciado
    assert resolvida.enunciado == questao.enunciado
    assert "[FORMULA_01]" in resolvida.enunciado


def test_formula_com_chaves_desbalanceadas_mantem_marcador():
    questao = _questao(
        "Veja [FORMULA_01].",
        [Formula(id="FORMULA_01", latex=r"\frac{23}{2", display=True, confidence=1.0)],
    )
    resolvida = resolver_formulas_questao(questao)
    assert "[FORMULA_01]" in resolvida.enunciado


def test_formula_com_comando_nao_suportado_mantem_marcador():
    questao = _questao(
        "Veja [FORMULA_01].",
        [Formula(id="FORMULA_01", latex=r"\begin{matrix}1&2\\3&4\end{matrix}", display=True, confidence=1.0)],
    )
    resolvida = resolver_formulas_questao(questao)
    assert "[FORMULA_01]" in resolvida.enunciado


def test_formula_que_falha_render_bruto_mas_recupera_apos_normalizacao():
    # \tfrac não é entendido pelo matplotlib.mathtext cru, mas
    # normalizar_latex_seguro troca por \frac (equivalente visual) — a
    # cadeia de fallback deve aceitar a versão normalizada em vez de
    # desistir e usar o recorte original.
    questao = _questao(
        "Veja [FORMULA_01].",
        [Formula(id="FORMULA_01", latex=r"\tfrac{1}{2}", display=True, confidence=1.0)],
    )
    resolvida = resolver_formulas_questao(questao)
    assert "[FORMULA_01]" not in resolvida.enunciado
    assert r"\frac{1}{2}" in resolvida.enunciado


def test_formula_sem_marcador_no_enunciado_nao_altera_nada():
    questao = _questao("Enunciado sem nenhuma fórmula.", [])
    resolvida = resolver_formulas_questao(questao)
    assert resolvida is questao  # early-return: nem tenta processar


def test_multiplas_formulas_algumas_aceitas_outras_nao():
    questao = _questao(
        "Primeiro [FORMULA_01], depois [FORMULA_02].",
        [
            Formula(id="FORMULA_01", latex=r"x^{2}", display=False, confidence=0.9),
            Formula(id="FORMULA_02", latex=r"\begin{matrix}1&2\end{matrix}", display=True, confidence=1.0),
        ],
    )
    resolvida = resolver_formulas_questao(questao)
    assert "$x^{2}$" in resolvida.enunciado
    assert "[FORMULA_01]" not in resolvida.enunciado
    assert "[FORMULA_02]" in resolvida.enunciado  # rejeitada, mantém o recorte


def test_resolver_formulas_aplica_a_lista_inteira():
    questoes = [
        _questao("A: [FORMULA_01].", [Formula(id="FORMULA_01", latex="x", display=False, confidence=1.0)]),
        _questao("B: [FORMULA_01].", [Formula(id="FORMULA_01", latex="y", display=False, confidence=1.0)]),
    ]
    resolvidas = resolver_formulas(questoes)
    assert "$x$" in resolvidas[0].enunciado
    assert "$y$" in resolvidas[1].enunciado


# --- regressão específica do bug relatado (G(t)) -----------------------------


def test_regressao_gt_transcricao_correta_e_aceita_e_preserva_todos_os_termos():
    questao = _questao(
        "Considere a função [FORMULA_01] definida no intervalo dado.",
        [Formula(id="FORMULA_01", latex=LATEX_G_CORRETO, display=True, confidence=0.97)],
    )
    resolvida = resolver_formulas_questao(questao)
    assert "[FORMULA_01]" not in resolvida.enunciado
    for termo in ("t^{3}", r"\frac{23}{2}", "t^{2}", r"\frac{55}{4}", r"\frac{399}{8}"):
        assert termo in resolvida.enunciado


def test_regressao_gt_transcricao_errada_com_confianca_baixa_nao_e_aplicada():
    # se a IA cometesse o mesmo erro relatado (perder o termo cúbico) MAS
    # sinalizasse baixa confiança (o comportamento honesto esperado quando
    # não tem certeza), o sistema preserva o recorte original em vez de
    # publicar a versão corrompida.
    questao = _questao(
        "Considere a função [FORMULA_01] definida no intervalo dado.",
        [Formula(id="FORMULA_01", latex=LATEX_G_ERRADO, display=True, confidence=0.3)],
    )
    resolvida = resolver_formulas_questao(questao)
    assert "[FORMULA_01]" in resolvida.enunciado
    assert LATEX_G_ERRADO not in resolvida.enunciado


def test_substituicao_do_marcador_preserva_texto_ao_redor_intacto():
    # mesmo que a IA (incorretamente) devolva o LaTeX corrompido com alta
    # confiança, o pior caso possível é a versão errada aparecer no
    # documento (falha de fidelidade da IA, não deste módulo) — o que este
    # módulo GARANTE é nunca reescrever/reordenar o enunciado de nenhuma
    # outra forma além da substituição direta do marcador pelo latex dado.
    questao = _questao(
        "Antes. [FORMULA_01] Depois.",
        [Formula(id="FORMULA_01", latex=LATEX_G_ERRADO, display=True, confidence=0.97)],
    )
    resolvida = resolver_formulas_questao(questao)
    assert resolvida.enunciado == f"Antes. $${LATEX_G_ERRADO}$$ Depois."
