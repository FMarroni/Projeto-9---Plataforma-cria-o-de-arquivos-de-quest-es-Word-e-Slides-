import os
import time

from app import session_store
from app.schemas import ExtractionResult, Questao


def _extraction():
    return ExtractionResult(
        nome_concurso="Concurso Teste",
        bancas=["CEBRASPE"],
        anos=[2024],
        cargos=["Analista"],
        questoes=[
            Questao(
                numero=1,
                banca="CEBRASPE",
                materia="Direito",
                assunto="Assunto X",
                enunciado="[IMAGEM_01] enunciado",
                alternativas=[],
                gabarito="A",
                comentario="comentário já feito",
            )
        ],
    )


def test_round_trip_estado_e_imagens(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store.config, "SESSIONS_DIR", str(tmp_path))

    session_id = session_store.novo_session_id()
    assert not session_store.existe_sessao(session_id)

    extraction = _extraction()
    session_store.salvar_estado(session_id, "anthropic", "claude-sonnet-5", extraction, ["doc_abc123"])
    session_store.salvar_imagens(session_id, {"IMAGEM_01": b"conteudo-fake"})

    assert session_store.existe_sessao(session_id)

    provider, model, extraction_carregada, documentos_biblioteca = session_store.carregar_estado(session_id)
    assert provider == "anthropic"
    assert model == "claude-sonnet-5"
    assert extraction_carregada.questoes[0].comentario == "comentário já feito"
    assert documentos_biblioteca == ["doc_abc123"]

    imagens = session_store.carregar_imagens(session_id)
    assert imagens == {"IMAGEM_01": b"conteudo-fake"}


def test_salvar_estado_preserva_documentos_biblioteca_ao_regravar_sem_informar(tmp_path, monkeypatch):
    """A cada questão comentada, pipeline.py regrava o estado sem repassar
    `documentos_biblioteca` — não pode apagar a seleção já salva no início."""
    monkeypatch.setattr(session_store.config, "SESSIONS_DIR", str(tmp_path))

    session_id = session_store.novo_session_id()
    extraction = _extraction()
    session_store.salvar_estado(session_id, "fake", None, extraction, ["doc_xyz"])

    session_store.salvar_estado(session_id, "fake", None, extraction)  # sem documentos_biblioteca

    _, _, _, documentos_biblioteca = session_store.carregar_estado(session_id)
    assert documentos_biblioteca == ["doc_xyz"]


def test_remover_sessao_apaga_tudo(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store.config, "SESSIONS_DIR", str(tmp_path))

    session_id = session_store.novo_session_id()
    session_store.salvar_estado(session_id, "fake", None, _extraction())
    assert session_store.existe_sessao(session_id)

    session_store.remover_sessao(session_id)
    assert not session_store.existe_sessao(session_id)


def test_carregar_imagens_de_sessao_inexistente_devolve_vazio(tmp_path, monkeypatch):
    monkeypatch.setattr(session_store.config, "SESSIONS_DIR", str(tmp_path))
    assert session_store.carregar_imagens("nao-existe") == {}


def _tornar_antigo(caminho: str, horas: float) -> None:
    antigo = time.time() - horas * 3600
    os.utime(caminho, (antigo, antigo))


def test_limpar_expirados_remove_apenas_sessoes_velhas(tmp_path, monkeypatch):
    sessions_dir = tmp_path / "sessions"
    output_dir = tmp_path / "output"
    sessions_dir.mkdir()
    output_dir.mkdir()
    monkeypatch.setattr(session_store.config, "SESSIONS_DIR", str(sessions_dir))
    monkeypatch.setattr(session_store.config, "OUTPUT_DIR", str(output_dir))

    velha = session_store.novo_session_id()
    recente = session_store.novo_session_id()
    session_store.salvar_estado(velha, "fake", None, _extraction())
    session_store.salvar_estado(recente, "fake", None, _extraction())

    # simula um arquivo final gerado (docx/pptx/html) para cada sessão
    for sid in (velha, recente):
        with open(output_dir / f"{sid}_lista.docx", "w") as f:
            f.write("conteudo")

    # "envelhece" só a sessão `velha` (JSON de estado + arquivo final) para além do TTL
    _tornar_antigo(str(sessions_dir / velha / "sessao.json"), horas=72)
    _tornar_antigo(str(output_dir / f"{velha}_lista.docx"), horas=72)

    removidos = session_store.limpar_expirados(ttl_horas=48)

    assert not session_store.existe_sessao(velha)
    assert not (output_dir / f"{velha}_lista.docx").exists()
    assert session_store.existe_sessao(recente)
    assert (output_dir / f"{recente}_lista.docx").exists()
    assert f"sessions/{velha}" in removidos
    assert f"{velha}_lista.docx" in removidos
