"""Medição tipográfica + paginação determinística do corpo dos slides de
questão (`ph_corpo_questao`), substituindo a estimativa antiga baseada em
"70 caracteres por linha" / "13 linhas por slide" + autoajuste do PowerPoint
(`MSO_AUTO_SIZE.TEXT_TO_FIT_SHAPE`) como rede de segurança.

Por que a estimativa antiga estourava ou sobrava espaço: ela contava
CARACTERES, não largura visual — "iiiiiiiiiiiiiiii" e "WWWWWWWWWWWWWWWW" (mesmo
nº de caracteres) ocupam larguras completamente diferentes na tela, então o
orçamento de linhas era só uma média grosseira, com folga de segurança embutida
(daí o espaço em branco sobrando) e ainda assim sem garantia contra estouro em
casos adversos (texto muito "largo") — daí depender do autoajuste do
PowerPoint como última linha de defesa, que ou encolhe demais a fonte ou
diverge entre PowerPoint/LibreOffice.

A abordagem aqui:
  1. Geometria REAL da caixa (`TextLayoutConfig.from_shape`) — largura/altura
     úteis vêm do próprio shape do template, não de números repetidos no código.
  2. Fonte REAL (Montserrat, a mesma gravada nos runs do PPTX — ver
     `assets/fonts/Montserrat/`) usada tanto para medir quanto para gravar.
  3. Medição por MÉTRICA DE GLIFO (FreeType, via matplotlib.ft2font) — não
     contagem de caracteres — cacheada (`functools.lru_cache`) porque as
     mesmas palavras (concordância verbal, artigos, jargão jurídico) se
     repetem muito entre questões.
  4. Quebra de linha (`_simular_linhas`) é uma SIMULAÇÃO usada só para decidir
     quantas linhas um parágrafo ocupa e, quando necessário, ONDE cortá-lo —
     o PPTX final continua confiando no word-wrap nativo do PowerPoint
     (`text_frame.word_wrap = True`), nunca grava quebra de linha manual.
  5. Paginação por CURSOR VERTICAL (`paginar_blocos`) que nunca deixa um bloco
     maior que a página inteira ser inserido sem fragmentação, e evita deixar
     rótulos curtos ("Gabarito:", "Comentário:") isolados quando o bloco
     seguinte poderia acompanhá-los (`LayoutBlock.keep_with_next`) — mas
     permite que um parágrafo NARRATIVO longo (`keep_together=False`) seja
     fatiado sempre que sobrar espaço no slide atual, para não desperdiçar área.
"""

import logging
import math
import re
from dataclasses import dataclass, field, replace
from functools import lru_cache

from matplotlib import font_manager
from matplotlib.ft2font import FT2Font

from app import config
from app.formatting import Token

logger = logging.getLogger(__name__)

# --- Fonte -------------------------------------------------------------------
# Mesma família gravada nos runs do PPTX (ver scripts/build_templates.py
# FONTE_UI_PPTX e pptx_gen.py) — instâncias estáticas OFL distribuídas com o
# projeto (ver assets/fonts/Montserrat/NOTICE.txt), para que a medição use
# exatamente a mesma fonte que será gravada no arquivo final.
FONTE_CORPO = "Montserrat"
TAMANHO_FONTE_CORPO_PT = 16.0

# Fração da altura útil realmente orçada para texto — reserva uma folga contra
# diferenças de renderização entre motores (PowerPoint/LibreOffice calculam
# "espaçamento simples" a partir das métricas verticais da fonte de formas
# ligeiramente diferentes; isto absorve essa variação sem depender de
# encolhimento automático de fonte).
MARGEM_SEGURANCA_VERTICAL = 0.94

_ARQUIVOS_FONTE = {
    (False, False): "Montserrat-Regular.ttf",
    (True, False): "Montserrat-Bold.ttf",
    (False, True): "Montserrat-Italic.ttf",
    (True, True): "Montserrat-BoldItalic.ttf",
}


