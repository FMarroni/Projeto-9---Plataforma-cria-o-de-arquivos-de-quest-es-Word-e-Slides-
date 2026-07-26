"""Tokenizador de texto rico (markdown-lite + LaTeX básico), portado de
`Subsídios/Códigos de outros projetos que podem ser úteis/Projeto 1 - pptx_builder.py`.

Este módulo é agnóstico de biblioteca (não importa python-docx nem python-pptx):
ele só devolve uma lista de `Token`s com flags de estilo (incluindo tokens de
imagem, para os placeholders [IMAGEM_NN] inseridos por `pdf_extract.py`). Cada
gerador (`docx_render.py`, `pptx_gen.py`) decide como aplicar essas flags com
a API da sua própria biblioteca (docx: `run.font.superscript`/`subscript`
nativos + `run.add_picture`; pptx: o hack de XML `baseline` em
`pptx_xml_utils.py` + `adicionar_imagem_slide`).
"""

import re
from dataclasses import dataclass, field

# Dicionário para traduzir comandos LaTeX em Unicode compatível com fontes comuns.
# Copiado verbatim do legado — a ordem de aplicação (mais longo primeiro) é essencial
# para não corromper comandos compostos como \not\subseteq (ver tokenize_rich_text).
LATEX_TO_UNICODE = {
    # Letras Gregas Minúsculas
    r'\alpha': 'α', r'\beta': 'β', r'\gamma': 'γ', r'\delta': 'δ', r'\epsilon': 'ε',
    r'\zeta': 'ζ', r'\eta': 'η', r'\theta': 'θ', r'\iota': 'ι', r'\kappa': 'κ',
    r'\lambda': 'λ', r'\mu': 'μ', r'\nu': 'ν', r'\xi': 'ξ', r'\pi': 'π',
    r'\rho': 'ρ', r'\sigma': 'σ', r'\tau': 'τ', r'\upsilon': 'υ', r'\phi': 'φ',
    r'\chi': 'χ', r'\psi': 'ψ', r'\omega': 'ω', r'\varepsilon': 'ε', r'\varphi': 'φ',

    # Letras Gregas Maiúsculas
    r'\Gamma': 'Γ', r'\Delta': 'Δ', r'\Theta': 'Θ', r'\Lambda': 'Λ', r'\Xi': 'Ξ',
    r'\Pi': 'Π', r'\Sigma': 'Σ', r'\Upsilon': 'Υ', r'\Phi': 'Φ', r'\Psi': 'Ψ', r'\Omega': 'Ω',

    # Lógica Proposicional
    r'\neg': '¬', r'\lnot': '¬',
    r'\land': '∧', r'\wedge': '∧',
    r'\lor': '∨', r'\vee': '∨',
    r'\oplus': '⊕', r'\xor': '⊕',
    r'\to': '→', r'\rightarrow': '→', r'\Rightarrow': '⇒',
    r'\gets': '←', r'\leftarrow': '←', r'\Leftarrow': '⇐',
    r'\leftrightarrow': '↔', r'\Leftrightarrow': '⇔', r'\iff': '⇔',
    r'\implies': '⇒', r'\impliedby': '⇐',
    r'\therefore': '∴', r'\because': '∵',
    r'\vdash': '⊢', r'\dashv': '⊣', r'\models': '⊨',
    r'\top': '⊤', r'\bot': '⊥',
    r'\tautology': '⊤', r'\contradiction': '⊥',

    # Quantificadores e Predicados
    r'\forall': '∀', r'\exists!': '∃!', r'\exists': '∃', r'\nexists': '∄',
    r'\suchthat': '|', r'\st': '|',
    r'\mid': '|', r'\colon': ':',

    # Teoria dos Conjuntos
    r'\infty': '∞',
    r'\not\subseteq': '⊈', r'\not\supseteq': '⊉',
    r'\not\subset': '⊄', r'\not\supset': '⊅',
    r'\nsubseteq': '⊈', r'\nsupseteq': '⊉',
    r'\nsubset': '⊄', r'\nsupset': '⊅',
    r'\subseteq': '⊆', r'\supseteq': '⊇',
    r'\subsetneq': '⊊', r'\supsetneq': '⊋',
    r'\subset': '⊂', r'\supset': '⊃',
    r'\notin': '∉', r'\not\in': '∉',
    r'\not': '¬',
    r'\in': '∈', r'\ni': '∋', r'\owns': '∋',
    r'\cup': '∪', r'\union': '∪',
    r'\cap': '∩', r'\intersect': '∩',
    r'\setminus': '∖', r'\backslash': '∖',
    r'\emptyset': '∅', r'\varnothing': '∅',
    r'\mathbb{N}': 'ℕ', r'\mathbb{Z}': 'ℤ', r'\mathbb{Q}': 'ℚ',
    r'\mathbb{R}': 'ℝ', r'\mathbb{C}': 'ℂ',
    r'\mathcal{P}': '℘', r'\wp': '℘',
    r'\cartesian': '×',

    # Operadores Relacionais
    r'\leqslant': '≤', r'\geqslant': '≥',
    r'\leq': '≤', r'\geq': '≥', r'\le': '≤', r'\ge': '≥',
    r'\neq': '≠', r'\ne': '≠', r'\equiv': '≡',
    r'\approx': '≈', r'\cong': '≅', r'\simeq': '≃', r'\sim': '∼',
    r'\propto': '∝',
    r'\ll': '≪', r'\gg': '≫',
    r'\preceq': '≼', r'\succeq': '≽',
    r'\prec': '≺', r'\succ': '≻',

    # Operadores Aritméticos e Algébricos
    r'\cdot': '·', r'\times': '×', r'\div': '÷', r'\pm': '±', r'\mp': '∓',
    r'\ast': '∗', r'\star': '⋆', r'\circledast': '⊛', r'\circ': '∘', r'\bullet': '•',
    r'\sum': '∑', r'\prod': '∏', r'\coprod': '∐',
    r'\int': '∫', r'\iint': '∫∫', r'\iiint': '∫∫∫',
    r'\oint': '∮',
    r'\partial': '∂', r'\nabla': '∇',
    r'\sqrt': '√',

    # Símbolos Matemáticos Diversos
    r'\aleph': 'ℵ',
    r'\angle': '∠', r'\perp': '⊥', r'\parallel': '∥',
    r'\degree': '°',
    r'\triangle': '△', r'\square': '□',
    r'\ldots': '…', r'\cdots': '⋯', r'\vdots': '⋮', r'\ddots': '⋱',
    r'\prime': '′', r'\doubleprime': '″',
    r'\Re': 'ℜ', r'\Im': 'ℑ',
    r'\left|': '|', r'\right|': '|',
    r'\lfloor': '⌊', r'\rfloor': '⌋',
    r'\lceil': '⌈', r'\rceil': '⌉',
}

