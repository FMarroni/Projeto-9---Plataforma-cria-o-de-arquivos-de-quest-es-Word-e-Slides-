import os

import fitz
import pytest

from app.pdf_extract import (
    PdfSemTextoError,
    _bloco_e_formula_suspeita,
    _recortar_regiao_pagina,
    extrair_conteudo_pdf,
)

AMOSTRA_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "..",
    "Subsídios",
    "Tec Concursos - Questões para concursos, provas, editais, simulados_.pdf",
)

MATEMATICA_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "..",
    "Subsídios",
    "Tec Concursos - Questões Matemática.pdf",
)


def test_extrai_texto_e_imagens_do_pdf_de_amostra():
    with open(AMOSTRA_PATH, "rb") as f:
        dados = f.read()
    texto, imagens = extrair_conteudo_pdf(dados)

    assert texto.strip()
    assert "Gabarito" in texto

    # o PDF de amostra ("Questões com imagens, anulada e normal") tem 2 imagens
    # de conteúdo relevante (tabela + histograma) e 1 logo pequeno descartado
    assert set(imagens.keys()) == {"IMAGEM_01", "IMAGEM_02"}
    assert "[IMAGEM_01]" in texto
    assert "[IMAGEM_02]" in texto
    # confirma que os bytes são PNGs válidos (assinatura de arquivo)
    for dados_imagem in imagens.values():
        assert dados_imagem[:8] == b"\x89PNG\r\n\x1a\n"


def test_expoente_e_reconstruido_como_marcacao_de_sobrescrito():
    # regressão: este PDF renderiza "6x²" como um "2" normal, só que menor e
    # deslocado para cima (mesmo caractere, sem marcação Unicode) — sem a
    # detecção via span["flags"]/tamanho/posição, viraria "6x2" (achatado).
    with open(MATEMATICA_PATH, "rb") as f:
        dados = f.read()
    texto, _imagens = extrair_conteudo_pdf(dados)

    assert "6x$^{2}$" in texto
    assert "5xy$^{2}$" in texto
    assert "6x2" not in texto  # não pode ter achatado


def test_moeda_no_pdf_de_matematica_permanece_intacta():
    # o mesmo PDF tem várias questões de "Sistema Monetário" cheias de "R$" —
    # a detecção de sobrescrito não pode confundir isso com fórmula
    with open(MATEMATICA_PATH, "rb") as f:
        dados = f.read()
    texto, _imagens = extrair_conteudo_pdf(dados)

    assert "R$ 200,00" in texto
    assert "R$4,50" in texto
    assert texto.count("R$") >= 10  # várias ocorrências ao longo do caderno


def test_pdf_vazio_levanta_erro():
    doc = fitz.open()
    doc.new_page()
    dados = doc.tobytes()
    doc.close()

    with pytest.raises(PdfSemTextoError):
        extrair_conteudo_pdf(dados)


# --- heurística de "fórmula matemática suspeita" (_bloco_e_formula_suspeita) -


def _bloco(bbox: tuple[float, float, float, float], n_linhas: int) -> dict:
    """Bloco sintético mínimo (só os campos que `_bloco_e_formula_suspeita`
    de fato lê: bbox e a QUANTIDADE de linhas — o conteúdo textual de cada
    linha é passado à parte, já pré-computado, como faria `_texto_da_linha`)."""
    return {"bbox": bbox, "lines": [None] * n_linhas}


def test_fracao_estreita_multilinha_com_digitos_e_suspeita():
    # reproduz o mecanismo real do bug relatado: numerador/denominador de uma
    # fração viram linhas SEPARADAS (mesmo tamanho de fonte, sem contraste
    # de sobrescrito) dentro de um bloco estreito.
    bloco = _bloco((100.0, 96.0, 133.0, 104.0), 2)
    linhas = ["23", "2"]
    assert _bloco_e_formula_suspeita(bloco, linhas)


def test_paragrafo_largo_com_ordinal_isolado_nao_e_suspeito():
    bloco = _bloco((28.5, 316.3, 567.7, 333.7), 2)
    linhas = [
        "Henrique pagou R$ 200,00 por 100 canetas que ele quer revender no 1º semestre.",
        "Vendeu metade a R$ 5,50 cada uma para obter lucro no 2º trimestre.",
    ]
    assert not _bloco_e_formula_suspeita(bloco, linhas)


def test_expoente_solto_em_linha_unica_nao_e_suspeito():
    # "6x²" vira 1 única linha (mesma linha/baseline) — MIN_LINHAS exige 2+.
    bloco = _bloco((38.4, 190.9, 249.3, 201.3), 1)
    linhas = ["Considerando x = 3 e y = 4, o valor de 6x$^{2}$ + 5xy$^{2}$+ y é"]
    assert not _bloco_e_formula_suspeita(bloco, linhas)


def test_lista_de_alternativas_estreita_nao_e_suspeita():
    # "a) 286".."e) 166" empilhados numa coluna estreita: estreito + curto +
    # numérico, mas NÃO é fórmula (regressão: falso positivo real encontrado
    # ao calibrar contra o PDF de amostra de Matemática).
    bloco = _bloco((46.1, 207.3, 69.0, 251.2), 5)
    linhas = ["a) 286", "b) 198", "c) 266", "d) 298", "e) 166"]
    assert not _bloco_e_formula_suspeita(bloco, linhas)


