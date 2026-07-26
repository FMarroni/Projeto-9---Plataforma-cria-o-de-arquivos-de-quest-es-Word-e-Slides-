from abc import ABC, abstractmethod

from app.schemas import ExtractionResult


class LLMError(Exception):
    """Erro normalizado de qualquer provedor de LLM, já mapeado para um status HTTP."""

    def __init__(self, message: str, status_code: int = 502):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


class LLMProvider(ABC):
    """Interface comum aos 3 provedores. Nenhuma implementação guarda a
    api_key em estado — ela é sempre passada por chamada, nunca lida de env var.

    Ambos os métodos são multimodais: `imagens` é uma lista de bytes brutos
    (PNG/JPEG) anexados como conteúdo visual junto ao texto, na ordem dada.
    Passe lista vazia/None quando não há imagem relevante."""

    @abstractmethod
    async def extrair(
        self,
        texto: str,
        api_key: str,
        model: str | None = None,
        imagens: list[bytes] | None = None,
    ) -> ExtractionResult:
        """Extração estruturada (JSON) do texto do PDF, com Vision se houver imagens."""

    @abstractmethod
    async def comentar(
        self,
        system_prompt: str,
        user_message: str,
        api_key: str,
        model: str | None = None,
        imagens: list[bytes] | None = None,
    ) -> str:
        """Chamada de texto livre (usada pelo módulo Coruj.IA de comentários), com Vision se houver imagens."""
