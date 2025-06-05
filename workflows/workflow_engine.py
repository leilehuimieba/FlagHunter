"""Workflow execution engine for GHOSTCREW."""

import asyncio
from typing import List, Dict, Any, Optional
from colorama import Fore, Style
from datetime import datetime
from workflows.workflow_definitions import (
    get_available_workflows, get_workflow_by_key, list_workflow_names
)
from config.constants import (
    ERROR_NO_WORKFLOWS, ERROR_WORKFLOW_NOT_FOUND, WORKFLOW_TARGET_PROMPT,
    WORKFLOW_CONFIRM_PROMPT, WORKFLOW_CANCELLED_MESSAGE, WORKFLOW_COMPLETED_MESSAGE
)
from tools.mcp_manager import MCPManager


class WorkflowEngine:
    """Handles automated workflow execution."""
    
    def __init__(self):
        """Initialize the workflow engine."""
        self.workflows_available = self._check_workflows_available()
    
    @staticmethod
    def _check_workflows_available() -> bool:
        """Check if workflow definitions are available."""
        try:
            # Test import to verify module is available
            from workflows.workflow_definitions import get_available_workflows
            return True
        except ImportError:
            return False
    
    def is_available(self) -> bool:
        """Check if workflows are available."""
        return self.workflows_available
    
    @staticmethod
    def show_automated_menu() -> Optional[List[tuple]]:
        """Display the automated workflow selection menu."""
        try:
            print(f"\n{Fore.CYAN}WORKFLOWS{Style.RESET_ALL}")
            print(f"{Fore.WHITE}{'='*50}{Style.RESET_ALL}")
            
            workflow_list = list_workflow_names()
            workflows = get_available_workflows()
            
            for i, (key, name) in enumerate(workflow_list, 1):
                description = workflows[key]["description"]
                step_count = len(workflows[key]["steps"])
                print(f"{i}. {Fore.YELLOW}{name}{Style.RESET_ALL}")
                print(f"   {Fore.WHITE}{description}{Style.RESET_ALL}")
                print(f"   {Fore.CYAN}Steps: {step_count}{Style.RESET_ALL}")
                print()
            
            print(f"{len(workflow_list)+1}. {Fore.RED}Back to Main Menu{Style.RESET_ALL}")
            
            return workflow_list
        except Exception:
            print(f"{Fore.YELLOW}Error loading workflows.{Style.RESET_ALL}")
            return None
    
    async def run_automated_workflow(
        self, 
        workflow: Dict[str, Any], 
        target: str, 
        connected_servers: List[Any], 
        conversation_history: List[Dict[str, str]], 
        kb_instance: Any,
        run_agent_func: Any
    ) -> List[Dict[str, Any]]:
        """
        Execute a workflow.
        
        Args:
            workflow: The workflow definition
            target: The target for the workflow
            connected_servers: List of connected MCP servers
            conversation_history: Conversation history list
            kb_instance: Knowledge base instance
            run_agent_func: Function to run agent queries
            
        Returns:
            List of workflow results
        """
        available_tools = MCPManager.get_available_tools(connected_servers)
        
        print(f"\n{Fore.CYAN}Starting Automated Workflow: {workflow['name']}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Target: {target}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Available Tools: {', '.join(available_tools) if available_tools else 'None'}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Description: {workflow['description']}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}{'='*60}{Style.RESET_ALL}")
        
        results = []
        
        for i, step in enumerate(workflow['steps'], 1):
            print(f"\n{Fore.CYAN}Step {i}/{len(workflow['steps'])}{Style.RESET_ALL}")
            formatted_step = step.format(target=target)
            print(f"{Fore.WHITE}{formatted_step}{Style.RESET_ALL}")
            
            # Create comprehensive query for this step
            enhanced_query = f"""
TARGET: {target}
STEP: {formatted_step}

Execute this step and provide the results.
"""
            
            # Execute the step through the agent
            result = await run_agent_func(
                enhanced_query, 
                connected_servers, 
                history=conversation_history, 
                streaming=True, 
                kb_instance=kb_instance
            )
            
            if result and hasattr(result, "final_output"):
                results.append({
                    "step": i,
                    "description": formatted_step,
                    "output": result.final_output
                })
                
                # Add to conversation history
                conversation_history.append({
                    "user_query": enhanced_query,
                    "ai_response": result.final_output
                })
            
            print(f"{Fore.GREEN}Step {i} completed{Style.RESET_ALL}")
            
            # Brief delay between steps
            await asyncio.sleep(1)
        
        # Workflow completion summary
        print(f"{Fore.CYAN}Steps executed: {len(results)}/{len(workflow['steps'])}{Style.RESET_ALL}")
        
        return results
    
    def get_workflow(self, workflow_key: str) -> Optional[Dict[str, Any]]:
        """Get a workflow by its key."""
        try:
            return get_workflow_by_key(workflow_key)
        except Exception:
            return None
    
    def get_workflow_list(self) -> List[tuple]:
        """Get list of available workflows."""
        try:
            return list_workflow_names()
        except Exception:
            return [] 