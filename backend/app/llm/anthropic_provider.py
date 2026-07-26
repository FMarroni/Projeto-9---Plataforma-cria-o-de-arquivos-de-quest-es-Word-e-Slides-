import anthropic
from anthropic import AsyncAnthropic

from app.images import preparar_para_envio
from app.llm.base import LLMError, LLMProvider
from app.llm.retry import com_retry_rate_limit
from app.prompts import EXTRACTION_SYSTEM_PROMPT, build_extraction_user_message
from app.schemas import EXTRACTION_JSON_SCHEMA, ExtractionResult

DEFAULT_MODEL = "claude-sonnet-5"
TOOL_NAME = "registrar_extracao"

_retry_429 = com_retry_rate_limit((anthropic.RateLimitError,))

# Um max_tokens fixo baixo corta a extração no meio de um caderno com muitas
# questões (a resposta é um objeto JSON por questão, com todos os campos do
# schema repetidos — cresce proporcionalmente ao nº de questões do PDF, não
# é um tamanho fixo) — um caderno de ~20 questões já passa de 8192 tokens de
# saída, e o corte produz uma extração vazia/incompleta em vez de um erro
# visível. Escala com o tamanho do texto de entrada (proxy razoável do nº de
# questões), com piso e teto generosos.
_MAX_TOKENS_EXTRACAO_PISO = 8192
_MAX_TOKENS_EXTRACAO_TETO = 64000


def _max_tokens_extracao(texto: str) -> int:
    tokens_entrada_estimados = len(texto) // 4  # ~4 caracteres por token, estimativa padrão
    return max(_MAX_TOKENS_EXTRACAO_PISO, min(_MAX_TOKENS_EXTRACAO_TETO, tokens_entrada_estimados * 3))


def _montar_conteudo_multimodal(texto: str, imagens: list[bytes] | None) -> str | list[dict]:
    if not imagens:
        return texto
    blocos: list[dict] = []
    for dados in imagens:
        mime, b64 = preparar_para_envio(dados)
        blocos.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": b64}})
    blocos.append({"type": "text", "text": texto})
    return blocos


class AnthropicProvider(LLMProvider):
    async def extrair(
        self,
        texto: str,
        api_key: str,
        model: str | None = None,
        imagens: list[bytes] | None = None,
    ) -> ExtractionResult:
        client = AsyncAnthropic(api_key=api_key)

        @_retry_429
        async def _chamar():
            return await client.messages.create(
                model=model or DEFAULT_MODEL,
                max_tokens=_max_tokens_extracao(texto),
                system=EXTRACTION_SYSTEM_PROMPT,
                tools=[
                    {
                        "name": TOOL_NAME,
                        "description": "Registra os dados estruturados extraídos do PDF do TEC Concursos.",
                        "input_schema": EXTRACTION_JSON_SCHEMA,
                    }
                ],
                tool_choice={"type": "tool", "name": TOOL_NAME},
                messages=[
                    {
                        "role": "user",
                        "content": _montar_conteudo_multimodal(
                            build_extraction_user_message(texto), imagens
                        ),
                    }
                ],
                timeout=120,
            )

        try:
            resp = await _chamar()
        except anthropic.AuthenticationError as e:
            raise LLMError("Chave de API da Anthropic inválida ou sem permissão.", 401) from e
        except anthropic.RateLimitError as e:
            raise LLMError("Limite de requisições da Anthropic atingido mesmo após novas tentativas.", 429) from e
        except anthropic.APITimeoutError as e:
            raise LLMError("A Anthropic demorou demais para responder.", 504) from e
        except anthropic.APIError as e:
            raise LLMError(f"Erro na chamada à Anthropic: {e}", 502) from e

        # resp.stop_reason == "max_tokens" -> a resposta foi cortada no meio
        # (o "input" da tool_use fica incompleto/inválido) — melhor um erro
        # explícito do que arriscar validar um JSON truncado como extração
        # vazia ou parcial silenciosa.
        if resp.stop_reason == "max_tokens":
            raise LLMError(
                "A resposta da Anthropic foi cortada por exceder o limite de tokens "
                "(PDF com muitas questões). Tente novamente ou divida o PDF em partes menores.",
                502,
            )

        for bloco in resp.content:
            if bloco.type == "tool_use" and bloco.name == TOOL_NAME:
                return ExtractionResult.model_validate(bloco.input)

        raise LLMError("A Anthropic não retornou os dados estruturados esperados.", 502)

    async def comentar(
        self,
        system_prompt: str,
        user_message: str,
        api_key: str,
        model: str | None = None,
        imagens: list[bytes] | None = None,
    ) -> str:
        client = AsyncAnthropic(api_key=api_key)

        @_retry_429
        async def _chamar():
            return await client.messages.create(
                model=model or DEFAULT_MODEL,
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": "user", "content": _montar_conteudo_multimodal(user_message, imagens)}],
                timeout=60,
            )

        try:
            resp = await _chamar()
        except anthropic.AuthenticationError as e:
            raise LLMError("Chave de API da Anthropic inválida ou sem permissão.", 401) from e
        except anthropic.RateLimitError as e:
            raise LLMError("Limite de requisições da Anthropic atingido mesmo após novas tentativas.", 429) from e
        except anthropic.APIError as e:
            raise LLMError(f"Erro na chamada à Anthropic: {e}", 502) from e

        textos = [bloco.text for bloco in resp.content if bloco.type == "text"]
        return "\n".join(textos).strip()
