import importlib


def test_importar_app_main_cria_output_dir_mesmo_sem_ele_existir(tmp_path, monkeypatch):
    """Regressão: StaticFiles exige que o diretório exista já na importação do
    módulo (antes do evento de "startup" rodar) — num checkout limpo do
    projeto (sem nunca ter gerado nada em output/ ainda), isso derrubava o
    processo com 'RuntimeError: Directory ... does not exist'."""
    from app import config

    novo_output = tmp_path / "output_novo"
    monkeypatch.setattr(config, "OUTPUT_DIR", str(novo_output))
    assert not novo_output.exists()

    from app import main

    importlib.reload(main)

    assert novo_output.exists()
