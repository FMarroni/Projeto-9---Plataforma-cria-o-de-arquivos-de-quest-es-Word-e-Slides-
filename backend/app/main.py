import asyncio
import logging
import mimetypes
import os

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from app import config, pipeline, prompt_store, rag, session_store

# O registro de mimetypes do Windows não conhece .webp por padrão — sem isso,
# a logo em frontend/assets/logo-branca.webp seria servida como
# application/octet-stream em vez de image/webp.
mimetypes.add_type("image/webp", ".webp")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Coruj.IA")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_tarefa_limpeza: asyncio.Task | None = None


async def _loop_limpeza_sessoes() -> None:
    """Roda em segundo plano pela vida inteira do processo, removendo sessões/
    arquivos com mais de SESSAO_TTL_HORAS a cada LIMPEZA_INTERVALO_SEGUNDOS —
    sem isso, `output/sessions/` e os arquivos gerados cresceriam
    indefinidamente em produção contínua até encher o disco."""
    while True:
        try:
            session_store.limpar_expirados(config.SESSAO_TTL_HORAS)
        except Exception:
            logger.exception("Falha ao limpar sessões/arquivos expirados")
        await asyncio.sleep(config.LIMPEZA_INTERVALO_SEGUNDOS)


@app.on_event("startup")
async def verificar_templates() -> None:
    for caminho in config.TEMPLATE_PATHS:
        if not os.path.exists(caminho):
            raise RuntimeError(
                f"Template obrigatório não encontrado: {caminho}. "
                "Rode backend/scripts/build_templates.py para gerá-lo."
            )
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)
    os.makedirs(config.SESSIONS_DIR, exist_ok=True)
    os.makedirs(config.BIBLIOTECA_DIR, exist_ok=True)

    global _tarefa_limpeza
    session_store.limpar_expirados(config.SESSAO_TTL_HORAS)  # limpa qualquer atraso já ao subir
    _tarefa_limpeza = asyncio.create_task(_loop_limpeza_sessoes())


@app.on_event("shutdown")
async def parar_limpeza_sessoes() -> None:
    if _tarefa_limpeza is not None:
        _tarefa_limpeza.cancel()


def _validar_requisicao(provider: str, api_key: str) -> None:
    if provider not in config.PROVIDERS_VALIDOS:
        raise HTTPException(
            400, f"Provedor desconhecido: '{provider}'. Use um de: {', '.join(config.PROVIDERS_VALIDOS)}."
        )
    if provider != "fake" and not api_key:
        raise HTTPException(400, "Chave de API é obrigatória para este provedor.")


@app.post("/api/gerar/stream")
async def gerar_stream(
    pdf: UploadFile = File(...),
    modo: str = Form("ia"),
    provider: str = Form(""),
    api_key: str = Form(""),
    model: str | None = Form(None),
    documentos_biblioteca: list[str] = Form([]),
):
    if modo not in ("ia", "script"):
        raise HTTPException(400, "Modo inválido. Use 'ia' (Com Comentários) ou 'script' (Sem Comentários, sem IA).")

    if modo == "ia":
        _validar_requisicao(provider, api_key)

    if (pdf.content_type not in ("application/pdf", "application/octet-stream")) and not (
        pdf.filename or ""
    ).lower().endswith(".pdf"):
        raise HTTPException(400, "Envie um arquivo PDF.")

    pdf_bytes = await pdf.read()
    if len(pdf_bytes) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"PDF maior que {config.MAX_UPLOAD_MB}MB.")

    if modo == "script":
        return EventSourceResponse(pipeline.executar_pipeline_script(pdf_bytes))

    return EventSourceResponse(
        pipeline.executar_pipeline_fresh(pdf_bytes, provider, api_key, model, documentos_biblioteca)
    )


@app.post("/api/retomar/stream")
async def retomar_stream(session_id: str = Form(...), api_key: str = Form("")):
    if not session_store.existe_sessao(session_id):
        raise HTTPException(404, f"Sessão '{session_id}' não encontrada.")

    return EventSourceResponse(pipeline.executar_pipeline_retomar(session_id, api_key))


class PromptComentarioBody(BaseModel):
    prompt: str


@app.get("/api/prompt/comentario")
async def obter_prompt_comentario():
    return {
        "prompt": prompt_store.obter_prompt(),
        "customizado": prompt_store.esta_customizado(),
        "prompt_padrao": prompt_store.obter_prompt_padrao(),
    }


@app.put("/api/prompt/comentario")
async def salvar_prompt_comentario(body: PromptComentarioBody):
    if not body.prompt.strip():
        raise HTTPException(400, "O prompt não pode ficar vazio.")
    prompt_store.salvar_prompt(body.prompt)
    return {"prompt": prompt_store.obter_prompt(), "customizado": True}


@app.delete("/api/prompt/comentario")
async def restaurar_prompt_comentario():
    prompt_store.restaurar_padrao()
    return {"prompt": prompt_store.obter_prompt(), "customizado": False}


@app.post("/api/biblioteca/upload")
async def upload_biblioteca(pdf: UploadFile = File(...)):
    if (pdf.content_type not in ("application/pdf", "application/octet-stream")) and not (
        pdf.filename or ""
    ).lower().endswith(".pdf"):
        raise HTTPException(400, "Envie um arquivo PDF.")

    pdf_bytes = await pdf.read()
    if len(pdf_bytes) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(400, f"PDF maior que {config.MAX_UPLOAD_MB}MB.")

    try:
        return rag.adicionar_documento(pdf.filename or "documento.pdf", pdf_bytes)
    except rag.PdfSemTextoError as e:
        raise HTTPException(400, str(e)) from e


@app.get("/api/biblioteca")
async def listar_biblioteca():
    return {"documentos": rag.listar_documentos()}


@app.delete("/api/biblioteca/{doc_id}")
async def excluir_biblioteca(doc_id: str):
    if not rag.remover_documento(doc_id):
        raise HTTPException(404, f"Documento '{doc_id}' não encontrado na biblioteca.")
    return {"removido": doc_id}


# StaticFiles exige que o diretório já exista NO MOMENTO EM QUE O MÓDULO É
# IMPORTADO (antes até do evento de "startup" rodar) — sem isso, um checkout
# limpo do projeto (sem nunca ter gerado nada em output/ ainda) derruba o
# processo na importação, com "RuntimeError: Directory ... does not exist".
os.makedirs(config.OUTPUT_DIR, exist_ok=True)

app.mount("/output", StaticFiles(directory=config.OUTPUT_DIR), name="output")
app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="frontend")