def _registrar_fontes() -> None:
    """Registra os 4 estilos estáticos de Montserrat no font_manager do
    matplotlib. Melhor esforço: se os arquivos não existirem (instalação
    corrompida/incompleta), loga um aviso e segue — `_resolver_caminho_fonte`
    cai para o fallback padrão do matplotlib (DejaVu Sans) automaticamente,
    então a geração nunca quebra por causa da fonte."""
    for nome_arquivo in _ARQUIVOS_FONTE.values():
        caminho = f"{config.MONTSERRAT_FONTS_DIR}/{nome_arquivo}"
        try:
            font_manager.fontManager.addfont(caminho)
        except Exception:
            logger.warning(
                "Não foi possível carregar %s — medindo com o fallback do "
                "matplotlib (DejaVu Sans) em vez de Montserrat. O PPTX "
                "continua gravando 'Montserrat' nos runs; se essa fonte não "
                "estiver instalada em quem abrir o arquivo, a substituição "
                "visual fica a cargo do próprio PowerPoint/LibreOffice.",
                caminho,
                exc_info=True,
            )


_registrar_fontes()


@lru_cache(maxsize=8)
def _resolver_caminho_fonte(bold: bool, italic: bool) -> str:
    """Caminho do arquivo de fonte a usar para medir um texto bold/italic —
    resolvido via matplotlib (que cai para DejaVu Sans sozinho se Montserrat
    não estiver registrada), nunca hard-coded, para que medição e fallback
    fiquem sempre consistentes entre si."""
    fp = font_manager.FontProperties(
        family=FONTE_CORPO,
        weight="bold" if bold else "normal",
        style="italic" if italic else "normal",
    )
    return font_manager.findfont(fp)


@lru_cache(maxsize=8)
def _fonte_ft2(caminho: str) -> FT2Font:
    return FT2Font(caminho)


@lru_cache(maxsize=8192)
def largura_texto_pt(texto: str, bold: bool, italic: bool, tamanho_pt: float) -> float:
    """Largura tipográfica real (em pt) de `texto`, medida por métrica de
    glifo (FreeType) — não por contagem de caracteres. Distingue corretamente
    'iiiiiiiiiiiiiiii' de 'WWWWWWWWWWWWWWWW' (mesmo nº de caracteres, larguras
    bem diferentes) e conta espaços normalmente. Cacheada: o mesmo fragmento
    (palavra/espaço) se repete muito entre questões."""
    if not texto:
        return 0.0
    fonte = _fonte_ft2(_resolver_caminho_fonte(bold, italic))
    fonte.set_size(tamanho_pt, 72)  # dpi=72 -> 1pt = 1 "pixel" nas unidades do FT2Font
    fonte.set_text(texto, 0)
    largura, _altura = fonte.get_width_height()
    return largura / 64.0  # FT2Font devolve 26.6 fixed point


@lru_cache(maxsize=1)
def _metricas_verticais_fonte_regular() -> tuple[int, int]:
    fonte = _fonte_ft2(_resolver_caminho_fonte(False, False))
    return fonte.height, fonte.units_per_EM


def altura_linha_pt(tamanho_pt: float = TAMANHO_FONTE_CORPO_PT) -> float:
    """Altura de uma linha "espaçamento simples" (100% — confirmado no
    próprio template, ver `slide_master` -> `p:txStyles/p:bodyStyle/a:lvl1pPr`:
    `lnSpc=100%`, `spcBef=spcAft=0`), calculada a partir das métricas verticais
    reais da fonte (ascender+descender+line gap), não de um multiplicador
    arbitrário tipo "1.2x" — usa sempre o estilo Regular como referência
    porque só o TAMANHO da fonte muda a altura de linha aqui (peso/itálico não)."""
    altura_fonte, units_per_em = _metricas_verticais_fonte_regular()
    return (altura_fonte / units_per_em) * tamanho_pt


# --- Geometria da caixa --------------------------------------------------------


@dataclass(frozen=True)
class TextLayoutConfig:
    largura_util_pt: float
    altura_util_pt: float
    tamanho_fonte_pt: float = TAMANHO_FONTE_CORPO_PT
    altura_linha_pt: float = 0.0

    def __post_init__(self):
        if not self.altura_linha_pt:
            object.__setattr__(self, "altura_linha_pt", altura_linha_pt(self.tamanho_fonte_pt))

    @classmethod
    def from_shape(
        cls,
        shape,
        *,
        tamanho_fonte_pt: float = TAMANHO_FONTE_CORPO_PT,
        margem_seguranca_vertical: float = MARGEM_SEGURANCA_VERTICAL,
    ) -> "TextLayoutConfig":
        """Deriva largura/altura úteis da geometria REAL do shape (não de
        números repetidos no código) — descontando as margens internas do
        próprio text_frame, exatamente como o PowerPoint faz."""
        tf = shape.text_frame
        largura_util = shape.width.pt - tf.margin_left.pt - tf.margin_right.pt
        altura_bruta = shape.height.pt - tf.margin_top.pt - tf.margin_bottom.pt
        return cls(
            largura_util_pt=largura_util,
            altura_util_pt=altura_bruta * margem_seguranca_vertical,
            tamanho_fonte_pt=tamanho_fonte_pt,
        )