_LATEX_ITEMS_LONGEST_FIRST = sorted(
    LATEX_TO_UNICODE.items(), key=lambda item: len(item[0]), reverse=True
)

_SPLIT_PATTERN = re.compile(
    # dois sinais para não confundir "R$ 200,00" (moeda) com abertura de modo
    # matemático: (1) "$" colado logo depois de um "R" (o símbolo do Real
    # brasileiro é sempre "R$", nunca hífen entre eles) e (2) "$" seguido de
    # dígito (com ou sem espaço) — típico de valor monetário, nunca de LaTeX.
    # Isso preserva casos como "x$^{2}$" (variável colada no "$", sem dígito
    # logo depois) que o pdf_extract.py gera para expoentes/índices.
    # "[IMAGEM_NN]"/"[FORMULA_NN]" são tratados de forma idêntica aqui (ambos
    # viram um Token is_image) — a distinção entre "imagem de conteúdo" e
    # "recorte de fórmula suspeita" só importa para o prompt da IA e para
    # `app.formula_resolve` (ver pdf_extract.py), nunca para o tokenizer.
    r'(\[(?:IMAGEM|FORMULA)_\d+\]|(?<!R)\$\$(?!\s*\d).*?\$\$|(?<!R)\$(?!\s*\d).*?\$'
    r'|\*\*\*.*?\*\*\*|\*\*.*?\*\*|\*[^*\n]+?\*|_[^_\n]+_|\n)',
    flags=re.DOTALL,
)
_MATH_SUPSUB_PATTERN = re.compile(r'(\^\{.*?\}|\^.|_{.*?}|_.)')
_IMAGE_TOKEN_PATTERN = re.compile(r'^\[((?:IMAGEM|FORMULA)_\d+)\]$')


