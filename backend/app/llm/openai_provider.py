import openai
from openai import AsyncOpenAI

from app.images import preparar_para_envio
from app.llm.base import LLMError, LLMProvider
from app.llm.retry import com_retry_rate_limit
from app.prompts import EXTRACTION_SYSTEM_PROMPT, build_extraction_user_message
from app.schemas import EXTRACTION_JSON_SCHEMA, ExtractionResult

DEFAULT_MODEL = "gpt-4o-mini"

_retry_429 = com_retry_rate_limit((openai.RateLimitError,))


def _montar_conteudo_multimodal(texto: str, imagens: list[bytes] | None) -> str | list[dict]:
    if not imagens:
        return texto
    blocos: list[dict] = [{"type": "text", "text": texto}]
    for dados in imagens:
        mime, b64 = preparar_para_envio(dados)
        blocos.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    return blocos


class OpenAIProvider(LLMProvider):
    async def extrair(
        self,
        texto: str,
        api_key: str,
        model: str | None = None,
        imagens: list[bytes] | None = None,
    ) -> ExtractionResult:
        client = AsyncOpenAI(api_key=api_key)

        @_retry_429
        async def _chamar():
            return await client.chat.completions.create(
                model=model or DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": _montar_conteudo_multimodal(
                            build_extraction_user_message(texto), imagens
                        ),
                    },
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "extracao_tec_concursos",
                        "schema": EXTRACTION_JSON_SCHEMA,
                        "strict": True,
                    },
                },
                timeout=120,
            )

        try:
            resp = await _chamar()
        except openai.AuthenticationError as e:
            raise LLMError("Chave de API da OpenAI inválida ou sem permissão.", 401) from e
        except openai.RateLimitError as e:
            raise LLMError("Limite de requisições da OpenAI atingido mesmo após novas tentativas.", 429) from e
        except openai.APITimeoutError as e:
            raise LLMError("A OpenAI demorou demais para responder.", 504) from e
        except openai.APIError as e:
            raise LLMError(f"Erro na chamada à OpenAI: {e}", 502) from e

        conteudo = resp.choices[0].message.content
        return ExtractionResult.model_validate_json(conteudo)

    async def comentar(
        self,
        system_prompt: str,
        user_message: str,
        api_key: str,
        model: str | None = None,
        imagens: list[bytes] | None = None,
    ) -> str:
        client = AsyncOpenAI(api_key=api_key)

        @_retry_429
        async def _chamar():
            return await client.chat.completions.create(
                model=model or DEFAULT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": _montar_conteudo_multimodal(user_message, imagens)},
                ],
                timeout=60,
            )

        try:
            resp = await _chamar()
        except openai.AuthenticationError as e:
            raise LLMError("Chave de API da OpenAI inválida ou sem permissão.", 401) from e
        except openai.RateLimitError as e:
            raise LLMError("Limite de requisições da OpenAI atingido mesmo após novas tentativas.", 429) from e
        except openai.APIError as e:
            raise LLMError(f"Erro na chamada à OpenAI: {e}", 502) from e

        return (resp.choices[0].message.content or "").strip()
