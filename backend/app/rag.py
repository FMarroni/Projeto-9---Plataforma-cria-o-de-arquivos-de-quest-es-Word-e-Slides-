"""Épico 4 — Módulo Biblioteca: gerencia a coleção local de documentos (PDFs de
aula) usada como base de conhecimento opcional (RAG) para os comentários.

Ingestão: fatia o texto do PDF por página via PyMuPDF (já usado em
pdf_extract.py), agrupando parágrafos em chunks de até `_TAMANHO_MAX_CHUNK`
caracteres SEM nunca misturar conteúdo de páginas diferentes no mesmo chunk —
isso é o que garante a citação exata de arquivo+página na rastreabilidade
(Épico 4, item 4). Cada chunk vira um vetor no ChromaDB (embedding local via
onnxruntime, sem custo de API), com metadados {doc_id, arquivo, pagina}.

Uso opcional: se nenhum documento for selecionado pelo usuário na extração
(ver app/comments.py), este módulo simplesmente não é chamado — o pipeline
continua funcionando exatamente como antes do Épico 4."""

import json
import os
import uuid

import chromadb
import fitz  # PyMuPDF

from app import config

_TAMANHO_MAX_CHUNK = 1500  # chars — mesmo tamanho usado como referência em outros pontos do projeto

_NOME_COLECAO = "biblioteca"
_cliente = None
_colecao = None


class PdfSemTextoError(Exception):
    """PDF de biblioteca sem texto nativo extraível (ex.: digitalizado/imagem)."""


def _obter_colecao():
    global _cliente, _colecao
    if _colecao is None:
        os.makedirs(config.VECTOR_DB_DIR, exist_ok=True)
        _cliente = chromadb.PersistentClient(path=config.VECTOR_DB_DIR)
        _colecao = _cliente.get_or_create_collection(_NOME_COLECAO)
    return _colecao


def _novo_doc_id() -> str:
    return uuid.uuid4().hex[:12]


def _carregar_metadados() -> list[dict]:
    caminho = config.BIBLIOTECA_METADATA_PATH
    if not os.path.exists(caminho):
        return []
    with open(caminho, encoding="utf-8") as f:
        return json.load(f)


def _salvar_metadados(documentos: list[dict]) -> None:
    os.makedirs(config.BIBLIOTECA_DIR, exist_ok=True)
    caminho = config.BIBLIOTECA_METADATA_PATH
    caminho_tmp = caminho + ".tmp"
    with open(caminho_tmp, "w", encoding="utf-8") as f:
        json.dump(documentos, f, ensure_ascii=False, indent=2)
    os.replace(caminho_tmp, caminho)


def _chunks_por_pagina(pdf_bytes: bytes) -> list[tuple[int, str]]:
    """Devolve [(numero_pagina, texto_chunk), ...], agrupando parágrafos
    (separados por linha em branco) até `_TAMANHO_MAX_CHUNK` caracteres — nunca
    junta texto de páginas diferentes no mesmo chunk."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    chunks: list[tuple[int, str]] = []
    try:
        for numero_pagina, page in enumerate(doc, start=1):
            texto_pagina = page.get_text("text").strip()
            if not texto_pagina:
                continue
            paragrafos = [p.strip() for p in texto_pagina.split("\n\n") if p.strip()]
            atual = ""
            for paragrafo in paragrafos:
                candidato = f"{atual}\n\n{paragrafo}" if atual else paragrafo
                if len(candidato) > _TAMANHO_MAX_CHUNK and atual:
                    chunks.append((numero_pagina, atual))
                    atual = paragrafo
                else:
                    atual = candidato
            if atual:
                chunks.append((numero_pagina, atual))
    finally:
        doc.close()
    return chunks


def adicionar_documento(nome_arquivo: str, pdf_bytes: bytes) -> dict:
    """Extrai, fatia e indexa o PDF; salva o arquivo original em disco para
    consulta/exclusão posterior. Levanta PdfSemTextoError se não houver texto
    nativo extraível (ex.: PDF digitalizado)."""
    chunks = _chunks_por_pagina(pdf_bytes)
    if not chunks:
        raise PdfSemTextoError(f"'{nome_arquivo}' não tem texto nativo extraível.")

    doc_id = _novo_doc_id()
    colecao = _obter_colecao()
    colecao.add(
        ids=[f"{doc_id}_{i}" for i in range(len(chunks))],
        documents=[texto for _, texto in chunks],
        metadatas=[{"doc_id": doc_id, "arquivo": nome_arquivo, "pagina": pagina} for pagina, _ in chunks],
    )

    os.makedirs(config.BIBLIOTECA_PDFS_DIR, exist_ok=True)
    with open(os.path.join(config.BIBLIOTECA_PDFS_DIR, f"{doc_id}.pdf"), "wb") as f:
        f.write(pdf_bytes)

    registro = {
        "doc_id": doc_id,
        "nome_arquivo": nome_arquivo,
        "n_paginas": max(pagina for pagina, _ in chunks),
        "n_chunks": len(chunks),
    }
    documentos = _carregar_metadados()
    documentos.append(registro)
    _salvar_metadados(documentos)
    return registro


def listar_documentos() -> list[dict]:
    return _carregar_metadados()


def remover_documento(doc_id: str) -> bool:
    """Remove o documento (metadados + vetores + PDF salvo). Devolve False se
    `doc_id` não existir na biblioteca."""
    documentos = _carregar_metadados()
    restantes = [d for d in documentos if d["doc_id"] != doc_id]
    if len(restantes) == len(documentos):
        return False

    _obter_colecao().delete(where={"doc_id": doc_id})

    caminho_pdf = os.path.join(config.BIBLIOTECA_PDFS_DIR, f"{doc_id}.pdf")
    if os.path.exists(caminho_pdf):
        os.remove(caminho_pdf)

    _salvar_metadados(restantes)
    return True


def buscar_trechos_relevantes(query: str, doc_ids: list[str], top_k: int = config.RAG_TOP_K) -> list[dict]:
    """Devolve até `top_k` trechos ({arquivo, pagina, texto}) mais relevantes
    para `query`, restritos aos documentos em `doc_ids` — lista vazia se
    `doc_ids` estiver vazio ou não houver nenhum resultado (ex.: coleção sem
    esses documentos, texto de busca vazio)."""
    if not doc_ids or not query.strip():
        return []

    colecao = _obter_colecao()
    where = {"doc_id": {"$in": doc_ids}} if len(doc_ids) > 1 else {"doc_id": doc_ids[0]}
    resultado = colecao.query(query_texts=[query], n_results=top_k, where=where)

    documentos = (resultado.get("documents") or [[]])[0]
    metadatas = (resultado.get("metadatas") or [[]])[0]
    return [
        {"arquivo": meta["arquivo"], "pagina": meta["pagina"], "texto": texto}
        for texto, meta in zip(documentos, metadatas)
    ]
