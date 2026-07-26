import pytest

from app.llm import retry as retry_mod


class ErroRateLimit(Exception):
    pass


class OutroErro(Exception):
    pass


@pytest.mark.asyncio
async def test_retry_tenta_novamente_ate_dar_certo(monkeypatch):
    # tempos de espera reduzidos para o teste rodar rápido
    monkeypatch.setattr(retry_mod, "ESPERA_MINIMA_S", 0.001)
    monkeypatch.setattr(retry_mod, "ESPERA_MAXIMA_S", 0.01)
    monkeypatch.setattr(retry_mod, "MAX_TENTATIVAS", 5)

    tentativas = {"n": 0}

    @retry_mod.com_retry_rate_limit((ErroRateLimit,))
    async def chamada():
        tentativas["n"] += 1
        if tentativas["n"] < 3:
            raise ErroRateLimit("429")
        return "sucesso"

    resultado = await chamada()
    assert resultado == "sucesso"
    assert tentativas["n"] == 3


@pytest.mark.asyncio
async def test_retry_desiste_apos_max_tentativas(monkeypatch):
    monkeypatch.setattr(retry_mod, "ESPERA_MINIMA_S", 0.001)
    monkeypatch.setattr(retry_mod, "ESPERA_MAXIMA_S", 0.01)
    monkeypatch.setattr(retry_mod, "MAX_TENTATIVAS", 3)

    tentativas = {"n": 0}

    @retry_mod.com_retry_rate_limit((ErroRateLimit,))
    async def chamada():
        tentativas["n"] += 1
        raise ErroRateLimit("429 sempre")

    with pytest.raises(ErroRateLimit):
        await chamada()
    assert tentativas["n"] == 3


@pytest.mark.asyncio
async def test_retry_nao_reprocessa_excecao_de_outro_tipo(monkeypatch):
    monkeypatch.setattr(retry_mod, "ESPERA_MINIMA_S", 0.001)
    monkeypatch.setattr(retry_mod, "MAX_TENTATIVAS", 5)

    tentativas = {"n": 0}

    @retry_mod.com_retry_rate_limit((ErroRateLimit,))
    async def chamada():
        tentativas["n"] += 1
        raise OutroErro("não é rate limit")

    with pytest.raises(OutroErro):
        await chamada()
    assert tentativas["n"] == 1  # não fez retry para um erro que não é da lista
