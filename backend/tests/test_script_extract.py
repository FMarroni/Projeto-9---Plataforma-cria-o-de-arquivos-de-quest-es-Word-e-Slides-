import pytest

from app.script_extract import TextoNaoReconhecidoError, extrair_estruturado

TEXTO_MULTIPLA_ESCOLHA = """Improbidade Adm
https://www.tecconcursos.com.br/s/Q6h46I
Ordenação: Por Matéria e Assunto
www.tecconcursos.com.br/questoes/3832883
VUNESP - Prom Jus (MPE SC)/MPE SC/2026
Direito Administrativo (Doutrina e Leis Federais) - Dos Atos de Improbidade (arts. 9º a 11 da Lei nº 8.429/1992)
À luz do disposto na Lei nº 8.429/1992, é correto afirmar que pratica ato de improbidade administrativa:
a) O servidor público municipal que promove o direcionamento de procedimento licitatório,
frustrando seu caráter concorrencial.
b) O Secretário da Fazenda que contrai dívida milionária em nome do Município.
c) Agente de trânsito que solicita propina mas não chega a receber a vantagem ilícita.
d) O monitor de abrigo municipal que pratica atos de tortura contra criança.
e) Empresários que frustram dolosamente a licitude de processo licitatório.
www.tecconcursos.com.br/questoes/3832998
VUNESP - Prom Jus (MPE SC)/MPE SC/2026
Direito Administrativo (Doutrina e Leis Federais) - Da Prescrição (arts. 23 a 23-C da Lei nº 8.429/1992)
Com o advento da Lei nº 14.230/2021, assinale a alternativa correta.
a) O Acordo de Não Persecução Cível constitui direito subjetivo do investigado.
b) A norma mais benéfica aplica-se retroativamente aos processos em curso.
c) O novo regime de prescrição intercorrente aplica-se aos processos em curso.
d) A instauração do Inquérito Civil suspende o curso do prazo prescricional.
e) A revogação da modalidade culposa caracteriza abolitio criminis.
Gabarito
1) A
2) Anulada
"""

TEXTO_CERTO_ERRADO = """Caderno de Estudo
https://www.tecconcursos.com.br/s/Q6hWJL
Ordenação: Por Matéria e Assunto
www.tecconcursos.com.br/questoes/3907707
CEBRASPE (CESPE) - Diplomata/IRBr/2026
Direito Constitucional (CF/1988 e Doutrina) - Dos Direitos e Deveres Individuais e Coletivos (art. 5º da CF/1988)
Acerca dos direitos e garantias fundamentais previstos na CF, julgue o item a seguir.
Os direitos e garantias fundamentais previstos na CF incluem o de não ser submetido a tortura.
Certo
Errado
www.tecconcursos.com.br/questoes/3963774
CEBRASPE (CESPE) - Ana Adm (TCE RN)/TCE RN/Arquivologia/2026
Direito Constitucional (CF/1988 e Doutrina) - Dos Direitos e Deveres Individuais e Coletivos (art. 5º da CF/1988)
As atividades das associações só poderão ser suspensas por decisão judicial transitada em julgado.
Certo
Errado
www.tecconcursos.com.br/questoes/3973231
CEBRASPE (CESPE) - Tec Adm (TCE RN)/TCE RN/2026
Direito Constitucional (CF/1988 e Doutrina) - Perda e Suspensão dos Direitos Políticos
A condenação criminal transitada em julgado enseja a suspensão dos direitos políticos do condenado.
Certo
Errado
Gabarito
1) Certo
2) Errado
3) Anulada
"""

TEXTO_ITENS_ROMANOS = """Caderno de Estudo
https://www.tecconcursos.com.br/s/Q6hWJL
Ordenação: Por Matéria e Assunto
www.tecconcursos.com.br/questoes/3816434
CEBRASPE (CESPE) - ACE (TCE-MG)/TCE MG/Direito/2026
Direito Constitucional (CF/1988 e Doutrina) - Questões Mescladas de Remédios Constitucionais
A respeito dos remédios constitucionais, julgue os itens a seguir.
I O Ministério Público de Contas dos estados possui legitimidade para impetrar mandado de segurança.
II A imposição de valor a ser ressarcido aos cofres públicos ensejam a legitimidade desta instituição.
III Segundo entendimento do STF, admite-se a utilização do mandado de injunção como sucedâneo.
Assinale a opção correta.
a) Apenas o item II está certo.
b) Apenas o item III está certo.
c) Apenas os itens I e II estão certos.
d) Apenas os itens I e III estão certos.
e) Todos os itens estão certos.
Gabarito
1) A
"""

TEXTO_CABECALHO_COM_ASPAS = """Caderno de Estudo
https://www.tecconcursos.com.br/s/Q6hWJL
Ordenação: Por Matéria e Assunto
www.tecconcursos.com.br/questoes/3945114
CEBRASPE (CESPE) - AProj (AgSUS)/AgSUS/"Sem Área"/2026
Direito Constitucional (CF/1988 e Doutrina) - Dos Direitos e Deveres Individuais e Coletivos (art. 5º da CF/1988)
Em relação a políticas públicas e ações afirmativas, julgue o seguinte item.
Além das cotas raciais, as ações afirmativas incluem bolsas de estudo.
Certo
Errado
Gabarito
1) Certo
"""


