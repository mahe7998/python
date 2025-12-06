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

        # Max context window size (in words) - configurable via env var
        self.max_context_words = int(os.getenv("LLM_MAX_CONTEXT_WORDS", "4000"))

        # Create Ollama client instance with custom host
        self.client = ollama.Client(host=self.base_url)

        logger.info(f"Initialized Ollama client: {self.base_url} (model: {default_model}, max_context: {self.max_context_words} words)")

    def _chunk_text_at_sentences(self, text: str, max_words: int) -> list[str]:
        """
        Split text into chunks at sentence boundaries, respecting max word count.

        Args:
            text: Text to chunk
            max_words: Maximum words per chunk

        Returns:
            List of text chunks
        """
        import re
        sentence_pattern = r'([^.]+\.)\s*'
        sentences = re.findall(sentence_pattern, text)

        if not sentences:
            return [text]

        last_period_pos = text.rfind('.')
        if last_period_pos >= 0 and last_period_pos < len(text) - 1:
            remaining = text[last_period_pos + 1:].strip()
            if remaining:
                sentences.append(remaining)

        chunks = []
        current_chunk = []
        current_word_count = 0

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            sentence_words = len(sentence.split())

            if current_word_count + sentence_words > max_words and current_chunk:
                chunks.append(' '.join(current_chunk))
                current_chunk = []
                current_word_count = 0

            current_chunk.append(sentence)
            current_word_count += sentence_words

        if current_chunk:
            chunks.append(' '.join(current_chunk))

        return chunks if chunks else [text]

    async def is_available(self) -> bool:
        """
        Check if Ollama server is available

        Returns:
            True if Ollama is reachable, False otherwise
        """
        try:
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
            instruction: Instruction for how to rewrite
            model: Model to use (defaults to default_model)

        Returns:
            Rewritten text
        """
        model = model or self.default_model

        try:
            prompt = f"{instruction}\n\nOriginal text:\n{text}\n\nRewritten text:"

            logger.info(f"Requesting rewrite from Ollama (model: {model})")

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

    async def fix_grammar(self, text: str, model: Optional[str] = None, context_words: Optional[int] = None) -> str:
        """
        Fix grammar and spelling in text

        Args:
            text: Text to fix
            model: Model to use
            context_words: Max words per chunk

        Returns:
            Text with corrected grammar
        """
        max_words = context_words or self.max_context_words
        chunks = self._chunk_text_at_sentences(text, max_words)

        if len(chunks) > 1:
            logger.info(f"Processing {len(chunks)} chunks for grammar fixing")

        instruction = (
            "Fix all grammar, spelling, and punctuation errors in the following text. "
            "Preserve the original meaning and style. Only output the corrected text, "
            "nothing else."
        )

        processed_chunks = []
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk.split())} words)")
            processed_chunk = await self.rewrite_text(chunk, instruction, model)
            processed_chunks.append(processed_chunk)

        return ' '.join(processed_chunks)

    async def rephrase_professionally(self, text: str, model: Optional[str] = None, context_words: Optional[int] = None) -> str:
        """
        Rephrase text in a more professional tone

        Args:
            text: Text to rephrase
            model: Model to use
            context_words: Max words per chunk

        Returns:
            Professionally rephrased text
        """
        max_words = context_words or self.max_context_words
        chunks = self._chunk_text_at_sentences(text, max_words)

        if len(chunks) > 1:
            logger.info(f"Processing {len(chunks)} chunks for professional rephrasing")

        instruction = (
            "Rephrase the following text in a more professional and formal tone. "
            "Maintain the key information but improve clarity and professionalism. "
            "Only output the rephrased text, nothing else."
        )

        processed_chunks = []
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk.split())} words)")
            processed_chunk = await self.rewrite_text(chunk, instruction, model)
            processed_chunks.append(processed_chunk)

        return ' '.join(processed_chunks)

    async def summarize(self, text: str, model: Optional[str] = None, max_length: int = 100, context_words: Optional[int] = None) -> str:
        """
        Create a concise summary of text

        Args:
            text: Text to summarize
            model: Model to use
            max_length: Maximum length of summary in characters
            context_words: Max words per chunk

        Returns:
            Summary of the text
        """
        max_words = context_words or self.max_context_words
        chunks = self._chunk_text_at_sentences(text, max_words)
        first_chunk = chunks[0]

        logger.info(f"Summarizing text: {len(text.split())} words total, using first {len(first_chunk.split())} words")

        instruction = (
            f"Create a very concise summary of the following text in maximum {max_length} characters. "
            f"Capture the key points and main ideas in a single phrase or sentence. "
            f"IMPORTANT: Your response must be {max_length} characters or less. "
            f"Only output the summary, nothing else."
        )
        summary = await self.rewrite_text(first_chunk, instruction, model)

        if len(summary) > max_length:
            summary = summary[:max_length - 3] + "..."

        return summary

    async def improve_text(self, text: str, model: Optional[str] = None, context_words: Optional[int] = None) -> str:
        """
        Improve text overall (grammar, clarity, flow)

        Args:
            text: Text to improve
            model: Model to use
            context_words: Max words per chunk

        Returns:
            Improved text
        """
        max_words = context_words or self.max_context_words
        chunks = self._chunk_text_at_sentences(text, max_words)

        if len(chunks) > 1:
            logger.info(f"Processing {len(chunks)} chunks for text improvement")

        instruction = (
            "Improve the following text by fixing grammar, enhancing clarity, "
            "and improving flow. Preserve the original meaning and style. "
            "Only output the improved text, nothing else."
        )

        processed_chunks = []
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk.split())} words)")
            processed_chunk = await self.rewrite_text(chunk, instruction, model)
            processed_chunks.append(processed_chunk)

        return ' '.join(processed_chunks)

    async def extract_action_items(self, text: str, model: Optional[str] = None, context_words: Optional[int] = None) -> str:
        """
        Extract action items from transcription

        Args:
            text: Text to analyze
            model: Model to use
            context_words: Max words per chunk

        Returns:
            List of action items
        """
        max_words = context_words or self.max_context_words
        chunks = self._chunk_text_at_sentences(text, max_words)

        if len(chunks) > 1:
            logger.info(f"Processing {len(chunks)} chunks for action item extraction")

        instruction = (
            "Extract all action items, tasks, and to-dos from the following transcription. "
            "Format them as a bulleted list. If there are no action items, say 'No action items found.'"
        )

        processed_chunks = []
        for i, chunk in enumerate(chunks):
            logger.info(f"Processing chunk {i+1}/{len(chunks)} ({len(chunk.split())} words)")
            processed_chunk = await self.rewrite_text(chunk, instruction, model)
            processed_chunks.append(processed_chunk)

        combined_result = '\n'.join(processed_chunks)

        if all('no action items found' in chunk.lower() for chunk in processed_chunks):
            return 'No action items found.'

        return combined_result


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
