"""Extração 100% local (sem IA) de questões a partir do texto de um PDF
exportado do TEC Concursos — usa só o padrão fixo do próprio site (nenhuma
chamada de rede, nenhuma chave de API):

  www.tecconcursos.com.br/questoes/<id>      <- marcador de início de questão
  Banca - Cargo (Órgão)/SubÓrgão/.../Ano     <- cabeçalho
  Matéria - Assunto                          <- cabeçalho
  <enunciado, uma ou mais linhas>
  a) ... / b) ... / ... (múltipla escolha)   <- OU
  Certo / Errado                             (Cespe, Certo ou Errado)
  ... (próxima questão ou fim)
  Gabarito
  1) X  2) Y  3) Anulada ...                 <- consolidado no final, 1 por questão

Isso cobre o formato-padrão do TEC Concursos, que é o mesmo já documentado em
`pdf_extract.py`. Questões fora desse padrão (discursivas, layouts atípicos)
ainda geram uma Questao (best-effort, sem travar as demais) — a menos que o
PDF inteiro não tenha nenhum marcador de questão reconhecível, caso em que
`TextoNaoReconhecidoError` é levantada para o pipeline sugerir a extração por IA."""

import re

from app.schemas import Alternativa, ExtractionResult, Questao

_MARCADOR_QUESTAO = re.compile(r"www\.tecconcursos\.com\.br/questoes/\d+")
_CABECALHO_GABARITO = re.compile(r"^Gabarito\s*$", re.M)
_GABARITO_ITEM = re.compile(r"(\d+)\)\s*(Anulada|Certo|Errado|[A-E])\b")
_LINHA_ALTERNATIVA = re.compile(r"^([a-eA-E])\)\s*(.*)$")
_LINHA_CE = re.compile(r"^(Certo|Errado)\s*$")
_NUMERO_INICIAL = re.compile(r"^\d+\)\s*")


class TextoNaoReconhecidoError(Exception):
    """Levantado quando o texto não contém nenhum marcador de questão do TEC
    Concursos — sinal de que este PDF não está no formato que o extrator por
    regras entende (nesse caso, use a extração por IA)."""


def _separar_gabarito(texto: str) -> tuple[str, str]:
    """O bloco 'Gabarito' vem sempre consolidado no final do documento —
    separá-lo ANTES de dividir por questão evita que ele seja engolido como
    enunciado da última questão."""
    matches = list(_CABECALHO_GABARITO.finditer(texto))
    if not matches:
        return texto, ""
    corte = matches[-1].start()
    return texto[:corte], texto[corte:]


def _dividir_por_questao(texto: str) -> list[str]:
    posicoes = [m.start() for m in _MARCADOR_QUESTAO.finditer(texto)]
    if not posicoes:
        raise TextoNaoReconhecidoError(
            "Nenhuma questão no formato TEC Concursos foi reconhecida neste PDF "
            "— tente a extração Com IA."
        )
    posicoes.append(len(texto))
    return [texto[posicoes[i] : posicoes[i + 1]] for i in range(len(posicoes) - 1)]


def _parse_gabarito(bloco_gabarito: str) -> dict[int, str]:
    return {int(numero): valor for numero, valor in _GABARITO_ITEM.findall(bloco_gabarito)}


def _parse_cabecalho(linha: str) -> tuple[str, str, str | None, str | None, int | None]:
    """'Banca - Cargo (Órgão)/SubÓrgão/.../Ano' -> (banca, cargo, orgao, sub_orgao, ano).

    O nº de segmentos separados por '/' varia (algumas bancas incluem um
    segmento extra de especialidade) — heurística usada: o cargo é sempre o
    1º segmento; o último só é tratado como ano se for puramente numérico de
    4 dígitos; o que sobra no meio vira orgao (1º) + sub_orgao (resto)."""
    banca, _, resto = linha.partition(" - ")
    segmentos = [s.strip().strip('"') for s in resto.split("/") if s.strip()]
    if not segmentos:
        return banca.strip(), "", None, None, None

    cargo = segmentos[0]
    meio = segmentos[1:]

    ano = None
    if meio and re.fullmatch(r"\d{4}", meio[-1]):
        ano = int(meio[-1])
        meio = meio[:-1]

    orgao = meio[0] if meio else None
    sub_orgao = "/".join(meio[1:]) if len(meio) > 1 else None
    return banca.strip(), cargo, orgao, sub_orgao, ano


def _parse_questao(numero: int, bloco: str, gabaritos: dict[int, str]) -> Questao:
    linhas_uteis = [linha for linha in bloco.split("\n")[1:] if linha.strip()]
    if len(linhas_uteis) < 2:
        return Questao(numero=numero, banca="", materia="", assunto="", enunciado="")

    banca, cargo, orgao, sub_orgao, ano = _parse_cabecalho(linhas_uteis[0])
    materia, _, assunto = linhas_uteis[1].partition(" - ")

    corpo = linhas_uteis[2:]
    enunciado_linhas: list[str] = []
    alternativas: list[Alternativa] = []
    tipo_certo_errado = False

    i = 0
    while i < len(corpo):
        linha = corpo[i]
        match_alternativa = _LINHA_ALTERNATIVA.match(linha)
        if match_alternativa:
            letra = match_alternativa.group(1).lower()
            texto_alt = match_alternativa.group(2)
            i += 1
            # linhas de continuação (a própria alternativa quebrou de linha)
            while i < len(corpo) and not _LINHA_ALTERNATIVA.match(corpo[i]) and not _LINHA_CE.match(corpo[i]):
                texto_alt += " " + corpo[i]
                i += 1
            alternativas.append(Alternativa(letra=letra, texto=texto_alt.strip()))
            continue

        if _LINHA_CE.match(linha):
            tipo_certo_errado = True
            i += 1
            continue

        enunciado_linhas.append(linha)
        i += 1

    enunciado = _NUMERO_INICIAL.sub("", "\n".join(enunciado_linhas).strip(), count=1)

    valor_gabarito = gabaritos.get(numero)
    anulada = valor_gabarito == "Anulada"
    if anulada:
        gabarito = None
    elif tipo_certo_errado and valor_gabarito in ("Certo", "Errado"):
        gabarito = valor_gabarito
    else:
        gabarito = valor_gabarito

    return Questao(
        numero=numero,
        banca=banca,
        orgao=orgao,
        sub_orgao=sub_orgao,
        cargo=cargo or None,
        ano=ano,
        materia=materia.strip(),
        assunto=assunto.strip(),
        enunciado=enunciado,
        alternativas=alternativas,
        gabarito=gabarito,
        anulada=anulada,
    )


def extrair_estruturado(texto: str) -> ExtractionResult:
    """Extração por regras (sem IA, sem chave de API) do texto já extraído do
    PDF (`app.pdf_extract.extrair_conteudo_pdf`) — ver docstring do módulo
    para o formato esperado."""
    nome_concurso = texto.strip().split("\n", 1)[0].strip() or None

    texto_questoes, texto_gabarito = _separar_gabarito(texto)
    blocos = _dividir_por_questao(texto_questoes)
    gabaritos = _parse_gabarito(texto_gabarito)

    questoes = [_parse_questao(i + 1, bloco, gabaritos) for i, bloco in enumerate(blocos)]

    return ExtractionResult(
        nome_concurso=nome_concurso,
        escolaridade=None,
        bancas=sorted({q.banca for q in questoes if q.banca}),
        anos=sorted({q.ano for q in questoes if q.ano is not None}),
        cargos=sorted({q.cargo for q in questoes if q.cargo}),
        questoes=questoes,
    )