# --- Fragmentação de tokens para word-wrap -------------------------------------

_PADRAO_FRAGMENTO = re.compile(r"\S+|\s+")


def _fragmentar_token(token: Token) -> list[Token]:
    """Quebra `token.text` em fragmentos (palavras e sequências de espaço),
    cada um herdando os estilos do token original — nunca perde nem duplica
    caractere (a concatenação dos fragmentos, em ordem, reconstrói o texto
    original exatamente)."""
    if not token.text:
        return [token]
    return [replace(token, text=parte) for parte in _PADRAO_FRAGMENTO.findall(token.text)]


def _fatiar_por_caractere(token: Token, largura_util_pt: float, tamanho_pt: float) -> list[Token]:
    """Último recurso (requisito 4/6): uma palavra (ou sequência sem espaços)
    maior que a largura útil inteira é fatiada caractere a caractere até
    caber — preserva todos os caracteres, só deixa de respeitar fronteira de
    palavra (inevitável: não há espaço nenhum para quebrar)."""
    pedacos: list[Token] = []
    atual = ""
    for ch in token.text:
        candidato = atual + ch
        if atual and largura_texto_pt(candidato, token.bold, token.italic, tamanho_pt) > largura_util_pt:
            pedacos.append(replace(token, text=atual))
            atual = ch
        else:
            atual = candidato
    if atual:
        pedacos.append(replace(token, text=atual))
    return pedacos


def _simular_linhas(tokens: list[Token], config_layout: TextLayoutConfig) -> list[list[Token]]:
    """Word-wrap guloso: enche cada linha simulada enquanto os fragmentos
    couberem na largura útil; ao estourar, inicia nova linha. É uma SIMULAÇÃO
    (usada para orçar altura e decidir pontos de corte) — o PPTX gravado não
    grava quebra manual, confia no word-wrap nativo do PowerPoint (ver
    docstring do módulo). Parágrafo vazio -> 1 linha vazia (continua
    consumindo altura real, nunca é ignorado)."""
    fragmentos: list[Token] = []
    for token in tokens:
        fragmentos.extend(_fragmentar_token(token))

    if not fragmentos:
        return [[]]

    largura_util = config_layout.largura_util_pt
    tamanho_pt = config_layout.tamanho_fonte_pt

    linhas: list[list[Token]] = []
    linha: list[Token] = []
    largura_linha = 0.0

    for frag in fragmentos:
        largura_frag = largura_texto_pt(frag.text, frag.bold, frag.italic, tamanho_pt)

        if largura_frag > largura_util and frag.text.strip():
            for pedaco in _fatiar_por_caractere(frag, largura_util, tamanho_pt):
                largura_pedaco = largura_texto_pt(pedaco.text, pedaco.bold, pedaco.italic, tamanho_pt)
                if linha and largura_linha + largura_pedaco > largura_util:
                    linhas.append(linha)
                    linha, largura_linha = [], 0.0
                linha.append(pedaco)
                largura_linha += largura_pedaco
            continue

        if linha and largura_linha + largura_frag > largura_util:
            linhas.append(linha)
            linha, largura_linha = [], 0.0

        linha.append(frag)
        largura_linha += largura_frag

    linhas.append(linha)
    return linhas


# --- Blocos semânticos e paginação ---------------------------------------------


