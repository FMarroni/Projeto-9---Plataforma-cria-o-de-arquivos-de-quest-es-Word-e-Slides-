import pytest

from app import pipeline
from app.schemas import ExtractionResult, Formula, Questao


class _ProviderExtracaoVazia:
    """Simula uma IA que responde sem erro, mas não extrai nenhuma questão —
    o cenário relatado (Anthropic, PDF de 20 questões) que antes seguia
    silenciosamente até gerar documentos vazios."""

    async def extrair(self, texto, api_key, model=None, imagens=None):
        return ExtractionResult(questoes=[])


@pytest.mark.asyncio
async def test_extracao_vazia_gera_erro_e_nao_prossegue_para_gerar_documentos(monkeypatch):
    monkeypatch.setattr(pipeline, "extrair_conteudo_pdf", lambda pdf_bytes: ("texto qualquer", {}))
    monkeypatch.setattr(pipeline, "get_provider", lambda nome: _ProviderExtracaoVazia())

    eventos = [ev async for ev in pipeline.executar_pipeline_fresh(b"pdf-fake", "anthropic", "sk-fake", None)]

    tipos = [ev["event"] for ev in eventos]
    assert "erro" in tipos
    assert "concluido" not in tipos
    # nenhuma etapa de geração de documento deveria ter sido anunciada
    assert not any("Gerando" in ev["data"] for ev in eventos)


class _ProviderComFormula:
    """Simula uma IA que extrai 1 questão com uma fórmula estruturada válida
    referenciando um marcador [FORMULA_NN] — usado para confirmar que o
    pipeline resolve `Questao.formulas` (ver app.formula_resolve) ANTES de
    salvar a sessão/gerar comentários e documentos."""

    async def extrair(self, texto, api_key, model=None, imagens=None):
        questao = Questao(
            numero=1,
            banca="FCC",
            ano=2025,
            materia="Matemática",
            assunto="Funções",
            enunciado="Considere [FORMULA_01] a seguir.",
            alternativas=[],
            gabarito=None,
            formulas=[Formula(id="FORMULA_01", latex="x^{2}", display=False, confidence=0.9)],
        )
        return ExtractionResult(bancas=["FCC"], anos=[2025], cargos=[], questoes=[questao])


@pytest.mark.asyncio
async def test_pipeline_resolve_formulas_antes_de_salvar_sessao(monkeypatch, tmp_path):
    monkeypatch.setattr(pipeline, "extrair_conteudo_pdf", lambda pdf_bytes: ("texto qualquer", {}))
    monkeypatch.setattr(pipeline, "get_provider", lambda nome: _ProviderComFormula())
    monkeypatch.setattr(pipeline.config, "OUTPUT_DIR", str(tmp_path))

    estados_salvos = []
    monkeypatch.setattr(
        pipeline.session_store,
        "salvar_estado",
        lambda session_id, provider_nome, model, extraction, documentos_biblioteca=None: estados_salvos.append(
            extraction
        ),
    )
    monkeypatch.setattr(pipeline.session_store, "salvar_imagens", lambda session_id, imagens: None)

    async def _comentarios_fake(questoes, provider, api_key, imagens=None, model=None, documentos_biblioteca=None):
        return
        yield  # pragma: no cover - gerador vazio

    monkeypatch.setattr(pipeline, "gerar_comentarios", _comentarios_fake)

    eventos = [
        ev
        async for ev in pipeline.executar_pipeline_fresh(b"pdf-fake", "anthropic", "sk-fake", None)
    ]

    assert any(ev["event"] == "concluido" for ev in eventos)
    assert estados_salvos, "session_store.salvar_estado deveria ter sido chamado"
    questao_salva = estados_salvos[0].questoes[0]
    # a fórmula válida foi resolvida (substituída) ANTES de persistir o estado
    assert "[FORMULA_01]" not in questao_salva.enunciado
    assert "$x^{2}$" in questao_salva.enunciado
