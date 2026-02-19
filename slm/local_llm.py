"""
In-process local LLM via llama-cpp-python. No server, no cloud.
Deterministic: temperature=0, seed=42.
"""
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class LocalLLMConfig:
    model_path: str
    n_ctx: int = 4096
    n_threads: Optional[int] = None
    n_batch: int = 512
    temperature: float = 0.0
    top_p: float = 1.0
    top_k: int = 0
    seed: int = 42
    max_tokens: int = 300
    verbose: bool = False


class LocalLLM:
    """Load GGUF in-process and generate from system + user prompts."""

    def __init__(self, config: LocalLLMConfig):
        self.config = config
        n_threads = config.n_threads
        if n_threads is None:
            try:
                n_threads = min(8, (os.cpu_count() or 4))
            except Exception:
                n_threads = 4
        self._llm = None
        self._model_path = config.model_path
        self._n_ctx = config.n_ctx
        self._n_threads = n_threads
        self._n_batch = config.n_batch
        self._seed = config.seed
        self._verbose = config.verbose

    def _ensure_loaded(self) -> None:
        if self._llm is not None:
            return
        from llama_cpp import Llama
        self._llm = Llama(
            model_path=self._model_path,
            n_ctx=self._n_ctx,
            n_threads=self._n_threads,
            n_batch=self._n_batch,
            seed=self._seed,
            verbose=self._verbose,
        )

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: Optional[int] = None) -> str:
        """Return generated text. Uses create_chat_completion with temperature=0."""
        self._ensure_loaded()
        max_tok = max_tokens if max_tokens is not None else self.config.max_tokens
        messages = [
            {"role": "system", "content": system_prompt or ""},
            {"role": "user", "content": user_prompt or ""},
        ]
        out = self._llm.create_chat_completion(
            messages=messages,
            max_tokens=max_tok,
            temperature=self.config.temperature,
            top_p=self.config.top_p,
            top_k=self.config.top_k,
            seed=self.config.seed,
        )
        choice = (out.get("choices") or [None])[0]
        if not choice:
            return ""
        msg = choice.get("message") or choice
        return (msg.get("content") or "").strip()
