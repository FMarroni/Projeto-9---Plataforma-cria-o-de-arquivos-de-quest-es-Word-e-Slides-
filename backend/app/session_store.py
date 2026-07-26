"""Persistência de sessão (Épico 2): salva o estado da extração (ExtractionResult,
já com os comentários preenchidos até onde o processamento chegou) e as imagens
extraídas do PDF em disco, para que o usuário possa 'Retomar Sessão' depois de
uma queda de conexão ou rate limit esgotado. NUNCA persiste a api_key."""

import json
import logging
import os
import re
import shutil
import time
import uuid

from app import config
from app.schemas import ExtractionResult

logger = logging.getLogger(__name__)

TTL_HORAS_PADRAO = 48
_PREFIXO_SESSION_ID = re.compile(r"^[0-9a-f]{12}_")


def novo_session_id() -> str:
    return uuid.uuid4().hex[:12]


def _session_dir(session_id: str) -> str:
    return os.path.join(config.SESSIONS_DIR, session_id)


def _session_json_path(session_id: str) -> str:
    return os.path.join(_session_dir(session_id), "sessao.json")


def _imagens_dir(session_id: str) -> str:
    return os.path.join(_session_dir(session_id), "imagens")


def salvar_imagens(session_id: str, imagens: dict[str, bytes]) -> None:
    pasta = _imagens_dir(session_id)
    os.makedirs(pasta, exist_ok=True)
    for image_id, dados in imagens.items():
        with open(os.path.join(pasta, f"{image_id}.bin"), "wb") as f:
            f.write(dados)


def carregar_imagens(session_id: str) -> dict[str, bytes]:
    pasta = _imagens_dir(session_id)
    if not os.path.isdir(pasta):
        return {}
    imagens: dict[str, bytes] = {}
    for nome in os.listdir(pasta):
        image_id = os.path.splitext(nome)[0]
        with open(os.path.join(pasta, nome), "rb") as f:
            imagens[image_id] = f.read()
    return imagens


def salvar_estado(
    session_id: str,
    provider: str,
    model: str | None,
    extraction: ExtractionResult,
    documentos_biblioteca: list[str] | None = None,
) -> None:
    """Grava o estado atual (write-then-rename, para nunca deixar um JSON
    truncado se o processo cair no meio da escrita). `documentos_biblioteca`
    (Épico 4 — Módulo Biblioteca) é a seleção de material de apoio usada nesta
    sessão; se omitido ao regravar (ex.: a cada questão comentada), preserva o
    valor já salvo anteriormente em vez de apagá-lo."""
    os.makedirs(_session_dir(session_id), exist_ok=True)
    if documentos_biblioteca is None and existe_sessao(session_id):
        with open(_session_json_path(session_id), encoding="utf-8") as f:
            documentos_biblioteca = json.load(f).get("documentos_biblioteca", [])
    estado = {
        "session_id": session_id,
        "provider": provider,
        "model": model,
        "extraction": extraction.model_dump(),
        "documentos_biblioteca": documentos_biblioteca or [],
    }
    caminho = _session_json_path(session_id)
    caminho_tmp = caminho + ".tmp"
    with open(caminho_tmp, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False, indent=2)
    os.replace(caminho_tmp, caminho)


def existe_sessao(session_id: str) -> bool:
    return os.path.exists(_session_json_path(session_id))


def carregar_estado(session_id: str) -> tuple[str, str | None, ExtractionResult, list[str]]:
    with open(_session_json_path(session_id), encoding="utf-8") as f:
        estado = json.load(f)
    extraction = ExtractionResult.model_validate(estado["extraction"])
    return estado["provider"], estado.get("model"), extraction, estado.get("documentos_biblioteca", [])


def remover_sessao(session_id: str) -> None:
    pasta = _session_dir(session_id)
    if os.path.isdir(pasta):
        shutil.rmtree(pasta)


def limpar_expirados(ttl_horas: float = TTL_HORAS_PADRAO) -> list[str]:
    """Remove pastas de sessão (`output/sessions/{id}/`, JSON + imagens) e os
    arquivos finais gerados (`output/{id}_*.docx|pptx|html`) cuja última
    atividade seja mais antiga que `ttl_horas` — evita que o disco cresça
    indefinidamente em produção contínua (dezenas de PNGs/JSONs por extração).

    A "última atividade" é a data de modificação do `sessao.json` (que é
    reescrito a cada questão comentada com sucesso, ver `salvar_estado`), então
    uma sessão em andamento ou recém-concluída nunca é removida por engano —
    só sessões realmente abandonadas/já baixadas pelo usuário. Devolve a lista
    de itens removidos (para log)."""
    limite = time.time() - (ttl_horas * 3600)
    removidos: list[str] = []

    if os.path.isdir(config.SESSIONS_DIR):
        for nome in os.listdir(config.SESSIONS_DIR):
            caminho_json = os.path.join(config.SESSIONS_DIR, nome, "sessao.json")
            if os.path.exists(caminho_json) and os.path.getmtime(caminho_json) < limite:
                remover_sessao(nome)
                removidos.append(f"sessions/{nome}")

    if os.path.isdir(config.OUTPUT_DIR):
        for nome in os.listdir(config.OUTPUT_DIR):
            caminho = os.path.join(config.OUTPUT_DIR, nome)
            if (
                os.path.isfile(caminho)
                and _PREFIXO_SESSION_ID.match(nome)
                and os.path.getmtime(caminho) < limite
            ):
                os.remove(caminho)
                removidos.append(nome)

    if removidos:
        logger.info("Limpeza de sessões expiradas (>%sh): %s", ttl_horas, removidos)
    return removidos