@dataclass
class Token:
    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    superscript: bool = False
    subscript: bool = False
    new_paragraph: bool = False
    is_image: bool = False
    image_id: str | None = None
    # V3: bloco de matemática $$...$$ ainda não resolvido — ver latex_render.py.
    # `resolver_tokens_equacao` transforma isto num Token is_image antes de
    # qualquer geração de docx/pptx acontecer (ou faz fallback para
    # tokenize_formula_unicode se a renderização falhar).
    is_equation: bool = False
    latex_formula: str | None = None
    # Sinaliza que este run deve sair na cor de marca (roxo) em vez da cor
    # padrão — usado no enunciado das questões (docx já faz isso via o
    # parâmetro `cor` de `inserir_paragrafo_tokenizado`; este flag existe para
    # o pptx, que escreve o slide inteiro num único `escrever_texto_formatado`
    # e por isso precisa da informação de cor por token, não por chamada).
    cor_marca: bool = False


def extrair_ids_imagem(texto: str) -> list[str]:
    """Devolve, em ordem, os IDs de imagem (ex.: 'IMAGEM_01', 'FORMULA_01')
    referenciados em `texto`."""
    return [m.group(1) for m in re.finditer(r'\[((?:IMAGEM|FORMULA)_\d+)\]', texto)]


def tokenize_formula_unicode(formula: str) -> list[Token]:
    """Conversão LaTeX->Unicode em linha (dicionário + sobre/subscrito via
    baseline) — usada para `$...$` (inline) e como fallback de
    `$$...$$` quando a renderização em imagem (latex_render.py) falha."""
    formula = formula.replace('\n', ' ')
    formula = re.sub(r'\\frac\{([^{}]+)\}\{([^{}]+)\}', r'\1/\2', formula)
    formula = re.sub(r'\\sqrt\{([^{}]+)\}', r'√(\1)', formula)

    for comando, simbolo in _LATEX_ITEMS_LONGEST_FIRST:
        formula = formula.replace(comando, simbolo)

    formula = formula.replace(r'\ ', ' ')

    tokens: list[Token] = []
    for parte in _MATH_SUPSUB_PATTERN.split(formula):
        if not parte:
            continue

        if parte.startswith('^{') and parte.endswith('}'):
            tokens.append(Token(text=parte[2:-1], italic=True, superscript=True))
        elif parte.startswith('^'):
            tokens.append(Token(text=parte[1:], italic=True, superscript=True))
        elif parte.startswith('_{') and parte.endswith('}'):
            tokens.append(Token(text=parte[2:-1], italic=True, subscript=True))
        elif parte.startswith('_'):
            tokens.append(Token(text=parte[1:], italic=True, subscript=True))
        else:
            tokens.append(Token(text=parte.replace('{', '').replace('}', ''), italic=True))

    return tokens


def tokenize_rich_text(texto: str) -> list[Token]:
    """Divide `texto` em tokens estilizados (bold/italic/underline/super/subscrito).

    `\n` vira um Token vazio com `new_paragraph=True` — o chamador decide como
    iniciar um novo parágrafo/linha na biblioteca de destino.
    """
    tokens: list[Token] = []

    for trecho in _SPLIT_PATTERN.split(texto):
        if not trecho:
            continue

        if trecho == '\n':
            tokens.append(Token(text='', new_paragraph=True))
            continue

        match_imagem = _IMAGE_TOKEN_PATTERN.match(trecho)
        if match_imagem:
            tokens.append(Token(text='', is_image=True, image_id=match_imagem.group(1)))
            continue

        if trecho.startswith('***') and trecho.endswith('***') and len(trecho) >= 6:
            tokens.append(Token(text=trecho[3:-3], bold=True, italic=True))
        elif trecho.startswith('**') and trecho.endswith('**') and len(trecho) >= 4:
            tokens.append(Token(text=trecho[2:-2], bold=True))
        elif trecho.startswith('*') and trecho.endswith('*') and len(trecho) >= 3:
            tokens.append(Token(text=trecho[1:-1], italic=True))
        elif trecho.startswith('_') and trecho.endswith('_') and len(trecho) >= 3:
            tokens.append(Token(text=trecho[1:-1], underline=True))
        elif trecho.startswith('$$') and trecho.endswith('$$') and len(trecho) >= 4:
            # bloco de matemática (display): renderizado como imagem (V3, ver
            # latex_render.py) em vez de substituição Unicode em linha —
            # necessário para estruturas 2D (frações aninhadas, integrais com
            # limites) que a conversão por dicionário não representa bem.
            tokens.append(Token(text='', is_equation=True, latex_formula=trecho[2:-2]))
        elif trecho.startswith('$') and trecho.endswith('$') and len(trecho) >= 2:
            tokens.extend(tokenize_formula_unicode(trecho[1:-1]))
        else:
            tokens.append(Token(text=trecho))

    return tokens
