"""
AID Demo - zentrale LLM/API-Konfiguration.
Unterstützt OpenAI (gpt-*) und Anthropic Claude (claude-*) Modelle.
"""

from __future__ import annotations

import os


DEFAULT_MODEL = "gpt-4o-mini"

_CLAUDE_MODELS = {"claude-sonnet-4-6", "claude-opus-4-7", "claude-haiku-4-5-20251001"}


def get_model_name() -> str:
    return os.getenv("OPENAI_MODEL", DEFAULT_MODEL)


def _is_claude_model(model: str) -> bool:
    return model.startswith("claude-")


def is_llm_configured() -> bool:
    """True, wenn ein API-Key für den konfigurierten Provider gesetzt ist."""
    model = get_model_name()
    if _is_claude_model(model):
        return bool(os.getenv("ANTHROPIC_API_KEY"))
    return bool(os.getenv("OPENAI_API_KEY"))


def get_chat_model(*, temperature: float = 0.0):
    """Erzeugt ein LangChain-Chatmodell — OpenAI oder Anthropic je nach Modellname."""
    model = get_model_name()
    if _is_claude_model(model):
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=model, temperature=temperature)
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=model, temperature=temperature)


def invoke_messages(messages: list, *, temperature: float = 0.0) -> str | None:
    """Führt einen LLM-Call aus, falls ein API-Key gesetzt ist."""
    if not is_llm_configured():
        return None
    response = get_chat_model(temperature=temperature).invoke(messages)
    return response.content
