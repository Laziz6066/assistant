from __future__ import annotations
import time
import httpx
import ollama
from loguru import logger

from voice_assistant.core.types import Intent
from voice_assistant.nlu.parse import parse_and_validate


_UNREACHABLE_COOLDOWN_S = 60.0
_PERMANENT_UNREACHABLE_S = 1e12  # effectively forever (decades)
_KEEP_ALIVE = "5m"
_MAX_TOKENS = 100


class OllamaClient:
    """Synchronous classifier that asks a local ollama model to pick an intent.

    Failure policy: any error (connection, timeout, bad JSON, hallucinated
    intent, low confidence) results in Intent.unknown(). Pipeline never blocks
    longer than `timeout_s` and never sees an exception from this layer.
    """

    def __init__(self, host: str, model: str, timeout_s: float,
                 temperature: float, min_confidence: float):
        self._client = ollama.Client(host=host, timeout=timeout_s)
        self._model = model
        self._temperature = temperature
        self._min_confidence = min_confidence
        self._unreachable_until: float = 0.0
        self._warned_unreachable = False
        self._warned_model_missing = False

    def classify(self, text: str, system_prompt: str,
                 catalog: dict[str, dict]) -> Intent:
        if time.monotonic() < self._unreachable_until:
            return Intent.unknown()
        try:
            resp = self._client.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                format="json",
                options={"temperature": self._temperature,
                         "num_predict": _MAX_TOKENS},
                keep_alive=_KEEP_ALIVE,
            )
        except (ConnectionError, httpx.ConnectError) as e:
            self._mark_connection_unreachable(e)
            return Intent.unknown()
        except ollama.ResponseError as e:
            status = getattr(e, "status_code", 0)
            msg = str(e).lower()
            if status == 404 or "not found" in msg:
                self._mark_model_missing(e)
            else:
                logger.debug(f"LLM ResponseError {status}: {e}")
            return Intent.unknown()
        except (TimeoutError, httpx.ReadTimeout, httpx.TimeoutException):
            logger.debug(f"LLM timeout on text (len={len(text)})")
            return Intent.unknown()
        except Exception:
            logger.exception("LLM classify unexpected error")
            return Intent.unknown()

        content = resp.message.content if hasattr(resp, "message") \
                  else resp["message"]["content"]
        return parse_and_validate(content, catalog, self._min_confidence)

    def _mark_connection_unreachable(self, exc: Exception) -> None:
        self._unreachable_until = time.monotonic() + _UNREACHABLE_COOLDOWN_S
        if not self._warned_unreachable:
            logger.warning(f"ollama unreachable: {exc}. "
                            f"Suppressing for {int(_UNREACHABLE_COOLDOWN_S)}s.")
            self._warned_unreachable = True

    def _mark_model_missing(self, exc: Exception) -> None:
        self._unreachable_until = time.monotonic() + _PERMANENT_UNREACHABLE_S
        if not self._warned_model_missing:
            logger.error(f"ollama model {self._model!r} not found: {exc}. "
                          f"Run: ollama pull {self._model}")
            self._warned_model_missing = True
