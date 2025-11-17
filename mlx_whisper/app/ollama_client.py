"""
Ollama client for AI-powered text review and rewriting
"""
import os
import logging
from typing import Optional
import asyncio

import ollama

logger = logging.getLogger(__name__)


class OllamaClient:
    """
    Client for interacting with local Ollama instance
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        default_model: str = "llama3.3:70b",
    ):
        """
        Initialize Ollama client

        Args:
            base_url: Ollama server URL (defaults to env var OLLAMA_BASE_URL)
            default_model: Default model to use for generation
        """
        self.base_url = base_url or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self.default_model = default_model

        # Create Ollama client instance with custom host
        self.client = ollama.Client(host=self.base_url)

        logger.info(f"Initialized Ollama client: {self.base_url} (model: {default_model})")

    async def is_available(self) -> bool:
        """
        Check if Ollama server is available

        Returns:
            True if Ollama is reachable, False otherwise
        """
        try:
            # Run in thread pool since ollama library is synchronous
            loop = asyncio.get_event_loop()
            models = await loop.run_in_executor(None, self.client.list)
            logger.info(f"Ollama is available. Models: {len(models.get('models', []))}")
            return True
        except Exception as e:
            logger.warning(f"Ollama not available: {e}")
            return False

    async def rewrite_text(
        self,
        text: str,
        instruction: str,
        model: Optional[str] = None,
    ) -> str:
        """
        Rewrite text based on instruction using Ollama

        Args:
            text: Text to rewrite
            instruction: Instruction for how to rewrite (e.g., "Fix grammar", "Rephrase professionally")
            model: Model to use (defaults to default_model)

        Returns:
            Rewritten text
        """
        model = model or self.default_model

        try:
            prompt = f"{instruction}\n\nOriginal text:\n{text}\n\nRewritten text:"

            logger.info(f"Requesting rewrite from Ollama (model: {model})")

            # Run in thread pool since ollama library is synchronous
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.generate(model=model, prompt=prompt),
            )

            rewritten = response.get("response", "").strip()
            logger.info(f"Received rewrite from Ollama ({len(rewritten)} chars)")

            return rewritten

        except Exception as e:
            logger.error(f"Error rewriting text with Ollama: {e}")
            raise

    async def fix_grammar(self, text: str, model: Optional[str] = None) -> str:
        """
        Fix grammar and spelling in text

        Args:
            text: Text to fix
            model: Model to use

        Returns:
            Text with corrected grammar
        """
        instruction = (
            "Fix all grammar, spelling, and punctuation errors in the following text. "
            "Preserve the original meaning and style. Only output the corrected text, "
            "nothing else."
        )
        return await self.rewrite_text(text, instruction, model)

    async def rephrase_professionally(self, text: str, model: Optional[str] = None) -> str:
        """
        Rephrase text in a more professional tone

        Args:
            text: Text to rephrase
            model: Model to use

        Returns:
            Professionally rephrased text
        """
        instruction = (
            "Rephrase the following text in a more professional and formal tone. "
            "Maintain the key information but improve clarity and professionalism. "
            "Only output the rephrased text, nothing else."
        )
        return await self.rewrite_text(text, instruction, model)

    async def summarize(self, text: str, model: Optional[str] = None) -> str:
        """
        Create a concise summary of text

        Args:
            text: Text to summarize
            model: Model to use

        Returns:
            Summary of the text
        """
        instruction = (
            "Create a concise summary of the following text. "
            "Capture the key points and main ideas. Keep it brief but informative. "
            "Only output the summary, nothing else."
        )
        return await self.rewrite_text(text, instruction, model)

    async def improve_text(self, text: str, model: Optional[str] = None) -> str:
        """
        Improve text overall (grammar, clarity, flow)

        Args:
            text: Text to improve
            model: Model to use

        Returns:
            Improved text
        """
        instruction = (
            "Improve the following text by fixing grammar, enhancing clarity, "
            "and improving flow. Preserve the original meaning and style. "
            "Only output the improved text, nothing else."
        )
        return await self.rewrite_text(text, instruction, model)

    async def extract_action_items(self, text: str, model: Optional[str] = None) -> str:
        """
        Extract action items from transcription

        Args:
            text: Text to analyze
            model: Model to use

        Returns:
            List of action items
        """
        instruction = (
            "Extract all action items, tasks, and to-dos from the following transcription. "
            "Format them as a bulleted list. If there are no action items, say 'No action items found.'"
        )
        return await self.rewrite_text(text, instruction, model)


# Global client instance
ollama_client: Optional[OllamaClient] = None


def get_ollama_client() -> OllamaClient:
    """
    Get or create Ollama client instance

    Returns:
        OllamaClient instance
    """
    global ollama_client
    if ollama_client is None:
        ollama_client = OllamaClient()

    return ollama_client