def test_multipla_escolha_extrai_alternativas_e_gabarito():
    resultado = extrair_estruturado(TEXTO_MULTIPLA_ESCOLHA)

    assert resultado.nome_concurso == "Improbidade Adm"
    assert len(resultado.questoes) == 2

    q1 = resultado.questoes[0]
    assert q1.numero == 1
    assert q1.banca == "VUNESP"
    assert q1.cargo == "Prom Jus (MPE SC)"
    assert q1.orgao == "MPE SC"
    assert q1.sub_orgao is None
    assert q1.ano == 2026
    assert q1.materia == "Direito Administrativo (Doutrina e Leis Federais)"
    assert q1.assunto == "Dos Atos de Improbidade (arts. 9º a 11 da Lei nº 8.429/1992)"
    assert not q1.enunciado.startswith("1)")
    assert len(q1.alternativas) == 5
    # alternativa "a" quebra em 2 linhas no PDF — precisa juntar numa só
    assert q1.alternativas[0].texto == (
        "O servidor público municipal que promove o direcionamento de procedimento licitatório, "
        "frustrando seu caráter concorrencial."
    )
    assert q1.gabarito == "A"
    assert not q1.anulada

    q2 = resultado.questoes[1]
    assert q2.gabarito is None
    assert q2.anulada

    assert resultado.bancas == ["VUNESP"]
    assert resultado.anos == [2026]


def test_certo_ou_errado_sem_alternativas_letradas():
    resultado = extrair_estruturado(TEXTO_CERTO_ERRADO)
    assert len(resultado.questoes) == 3

    q1 = resultado.questoes[0]
    assert q1.alternativas == []
    assert q1.gabarito == "Certo"
    assert not q1.anulada

    q2 = resultado.questoes[1]
    assert q2.gabarito == "Errado"
    # cabeçalho com segmento extra de especialidade: Cargo/Orgao/SubOrgao/Ano
    assert q2.cargo == "Ana Adm (TCE RN)"
    assert q2.orgao == "TCE RN"
    assert q2.sub_orgao == "Arquivologia"
    assert q2.ano == 2026

    q3 = resultado.questoes[2]
    assert q3.anulada
    assert q3.gabarito is None


def test_itens_romanos_ficam_no_enunciado_sem_virar_alternativas():
    resultado = extrair_estruturado(TEXTO_ITENS_ROMANOS)
    q1 = resultado.questoes[0]

    assert "I O Ministério Público" in q1.enunciado
    assert "III Segundo entendimento do STF" in q1.enunciado
    assert len(q1.alternativas) == 5
    assert q1.alternativas[0].texto == "Apenas o item II está certo."
    assert q1.gabarito == "A"


def test_cabecalho_com_segmento_entre_aspas():
    resultado = extrair_estruturado(TEXTO_CABECALHO_COM_ASPAS)
    q1 = resultado.questoes[0]

    assert q1.cargo == "AProj (AgSUS)"
    assert q1.orgao == "AgSUS"
    assert q1.sub_orgao == "Sem Área"
    assert q1.ano == 2026


def test_gabarito_com_varias_entradas_na_mesma_linha():
    """No PDF real o bloco Gabarito quebra de linha no meio de uma sequência
    de itens ('...6) Certo\\n7) Errado...') — o parser não pode depender de
    uma entrada por linha."""
    texto = (
        "Caderno\n"
        "www.tecconcursos.com.br/questoes/1\n"
        "BANCA - Cargo/Orgao/2020\n"
        "Materia - Assunto\n"
        "Enunciado 1.\n"
        "Certo\nErrado\n"
        "www.tecconcursos.com.br/questoes/2\n"
        "BANCA - Cargo/Orgao/2020\n"
        "Materia - Assunto\n"
        "Enunciado 2.\n"
        "Certo\nErrado\n"
        "Gabarito\n"
        "1) Certo 2) Errado\n"
    )
    resultado = extrair_estruturado(texto)
    assert resultado.questoes[0].gabarito == "Certo"
    assert resultado.questoes[1].gabarito == "Errado"


def test_placeholder_de_imagem_passa_intacto_pelo_enunciado():
    texto = (
        "Caderno\n"
        "www.tecconcursos.com.br/questoes/1\n"
        "BANCA - Cargo/Orgao/2020\n"
        "Materia - Assunto\n"
        "[IMAGEM_01]\n"
        "Considerando a figura acima, assinale a opção correta.\n"
        "a) primeira.\n"
        "b) segunda.\n"
        "Gabarito\n"
        "1) A\n"
    )
    resultado = extrair_estruturado(texto)
    assert "[IMAGEM_01]" in resultado.questoes[0].enunciado


def test_texto_sem_nenhuma_questao_do_tec_levanta_erro():
    with pytest.raises(TextoNaoReconhecidoError):
        extrair_estruturado("Um PDF qualquer sem nenhum marcador de questão do TEC Concursos.")
