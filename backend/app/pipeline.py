"""Orquestrador único do pipeline completo (Épico 2 + 3): extração -> Vision ->
comentários (Coruj.IA) -> geração dos 4 arquivos finais, emitindo progresso
incremental (consumido via SSE pelo frontend) tanto para uma execução nova a
partir de um PDF quanto para retomar uma sessão salva. Este módulo NÃO sabe
como um docx/pptx é montado por baixo dos panos — só fala com
`DocumentFormatterService` (Épico 3: Service Pattern)."""

import json
from collections.abc import AsyncIterator

from app import config, script_extract, session_store
from app.analysis import verificar_gabaritos
from app.comments import gerar_comentarios
from app.formula_resolve import resolver_formulas
from app.llm.base import LLMError, LLMProvider
from app.llm.factory import get_provider
from app.pdf_extract import PdfSemTextoError, extrair_conteudo_pdf
from app.schemas import ExtractionResult
from app.services.document_formatter import DocumentFormatterService

_formatter = DocumentFormatterService()


def _evento(tipo: str, dados: dict) -> dict:
    """Formato consumido pelo sse-starlette: {"event": ..., "data": <str>}."""
    return {"event": tipo, "data": json.dumps(dados, ensure_ascii=False)}


async def executar_pipeline_fresh(
    pdf_bytes: bytes,
    provider_nome: str,
    api_key: str,
    model: str | None,
    documentos_biblioteca: list[str] | None = None,
) -> AsyncIterator[dict]:
    session_id = session_store.novo_session_id()
    yield _evento("progresso", {"mensagem": f"Sessão {session_id} iniciada.", "session_id": session_id})

    try:
        yield _evento("progresso", {"mensagem": "Extraindo texto e imagens do PDF..."})
        texto, imagens = extrair_conteudo_pdf(pdf_bytes)
        yield _evento("progresso", {"mensagem": f"{len(imagens)} imagem(ns) encontrada(s) no PDF."})

        provider = get_provider(provider_nome)

        msg_vision = " (com Vision, imagens anexadas)" if imagens else ""
        yield _evento("progresso", {"mensagem": f"Enviando PDF para a IA (extração estruturada){msg_vision}..."})
        extraction = await provider.extrair(texto, api_key, model, imagens=list(imagens.values()))
        yield _evento("progresso", {"mensagem": f"{len(extraction.questoes)} questão(ões) extraída(s)."})

        if not extraction.questoes:
            yield _evento(
                "erro",
                {
                    "mensagem": (
                        "A IA não extraiu nenhuma questão deste PDF — nenhum arquivo foi gerado. "
                        "Isso costuma acontecer com PDFs muito longos/com muitas questões; tente "
                        "novamente, use outro provedor/modelo, ou divida o PDF em partes menores."
                    ),
                    "session_id": session_id,
                },
            )
            return

        # Resolve `Questao.formulas` (transcrições LaTeX estruturadas que a IA
        # devolveu para os marcadores [FORMULA_NN] — ver pdf_extract.py/
        # formula_resolve.py): substitui o marcador por $$...$$/$...$ quando a
        # transcrição passa validação, ou mantém o marcador intocado (resolve
        # como o recorte fiel da página original) caso contrário.
        extraction.questoes = resolver_formulas(extraction.questoes)

        for aviso in verificar_gabaritos(extraction.questoes):
            yield _evento("aviso", {"mensagem": aviso})

        session_store.salvar_imagens(session_id, imagens)
        session_store.salvar_estado(session_id, provider_nome, model, extraction, documentos_biblioteca)

        async for evento in _comentar_e_gerar(
            session_id, provider_nome, model, provider, api_key, extraction, imagens, documentos_biblioteca
        ):
            yield evento

    except PdfSemTextoError as e:
        yield _evento("erro", {"mensagem": str(e), "session_id": session_id})
    except LLMError as e:
        yield _evento("erro", {"mensagem": e.message, "status_code": e.status_code, "session_id": session_id})
    except Exception as e:  # noqa: BLE001 — qualquer falha inesperada vira evento de erro, não derruba o stream
        yield _evento("erro", {"mensagem": f"Erro inesperado: {e}", "session_id": session_id})


async def executar_pipeline_script(pdf_bytes: bytes) -> AsyncIterator[dict]:
    """Gera os 4 documentos sem nenhuma chamada de IA: a extração das questões
    usa `app.script_extract` (regras fixas do formato de export do TEC
    Concursos) em vez de um LLM, e nenhum comentário é gerado — por isso não
    precisa de provedor nem de chave de API. Sem retomada de sessão (o modo é
    síncrono/local e rápido o bastante para não precisar dessa resiliência)."""
    session_id = session_store.novo_session_id()
    yield _evento("progresso", {"mensagem": f"Sessão {session_id} iniciada (modo Sem Comentários/sem IA)."})

    try:
        yield _evento("progresso", {"mensagem": "Extraindo texto e imagens do PDF..."})
        texto, imagens = extrair_conteudo_pdf(pdf_bytes)
        yield _evento("progresso", {"mensagem": f"{len(imagens)} imagem(ns) encontrada(s) no PDF."})

        yield _evento("progresso", {"mensagem": "Reconhecendo questões (extração por regras, sem IA)..."})
        extraction = script_extract.extrair_estruturado(texto)
        yield _evento("progresso", {"mensagem": f"{len(extraction.questoes)} questão(ões) reconhecida(s)."})

        for aviso in verificar_gabaritos(extraction.questoes):
            yield _evento("aviso", {"mensagem": aviso})

        async for evento in _gerar_documentos(session_id, extraction, imagens):
            yield evento

    except PdfSemTextoError as e:
        yield _evento("erro", {"mensagem": str(e), "session_id": session_id})
    except script_extract.TextoNaoReconhecidoError as e:
        yield _evento("erro", {"mensagem": str(e), "session_id": session_id})
    except Exception as e:  # noqa: BLE001 — qualquer falha inesperada vira evento de erro, não derruba o stream
        yield _evento("erro", {"mensagem": f"Erro inesperado: {e}", "session_id": session_id})


