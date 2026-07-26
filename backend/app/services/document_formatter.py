"""Fachada (Épico 3 — Service Pattern) que isola `pipeline.py`/`main.py` dos
detalhes sujos de manipulação do python-docx/python-pptx. O orquestrador só
conhece `DocumentFormatterService` — nunca importa `docx_lista`, `docx_comentada`,
`html_gen` ou `pptx_gen` diretamente, nem sabe como um slide é duplicado ou
como uma imagem é injetada."""

from app import config
from app.docx_comentada import gerar_docx_comentada
from app.docx_lista import gerar_docx_lista
from app.docx_rastreabilidade import gerar_docx_rastreabilidade
from app.html_gen import gerar_html
from app.pptx_gen import gerar_pptx
from app.schemas import ExtractionResult


class DocumentFormatterService:
    def __init__(
        self,
        lista_template_path: str = config.LISTA_TEMPLATE_PATH,
        comentada_template_path: str = config.COMENTADA_TEMPLATE_PATH,
        slides_template_path: str = config.SLIDES_TEMPLATE_PATH,
        rastreabilidade_template_path: str = config.RASTREABILIDADE_TEMPLATE_PATH,
    ):
        self._lista_template_path = lista_template_path
        self._comentada_template_path = comentada_template_path
        self._slides_template_path = slides_template_path
        self._rastreabilidade_template_path = rastreabilidade_template_path

    def gerar_lista(
        self, extraction: ExtractionResult, imagens: dict[str, bytes], saida_path: str
    ) -> str:
        return gerar_docx_lista(extraction, self._lista_template_path, saida_path, imagens)

    def gerar_comentada(
        self, extraction: ExtractionResult, imagens: dict[str, bytes], saida_path: str
    ) -> str:
        return gerar_docx_comentada(extraction, self._comentada_template_path, saida_path, imagens)

    def gerar_analise_html(self, extraction: ExtractionResult, saida_path: str) -> str:
        return gerar_html(extraction, saida_path)

    def gerar_slides(
        self, extraction: ExtractionResult, imagens: dict[str, bytes], saida_path: str
    ) -> str:
        return gerar_pptx(extraction, self._slides_template_path, saida_path, imagens)

    def gerar_rastreabilidade(self, extraction: ExtractionResult, saida_path: str) -> str:
        return gerar_docx_rastreabilidade(extraction, self._rastreabilidade_template_path, saida_path)
