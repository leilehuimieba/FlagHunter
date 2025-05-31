"""Agent execution and query processing for GHOSTCREW."""

import json
import asyncio
import traceback
from typing import List, Dict, Optional, Any
from colorama import Fore, Style
from agents import Agent, RunConfig, Runner, ModelSettings
from openai.types.responses import ResponseTextDeltaEvent, ResponseContentPartDoneEvent
from core.model_manager import model_manager
from config.constants import BASE_INSTRUCTIONS, CONNECTION_RETRY_DELAY, DEFAULT_KNOWLEDGE_BASE_PATH
from config.app_config import app_config
import os


class AgentRunner:
    """Handles AI agent query processing and execution."""
    
    def __init__(self):
        """Initialize the agent runner."""
        self.model_provider = model_manager.get_model_provider()
        self.client = app_config.get_openai_client()
    
    async def run_agent(
        self,
        query: str,
        mcp_servers: List[Any],  # Use Any to avoid import issues
        history: Optional[List[Dict[str, str]]] = None,
        streaming: bool = True,
        kb_instance: Any = None
    ) -> Any:
        """
        Run cybersecurity agent with connected MCP servers, supporting streaming output and conversation history.

        Args:
            query: User's natural language query
            mcp_servers: List of connected MCPServerStdio instances
            history: Conversation history, list containing user questions and AI answers
            streaming: Whether to use streaming output
            kb_instance: Knowledge base instance for retrieval
            
        Returns:
            Agent execution result
        """
        # If no history is provided, initialize an empty list
        if history is None:
            history = []
        
        try:
            # Build instructions containing conversation history
            instructions = self._build_instructions(mcp_servers, history, query, kb_instance)
            
            # Calculate max output tokens
            max_output_tokens = model_manager.calculate_max_output_tokens(instructions, query)
            
            # Set model settings based on whether there are connected MCP servers
            model_settings = self._create_model_settings(mcp_servers, max_output_tokens)
            
            # Create agent
            secure_agent = Agent(
                name="Cybersecurity Expert",
                instructions=instructions,
                mcp_servers=mcp_servers,
                model_settings=model_settings
            )

            print(f"{Fore.CYAN}\nProcessing query: {Fore.WHITE}{query}{Style.RESET_ALL}\n")

            if streaming:
                return await self._run_streaming(secure_agent, query)
            else:
                # Non-streaming mode could be implemented here if needed
                pass

        except Exception as e:
            print(f"{Fore.RED}Error processing agent request: {e}{Style.RESET_ALL}", flush=True)
            traceback.print_exc()
            return None
    
    def _build_instructions(
        self,
        mcp_servers: List[Any],  # Use Any to avoid import issues
        history: List[Dict[str, str]],
        query: str,
        kb_instance: Any
    ) -> str:
        """Build agent instructions with context."""
        instructions = BASE_INSTRUCTIONS
        
        # Add information about available tools
        if mcp_servers:
            available_tool_names = [server.name for server in mcp_servers]
            if available_tool_names:
                instructions += f"\n\nYou have access to the following tools: {', '.join(available_tool_names)}."

        # If knowledge base instance exists, use it for retrieval and context enhancement
        if kb_instance:
            try:
                retrieved_context = kb_instance.search(query)
                if retrieved_context:
                    # Add file path information to make LLM aware of actual files
                    available_files = []
                    if os.path.exists(DEFAULT_KNOWLEDGE_BASE_PATH):
                        for filename in os.listdir(DEFAULT_KNOWLEDGE_BASE_PATH):
                            filepath = os.path.join(DEFAULT_KNOWLEDGE_BASE_PATH, filename)
                            if os.path.isfile(filepath):
                                available_files.append(filename)
                    
                    file_info = ""
                    if available_files:
                        file_info = f"\n\nIMPORTANT: The following actual files are available in the knowledge folder that you can reference by path:\n"
                        for filename in available_files:
                            file_info += f"- {DEFAULT_KNOWLEDGE_BASE_PATH}/{filename}\n"
                        file_info += "\nWhen using security tools that require external files, you can reference these files by their full path.\n"
                        file_info += f"ONLY use {DEFAULT_KNOWLEDGE_BASE_PATH}/ for files.\n"
                    
                    instructions = f"Based on the following knowledge base information:\n{retrieved_context}{file_info}\n\n{instructions}"
                    print(f"{Fore.MAGENTA}Relevant information retrieved from knowledge base.{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}Failed to retrieve information from knowledge base: {e}{Style.RESET_ALL}")

        # If there's conversation history, add it to the instructions
        if history:
            instructions += "\n\nBelow is the previous conversation history, please refer to this information to answer the user's question:\n"
            for i, entry in enumerate(history):
                instructions += f"\nUser question {i+1}: {entry['user_query']}"
                if 'ai_response' in entry and entry['ai_response']:
                    instructions += f"\nAI answer {i+1}: {entry['ai_response']}\n"
        
        return instructions
    
    def _create_model_settings(self, mcp_servers: List[Any], max_output_tokens: int) -> ModelSettings:
        """Create model settings based on available tools."""
        if mcp_servers:
            # With tools available, enable tool_choice and parallel_tool_calls
            return ModelSettings(
                temperature=0.6,
                top_p=0.9,
                max_tokens=max_output_tokens,
                tool_choice="auto",
                parallel_tool_calls=False,
                truncation="auto"
            )
        else:
            # Without tools, don't set tool_choice or parallel_tool_calls
            return ModelSettings(
                temperature=0.6,
                top_p=0.9,
                max_tokens=max_output_tokens,
                truncation="auto"
            )
    
    async def _run_streaming(self, agent: Agent, query: str) -> Any:
        """Run agent with streaming output."""
        result = Runner.run_streamed(
            agent,
            input=query,
            max_turns=10,
            run_config=RunConfig(
                model_provider=self.model_provider,
                trace_include_sensitive_data=True,
                handoff_input_filter=None
            )
        )

        print(f"{Fore.GREEN}Reply:{Style.RESET_ALL}", end="", flush=True)
        
        try:
            async for event in result.stream_events():
                await self._handle_stream_event(event)
        except Exception as e:
            await self._handle_stream_error(e)

        print(f"\n\n{Fore.GREEN}Query completed!{Style.RESET_ALL}")
        return result
    
    async def _handle_stream_event(self, event: Any) -> None:
        """Handle individual stream events."""
        if event.type == "raw_response_event":
            if isinstance(event.data, ResponseTextDeltaEvent):
                print(f"{Fore.WHITE}{event.data.delta}{Style.RESET_ALL}", end="", flush=True)
            elif isinstance(event.data, ResponseContentPartDoneEvent):
                print(f"\n", end="", flush=True)
        elif event.type == "run_item_stream_event":
            if event.item.type == "tool_call_item":
                await self._handle_tool_call(event.item)
            elif event.item.type == "tool_call_output_item":
                await self._handle_tool_output(event.item)
    
    async def _handle_tool_call(self, item: Any) -> None:
        """Handle tool call events."""
        raw_item = getattr(item, "raw_item", None)
        tool_name = ""
        tool_args = {}
        
        if raw_item:
            tool_name = getattr(raw_item, "name", "Unknown tool")
            tool_str = getattr(raw_item, "arguments", "{}")
            if isinstance(tool_str, str):
                try:
                    tool_args = json.loads(tool_str)
                except json.JSONDecodeError:
                    tool_args = {"raw_arguments": tool_str}
        
        print(f"\n{Fore.CYAN}Tool name: {tool_name}{Style.RESET_ALL}", flush=True)
        print(f"\n{Fore.CYAN}Tool parameters: {tool_args}{Style.RESET_ALL}", flush=True)
    
    async def _handle_tool_output(self, item: Any) -> None:
        """Handle tool output events."""
        raw_item = getattr(item, "raw_item", None)
        tool_id = "Unknown tool ID"
        
        if isinstance(raw_item, dict) and "call_id" in raw_item:
            tool_id = raw_item["call_id"]
        
        output = getattr(item, "output", "Unknown output")
        output_text = self._parse_tool_output(output)
        
        print(f"\n{Fore.GREEN}Tool call {tool_id} returned result: {output_text}{Style.RESET_ALL}", flush=True)
    
    def _parse_tool_output(self, output: Any) -> str:
        """Parse tool output into readable text."""
        if isinstance(output, str) and (output.startswith("{") or output.startswith("[")):
            try:
                output_data = json.loads(output)
                if isinstance(output_data, dict):
                    if 'type' in output_data and output_data['type'] == 'text' and 'text' in output_data:
                        return output_data['text']
                    elif 'text' in output_data:
                        return output_data['text']
                    elif 'content' in output_data:
                        return output_data['content']
                    else:
                        return json.dumps(output_data, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                return f"Unparsable JSON output: {output}"
        return str(output)
    
    async def _handle_stream_error(self, error: Exception) -> None:
        """Handle streaming errors."""
        print(f"{Fore.RED}Error processing streamed response event: {error}{Style.RESET_ALL}", flush=True)
        
        if 'Connection error' in str(error):
            print(f"{Fore.YELLOW}Connection error details:{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}1. Check network connection{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}2. Verify API address: {app_config.base_url}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}3. Check API key validity{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}4. Try reconnecting...{Style.RESET_ALL}")
            await asyncio.sleep(CONNECTION_RETRY_DELAY)
            
            try:
                await self.client.connect()
                print(f"{Fore.GREEN}Reconnected successfully{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}Reconnection failed: {e}{Style.RESET_ALL}")


# Create singleton instance
agent_runner = AgentRunner() 