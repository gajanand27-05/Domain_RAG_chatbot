"""Configurable LLM provider layer.

    LLMProvider (abstract base)
    ├── GroqProvider      -> ChatGroq (Groq API)
    ├── GeminiProvider    -> ChatGoogleGenerativeAI (Google AI Studio)
    ├── OpenAIProvider    -> ChatOpenAI (api.openai.com)
    └── LocalProvider     -> ChatOpenAI pointed at any OpenAI-compatible
                             local server (Ollama, LM Studio, vLLM, ...)

The provider is selected with the LLM_PROVIDER variable in .env, so a new
model (including a local one) can be plugged in without touching the RAG
pipeline.
"""
import os
from abc import ABC, abstractmethod

from dotenv import load_dotenv

load_dotenv()


class LLMProviderError(Exception):
    """Raised when the selected provider is missing configuration."""


class LLMProvider(ABC):
    """Common interface every provider implements.

    The RAG pipeline only ever calls generate(messages) - it does not know
    which provider is active.
    """

    name = "base"
    default_model = ""

    @abstractmethod
    def _validate_config(self):
        """Check that the provider is configured. Raises LLMProviderError."""

    @abstractmethod
    def _build_model(self):
        """Create the LangChain chat model for this provider."""

    def is_configured(self):
        try:
            self._validate_config()
            return True
        except LLMProviderError:
            return False

    def model_name(self):
        return os.getenv(self._model_env(), self.default_model)

    def _model_env(self):
        return f"{self.name.upper()}_MODEL_NAME"

    def generate(self, messages):
        """Send [{role, content}] messages and return the model's text answer.

        Key validation happens here, so a missing key gives a clear, friendly
        error instead of a provider-specific stack trace.
        """
        self._validate_config()
        model = self._build_model()
        response = model.invoke(messages)
        content = getattr(response, "content", "")
        if isinstance(content, list):  # some providers return content blocks
            content = "".join(
                part.get("text", "") if isinstance(part, dict) else str(part)
                for part in content
            )
        return str(content).strip()


def _check_api_key(name, hint):
    value = os.getenv(name, "").strip()
    if not value or "your_" in value.lower() or value.lower().endswith("_here"):
        raise LLMProviderError(
            f"{name} is missing or still a placeholder. Put your real key in .env "
            f"(see .env.example). {hint}"
        )
    return value


class GroqProvider(LLMProvider):
    name = "groq"
    default_model = "llama-3.3-70b-versatile"

    def _validate_config(self):
        return _check_api_key("GROQ_API_KEY", "Keys are free at https://console.groq.com")

    def _build_model(self):
        from langchain_groq import ChatGroq

        return ChatGroq(
            groq_api_key=self._validate_config(),
            model=self.model_name(),
            temperature=0,
        )


class GeminiProvider(LLMProvider):
    name = "gemini"
    default_model = "gemini-2.0-flash"

    def _validate_config(self):
        return _check_api_key("GEMINI_API_KEY", "Keys are free at https://aistudio.google.com/apikey")

    def _build_model(self):
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(
            api_key=self._validate_config(),
            model=self.model_name(),
            temperature=0,
        )


class OpenAIProvider(LLMProvider):
    name = "openai"
    default_model = "gpt-4o-mini"

    def _validate_config(self):
        return _check_api_key("OPENAI_API_KEY", "Keys are at https://platform.openai.com/api-keys")

    def _build_model(self):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            api_key=self._validate_config(),
            model=self.model_name(),
            temperature=0,
        )


class LocalProvider(LLMProvider):
    """Any OpenAI-compatible local server (Ollama, LM Studio, vLLM, ...)."""

    name = "local"
    default_model = "llama3.1:8b"

    def _validate_config(self):
        # Nothing to validate up front; connection problems surface in generate()
        return os.getenv("LOCAL_BASE_URL", "http://localhost:11434/v1")

    def _build_model(self):
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            base_url=self._validate_config(),
            model=self.model_name(),
            api_key=os.getenv("LOCAL_API_KEY", "not-needed"),
            temperature=0,
        )


PROVIDERS = {p.name: p for p in (GroqProvider, GeminiProvider, OpenAIProvider, LocalProvider)}


def get_llm_provider(name=None):
    """Instantiate the provider selected by LLM_PROVIDER in .env."""
    name = (name or os.getenv("LLM_PROVIDER", "groq")).strip().lower()
    if name not in PROVIDERS:
        raise LLMProviderError(
            f"Unknown LLM_PROVIDER '{name}'. Available providers: {', '.join(PROVIDERS)}"
        )
    return PROVIDERS[name]()