def test_bloco_de_gabarito_estreito_nao_e_suspeito():
    # regressão real: o bloco de gabarito consolidado ("1) A 2) E 3) Anulada")
    # pode ser estreito o bastante para passar nos outros critérios — NUNCA
    # pode virar imagem (o cruzamento de gabarito depende de ler esse texto).
    bloco = _bloco((28.5, 67.5, 270.7, 76.2), 4)
    linhas = ["1) A", " 2) E", " 3) Anulada", " 4) C"]
    assert not _bloco_e_formula_suspeita(bloco, linhas)


def test_bloco_largo_multilinha_nao_e_suspeito_mesmo_com_digitos():
    bloco = _bloco((28.5, 448.3, 567.7, 474.6), 3)
    linhas = [
        "Dona Maria guarda moedas de 25 centavos e 10 centavos durante o ano.",
        "No Natal ela havia guardado R$ 250,00 em moedas de 25 centavos.",
        "de 10 centavos.",
    ]
    assert not _bloco_e_formula_suspeita(bloco, linhas)


def test_bloco_estreito_multilinha_com_linhas_longas_nao_e_suspeito():
    # estreito + multilinha, mas cada "linha" tem texto longo demais para
    # ser um fragmento de fórmula (fica acima da média máxima de caracteres).
    bloco = _bloco((30.0, 100.0, 250.0, 140.0), 2)
    linhas = [
        "primeira linha bem longa de texto corrido sem ser formula matematica",
        "segunda linha também bem longa de texto corrido sem ser fórmula",
    ]
    assert not _bloco_e_formula_suspeita(bloco, linhas)


def test_bloco_estreito_multilinha_sem_digito_nem_supsub_nao_e_suspeito():
    bloco = _bloco((100.0, 96.0, 160.0, 104.0), 2)
    linhas = ["ab", "cd"]
    assert not _bloco_e_formula_suspeita(bloco, linhas)


def test_bloco_com_marcadores_supsub_tambem_e_suspeito():
    bloco = _bloco((100.0, 96.0, 160.0, 130.0), 2)
    linhas = ["$^{a}$", "$_{b}$"]
    assert _bloco_e_formula_suspeita(bloco, linhas)


# --- recorte da página original (fallback garantidamente fiel) --------------


def test_recortar_regiao_pagina_devolve_png_valido():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), "G(t) = t^3", fontsize=11)

    dados = _recortar_regiao_pagina(page, (45.0, 90.0, 150.0, 110.0))
    doc.close()

    assert dados[:8] == b"\x89PNG\r\n\x1a\n"


def test_recortar_regiao_pagina_respeita_limites_da_pagina():
    # bbox + margem que extrapola a página não pode lançar erro (o `& page.rect`
    # do recorte satura no limite real da página).
    doc = fitz.open()
    page = doc.new_page()
    dados = _recortar_regiao_pagina(page, (0.0, 0.0, 5.0, 5.0), margem=50.0)
    doc.close()
    assert dados[:8] == b"\x89PNG\r\n\x1a\n"


# --- extrair_conteudo_pdf ponta a ponta: heurística real via PyMuPDF -------


def _pdf_sintetico_com_fracao() -> bytes:
    """PDF de 1 página com uma estrutura análoga ao bug relatado: uma fração
    (numerador '23' sobre denominador '2', mesma fonte, sem contraste de
    tamanho) ao lado de texto normal, e um parágrafo largo de prosa comum —
    a mesma técnica usada para calibrar a heurística (ver testes acima),
    agora através da API pública do módulo."""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), "G(t) = t", fontsize=11)
    page.insert_text((100, 96), "23", fontsize=7)
    page.insert_text((100, 104), "2", fontsize=7)
    page.insert_text((115, 100), "+ x", fontsize=11)
    page.insert_text(
        (50, 300),
        "Considerando a funcao acima, responda a questao a seguir com atencao.",
        fontsize=10,
    )
    dados = doc.tobytes()
    doc.close()
    return dados


def test_extrair_conteudo_pdf_sinaliza_fracao_como_formula_e_recorta():
    texto, imagens = extrair_conteudo_pdf(_pdf_sintetico_com_fracao())

    assert "[FORMULA_01]" in texto
    assert "FORMULA_01" in imagens
    assert imagens["FORMULA_01"][:8] == b"\x89PNG\r\n\x1a\n"
    # o parágrafo largo de prosa ao lado permanece como TEXTO, não imagem
    assert "Considerando a funcao acima" in texto


def test_extrair_conteudo_pdf_nao_sinaliza_nada_em_pdf_sem_formula():
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 100), "Texto comum de uma questao qualquer, sem nenhuma formula matematica.", fontsize=10)
    dados = doc.tobytes()
    doc.close()

    texto, imagens = extrair_conteudo_pdf(dados)
    assert not [k for k in imagens if k.startswith("FORMULA_")]
    assert "Texto comum" in texto
