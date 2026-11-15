"""
agents/kernel_factory.py
========================
Builds a Semantic Kernel `Kernel` object according to LLM_MODE.

LLM_MODE=live    → real OpenAI ChatCompletion service (needs OPENAI_API_KEY)
LLM_MODE=offline → a lightweight stub service that always returns a fixed reply,
                   so the demo and all tests run without any API key.

Every agent calls `build_kernel()` to get its kernel; they never construct one
themselves.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion

load_dotenv()  # reads .env if present; silently a no-op otherwise


# ---------------------------------------------------------------------------
# Offline stub
# ---------------------------------------------------------------------------

class _OfflineChatCompletion:
    """
    Minimal stub that satisfies the Semantic Kernel ChatCompletion interface
    well enough for our agents to run without calling any external API.

    Our agents do NOT rely on the LLM response text — all analysis is done
    by the deterministic tool functions.  The LLM layer is present for
    architectural correctness (Semantic Kernel best-practice) but its reply
    is ignored.
    """

    service_id: str = "offline"

    async def get_chat_message_contents(self, *args, **kwargs):  # type: ignore[override]
        """Return a stub response."""
        from semantic_kernel.contents import ChatMessageContent, AuthorRole
        return [
            ChatMessageContent(
                role=AuthorRole.ASSISTANT,
                content="[offline stub — tools handle all analysis]",
            )
        ]


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------

def build_kernel(service_id: str = "chat") -> Kernel:
    """
    Create and return a configured Semantic Kernel Kernel.

    Args:
        service_id: Identifier used to register the chat service with the kernel.

    Returns:
        A ready-to-use Kernel instance.
    """
    kernel = Kernel()
    mode   = os.environ.get("LLM_MODE", "offline").lower()

    if mode == "live":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        model   = os.environ.get("OPENAI_MODEL", "gpt-4o")
        if not api_key:
            raise EnvironmentError(
                "LLM_MODE=live but OPENAI_API_KEY is not set. "
                "Add it to .env or set the environment variable."
            )
        service = OpenAIChatCompletion(
            service_id=service_id,
            ai_model_id=model,
            api_key=api_key,
        )
        kernel.add_service(service)
    else:
        # Offline mode: stub service (no network calls)
        stub = _OfflineChatCompletion()
        stub.service_id = service_id
        kernel.add_service(stub)  # type: ignore[arg-type]

    return kernel
