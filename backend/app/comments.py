"""Orquestra a chamada obrigatória ao prompt 'Coruj.IA' (ver prompts.py) para
gerar o comentário de gabarito de cada questão extraída — agora com suporte a
Vision (a questão pode referenciar [IMAGEM_NN] no enunciado; a imagem
correspondente é anexada à chamada) e emitindo progresso incremental (usado
pelo pipeline SSE) conforme cada questão é concluída.

Épico 4 — Módulo Biblioteca (RAG): se `documentos_biblioteca` for passado
(não-vazio), a IA entra em "Modo Restrito" para cada questão — em vez do
prompt/mensagem padrão, primeiro recupera os trechos mais relevantes do
material de apoio selecionado (app/rag.py) e usa o prompt derivado
`build_prompt_rag()`, que instrui a IA a responder EXCLUSIVAMENTE com base
nesses trechos. Se não houver informação suficiente (nos trechos recuperados,
ou se a busca não encontrar nada), o comentário final é a mensagem de aviso
padrão — nunca uma resposta "adivinhada". Sem `documentos_biblioteca`, o
comportamento é idêntico ao anterior ao Épico 4."""

import asyncio
from collections.abc import AsyncIterator

from app import prompt_store, rag
from app.formatting import extrair_ids_imagem
from app.llm.base import LLMProvider
from app.prompts import (
    build_comment_user_message,
    build_comment_user_message_rag,
    build_prompt_rag,
    parse_resposta_rag,
)
from app.schemas import Questao, RastreabilidadeItem

_CONCORRENCIA_MAXIMA = 4

MENSAGEM_INFO_NAO_ENCONTRADA = (
    "⚠️ Comentário não gerado: a informação necessária para resolver esta questão "
    "não foi encontrada no material de apoio selecionado."
)


def _imagens_da_questao(questao: Questao, imagens: dict[str, bytes]) -> list[bytes] | None:
    ids = extrair_ids_imagem(questao.enunciado)
    encontradas = [imagens[i] for i in ids if i in imagens]
    return encontradas or None


def _texto_busca(questao: Questao) -> str:
    """Texto usado como query de recuperação (Retrieval) — enunciado +
    alternativas, para dar ao embedding o máximo de sinal sobre o assunto."""
    partes = [questao.enunciado]
    partes.extend(f"{alt.letra}) {alt.texto}" for alt in questao.alternativas)
    return "\n".join(partes)


async def gerar_comentarios(
    questoes: list[Questao],
    provider: LLMProvider,
    api_key: str,
    imagens: dict[str, bytes] | None = None,
    model: str | None = None,
    documentos_biblioteca: list[str] | None = None,
) -> AsyncIterator[str]:
    """Preenche `questao.comentario` (e `questao.rastreabilidade`, no Modo
    Restrito) in-place para cada questão não-anulada, com concorrência limitada
    por semáforo, e vai devolvendo (yield) uma mensagem de progresso a cada
    questão concluída — para consumo pelo pipeline SSE. Levanta a primeira
    exceção encontrada, se houver, só depois de todas as questões terem sido
    tentadas."""
    imagens = imagens or {}
    documentos_biblioteca = documentos_biblioteca or []
    semaforo = asyncio.Semaphore(_CONCORRENCIA_MAXIMA)
    total = len(questoes)
    fila: asyncio.Queue[str] = asyncio.Queue()
    erros: list[Exception] = []

    async def _comentar_rag(questao: Questao, imgs_questao: list[bytes] | None) -> None:
        trechos = rag.buscar_trechos_relevantes(_texto_busca(questao), documentos_biblioteca)
        if not trechos:
            questao.comentario = MENSAGEM_INFO_NAO_ENCONTRADA
            questao.rastreabilidade = []
            return

        prompt_sistema = build_prompt_rag(prompt_store.obter_prompt())
        mensagem = build_comment_user_message_rag(questao, trechos)
        resposta = await provider.comentar(prompt_sistema, mensagem, api_key, model, imgs_questao)
        comentario, rastreabilidade = parse_resposta_rag(resposta)

        if comentario is None:
            questao.comentario = MENSAGEM_INFO_NAO_ENCONTRADA
            questao.rastreabilidade = []
        else:
            questao.comentario = comentario
            questao.rastreabilidade = [RastreabilidadeItem(**item) for item in rastreabilidade]

    async def _comentar_uma(questao: Questao) -> None:
        if questao.comentario is not None:
            # já comentada com sucesso antes (ex.: retomando uma sessão) — não rechama a IA
            await fila.put(f"Questão {questao.numero}/{total} já comentada (sessão retomada).")
            return

        imgs_questao = _imagens_da_questao(questao, imagens)
        async with semaforo:
            try:
                if questao.anulada:
                    questao.comentario = "Questão anulada."
                elif questao.gabarito is None:
                    questao.comentario = None
                elif documentos_biblioteca:
                    await _comentar_rag(questao, imgs_questao)
                else:
                    mensagem = build_comment_user_message(questao)
                    questao.comentario = await provider.comentar(
                        prompt_store.obter_prompt(), mensagem, api_key, model, imgs_questao
                    )
            except Exception as e:  # noqa: BLE001 — capturado para não travar as demais questões
                erros.append(e)
                questao.comentario = None

        sufixo_imagem = " (com imagem, IA Vision)" if imgs_questao else ""
        sufixo_rag = " (Modo Restrito, base de conhecimento)" if documentos_biblioteca else ""
        await fila.put(f"Questão {questao.numero}/{total} comentada{sufixo_imagem}{sufixo_rag}.")

    tarefas = asyncio.gather(*(_comentar_uma(q) for q in questoes))

    for _ in range(total):
        yield await fila.get()

    await tarefas
    if erros:
        raise erros[0]
