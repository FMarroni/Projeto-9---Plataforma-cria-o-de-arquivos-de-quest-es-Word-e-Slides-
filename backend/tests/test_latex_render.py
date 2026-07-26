from app.formatting import Token, tokenize_rich_text
from app.latex_render import renderizar_formula, resolver_tokens_equacao


def test_tokenize_reconhece_bloco_dollar_duplo_como_equacao():
    tokens = tokenize_rich_text(r"veja $$\alpha + \beta$$ aqui")
    equacoes = [t for t in tokens if t.is_equation]
    assert len(equacoes) == 1
    assert equacoes[0].latex_formula == r"\alpha + \beta"


def test_tokenize_dollar_simples_continua_usando_substituicao_unicode():
    tokens = tokenize_rich_text(r"veja $\alpha$ aqui")
    assert not any(t.is_equation for t in tokens)
    assert any(t.text == "α" for t in tokens)


def test_renderiza_formula_valida_gera_png():
    dados = renderizar_formula(r"\frac{a}{b+c}")
    assert dados[:8] == b"\x89PNG\r\n\x1a\n"


def test_resolver_tokens_equacao_produz_token_imagem_e_preenche_dict():
    tokens = [Token(text="", is_equation=True, latex_formula=r"x^2 + y^2")]
    imagens: dict[str, bytes] = {}

    resolvidos = resolver_tokens_equacao(tokens, imagens)

    assert len(resolvidos) == 1
    assert resolvidos[0].is_image
    assert resolvidos[0].image_id in imagens
    assert imagens[resolvidos[0].image_id][:8] == b"\x89PNG\r\n\x1a\n"


def test_resolver_tokens_equacao_cai_no_fallback_unicode_se_render_falhar():
    # \begin{matrix} não é suportado pelo mathtext do matplotlib
    tokens = [Token(text="", is_equation=True, latex_formula=r"\begin{matrix}1&0\\0&1\end{matrix}")]
    imagens: dict[str, bytes] = {}

    resolvidos = resolver_tokens_equacao(tokens, imagens)

    assert not any(t.is_image for t in resolvidos)
    assert not any(t.is_equation for t in resolvidos)
    assert imagens == {}


def test_renderiza_formula_gt_do_bug_relatado_com_todos_os_termos():
    # regressão direta do bug relatado pelo usuário: G(t) com termo cúbico,
    # duas frações e domínio -- precisa renderizar sem erro (a fidelidade dos
    # TERMOS em si é garantida por app.formula_resolve/prompts.py, não aqui;
    # este teste garante que o subconjunto de comandos usado é suportado).
    latex_correto = r"G(t)=t^{3}-\frac{23}{2}t^{2}+\frac{55}{4}t+\frac{399}{8},\ t\in[0,10]"
    dados = renderizar_formula(latex_correto)
    assert dados[:8] == b"\x89PNG\r\n\x1a\n"


def test_resolver_tokens_equacao_reaproveita_cache_para_formula_repetida():
    tokens = [
        Token(text="", is_equation=True, latex_formula=r"\pi r^2"),
        Token(text="", is_equation=True, latex_formula=r"\pi r^2"),
    ]
    imagens: dict[str, bytes] = {}

    resolvidos = resolver_tokens_equacao(tokens, imagens)

    assert len(imagens) == 1  # mesma fórmula -> mesmo image_id, uma entrada só
    assert resolvidos[0].image_id == resolvidos[1].image_id
