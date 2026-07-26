from google import genai
from google.genai import errors as genai_errors
from google.genai import types

from app.images import detectar_mime, redimensionar_se_necessario
from app.llm.base import LLMError, LLMProvider
from app.llm.retry import com_retry_predicado
from app.prompts import EXTRACTION_SYSTEM_PROMPT, build_extraction_user_message
from app.schemas import ExtractionResult

DEFAULT_MODEL = "gemini-2.5-flash"


def _e_rate_limit(e: Exception) -> bool:
    return isinstance(e, genai_errors.ClientError) and getattr(e, "code", None) == 429


_retry_429 = com_retry_predicado(_e_rate_limit)


def _map_error(e: Exception) -> LLMError:
    status = getattr(e, "code", None) or getattr(e, "status_code", None)
    if status in (401, 403):
        return LLMError("Chave de API do Gemini inválida ou sem permissão.", 401)
    if status == 429:
        return LLMError("Limite de requisições do Gemini atingido mesmo após novas tentativas.", 429)
    return LLMError(f"Erro na chamada ao Gemini: {e}", 502)


def _montar_conteudo_multimodal(texto: str, imagens: list[bytes] | None) -> list[types.Part]:
    partes = [types.Part.from_text(text=texto)]
    for dados in imagens or []:
        dados_prontos = redimensionar_se_necessario(dados)
        mime = detectar_mime(dados_prontos)
        partes.append(types.Part.from_bytes(data=dados_prontos, mime_type=mime))
    return partes


class GeminiProvider(LLMProvider):
    async def extrair(
        self,
        texto: str,
        api_key: str,
        model: str | None = None,
        imagens: list[bytes] | None = None,
    ) -> ExtractionResult:
        client = genai.Client(api_key=api_key)

        @_retry_429
        async def _chamar():
            return await client.aio.models.generate_content(
                model=model or DEFAULT_MODEL,
                contents=_montar_conteudo_multimodal(build_extraction_user_message(texto), imagens),
                config=types.GenerateContentConfig(
                    system_instruction=EXTRACTION_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=ExtractionResult,
                ),
            )

        try:
            resp = await _chamar()
        except genai_errors.APIError as e:
            raise _map_error(e) from e

        if getattr(resp, "parsed", None) is not None:
            return resp.parsed
        return ExtractionResult.model_validate_json(resp.text)

    async def comentar(
        self,
        system_prompt: str,
        user_message: str,
        api_key: str,
        model: str | None = None,
        imagens: list[bytes] | None = None,
    ) -> str:
        client = genai.Client(api_key=api_key)

        @_retry_429
        async def _chamar():
            return await client.aio.models.generate_content(
                model=model or DEFAULT_MODEL,
                contents=_montar_conteudo_multimodal(user_message, imagens),
                config=types.GenerateContentConfig(system_instruction=system_prompt),
            )

        try:
            resp = await _chamar()
        except genai_errors.APIError as e:
            raise _map_error(e) from e

        return (resp.text or "").strip()
