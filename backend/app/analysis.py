"""Agregação pura (sem I/O, sem imports de docx/pptx) que transforma um
ExtractionResult em estatísticas por disciplina: incidência, Curva ABC e
checagem defensiva do cruzamento de gabarito. A incidência e a Curva ABC são
calculadas aqui em vez de pedidas ao LLM porque são aritmética exata sobre
contagens já extraídas — não deve depender da "matemática" do modelo."""

import logging

from app.schemas import AssuntoStats, DisciplinaStats, ExtractionResult, Questao

logger = logging.getLogger(__name__)


def _formatar_percentual_br(valor: float) -> str:
    return f"{valor * 100:.2f}".replace(".", ",") + "%"


def _juntar_oxford(itens: list[str]) -> str:
    if not itens:
        return "N/A"
    if len(itens) == 1:
        return itens[0]
    return ", ".join(itens[:-1]) + " e " + itens[-1]


def formatar_anos(anos: list[int]) -> str:
    if not anos:
        return "N/A"
    distintos = sorted(set(anos))
    if len(distintos) == 1:
        return str(distintos[0])
    return f"{distintos[0]} a {distintos[-1]}"


def _curva_abc(assuntos_desc: list[AssuntoStats]) -> tuple[str, str]:
    """Recebe assuntos JÁ ordenados desc por incidência. Soma incidência até
    atingir >= 0.5 (inclui a linha que cruza o limiar), marca destaque_curva_abc
    nos incluídos, e devolve (texto Oxford-joined, percentual formatado "53,27%").
    Porte fiel da lógica de `Projeto 2 - Código.txt` (soma até >=0.5, break)."""
    soma = 0.0
    nomes: list[str] = []
    for assunto in assuntos_desc:
        soma += assunto.incidencia
        nomes.append(assunto.assunto)
        assunto.destaque_curva_abc = True
        if soma >= 0.5:
            break
    return _juntar_oxford(nomes), _formatar_percentual_br(soma)


def build_disciplinas_stats(extraction: ExtractionResult) -> list[DisciplinaStats]:
    por_disciplina: dict[str, list[Questao]] = {}
    ordem_disciplinas: list[str] = []
    for q in extraction.questoes:
        if q.materia not in por_disciplina:
            por_disciplina[q.materia] = []
            ordem_disciplinas.append(q.materia)
        por_disciplina[q.materia].append(q)

    resultado: list[DisciplinaStats] = []
    for nome_disciplina in ordem_disciplinas:
        questoes_disc = por_disciplina[nome_disciplina]
        total = len(questoes_disc)

        contagem_assuntos: dict[str, int] = {}
        ordem_assuntos: list[str] = []
        for q in questoes_disc:
            if q.assunto not in contagem_assuntos:
                contagem_assuntos[q.assunto] = 0
                ordem_assuntos.append(q.assunto)
            contagem_assuntos[q.assunto] += 1

        assuntos = [
            AssuntoStats(
                assunto=nome,
                n_questoes=contagem_assuntos[nome],
                incidencia=contagem_assuntos[nome] / total,
                destaque_curva_abc=False,
            )
            for nome in ordem_assuntos
        ]
        assuntos.sort(key=lambda a: a.incidencia, reverse=True)

        curva_abc_texto, curva_abc_percentual = _curva_abc(assuntos)

        bancas = sorted({q.banca for q in questoes_disc if q.banca})
        anos = sorted({q.ano for q in questoes_disc if q.ano is not None})

        resultado.append(
            DisciplinaStats(
                nome=nome_disciplina,
                total_questoes=total,
                bancas=bancas,
                anos=anos,
                assuntos=assuntos,
                curva_abc_texto=curva_abc_texto,
                curva_abc_percentual=curva_abc_percentual,
                questoes=questoes_disc,
            )
        )

    return resultado


def verificar_gabaritos(questoes: list[Questao]) -> list[str]:
    """Checagem defensiva (não bloqueante) do cruzamento de gabarito feito pelo
    LLM: número duplicado, faltando, ou nem gabarito nem anulada preenchidos.
    A responsabilidade principal de evitar erro de cruzamento é do prompt de
    extração (ver prompts.EXTRACTION_SYSTEM_PROMPT) — isto só loga avisos."""
    avisos: list[str] = []
    vistos: dict[int, int] = {}
    for q in questoes:
        vistos[q.numero] = vistos.get(q.numero, 0) + 1
        if not q.anulada and q.gabarito is None:
            avisos.append(f"Questão {q.numero}: sem gabarito e não marcada como anulada.")

    duplicados = [n for n, c in vistos.items() if c > 1]
    if duplicados:
        avisos.append(f"Números de questão duplicados: {sorted(duplicados)}")

    numeros = sorted(vistos)
    if numeros:
        esperado = list(range(numeros[0], numeros[-1] + 1))
        faltando = [n for n in esperado if n not in vistos]
        if faltando:
            avisos.append(f"Números de questão ausentes na sequência: {faltando}")

    for aviso in avisos:
        logger.warning(aviso)
    return avisos
