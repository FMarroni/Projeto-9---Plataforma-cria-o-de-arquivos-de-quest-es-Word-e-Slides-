from app.llm.anthropic_provider import (
    _MAX_TOKENS_EXTRACAO_PISO,
    _MAX_TOKENS_EXTRACAO_TETO,
    _max_tokens_extracao,
)


def test_max_tokens_extracao_usa_piso_para_texto_curto():
    # regressão: um max_tokens fixo baixo (o antigo 8192) cortava a extração
    # de PDFs com muitas questões antes de terminar o JSON de resposta,
    # devolvendo uma extração vazia/incompleta em vez de um erro visível.
    assert _max_tokens_extracao("texto curto") == _MAX_TOKENS_EXTRACAO_PISO


def test_max_tokens_extracao_escala_com_o_tamanho_do_texto():
    texto_longo = "questão de exemplo " * 5000  # ~20 questões reais tem essa ordem de grandeza
    resultado = _max_tokens_extracao(texto_longo)
    assert resultado > _MAX_TOKENS_EXTRACAO_PISO
    assert resultado <= _MAX_TOKENS_EXTRACAO_TETO


def test_max_tokens_extracao_nunca_passa_do_teto():
    texto_gigante = "x" * 10_000_000
    assert _max_tokens_extracao(texto_gigante) == _MAX_TOKENS_EXTRACAO_TETO