@dataclass
class LayoutBlock:
    """Unidade semântica de conteúdo (um parágrafo, ou uma imagem/equação já
    resolvida) que `paginar_blocos` distribui entre slides.

    `keep_together`: True (padrão) = só é fragmentado se for maior que uma
    página vazia inteira (ex.: uma alternativa) — do contrário, se não couber
    no espaço restante, o bloco INTEIRO vai para a próxima página. False =
    texto narrativo (enunciado, comentário): pode ser fatiado sempre que
    sobrar espaço no slide atual, para aproveitar a área disponível em vez de
    deixá-la em branco.

    `keep_with_next`: nunca deixar este bloco como o único conteúdo "novo" no
    fim de um slide — usado nos rótulos curtos "Gabarito:"/"Comentário:", que
    não podem ficar sozinhos separados do que vêm a seguir.
    """

    tokens: list[Token] = field(default_factory=list)
    is_image: bool = False
    image_id: str | None = None
    keep_together: bool = True
    keep_with_next: bool = False
    # Altura REAL (pt) que este bloco de imagem vai ocupar quando desenhado —
    # só usada quando `is_image=True`. Quando None (imagem de conteúdo comum:
    # gráfico/tabela/foto do PDF, ver pptx_gen._resolver_equacoes_dos_blocos),
    # preserva o comportamento histórico: a imagem sempre recebe uma página
    # exclusiva (ela costuma ser grande o bastante para justificar isso).
    # Quando definida (fórmula renderizada — EQUACAO_/FORMULA_, tipicamente
    # pequena), o bloco passa a ser tratado como qualquer outro bloco de
    # altura conhecida: flui com o texto ao redor na mesma página quando cabe,
    # em vez de sempre forçar uma página só para ela (requisito: nunca deixar
    # um slide "só fórmula" órfão quando o texto vizinho caberia junto).
    altura_natural_pt: float | None = None


def _anexar(pagina: list[Token], tokens: list[Token]) -> list[Token]:
    if not tokens:
        return pagina
    if pagina:
        return [*pagina, Token(text="", new_paragraph=True), *tokens]
    return list(tokens)


def _altura_lookahead_pt(blocos: list[LayoutBlock], i: int, config_layout: TextLayoutConfig) -> float:
    """Altura extra que `keep_with_next` exige ver disponível ALÉM do próprio
    bloco `i`: os parágrafos em branco que vierem logo a seguir (cada um 1
    linha) mais a primeira linha do próximo bloco com conteúdo real — sem
    isso, um rótulo como "Gabarito:" ficaria satisfeito só de caber ele
    mesmo, mesmo que o que vem depois (o que realmente importa manter junto)
    não tivesse mais nenhum espaço sobrando."""
    extra = 0.0
    j = i + 1
    while j < len(blocos) and not blocos[j].is_image and not blocos[j].tokens:
        extra += config_layout.altura_linha_pt
        j += 1
    if j < len(blocos) and not blocos[j].is_image:
        extra += config_layout.altura_linha_pt
    return extra


