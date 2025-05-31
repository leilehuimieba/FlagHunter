"""Conversation history management for GHOSTCREW."""

from typing import List, Dict, Optional
import tiktoken
from config.app_config import app_config


class ConversationManager:
    """Manages conversation history and dialogue tracking."""
    
    def __init__(self, max_tokens: int = 4000):
        """
        Initialize the conversation manager.
        
        Args:
            max_tokens: Maximum tokens to keep in history
        """
        self.history: List[Dict[str, str]] = []
        self.max_tokens = max_tokens
        self.model_name = app_config.model_name
    
    def add_dialogue(self, user_query: str, ai_response: str = "") -> None:
        """
        Add a dialogue entry to the conversation history.
        
        Args:
            user_query: The user's query
            ai_response: The AI's response (can be empty initially)
        """
        dialogue = {
            "user_query": user_query,
            "ai_response": ai_response
        }
        self.history.append(dialogue)
        
        # Trim history if it exceeds token limit
        self._trim_history()
    
    def update_last_response(self, ai_response: str) -> None:
        """
        Update the AI response for the last dialogue entry.
        
        Args:
            ai_response: The AI's response to update
        """
        if self.history:
            self.history[-1]["ai_response"] = ai_response
    
    def get_history(self) -> List[Dict[str, str]]:
        """Get the complete conversation history."""
        return self.history
    
    def get_history_for_context(self) -> List[Dict[str, str]]:
        """Get conversation history suitable for context."""
        return self.history
    
    def estimate_tokens(self) -> int:
        """
        Estimate the number of tokens in the conversation history.
        
        Returns:
            Estimated token count
        """
        try:
            encoding = tiktoken.encoding_for_model(self.model_name)
            return sum(
                len(encoding.encode(entry['user_query'])) + 
                len(encoding.encode(entry.get('ai_response', ''))) 
                for entry in self.history
            )
        except Exception:
            # Fall back to approximate counting if tiktoken fails
            return sum(
                len(entry['user_query'].split()) + 
                len(entry.get('ai_response', '').split()) 
                for entry in self.history
            )
    
    def _trim_history(self) -> None:
        """Trim history to keep token count under the limit."""
        while self.estimate_tokens() > self.max_tokens and len(self.history) > 1:
            self.history.pop(0)
    
    def clear_history(self) -> None:
        """Clear all conversation history."""
        self.history = []
    
    def get_dialogue_count(self) -> int:
        """Get the number of dialogues in history."""
        return len(self.history)
    
    def get_workflow_conversation(self, start_index: int) -> List[Dict[str, str]]:
        """
        Get conversation history starting from a specific index.
        
        Args:
            start_index: The index to start from
            
        Returns:
            Subset of conversation history
        """
        return self.history[start_index:]
    
    def export_history(self) -> str:
        """
        Export conversation history as formatted text.
        
        Returns:
            Formatted conversation history
        """
        if not self.history:
            return "No conversation history available."
        
        output = []
        for i, entry in enumerate(self.history, 1):
            output.append(f"=== Dialogue {i} ===")
            output.append(f"User: {entry['user_query']}")
            if entry.get('ai_response'):
                output.append(f"AI: {entry['ai_response']}")
            output.append("")
        
        return "\n".join(output) 