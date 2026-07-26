from app.docx_common import cabecalho_inline
from app.schemas import Questao


def _questao(banca="FCC", orgao="TRT 1", ano=2025):
    return Questao(
        numero=1,
        banca=banca,
        orgao=orgao,
        ano=ano,
        materia="M",
        assunto="A",
        enunciado="e",
        alternativas=[],
        gabarito="A",
    )


def test_cabecalho_com_orgao_e_ano():
    assert cabecalho_inline(_questao()) == "(FCC / TRT 1 - 2025)"


def test_cabecalho_sem_orgao():
    assert cabecalho_inline(_questao(orgao=None)) == "(FCC - 2025)"


def test_cabecalho_sem_ano():
    assert cabecalho_inline(_questao(ano=None)) == "(FCC / TRT 1)"


def test_cabecalho_sem_orgao_e_sem_ano():
    assert cabecalho_inline(_questao(orgao=None, ano=None)) == "(FCC)"
