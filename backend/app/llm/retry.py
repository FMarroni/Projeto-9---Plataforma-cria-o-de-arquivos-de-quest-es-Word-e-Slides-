"""Retry com backoff exponencial para chamadas de LLM sujeitas a rate limit
(HTTP 429). Cada provider passa suas próprias classes de exceção de rate-limit
(o tipo do SDK correspondente) — o retry acontece ANTES de convertermos o erro
do SDK em LLMError, para não desistir na primeira tentativa."""

import logging

from tenacity import (
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

MAX_TENTATIVAS = 5
ESPERA_MINIMA_S = 2
ESPERA_MAXIMA_S = 60


def _log_antes_de_dormir(retry_state):
    logger.warning(
        "Rate limit atingido, tentativa %s/%s — aguardando %.1fs antes de tentar novamente.",
        retry_state.attempt_number,
        MAX_TENTATIVAS,
        retry_state.next_action.sleep if retry_state.next_action else 0,
    )


def com_retry_rate_limit(excecoes_rate_limit: tuple[type[Exception], ...]):
    """Decorator factory: aplica retry com backoff exponencial apenas para as
    exceções de rate-limit específicas do provider (matching por tipo). Outras
    exceções (auth, payload inválido etc.) propagam imediatamente, sem retry."""
    return retry(
        retry=retry_if_exception_type(excecoes_rate_limit),
        wait=wait_exponential(multiplier=1, min=ESPERA_MINIMA_S, max=ESPERA_MAXIMA_S),
        stop=stop_after_attempt(MAX_TENTATIVAS),
        reraise=True,
        before_sleep=_log_antes_de_dormir,
    )


def com_retry_predicado(predicado):
    """Variante para providers cujo SDK não tem uma classe de exceção dedicada
    para rate-limit (ex.: Gemini, onde 429 vem como ClientError.code == 429) —
    `predicado(exc) -> bool` decide se aquela exceção específica deve ser retentada."""
    return retry(
        retry=retry_if_exception(predicado),
        wait=wait_exponential(multiplier=1, min=ESPERA_MINIMA_S, max=ESPERA_MAXIMA_S),
        stop=stop_after_attempt(MAX_TENTATIVAS),
        reraise=True,
        before_sleep=_log_antes_de_dormir,
    )
