from app import prompt_store
from app.prompts import CORUJIA_SYSTEM_PROMPT


def _isolar_config(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    monkeypatch.setattr(prompt_store.config, "CONFIG_DIR", str(config_dir))
    monkeypatch.setattr(
        prompt_store.config, "PROMPT_CORUJIA_CUSTOMIZADO_PATH", str(config_dir / "prompt_corujia.txt")
    )


def test_obter_prompt_padrao_devolve_prompt_de_prompts_py():
    assert prompt_store.obter_prompt_padrao() == CORUJIA_SYSTEM_PROMPT


def test_sem_customizacao_obter_prompt_devolve_padrao(tmp_path, monkeypatch):
    _isolar_config(tmp_path, monkeypatch)

    assert not prompt_store.esta_customizado()
    assert prompt_store.obter_prompt() == CORUJIA_SYSTEM_PROMPT


def test_salvar_prompt_persiste_e_marca_customizado(tmp_path, monkeypatch):
    _isolar_config(tmp_path, monkeypatch)

    prompt_store.salvar_prompt("Novo prompt customizado pelo usuário.")

    assert prompt_store.esta_customizado()
    assert prompt_store.obter_prompt() == "Novo prompt customizado pelo usuário."


def test_restaurar_padrao_remove_customizacao(tmp_path, monkeypatch):
    _isolar_config(tmp_path, monkeypatch)

    prompt_store.salvar_prompt("Temporário")
    assert prompt_store.esta_customizado()

    prompt_store.restaurar_padrao()

    assert not prompt_store.esta_customizado()
    assert prompt_store.obter_prompt() == CORUJIA_SYSTEM_PROMPT


def test_restaurar_padrao_sem_customizacao_nao_falha(tmp_path, monkeypatch):
    _isolar_config(tmp_path, monkeypatch)

    prompt_store.restaurar_padrao()  # não deve levantar mesmo sem arquivo existente

    assert not prompt_store.esta_customizado()
