"""Extração nativa (sem OCR) de texto E imagens do PDF do TEC Concursos, em
ordem de leitura. Cada imagem relevante (gráficos, tabelas-imagem, tirinhas)
vira um placeholder `[IMAGEM_NN]` inserido no texto na posição em que aparece;
os bytes da imagem ficam disponíveis à parte (dict `imagens`), para serem
enviados como conteúdo multimodal aos LLMs (extração e comentário) e depois
injetados de volta nos documentos gerados (docx/pptx).

Sobrescrito/subscrito (ex.: "6x²"): o PDF do TEC Concursos renderiza expoentes
como um "2" normal, só que menor e deslocado para cima (mesmo caractere, sem
marcação Unicode de sobrescrito) — texto puro perderia essa informação. O
PyMuPDF expõe isso via `span["flags"]` (bit 1 = sobrescrito, confirmado contra
um PDF real de Matemática) e via tamanho/posição da linha de base; usamos os
dois sinais para reconstruir a marcação `$^{...}$`/`$_{...}$` que o tokenizer
(`formatting.py`) já sabe renderizar como sobrescrito/subscrito de verdade.

FÓRMULAS MATEMÁTICAS 2D (frações, expoentes empilhados) — bug de fidelidade
corrigido nesta versão: a reconstrução acima funciona bem para um expoente
"solto" numa única linha (ex.: "6x²"), mas uma fórmula com estrutura 2D real
(ex.: `G(t)=t³-23/2·t²+...`, com frações desenhadas como numerador/denominador
empilhados) é fatalmente ambígua na extração nativa — o numerador e o
denominador de uma fração quase sempre viram LINHAS SEPARADAS dentro do mesmo
bloco do PyMuPDF (sem relação de coordenada com o resto da fórmula preservada
pelo texto puro), e a barra da fração é um traço vetorial, não texto. Juntar
esses fragmentos só pela ordem em que o PyMuPDF os devolve reordena/perde
termos silenciosamente (caso real observado: o termo cúbico "t³" foi perdido e
seu expoente "3" reapareceu colado a outro termo).

Em vez de tentar reconstruir esse tipo de estrutura a partir de texto (
impossível de fazer com confiança), blocos heuristicamente identificados como
"provável fórmula 2D" (`_bloco_e_formula_suspeita`, custo controlado — só
dispara para blocos estreitos, com múltiplas linhas e múltiplos marcadores de
sobre/subscrito, nunca para parágrafos largos comuns nem para um "1º"/"2ª"
isolado) têm sua região recortada da própria página em alta resolução e
inserida como placeholder `[FORMULA_NN]` — o mesmo mecanismo de imagem usado
para `[IMAGEM_NN]` (ver `formatting.py`). Esse recorte é enviado à IA como
FONTE DE VERDADE VISUAL para a transcrição LaTeX estruturada (ver
`app.schemas.Formula`, `app.prompts` e `app.formula_resolve`) e, se a IA não
tiver confiança suficiente (ou a transcrição falhar na validação), o
placeholder é deixado intocado — resolvendo automaticamente como uma imagem
fiel do recorte original, nunca como texto potencialmente corrompido."""

import re

import fitz  # PyMuPDF

# Blocos de imagem menores que isto (pt²) são tratados como decorativos
# (logo do site, QR code) e descartados — calibrado contra o PDF de amostra,
# onde o logo/QR mede ~55x55pt e os gráficos de questão passam de ~170x90pt.
AREA_MINIMA_IMAGEM_RELEVANTE = 6000

_SUPERSCRIPT_FLAG = 1  # bit 0 dos span["flags"] do PyMuPDF
_RAZAO_TAMANHO_MAX = 0.92  # abaixo disso, o span é "pequeno" o bastante p/ ser super/subscrito
_DESLOCAMENTO_MINIMO_PT = 0.5  # offset vertical mínimo (pt) para não confundir jitter de renderização

