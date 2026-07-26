from app.formatting import extrair_ids_imagem, tokenize_rich_text


def test_tokenize_reconhece_placeholder_de_imagem_isolado():
    tokens = tokenize_rich_text("Veja: [IMAGEM_01] a seguir.")
    imagens = [t for t in tokens if t.is_image]
    assert len(imagens) == 1
    assert imagens[0].image_id == "IMAGEM_01"


def test_tokenize_nao_corrompe_markdown_ao_redor_da_imagem():
    tokens = tokenize_rich_text("**Atenção:** [IMAGEM_02] *fim*")
    textos_normais = [t for t in tokens if not t.is_image]
    assert any(t.text == "Atenção:" and t.bold for t in textos_normais)
    assert any(t.text == "fim" and t.italic for t in textos_normais)


def test_extrair_ids_imagem_preserva_ordem_e_duplicatas():
    texto = "[IMAGEM_01] texto [IMAGEM_02] mais texto [IMAGEM_01] de novo"
    assert extrair_ids_imagem(texto) == ["IMAGEM_01", "IMAGEM_02", "IMAGEM_01"]


def test_extrair_ids_imagem_vazio_quando_nao_ha_imagem():
    assert extrair_ids_imagem("texto sem nenhuma imagem") == []


# --- [FORMULA_NN]: tratado de forma idêntica a [IMAGEM_NN] (pdf_extract.py) -


def test_tokenize_reconhece_placeholder_de_formula_isolado():
    tokens = tokenize_rich_text("Veja: [FORMULA_01] a seguir.")
    imagens = [t for t in tokens if t.is_image]
    assert len(imagens) == 1
    assert imagens[0].image_id == "FORMULA_01"


def test_tokenize_nao_corrompe_markdown_ao_redor_da_formula():
    tokens = tokenize_rich_text("**Atenção:** [FORMULA_02] *fim*")
    textos_normais = [t for t in tokens if not t.is_image]
    assert any(t.text == "Atenção:" and t.bold for t in textos_normais)
    assert any(t.text == "fim" and t.italic for t in textos_normais)


def test_extrair_ids_imagem_reconhece_marcadores_de_formula_tambem():
    texto = "[IMAGEM_01] texto [FORMULA_01] mais texto [FORMULA_02]"
    assert extrair_ids_imagem(texto) == ["IMAGEM_01", "FORMULA_01", "FORMULA_02"]


def test_moeda_rs_nao_e_confundida_com_delimitador_de_formula():
    # regressão: "R$" (Real brasileiro) tem "$" colado numa letra — não pode
    # ser tratado como abertura de modo matemático, senão tudo entre dois "R$"
    # vira uma "fórmula" só, corrompendo a formatação e sumindo com o "$"
    texto = (
        "Henrique pagou R$ 200,00 por 100 canetas. Vendeu metade a R$ 5,50 cada "
        "uma e 10 canetas a R$4,50 cada, com lucro de R$ 200,00."
    )
    tokens = tokenize_rich_text(texto)
    assert len(tokens) == 1
    assert tokens[0].text == texto
    assert not tokens[0].italic
    assert "$" in tokens[0].text


def test_matematica_legitima_continua_funcionando_junto_com_moeda_no_mesmo_texto():
    texto = r"Custou R$10 e vale $x^2$ pontos"
    tokens = tokenize_rich_text(texto)
    assert any(t.text == "R$10" or "R$10" in t.text for t in tokens if not t.is_image)
    assert any(t.superscript and t.text == "2" for t in tokens)


def test_expoente_colado_em_variavel_nao_e_confundido_com_moeda():
    # regressão: pdf_extract.py gera exatamente "x$^{2}$" (o "$" vem colado na
    # variável, sem espaço) — o guard de moeda não pode bloquear isso, já que
    # aqui o "$" não é precedido por "R" nem seguido de dígito
    texto = "o valor da expressão 6x$^{2}$ + 5xy$^{2}$+ y é"
    tokens = tokenize_rich_text(texto)
    superscritos = [t.text for t in tokens if t.superscript]
    assert superscritos == ["2", "2"]
    assert not any("$" in t.text for t in tokens)


def test_moeda_e_expoente_juntos_no_mesmo_texto():
    texto = r"Custou R$10 e vale x$^{2}$ pontos, ou ainda R$ 5,00"
    tokens = tokenize_rich_text(texto)
    assert any("R$10" in t.text for t in tokens)
    assert any("R$ 5,00" in t.text for t in tokens)
    assert any(t.superscript and t.text == "2" for t in tokens)
