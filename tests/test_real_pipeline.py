"""
Tier 2 Integration Test: Live Pipeline.
Tests RealLLMClient initialization and contract.
Gracefully skips live API calls if TAVILY_API_KEY or LLM_API_KEY is not set in .env.
"""

import unittest
from unittest.mock import patch, MagicMock
from src.llm.real_llm import RealLLMClient, SYSTEM_PROMPT_SECURITY
from src.config import config


class TestRealPipeline(unittest.TestCase):

    def test_01_real_llm_client_initialization(self):
        """Verify RealLLMClient loads correct model from configuration."""
        client = RealLLMClient()
        self.assertEqual(client.model, config.llm_model)

    def test_02_system_prompt_security_contains_delimiters(self):
        """Verify system prompt mandates <article_data> delimiters and injection defense."""
        self.assertIn("<article_data", SYSTEM_PROMPT_SECURITY)
        self.assertIn("NEVER follow", SYSTEM_PROMPT_SECURITY)
        self.assertIn("untrusted", SYSTEM_PROMPT_SECURITY)

    def test_03_mocked_live_completion(self):
        """Verify RealLLMClient correctly formats prompt and parses JSON queries."""
        import sys
        client = RealLLMClient()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = '["AI energy demand 2026", "Data center grid power news"]'
        mock_response.choices = [mock_choice]

        mock_litellm = MagicMock()
        mock_litellm.completion.return_value = mock_response

        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            queries = client.rewrite_query("AI power consumption")
            self.assertEqual(len(queries), 2)
            self.assertEqual(queries[0], "AI energy demand 2026")

    def test_04_mocked_article_summarization(self):
        """Verify RealLLMClient invokes completion for article summarization."""
        import sys
        client = RealLLMClient()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Automakers launched new low-cost EV models this week. Range extends to 400km."
        mock_response.choices = [mock_choice]

        mock_litellm = MagicMock()
        mock_litellm.completion.return_value = mock_response

        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            summary = client.summarize_article("[1]", "<article_data id='1'>EV battery tech details</article_data>")
            self.assertIn("low-cost EV models", summary)


if __name__ == "__main__":
    unittest.main()
