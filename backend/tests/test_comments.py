import re

import pytest

from app import comments as comments_module
from app.comments import MENSAGEM_INFO_NAO_ENCONTRADA, gerar_comentarios
from app.llm.base import LLMProvider
from app.schemas import Questao


class ProviderDeTeste(LLMProvider):
    def __init__(self, falhar_numero: int | None = None):
        self.chamadas: list[tuple[int, list[bytes] | None]] = []
        self._falhar_numero = falhar_numero

    async def extrair(self, texto, api_key, model=None, imagens=None):
        raise NotImplementedError

    async def comentar(self, system_prompt, user_message, api_key, model=None, imagens=None):
        # hack: usamos "#N" (dígitos logo após o #) na mensagem p/ identificar a questão no teste
        numero = int(re.match(r"[^#]*#(\d+)", user_message).group(1))
        if numero == self._falhar_numero:
            raise RuntimeError("falha simulada")
        self.chamadas.append((numero, imagens))
        return f"comentário da questão {numero}"


def _questao(numero, gabarito="A", anulada=False, comentario=None, enunciado="enunciado #{}"):
    return Questao(
        numero=numero,
        banca="X",
        materia="M",
        assunto="A",
        enunciado=enunciado.format(numero),
        alternativas=[],
        gabarito=gabarito,
        anulada=anulada,
        comentario=comentario,
    )


@pytest.mark.asyncio
async def test_pula_questao_ja_comentada():
    provider = ProviderDeTeste()
    q = _questao(1, comentario="já tinha comentário")
    mensagens = [msg async for msg in gerar_comentarios([q], provider, "key")]

    assert provider.chamadas == []
    assert "já comentada" in mensagens[0]
    assert q.comentario == "já tinha comentário"


@pytest.mark.asyncio
async def test_questao_anulada_nao_chama_provider():
    provider = ProviderDeTeste()
    q = _questao(1, gabarito=None, anulada=True)
    async for _ in gerar_comentarios([q], provider, "key"):
        pass

    assert provider.chamadas == []
    assert q.comentario == "Questão anulada."


@pytest.mark.asyncio
async def test_questao_sem_gabarito_fica_sem_comentario():
    provider = ProviderDeTeste()
    q = _questao(1, gabarito=None, anulada=False)
    async for _ in gerar_comentarios([q], provider, "key"):
        pass

    assert provider.chamadas == []
    assert q.comentario is None


@pytest.mark.asyncio
async def test_anexa_imagem_referenciada_no_enunciado():
    provider = ProviderDeTeste()
    q = _questao(1, enunciado="[IMAGEM_01] enunciado #1")
    imagens = {"IMAGEM_01": b"fake-png-bytes"}
    async for _ in gerar_comentarios([q], provider, "key", imagens=imagens):
        pass

    assert provider.chamadas == [(1, [b"fake-png-bytes"])]
    assert q.comentario == "comentário da questão 1"


@pytest.mark.asyncio
async def test_anexa_recorte_de_formula_nao_resolvida_referenciada_no_enunciado():
    # uma [FORMULA_NN] que não foi substituída por LaTeX validado (ver
    # app.formula_resolve) continua no enunciado como marcador de imagem —
    # a mesma imagem (recorte original) deve ser anexada ao comentário
    # também, para a IA ter contexto visual da fórmula ao comentar.
    provider = ProviderDeTeste()
    q = _questao(1, enunciado="[FORMULA_01] enunciado #1")
    imagens = {"FORMULA_01": b"fake-crop-bytes"}
    async for _ in gerar_comentarios([q], provider, "key", imagens=imagens):
        pass

    assert provider.chamadas == [(1, [b"fake-crop-bytes"])]


@pytest.mark.asyncio
async def test_erro_em_uma_questao_nao_impede_as_demais_mas_e_relevantado_no_final():
    provider = ProviderDeTeste(falhar_numero=1)
    q1 = _questao(1)
    q2 = _questao(2)

    with pytest.raises(RuntimeError, match="falha simulada"):
        async for _ in gerar_comentarios([q1, q2], provider, "key"):
            pass

    assert q1.comentario is None  # falhou
    assert q2.comentario == "comentário da questão 2"  # continuou normalmente


# --- Épico 4 — Módulo Biblioteca (Modo Restrito / RAG) -----------------------


