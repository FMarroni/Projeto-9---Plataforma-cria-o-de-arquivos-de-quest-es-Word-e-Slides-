from app.analysis import build_disciplinas_stats, verificar_gabaritos
from app.schemas import ExtractionResult, Questao


def _questao(numero, materia, assunto, gabarito="A", ano=2024, anulada=False):
    return Questao(
        numero=numero,
        banca="BANCA X",
        ano=ano,
        materia=materia,
        assunto=assunto,
        enunciado="enunciado",
        alternativas=[],
        gabarito=gabarito,
        anulada=anulada,
    )


def test_curva_abc_para_exatamente_no_limiar_de_50_por_cento():
    # 2 assuntos com 50% cada: a soma já cruza >=0.5 na primeira linha -> só ela entra
    extraction = ExtractionResult(
        questoes=[
            _questao(1, "Direito", "Assunto A"),
            _questao(2, "Direito", "Assunto B"),
        ]
    )
    disciplinas = build_disciplinas_stats(extraction)
    assert len(disciplinas) == 1
    d = disciplinas[0]
    assert d.curva_abc_percentual == "50,00%"
    assert d.curva_abc_texto == "Assunto A"
    destaques = [a.assunto for a in d.assuntos if a.destaque_curva_abc]
    assert destaques == ["Assunto A"]


def test_curva_abc_ultrapassando_50_por_cento():
    # 5 questões: Assunto A com 2 (40%), Assunto B com 2 (40%), Assunto C com 1 (20%)
    # soma após A = 0.4 (<0.5, continua); após B = 0.8 (>=0.5, para) -> A e B entram, C não
    extraction = ExtractionResult(
        questoes=[
            _questao(1, "Direito", "Assunto A"),
            _questao(2, "Direito", "Assunto A"),
            _questao(3, "Direito", "Assunto B"),
            _questao(4, "Direito", "Assunto B"),
            _questao(5, "Direito", "Assunto C"),
        ]
    )
    disciplinas = build_disciplinas_stats(extraction)
    d = disciplinas[0]
    assert d.curva_abc_texto == "Assunto A e Assunto B"
    assert d.curva_abc_percentual == "80,00%"
    destaques = {a.assunto for a in d.assuntos if a.destaque_curva_abc}
    assert destaques == {"Assunto A", "Assunto B"}
    nao_destaque = [a.assunto for a in d.assuntos if not a.destaque_curva_abc]
    assert nao_destaque == ["Assunto C"]


def test_incidencia_soma_100_por_cento_por_disciplina():
    extraction = ExtractionResult(
        questoes=[
            _questao(1, "Estatística", "X"),
            _questao(2, "Estatística", "Y"),
            _questao(3, "Estatística", "Y"),
        ]
    )
    d = build_disciplinas_stats(extraction)[0]
    soma = sum(a.incidencia for a in d.assuntos)
    assert abs(soma - 1.0) < 1e-9


def test_verificar_gabaritos_detecta_faltando_e_duplicado():
    questoes = [
        _questao(1, "X", "A"),
        _questao(1, "X", "A"),  # duplicado
        _questao(3, "X", "A"),  # 2 ausente
    ]
    avisos = verificar_gabaritos(questoes)
    assert any("duplicad" in a.lower() for a in avisos)
    assert any("ausentes" in a.lower() for a in avisos)


def test_verificar_gabaritos_sem_gabarito_e_sem_anulada_gera_aviso():
    q = _questao(1, "X", "A", gabarito=None, anulada=False)
    avisos = verificar_gabaritos([q])
    assert len(avisos) == 1
    assert "sem gabarito" in avisos[0].lower()
