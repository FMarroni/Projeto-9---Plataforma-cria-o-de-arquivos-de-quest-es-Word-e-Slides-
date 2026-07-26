"""Permite ao usuário consultar e customizar, via UI, o prompt "Coruj.IA"
usado para comentar cada questão (ver app/prompts.py e app/comments.py) —
sem precisar editar código. A customização é persistida em disco
(config/prompt_corujia.txt); enquanto não houver customização salva,
`obter_prompt()` devolve o prompt padrão embutido em prompts.py."""

import os

from app import config
from app.prompts import CORUJIA_SYSTEM_PROMPT as PROMPT_PADRAO


def obter_prompt_padrao() -> str:
    return PROMPT_PADRAO


def esta_customizado() -> bool:
    return os.path.exists(config.PROMPT_CORUJIA_CUSTOMIZADO_PATH)


def obter_prompt() -> str:
    """Devolve o prompt customizado salvo, ou o padrão se não houver nenhum."""
    if esta_customizado():
        with open(config.PROMPT_CORUJIA_CUSTOMIZADO_PATH, encoding="utf-8") as f:
            return f.read()
    return PROMPT_PADRAO


def salvar_prompt(texto: str) -> None:
    os.makedirs(config.CONFIG_DIR, exist_ok=True)
    caminho = config.PROMPT_CORUJIA_CUSTOMIZADO_PATH
    caminho_tmp = caminho + ".tmp"
    with open(caminho_tmp, "w", encoding="utf-8") as f:
        f.write(texto)
    os.replace(caminho_tmp, caminho)


def restaurar_padrao() -> None:
    if esta_customizado():
        os.remove(config.PROMPT_CORUJIA_CUSTOMIZADO_PATH)
