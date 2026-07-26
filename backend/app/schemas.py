from pydantic import BaseModel, Field


class Alternativa(BaseModel):
    letra: str
    texto: str


class RastreabilidadeItem(BaseModel):
    """Épico 4 (Modo Restrito/RAG): qual alternativa/item foi fundamentado por
    qual arquivo+página do material de apoio — usado só em rastreabilidade.docx,
    NUNCA exposto em comentada.docx/slides.pptx (ver docx_rastreabilidade.py)."""

    alternativa: str
    arquivo: str
    pagina: str


class Formula(BaseModel):
    """Transcrição LaTeX estruturada de um marcador `[FORMULA_NN]` do
    enunciado (ver `pdf_extract.py` — marcador inserido para blocos com
    heurística de "fórmula matemática suspeita", cujo recorte da página
    original é anexado como imagem à chamada de IA para servir de fonte de
    verdade visual). `id` DEVE ser exatamente o mesmo id do marcador
    `[FORMULA_NN]` presente no enunciado desta questão — nunca um id
    inventado. Ver `app/formula_resolve.py` para a validação e a cadeia de
    fallback que decide se `latex` é de fato usado ou se o marcador é
    deixado intocado (resolvendo como o recorte fiel da imagem original)."""

    id: str
    latex: str
    display: bool = False
    pagina: int | None = None
    bbox: list[float] | None = None
    confidence: float = 1.0
    usar_recorte_original: bool = False


class Questao(BaseModel):
    numero: int
    id_tec: str | None = None
    banca: str
    orgao: str | None = None
    sub_orgao: str | None = None
    cargo: str | None = None
    ano: int | None = None
    materia: str
    assunto: str
    enunciado: str
    alternativas: list[Alternativa] = Field(default_factory=list)
    gabarito: str | None = None
    anulada: bool = False
    comentario: str | None = None
    rastreabilidade: list[RastreabilidadeItem] = Field(default_factory=list)
    formulas: list[Formula] = Field(default_factory=list)


class ExtractionResult(BaseModel):
    nome_concurso: str | None = None
    escolaridade: str | None = None
    bancas: list[str] = Field(default_factory=list)
    anos: list[int] = Field(default_factory=list)
    cargos: list[str] = Field(default_factory=list)
    questoes: list[Questao] = Field(default_factory=list)


class AssuntoStats(BaseModel):
    assunto: str
    n_questoes: int
    incidencia: float
    destaque_curva_abc: bool


class DisciplinaStats(BaseModel):
    nome: str
    total_questoes: int
    bancas: list[str]
    anos: list[int]
    assuntos: list[AssuntoStats]
    curva_abc_texto: str
    curva_abc_percentual: str
    questoes: list[Questao]


# JSON Schema (dict form) shared by all 3 providers for the structured extraction call.
# Kept as a plain dict (not Pydantic's auto schema) so each provider's quirks
# (OpenAI strict mode, Anthropic tool input_schema, Gemini response_schema) can
# all consume the exact same source of truth without provider-specific tweaks.
EXTRACTION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "nome_concurso": {"type": ["string", "null"]},
        "escolaridade": {"type": ["string", "null"]},
        "bancas": {"type": "array", "items": {"type": "string"}},
        "anos": {"type": "array", "items": {"type": "integer"}},
        "cargos": {"type": "array", "items": {"type": "string"}},
        "questoes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "numero": {"type": "integer"},
                    "id_tec": {"type": ["string", "null"]},
                    "banca": {"type": "string"},
                    "orgao": {"type": ["string", "null"]},
                    "sub_orgao": {"type": ["string", "null"]},
                    "cargo": {"type": ["string", "null"]},
                    "ano": {"type": ["integer", "null"]},
                    "materia": {"type": "string"},
                    "assunto": {"type": "string"},
                    "enunciado": {"type": "string"},
                    "alternativas": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "letra": {"type": "string"},
                                "texto": {"type": "string"},
                            },
                            "required": ["letra", "texto"],
                            "additionalProperties": False,
                        },
                    },
                    "gabarito": {"type": ["string", "null"]},
                    "anulada": {"type": "boolean"},
                    "formulas": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "latex": {"type": "string"},
                                "display": {"type": "boolean"},
                                "pagina": {"type": ["integer", "null"]},
                                "bbox": {
                                    "type": ["array", "null"],
                                    "items": {"type": "number"},
                                },
                                "confidence": {"type": "number"},
                                "usar_recorte_original": {"type": "boolean"},
                            },
                            "required": [
                                "id", "latex", "display", "pagina", "bbox",
                                "confidence", "usar_recorte_original",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": [
                    "numero", "id_tec", "banca", "orgao", "sub_orgao", "cargo", "ano",
                    "materia", "assunto", "enunciado", "alternativas", "gabarito", "anulada",
                    "formulas",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["nome_concurso", "escolaridade", "bancas", "anos", "cargos", "questoes"],
    "additionalProperties": False,
}
