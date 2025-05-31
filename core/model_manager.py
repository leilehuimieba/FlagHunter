"""Model management and AI model setup for GHOSTCREW."""

import tiktoken
from agents import Model, ModelProvider, OpenAIChatCompletionsModel
from config.app_config import app_config
from config.constants import MAX_TOTAL_TOKENS, RESPONSE_BUFFER


class DefaultModelProvider(ModelProvider):
    """Model provider using OpenAI compatible interface."""
    
    def get_model(self, model_name: str) -> Model:
        """Get a model instance with the specified name."""
        return OpenAIChatCompletionsModel(
            model=model_name or app_config.model_name,
            openai_client=app_config.get_openai_client()
        )


class ModelManager:
    """Manages AI model operations and token counting."""
    
    def __init__(self):
        """Initialize the model manager."""
        self.model_provider = DefaultModelProvider()
        self.model_name = app_config.model_name
    
    @staticmethod
    def count_tokens(text: str, model_name: str = None) -> int:
        """
        Count tokens in the given text.
        
        Args:
            text: The text to count tokens for
            model_name: The model name to use for encoding (defaults to configured model)
            
        Returns:
            Number of tokens in the text
        """
        try:
            model = model_name or app_config.model_name
            encoding = tiktoken.encoding_for_model(model)
            return len(encoding.encode(text))
        except Exception:
            # Fall back to approximate counting if tiktoken fails
            return len(text.split())
    
    @staticmethod
    def calculate_max_output_tokens(input_text: str, query: str) -> int:
        """
        Calculate the maximum output tokens based on input size.
        
        Args:
            input_text: The base instructions or context
            query: The user query
            
        Returns:
            Maximum number of output tokens
        """
        input_token_estimate = ModelManager.count_tokens(input_text) + ModelManager.count_tokens(query)
        
        max_output_tokens = max(512, MAX_TOTAL_TOKENS - input_token_estimate)
        max_output_tokens = min(max_output_tokens, RESPONSE_BUFFER)
        
        return max_output_tokens
    
    def get_model_provider(self) -> ModelProvider:
        """Get the model provider instance."""
        return self.model_provider


# Create a singleton instance
model_manager = ModelManager() 