# --- Heurística de "fórmula matemática 2D suspeita" (cost-controlled) -------
#
# Critérios combinados — cada um sozinho tem falsos positivos conhecidos
# (testados empiricamente contra os PDFs de amostra em Subsídios/):
#   - EXCLUSÃO alternativas/gabarito: uma lista de alternativas "a) 286"/
#     "b) 198"/... OU o bloco de gabarito consolidado "1) A"/"2) E"/
#     "3) Anulada" empilhados numa coluna estreita (ambos comuns neste
#     template) batem em todos os critérios de tamanho abaixo (estreita,
#     curta, numérica) sem ser fórmula nenhuma — excluídos cedo pelo prefixo
#     "a)".."e) " ou "N) ". O gabarito em particular NUNCA pode virar imagem:
#     o cruzamento de gabarito (ver prompts.py) depende de ler esse texto.
#   - MIN_LINHAS: uma fórmula com fração/estrutura empilhada sempre gera 2+
#     "lines" no bloco do PyMuPDF (numerador e denominador não compartilham
#     baseline, MESMO quando cada um é um span isolado do mesmo tamanho —
#     testado empiricamente: não dá para depender só da marcação de sobre/
#     subscrito, que exige CONTRASTE de tamanho dentro da MESMA linha); um
#     expoente solto numa frase ("6x²", "1º andar") fica todo numa única linha.
#   - LARGURA_MAXIMA: parágrafos de prova (mesmo com um "1º"/"2ª" solto) são
#     largos (~500pt+ neste template); uma fórmula inline é estreita.
#   - MEDIA_MAXIMA_CARACTERES_LINHA: linhas de fórmula fragmentada são curtas
#     ("23", "2", "t"); linhas de prosa não.
#   - MARCADOR_SUPSUB **ou** DÍGITO: pelo menos um sinal de conteúdo
#     matemático de fato (sobre/subscrito já detectado, ou algum dígito) —
#     sem isso, uma coluna estreita de texto curto qualquer (ex.: uma legenda
#     "Fig. 1" quebrada em 2 linhas) seria sinalizada à toa.
_MIN_LINHAS_FORMULA = 2
_LARGURA_MAXIMA_BLOCO_FORMULA_PT = 260.0
_MIN_MARCADORES_SUPSUB_FORMULA = 2
_MEDIA_MAXIMA_CARACTERES_LINHA_FORMULA = 14.0

_PADRAO_SUPSUB_MARCADO = re.compile(r'\$[\^_]\{')
# "a) "/"b) "/... (alternativas) OU "1) "/"2) "/... (itens do bloco de
# gabarito consolidado, ver prompts.py) — qualquer linha nesse formato
# descarta o bloco como fórmula (ver justificativa acima).
_PADRAO_PREFIXO_EXCLUIDO = re.compile(r'^(?:[a-eA-E]\)|\d+\))\s*\S')

# Recorte da página original (fallback garantidamente fiel — nunca corrompe a
# fórmula, é um raster literal do PDF) — resolução alta o bastante para a IA
# ler símbolos pequenos (frações, expoentes) e para o professor ampliar sem
# pixelar demais, mas sem disparar para toda página (custo controlado pela
# heurística acima, não pela resolução).
DPI_RECORTE_FORMULA = 220
MARGEM_RECORTE_FORMULA_PT = 6.0


class PdfSemTextoError(Exception):
    """Levantado quando o PDF não contém texto nativo extraível (ex.: digitalizado/imagem)."""


def _texto_da_linha(linha: dict) -> str:
    """Concatena os spans de uma linha, envolvendo em `$^{...}$`/`$_{...}$`
    qualquer span identificado como sobrescrito/subscrito — usa o bit de
    sobrescrito do PyMuPDF (`flags & 1`, confiável) e, como reforço/fallback
    para subscrito (sem bit dedicado), tamanho menor + deslocamento vertical
    em relação ao span dominante da linha (o de texto mais longo)."""
    spans = [s for s in linha["spans"] if s["text"]]
    if not spans:
        return ""

    spans_com_texto = [s for s in spans if s["text"].strip()]
    dominante = max(spans_com_texto, key=lambda s: len(s["text"])) if spans_com_texto else spans[0]
    tamanho_dominante = dominante["size"]
    y_dominante = dominante["origin"][1]

    partes = []
    for span in spans:
        texto = span["text"]
        tipo = None

        if span["flags"] & _SUPERSCRIPT_FLAG:
            tipo = "super"
        elif tamanho_dominante > 0 and span["size"] / tamanho_dominante < _RAZAO_TAMANHO_MAX:
            delta_y = span["origin"][1] - y_dominante
            if delta_y < -_DESLOCAMENTO_MINIMO_PT:
                tipo = "super"
            elif delta_y > _DESLOCAMENTO_MINIMO_PT:
                tipo = "sub"

        if tipo == "super":
            partes.append(f"$^{{{texto}}}$")
        elif tipo == "sub":
            partes.append(f"$_{{{texto}}}$")
        else:
            partes.append(texto)

    return "".join(partes)


