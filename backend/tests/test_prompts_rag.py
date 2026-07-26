from app.prompts import (
    MARCADOR_INFO_NAO_ENCONTRADA,
    build_comment_user_message_rag,
    build_prompt_rag,
    parse_resposta_rag,
)
from app.schemas import Alternativa, Questao


def _questao(**overrides):
    base = dict(
        numero=1,
        banca="CEBRASPE",
        materia="Direito Penal",
        assunto="Furto",
        enunciado="O crime de furto exige subtração de coisa alheia móvel.",
        alternativas=[Alternativa(letra="a", texto="Certo"), Alternativa(letra="b", texto="Errado")],
        gabarito="a",
    )
    base.update(overrides)
    return Questao(**base)


def test_build_prompt_rag_inclui_o_prompt_base_e_o_adendo():
    prompt = build_prompt_rag("PROMPT BASE CUSTOMIZADO")

    assert "PROMPT BASE CUSTOMIZADO" in prompt
    assert "MODO RESTRITO" in prompt
    assert MARCADOR_INFO_NAO_ENCONTRADA in prompt
    assert "[COMENTARIO]" in prompt
    assert "[RASTREABILIDADE]" in prompt


def test_build_comment_user_message_rag_lista_os_trechos_com_fonte():
    questao = _questao()
    trechos = [
        {"arquivo": "Aula_01_Penal.pdf", "pagina": 14, "texto": "O furto está previsto no art. 155 do CP."},
        {"arquivo": "Aula_02_Penal.pdf", "pagina": 3, "texto": "Furto é crime contra o patrimônio."},
    ]

    mensagem = build_comment_user_message_rag(questao, trechos)

    assert "TRECHOS RECUPERADOS DO MATERIAL DE APOIO" in mensagem
    assert "Aula_01_Penal.pdf, página 14" in mensagem
    assert "art. 155 do CP" in mensagem
    assert "Aula_02_Penal.pdf, página 3" in mensagem
    assert "Gabarito correto: a" in mensagem  # reaproveita build_comment_user_message


def test_parse_resposta_rag_formato_completo_com_alternativas():
    resposta = """\
[COMENTARIO]
(a) Correto. O furto exige subtração de coisa alheia móvel, conforme o material;
(b) Errado. Contraria diretamente o texto do material de apoio.
[RASTREABILIDADE]
a: arquivo=Aula_01_Penal.pdf; pagina=14
b: arquivo=Aula_01_Penal.pdf; pagina=14
[FIM]
"""
    comentario, rastreabilidade = parse_resposta_rag(resposta)

    assert comentario is not None
    assert "(a) Correto." in comentario
    assert "[RASTREABILIDADE]" not in comentario  # não vaza a seção seguinte para o comentário
    assert rastreabilidade == [
        {"alternativa": "a", "arquivo": "Aula_01_Penal.pdf", "pagina": "14"},
        {"alternativa": "b", "arquivo": "Aula_01_Penal.pdf", "pagina": "14"},
    ]


def test_parse_resposta_rag_informacao_nao_encontrada_devolve_none():
    resposta = f"[COMENTARIO]\n{MARCADOR_INFO_NAO_ENCONTRADA}\n[FIM]\n"

    comentario, rastreabilidade = parse_resposta_rag(resposta)

    assert comentario is None
    assert rastreabilidade == []


def test_parse_resposta_rag_sem_marcadores_degrada_para_texto_puro():
    # se o modelo ignorar o formato pedido, não pode lançar exceção — o texto
    # inteiro vira o comentário, sem rastreabilidade, em vez de quebrar o pipeline.
    resposta = "Só um comentário livre, sem seguir o formato pedido."

    comentario, rastreabilidade = parse_resposta_rag(resposta)

    assert comentario == resposta
    assert rastreabilidade == []


def test_parse_resposta_rag_certo_errado_usa_identificador_principal():
    resposta = """\
[COMENTARIO]
Correto. Conforme o material de apoio, a afirmação está de acordo com o texto legal.
[RASTREABILIDADE]
PRINCIPAL: arquivo=Aula_03.pdf; pagina=7
[FIM]
"""
    comentario, rastreabilidade = parse_resposta_rag(resposta)

    assert comentario.startswith("Correto.")
    assert rastreabilidade == [{"alternativa": "PRINCIPAL", "arquivo": "Aula_03.pdf", "pagina": "7"}]