class ProviderRagDeTeste(LLMProvider):
    """Provider de teste para o Modo Restrito — devolve uma resposta fixa
    (formatada como o Modo Restrito espera) e guarda o system_prompt/mensagem
    recebidos, para o teste inspecionar o que foi montado."""

    def __init__(self, resposta: str):
        self._resposta = resposta
        self.chamadas: list[tuple[str, str]] = []

    async def extrair(self, texto, api_key, model=None, imagens=None):
        raise NotImplementedError

    async def comentar(self, system_prompt, user_message, api_key, model=None, imagens=None):
        self.chamadas.append((system_prompt, user_message))
        return self._resposta


@pytest.mark.asyncio
async def test_rag_sem_trechos_encontrados_usa_mensagem_padrao_sem_chamar_provider(monkeypatch):
    monkeypatch.setattr(comments_module.rag, "buscar_trechos_relevantes", lambda *a, **k: [])
    provider = ProviderRagDeTeste("não deveria ser usado")
    q = _questao(1)

    async for _ in gerar_comentarios([q], provider, "key", documentos_biblioteca=["doc_1"]):
        pass

    assert provider.chamadas == []
    assert q.comentario == MENSAGEM_INFO_NAO_ENCONTRADA
    assert q.rastreabilidade == []


@pytest.mark.asyncio
async def test_rag_com_trechos_preenche_comentario_e_rastreabilidade(monkeypatch):
    trechos_fake = [{"arquivo": "Aula_01.pdf", "pagina": 5, "texto": "trecho relevante"}]
    monkeypatch.setattr(comments_module.rag, "buscar_trechos_relevantes", lambda *a, **k: trechos_fake)

    resposta_rag = (
        "[COMENTARIO]\n"
        "(a) Correto, conforme o material de apoio.\n"
        "[RASTREABILIDADE]\n"
        "a: arquivo=Aula_01.pdf; pagina=5\n"
        "[FIM]\n"
    )
    provider = ProviderRagDeTeste(resposta_rag)
    q = _questao(1)

    async for _ in gerar_comentarios([q], provider, "key", documentos_biblioteca=["doc_1"]):
        pass

    assert len(provider.chamadas) == 1
    system_prompt, user_message = provider.chamadas[0]
    assert "MODO RESTRITO" in system_prompt
    assert "TRECHOS RECUPERADOS DO MATERIAL DE APOIO" in user_message
    assert "trecho relevante" in user_message

    assert q.comentario == "(a) Correto, conforme o material de apoio."
    assert len(q.rastreabilidade) == 1
    assert q.rastreabilidade[0].arquivo == "Aula_01.pdf"
    assert q.rastreabilidade[0].pagina == "5"


@pytest.mark.asyncio
async def test_rag_com_trechos_mas_provider_sinaliza_info_nao_encontrada(monkeypatch):
    trechos_fake = [{"arquivo": "Aula_01.pdf", "pagina": 5, "texto": "trecho não relacionado"}]
    monkeypatch.setattr(comments_module.rag, "buscar_trechos_relevantes", lambda *a, **k: trechos_fake)

    resposta_rag = "[COMENTARIO]\nINFORMACAO_NAO_ENCONTRADA\n[FIM]\n"
    provider = ProviderRagDeTeste(resposta_rag)
    q = _questao(1)

    async for _ in gerar_comentarios([q], provider, "key", documentos_biblioteca=["doc_1"]):
        pass

    assert len(provider.chamadas) == 1
    assert q.comentario == MENSAGEM_INFO_NAO_ENCONTRADA
    assert q.rastreabilidade == []


@pytest.mark.asyncio
async def test_sem_documentos_biblioteca_nao_consulta_rag(monkeypatch):
    """Regressão: sem `documentos_biblioteca`, o comportamento deve ser
    idêntico ao anterior ao Épico 4 — nem app.rag é consultado."""
    chamou_rag = False

    def _falha_se_chamado(*args, **kwargs):
        nonlocal chamou_rag
        chamou_rag = True
        return []

    monkeypatch.setattr(comments_module.rag, "buscar_trechos_relevantes", _falha_se_chamado)
    provider = ProviderDeTeste()
    q = _questao(1)

    async for _ in gerar_comentarios([q], provider, "key"):
        pass

    assert chamou_rag is False
    assert provider.chamadas == [(1, None)]
    assert q.comentario == "comentário da questão 1"