async def executar_pipeline_retomar(session_id: str, api_key: str) -> AsyncIterator[dict]:
    try:
        if not session_store.existe_sessao(session_id):
            yield _evento("erro", {"mensagem": f"Sessão '{session_id}' não encontrada."})
            return

        provider_nome, model, extraction, documentos_biblioteca = session_store.carregar_estado(session_id)
        imagens = session_store.carregar_imagens(session_id)
        yield _evento(
            "progresso",
            {"mensagem": f"Sessão {session_id} retomada — {len(extraction.questoes)} questão(ões) carregada(s)."},
        )

        provider = get_provider(provider_nome)
        async for evento in _comentar_e_gerar(
            session_id, provider_nome, model, provider, api_key, extraction, imagens, documentos_biblioteca
        ):
            yield evento

    except LLMError as e:
        yield _evento("erro", {"mensagem": e.message, "status_code": e.status_code, "session_id": session_id})
    except Exception as e:  # noqa: BLE001
        yield _evento("erro", {"mensagem": f"Erro inesperado: {e}", "session_id": session_id})


async def _comentar_e_gerar(
    session_id: str,
    provider_nome: str,
    model: str | None,
    provider: LLMProvider,
    api_key: str,
    extraction: ExtractionResult,
    imagens: dict[str, bytes],
    documentos_biblioteca: list[str] | None = None,
) -> AsyncIterator[dict]:
    documentos_biblioteca = documentos_biblioteca or []
    msg_rag = " (Modo Restrito, base de conhecimento selecionada)" if documentos_biblioteca else ""
    yield _evento("progresso", {"mensagem": f"Gerando comentários (Coruj.IA){msg_rag}..."})
    async for msg in gerar_comentarios(
        extraction.questoes, provider, api_key, imagens, model, documentos_biblioteca
    ):
        # persiste a cada questão concluída — é isto que permite retomar depois de uma queda
        session_store.salvar_estado(session_id, provider_nome, model, extraction, documentos_biblioteca)
        yield _evento("progresso", {"mensagem": msg})

    async for evento in _gerar_documentos(session_id, extraction, imagens, documentos_biblioteca):
        yield evento


async def _gerar_documentos(
    session_id: str,
    extraction: ExtractionResult,
    imagens: dict[str, bytes],
    documentos_biblioteca: list[str] | None = None,
) -> AsyncIterator[dict]:
    """Gera os 4 arquivos finais (lista/comentada/análise/slides) — e, se a
    biblioteca foi usada, a rastreabilidade — a partir de um ExtractionResult
    já pronto (com ou sem comentário preenchido). Compartilhado pelos 3
    caminhos do pipeline (fresh/retomar com IA, e o modo sem IA)."""
    documentos_biblioteca = documentos_biblioteca or []
    prefixo = f"{config.OUTPUT_DIR}/{session_id}"

    yield _evento("progresso", {"mensagem": "Gerando DOCX (lista de questões)..."})
    _formatter.gerar_lista(extraction, imagens, f"{prefixo}_lista.docx")

    yield _evento("progresso", {"mensagem": "Gerando DOCX (questões comentadas)..."})
    _formatter.gerar_comentada(extraction, imagens, f"{prefixo}_comentada.docx")

    yield _evento("progresso", {"mensagem": "Gerando HTML (análise agregada)..."})
    _formatter.gerar_analise_html(extraction, f"{prefixo}_analise.html")

    yield _evento("progresso", {"mensagem": "Gerando slides (PPTX)..."})
    _formatter.gerar_slides(extraction, imagens, f"{prefixo}_slides.pptx")

    resultado = {
        "session_id": session_id,
        "lista_url": f"/output/{session_id}_lista.docx",
        "comentada_url": f"/output/{session_id}_comentada.docx",
        "analise_url": f"/output/{session_id}_analise.html",
        "slides_url": f"/output/{session_id}_slides.pptx",
        "total_questoes": len(extraction.questoes),
    }

    # rastreabilidade.docx (Épico 4) só é gerado quando a biblioteca foi
    # efetivamente usada — sem ela, a saída permanece idêntica à anterior ao
    # Épico 4 (4 arquivos, sem um 5º link vazio/irrelevante no resultado).
    if documentos_biblioteca:
        yield _evento("progresso", {"mensagem": "Gerando DOCX (rastreabilidade)..."})
        _formatter.gerar_rastreabilidade(extraction, f"{prefixo}_rastreabilidade.docx")
        resultado["rastreabilidade_url"] = f"/output/{session_id}_rastreabilidade.docx"

    yield _evento("concluido", resultado)
