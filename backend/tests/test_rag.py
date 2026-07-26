import fitz
import pytest

from app import rag


def _pdf_com_paginas(paginas: list[str]) -> bytes:
    """Monta um PDF real (via PyMuPDF) com uma página por item de `paginas` —
    permite testar o fatiamento por página sem depender dos PDFs de amostra
    grandes em Subsídios/."""
    doc = fitz.open()
    for texto in paginas:
        page = doc.new_page()
        page.insert_text((72, 72), texto, fontsize=11)
    dados = doc.tobytes()
    doc.close()
    return dados


@pytest.fixture(autouse=True)
def _isolar_biblioteca(tmp_path, monkeypatch):
    """Cada teste ganha seu próprio diretório de biblioteca/vector DB — e o
    singleton de cliente/coleção do módulo precisa ser resetado, senão o
    primeiro teste a rodar 'gruda' o cliente antigo (apontando para outro
    tmp_path) nos testes seguintes."""
    base = tmp_path / "biblioteca"
    monkeypatch.setattr(rag.config, "BIBLIOTECA_DIR", str(base))
    monkeypatch.setattr(rag.config, "BIBLIOTECA_PDFS_DIR", str(base / "pdfs"))
    monkeypatch.setattr(rag.config, "BIBLIOTECA_METADATA_PATH", str(base / "biblioteca.json"))
    monkeypatch.setattr(rag.config, "VECTOR_DB_DIR", str(base / "vector_db"))
    monkeypatch.setattr(rag, "_cliente", None)
    monkeypatch.setattr(rag, "_colecao", None)
    yield


def test_listar_documentos_vazio_inicialmente():
    assert rag.listar_documentos() == []


def test_adicionar_documento_indexa_e_registra_metadados():
    pdf_bytes = _pdf_com_paginas(["Conteúdo da página um.", "Conteúdo da página dois."])

    registro = rag.adicionar_documento("Aula_01_Teste.pdf", pdf_bytes)

    assert registro["nome_arquivo"] == "Aula_01_Teste.pdf"
    assert registro["n_paginas"] == 2
    assert registro["n_chunks"] >= 2
    assert registro["doc_id"]

    documentos = rag.listar_documentos()
    assert len(documentos) == 1
    assert documentos[0] == registro


def test_adicionar_documento_pdf_sem_texto_levanta_erro():
    doc = fitz.open()
    doc.new_page()  # página em branco, sem texto extraível
    dados = doc.tobytes()
    doc.close()

    with pytest.raises(rag.PdfSemTextoError):
        rag.adicionar_documento("vazio.pdf", dados)


def test_remover_documento_remove_metadados_e_devolve_false_se_inexistente():
    pdf_bytes = _pdf_com_paginas(["Algum conteúdo."])
    registro = rag.adicionar_documento("Aula.pdf", pdf_bytes)

    assert rag.remover_documento("id-que-nao-existe") is False
    assert rag.listar_documentos() == [registro]

    assert rag.remover_documento(registro["doc_id"]) is True
    assert rag.listar_documentos() == []
    # os trechos desse documento não devem mais aparecer em buscas
    assert rag.buscar_trechos_relevantes("Algum conteúdo", [registro["doc_id"]]) == []


def test_buscar_trechos_relevantes_sem_doc_ids_devolve_vazio():
    assert rag.buscar_trechos_relevantes("qualquer busca", []) == []


def test_buscar_trechos_relevantes_encontra_trecho_da_pagina_certa():
    pdf_bytes = _pdf_com_paginas(
        [
            "O crime de furto está previsto no artigo 155 do Código Penal brasileiro.",
            "A fotossíntese é o processo pelo qual as plantas convertem luz solar em energia química.",
        ]
    )
    registro = rag.adicionar_documento("Aula_Direito_Penal.pdf", pdf_bytes)

    trechos = rag.buscar_trechos_relevantes("O que diz a lei sobre o crime de furto?", [registro["doc_id"]], top_k=1)

    assert len(trechos) == 1
    assert trechos[0]["arquivo"] == "Aula_Direito_Penal.pdf"
    assert trechos[0]["pagina"] == 1
    assert "furto" in trechos[0]["texto"].lower()


def test_buscar_trechos_relevantes_restringe_por_doc_ids_selecionados():
    doc_a = rag.adicionar_documento("A.pdf", _pdf_com_paginas(["Conteúdo exclusivo do documento A sobre biologia."]))
    doc_b = rag.adicionar_documento("B.pdf", _pdf_com_paginas(["Conteúdo exclusivo do documento B sobre biologia."]))

    trechos = rag.buscar_trechos_relevantes("biologia", [doc_a["doc_id"]])

    assert len(trechos) == 1
    assert trechos[0]["arquivo"] == "A.pdf"