def paginar_blocos(blocos: list[LayoutBlock], config_layout: TextLayoutConfig) -> list[list[Token]]:
    """Distribui `blocos` entre páginas (cada página = lista de Tokens pronta
    para `escrever_texto_formatado`), usando um cursor vertical baseado na
    altura real de cada bloco (linhas simuladas × altura de linha):

      1. bloco cabe inteiro no espaço restante da página atual (e, se
         `keep_with_next`, sobra pelo menos 1 linha do próximo bloco também)
         -> anexa e avança;
      2. não cabe, mas é `keep_together=True` (alternativa, rótulo) e caberia
         inteiro numa página vazia -> fecha a página atual e tenta de novo
         (preserva o bloco inteiro, nunca fragmenta algo que "cabia");
      3. não cabe, e é `keep_together=False` (texto narrativo: enunciado,
         comentário) -> FRAGMENTA para preencher o espaço restante agora, em
         vez de adiar o bloco inteiro — é isso que aproveita o espaço sobrando
         depois de um rótulo curto ("Gabarito:"/"Comentário:") em vez de
         deixá-lo sozinho no slide;
      4. maior que uma página vazia inteira (qualquer bloco, mesmo
         `keep_together=True`, ex.: uma alternativa gigantesca) -> cai na
         mesma fragmentação do item 3 — nunca insere um bloco inteiro sabendo
         que ele não cabe.

    Nunca cria página vazia (só avança o cursor quando há conteúdo real a
    inserir) e nunca perde/duplica conteúdo (cada fragmento de cada bloco é
    escrito exatamente uma vez, na ordem original)."""
    blocos = list(blocos)  # cópia local: esta função substitui blocos[i] internamente
    paginas: list[list[Token]] = []
    pagina: list[Token] = []
    altura_usada = 0.0

    i = 0
    while i < len(blocos):
        bloco = blocos[i]

        if bloco.is_image and bloco.altura_natural_pt is None:
            # imagem de conteúdo comum (gráfico/tabela/foto) — comportamento
            # histórico preservado: sempre página exclusiva.
            if pagina:
                paginas.append(pagina)
                pagina, altura_usada = [], 0.0
            paginas.append([Token(text="", is_image=True, image_id=bloco.image_id)])
            i += 1
            continue

        if bloco.is_image:
            # fórmula renderizada (altura natural conhecida) — bloco de
            # altura conhecida como outro qualquer: flui com o texto ao redor
            # quando cabe, só avança de página quando realmente não cabe mais
            # no espaço restante (nunca fragmentada — uma imagem não pode ser
            # cortada ao meio).
            imagem_token = Token(text="", is_image=True, image_id=bloco.image_id)
            altura_bloco = bloco.altura_natural_pt
            espaco_restante = config_layout.altura_util_pt - altura_usada

            if altura_bloco <= espaco_restante:
                pagina = _anexar(pagina, [imagem_token])
                altura_usada += altura_bloco
                i += 1
                continue

            if pagina:
                paginas.append(pagina)
                pagina, altura_usada = [], 0.0
            # mesmo maior que uma página vazia inteira (caso extremo, não
            # fragmentável): insere mesmo assim — nunca corta uma imagem.
            pagina = _anexar(pagina, [imagem_token])
            altura_usada = altura_bloco
            i += 1
            continue

        linhas = _simular_linhas(bloco.tokens, config_layout)
        altura_bloco = len(linhas) * config_layout.altura_linha_pt
        espaco_restante = config_layout.altura_util_pt - altura_usada
        cabe_em_pagina_vazia = altura_bloco <= config_layout.altura_util_pt

        # 1) cabe inteiro no espaço restante desta página?
        if altura_bloco <= espaco_restante:
            extra_lookahead = _altura_lookahead_pt(blocos, i, config_layout) if bloco.keep_with_next else 0.0
            if not pagina or altura_bloco + extra_lookahead <= espaco_restante:
                pagina = _anexar(pagina, bloco.tokens)
                altura_usada += altura_bloco
                i += 1
                continue
            # keep_with_next não satisfeito (o que vem depois ficaria sem
            # espaço) e a página já tem conteúdo -> força página nova, onde
            # o mesmo bloco sempre se encaixa (página vazia = espaço máximo)
            paginas.append(pagina)
            pagina, altura_usada = [], 0.0
            continue

        # 2) atômico e cabe inteiro numa página vazia, mas não no restante
        #    desta -- preserva-o inteiro na próxima página, não fragmenta
        if bloco.keep_together and cabe_em_pagina_vazia:
            paginas.append(pagina)
            pagina, altura_usada = [], 0.0
            continue  # reprocessa o mesmo bloco numa página vazia (sempre cabe)

        # 3)/4) fragmentação: narrativo que não coube no restante, OU
        # qualquer bloco maior que uma página vazia inteira
        if pagina and math.floor(espaco_restante / config_layout.altura_linha_pt) < 1:
            paginas.append(pagina)
            pagina, altura_usada = [], 0.0
            espaco_restante = config_layout.altura_util_pt

        n_linhas_cabem = max(1, math.floor(espaco_restante / config_layout.altura_linha_pt))
        linhas_agora, linhas_depois = linhas[:n_linhas_cabem], linhas[n_linhas_cabem:]
        tokens_agora = [frag for linha in linhas_agora for frag in linha]
        tokens_depois = [frag for linha in linhas_depois for frag in linha]

        pagina = _anexar(pagina, tokens_agora)
        if pagina:
            paginas.append(pagina)
        # bloco vazio (linha em branco dentro de um parágrafo narrativo, ex.:
        # uma quebra dupla no meio do comentário) -- `tokens_agora` fica vazio,
        # `_anexar` devolve `pagina` inalterada (vazia) e não há nada real a
        # inserir; sem este `if`, isso gerava uma página de conteúdo vazia
        # entre dois blocos de texto reais.
        pagina, altura_usada = [], 0.0

        blocos[i] = replace(bloco, tokens=tokens_depois)
        # não incrementa `i`: o restante do bloco (menor a cada volta) é
        # reprocessado no próximo laço, até caber inteiro numa página.

    if pagina:
        paginas.append(pagina)

    return paginas
