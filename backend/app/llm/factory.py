from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMProvider
from app.llm.fake_provider import FakeProvider
from app.llm.gemini_provider import GeminiProvider
from app.llm.openai_provider import OpenAIProvider

_PROVIDERS: dict[str, type[LLMProvider]] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "fake": FakeProvider,
}


def get_provider(name: str) -> LLMProvider:
    try:
        cls = _PROVIDERS[name]
    except KeyError:
        raise ValueError(
            f"Provedor desconhecido: '{name}'. Use um de: {', '.join(_PROVIDERS)}."
        ) from None
    return cls()