def _bloco_e_formula_suspeita(bloco: dict, linhas_texto: list[str]) -> bool:
    """Sinaliza `bloco` (um bloco de TEXTO do PyMuPDF, já com sobre/subscrito
    marcado em `linhas_texto`) como "provável fórmula matemática 2D" — ver a
    justificativa de cada critério na docstring do módulo. Os 4 critérios são
    exigidos em conjunto para manter o custo controlado (só blocos realmente
    suspeitos disparam um recorte de imagem + revisão extra pela IA) e evitar
    falsos positivos óbvios (parágrafo largo com um "1º"/"2ª" solto)."""
    linhas_pymupdf = bloco["lines"]
    if len(linhas_pymupdf) < _MIN_LINHAS_FORMULA:
        return False

    if any(_PADRAO_PREFIXO_EXCLUIDO.match(linha.strip()) for linha in linhas_texto):
        return False  # lista de alternativas ou bloco de gabarito, não fórmula

    largura_bloco = bloco["bbox"][2] - bloco["bbox"][0]
    if largura_bloco > _LARGURA_MAXIMA_BLOCO_FORMULA_PT:
        return False

    media_caracteres = sum(len(linha) for linha in linhas_texto) / len(linhas_texto)
    if media_caracteres > _MEDIA_MAXIMA_CARACTERES_LINHA_FORMULA:
        return False

    texto_bloco = "".join(linhas_texto)
    tem_marcador_supsub = len(_PADRAO_SUPSUB_MARCADO.findall(texto_bloco)) >= _MIN_MARCADORES_SUPSUB_FORMULA
    tem_digito = any(ch.isdigit() for ch in texto_bloco)
    return tem_marcador_supsub or tem_digito


def _recortar_regiao_pagina(
    page: "fitz.Page",
    bbox: tuple[float, float, float, float],
    margem: float = MARGEM_RECORTE_FORMULA_PT,
    dpi: int = DPI_RECORTE_FORMULA,
) -> bytes:
    """Recorta `bbox` (+ margem) da página original em alta resolução — usado
    tanto como conteúdo visual enviado à IA (fonte de verdade para a
    transcrição LaTeX) quanto como fallback garantidamente fiel quando a
    transcrição não é confiável o bastante (ver `app.formula_resolve`).
    Nunca falha por "fórmula complexa demais": é um raster literal do PDF,
    não depende de entender a estrutura da fórmula."""
    x0, y0, x1, y1 = bbox
    rect = fitz.Rect(x0 - margem, y0 - margem, x1 + margem, y1 + margem) & page.rect
    pix = page.get_pixmap(clip=rect, dpi=dpi, alpha=False)
    return pix.tobytes(output="png")


def extrair_conteudo_pdf(data: bytes) -> tuple[str, dict[str, bytes]]:
    """Retorna (texto_com_placeholders, imagens) onde `imagens` mapeia
    'IMAGEM_01' -> bytes brutos da imagem (já no formato original, PNG/JPEG)
    e 'FORMULA_01' -> recorte PNG (alta resolução) de um bloco heuristicamente
    suspeito de ser uma fórmula matemática 2D (ver docstring do módulo e
    `_bloco_e_formula_suspeita`) — ambos os tipos de placeholder são tratados
    de forma idêntica pelo tokenizer (`formatting.py`) e pelos geradores de
    docx/pptx; só a IA (via `app.prompts`) e `app.formula_resolve` distinguem
    os dois propósitos."""
    doc = fitz.open(stream=data, filetype="pdf")
    partes_texto: list[str] = []
    imagens: dict[str, bytes] = {}
    contador_imagem = 0
    contador_formula = 0

    try:
        for page in doc:
            blocos = page.get_text("dict")["blocks"]
            blocos_ordenados = sorted(blocos, key=lambda b: (round(b["bbox"][1]), b["bbox"][0]))

            for bloco in blocos_ordenados:
                if bloco["type"] == 1:  # bloco de imagem
                    largura = bloco["bbox"][2] - bloco["bbox"][0]
                    altura = bloco["bbox"][3] - bloco["bbox"][1]
                    if largura * altura < AREA_MINIMA_IMAGEM_RELEVANTE:
                        continue  # decorativo (logo/QR code), ignora

                    contador_imagem += 1
                    image_id = f"IMAGEM_{contador_imagem:02d}"
                    imagens[image_id] = bloco["image"]
                    partes_texto.append(f"[{image_id}]")
                    continue

                # bloco de texto
                linhas = [_texto_da_linha(linha) for linha in bloco["lines"]]
                linhas = [linha for linha in linhas if linha.strip()]
                if not linhas:
                    continue

                if _bloco_e_formula_suspeita(bloco, linhas):
                    contador_formula += 1
                    formula_id = f"FORMULA_{contador_formula:02d}"
                    imagens[formula_id] = _recortar_regiao_pagina(page, bloco["bbox"])
                    partes_texto.append(f"[{formula_id}]")
                else:
                    partes_texto.append("\n".join(linhas))

            partes_texto.append("")  # quebra entre páginas
    finally:
        doc.close()

    texto = "\n".join(partes_texto)
    if not texto.strip():
        raise PdfSemTextoError(
            "PDF sem texto nativo extraível — pode ser digitalizado/imagem."
        )
    return texto, imagens
