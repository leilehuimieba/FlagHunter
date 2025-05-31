"""Application configuration and initialization for GHOSTCREW."""

import os
from typing import Optional
from dotenv import load_dotenv
from openai import AsyncOpenAI


class AppConfig:
    """Manages application configuration and API client initialization."""
    
    def __init__(self):
        """Initialize application configuration."""
        # Load environment variables
        load_dotenv()
        
        # Set API-related environment variables
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_BASE_URL")
        self.model_name = os.getenv("MODEL_NAME")
        
        # Validate configuration
        self._validate_config()
        
        # Initialize OpenAI client
        self._client = AsyncOpenAI(
            base_url=self.base_url,
            api_key=self.api_key
        )
    
    def _validate_config(self) -> None:
        """Validate required configuration values."""
        if not self.api_key:
            raise ValueError("API key not set")
        if not self.base_url:
            raise ValueError("API base URL not set")
        if not self.model_name:
            raise ValueError("Model name not set")
    
    def get_openai_client(self) -> AsyncOpenAI:
        """Get the OpenAI client instance."""
        return self._client


# Create singleton instance
app_config = AppConfig() 