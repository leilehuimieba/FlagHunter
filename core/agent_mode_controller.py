"""Agent Mode Controller for autonomous PTT-based penetration testing."""

import asyncio
import json
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from colorama import Fore, Style

from core.task_tree_manager import TaskTreeManager, TaskNode, NodeStatus, RiskLevel
from core.ptt_reasoning import PTTReasoningModule
from core.model_manager import model_manager
from config.constants import DEFAULT_KNOWLEDGE_BASE_PATH


class AgentModeController:
    """Orchestrates the autonomous agent workflow using PTT."""
    
    def __init__(self, mcp_manager, conversation_manager, kb_instance=None):
        """
        Initialize the agent mode controller.
        
        Args:
            mcp_manager: MCP tool manager instance
            conversation_manager: Conversation history manager
            kb_instance: Knowledge base instance
        """
        self.mcp_manager = mcp_manager
        self.conversation_manager = conversation_manager
        self.kb_instance = kb_instance
        self.tree_manager = TaskTreeManager()
        self.reasoning_module = PTTReasoningModule(self.tree_manager)
        self.max_iterations = 50  # Safety limit
        self.iteration_count = 0
        self.start_time = None
        self.paused = False
        self.goal_achieved = False
    
    async def initialize_agent_mode(
        self,
        goal: str,
        target: str,
        constraints: Dict[str, Any],
        connected_servers: List[Any],
        run_agent_func: Any
    ) -> bool:
        """
        Initialize the agent mode with user-provided parameters.
        
        Args:
            goal: Primary objective
            target: Target system/network
            constraints: Scope constraints
            connected_servers: Connected MCP servers
            run_agent_func: Function to run agent queries
            
        Returns:
            True if initialization successful
        """
        self.connected_servers = connected_servers
        self.run_agent_func = run_agent_func
        self.start_time = datetime.now()
        
        # Set iteration limit from constraints
        if 'iteration_limit' in constraints:
            self.max_iterations = constraints['iteration_limit']
        
        print(f"\n{Fore.CYAN}Initializing Agent Mode...{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Goal: {goal}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Target: {target}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Iteration Limit: {self.max_iterations}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Constraints: {json.dumps(constraints, indent=2)}{Style.RESET_ALL}")
        
        # Initialize the task tree
        self.tree_manager.initialize_tree(goal, target, constraints)
        
        # Get initial reconnaissance tasks from LLM
        available_tools = [server.name for server in self.connected_servers]
        init_prompt = self.reasoning_module.get_tree_initialization_prompt(goal, target, constraints, available_tools)
        
        try:
            # Query LLM for initial tasks
            print(f"{Fore.YELLOW}Requesting initial tasks from AI (Available tools: {', '.join(available_tools)})...{Style.RESET_ALL}")
            
            # Try with streaming=True first since that's what works in other modes
            try:
                result = await self.run_agent_func(
                    init_prompt,
                    self.connected_servers,
                    history=[],
                    streaming=True,
                    kb_instance=self.kb_instance
                )
                print(f"{Fore.GREEN}Agent runner completed (streaming=True){Style.RESET_ALL}")
            except Exception as stream_error:
                print(f"{Fore.YELLOW}Streaming mode failed: {stream_error}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Trying with streaming=False...{Style.RESET_ALL}")
                result = await self.run_agent_func(
                    init_prompt,
                    self.connected_servers,
                    history=[],
                    streaming=False,
                    kb_instance=self.kb_instance
                )
                print(f"{Fore.GREEN}Agent runner completed (streaming=False){Style.RESET_ALL}")
            
            print(f"{Fore.YELLOW}Parsing AI response...{Style.RESET_ALL}")
            
            # Debug: Check what we got back
            if not result:
                print(f"{Fore.RED}No result returned from agent runner{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}This usually indicates an LLM configuration issue{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Falling back to default reconnaissance tasks...{Style.RESET_ALL}")
                
                # Use default tasks instead
                initial_tasks = self._get_default_initial_tasks(target, available_tools)
            else:
                print(f"{Fore.GREEN}Got result from agent runner: {type(result)}{Style.RESET_ALL}")
                
                # Check different possible response formats
                response_text = None
                if hasattr(result, "final_output"):
                    response_text = result.final_output
                    print(f"{Fore.CYAN}Using result.final_output{Style.RESET_ALL}")
                elif hasattr(result, "output"):
                    response_text = result.output
                    print(f"{Fore.CYAN}Using result.output{Style.RESET_ALL}")
                elif hasattr(result, "content"):
                    response_text = result.content
                    print(f"{Fore.CYAN}Using result.content{Style.RESET_ALL}")
                elif isinstance(result, str):
                    response_text = result
                    print(f"{Fore.CYAN}Using result as string{Style.RESET_ALL}")
                else:
                    print(f"{Fore.RED}Unknown result format: {type(result)}{Style.RESET_ALL}")
                    print(f"{Fore.YELLOW}Result attributes: {dir(result)}{Style.RESET_ALL}")
                    
                    # Try to get any text content from the result
                    for attr in ['text', 'message', 'response', 'data']:
                        if hasattr(result, attr):
                            response_text = getattr(result, attr)
                            print(f"{Fore.CYAN}Found text in result.{attr}{Style.RESET_ALL}")
                            break
                
                if not response_text:
                    print(f"{Fore.RED}No response text found in result{Style.RESET_ALL}")
                    print(f"{Fore.YELLOW}Using fallback initialization...{Style.RESET_ALL}")
                    initialization_data = self._get_fallback_initialization(target, available_tools)
                else:
                    print(f"{Fore.GREEN}Got response: {len(response_text)} characters{Style.RESET_ALL}")
                    
                    # Parse the response
                    initialization_data = self.reasoning_module.parse_tree_initialization_response(response_text)
                    
                    if not initialization_data or not initialization_data.get('initial_tasks'):
                        print(f"{Fore.YELLOW}No tasks parsed from response. Using fallback initialization.{Style.RESET_ALL}")
                        initialization_data = self._get_fallback_initialization(target, available_tools)
                    else:
                        analysis = initialization_data.get('analysis', '')
                        print(f"{Fore.CYAN}LLM determined approach: {analysis}{Style.RESET_ALL}")
            
            # Create the structure and tasks as determined by the LLM
            structure_nodes = {}
            
            # Create structure elements (phases, categories, etc.)
            for structure_element in initialization_data.get('structure', []):
                structure_node = TaskNode(
                    description=structure_element.get('name', 'Unknown Structure'),
                    parent_id=self.tree_manager.root_id,
                    node_type=structure_element.get('type', 'phase'),
                    attributes={
                        "details": structure_element.get('description', ''),
                        "justification": structure_element.get('justification', ''),
                        "llm_created": True
                    }
                )
                node_id = self.tree_manager.add_node(structure_node)
                structure_nodes[structure_element.get('name', 'Unknown')] = node_id
            
            # Add initial tasks to their specified parents
            initial_tasks = initialization_data.get('initial_tasks', [])
            for task_data in initial_tasks:
                parent_name = task_data.get('parent', 'root')
                
                # Determine parent node
                if parent_name == 'root':
                    parent_id = self.tree_manager.root_id
                else:
                    parent_id = structure_nodes.get(parent_name, self.tree_manager.root_id)
                
                task_node = TaskNode(
                    description=task_data.get('description', 'Unknown task'),
                    parent_id=parent_id,
                    tool_used=task_data.get('tool_suggestion'),
                    priority=task_data.get('priority', 5),
                    risk_level=task_data.get('risk_level', 'low'),
                    attributes={'rationale': task_data.get('rationale', ''), 'llm_created': True}
                )
                self.tree_manager.add_node(task_node)
            
            print(f"\n{Fore.GREEN}Agent Mode initialized with LLM-determined structure: {len(initialization_data.get('structure', []))} elements, {len(initial_tasks)} tasks.{Style.RESET_ALL}")
            
            # Display the initial tree
            print(f"\n{Fore.CYAN}Initial Task Tree:{Style.RESET_ALL}")
            print(self.tree_manager.to_natural_language())
            
            return True
            
        except Exception as e:
            print(f"{Fore.RED}Failed to initialize agent mode: {e}{Style.RESET_ALL}")
            import traceback
            traceback.print_exc()
            
            # Try to continue with default tasks even if there's an error
            print(f"{Fore.YELLOW}Attempting to continue with default tasks...{Style.RESET_ALL}")
            try:
                initialization_data = self._get_fallback_initialization(target, available_tools)
                
                # Create structure and tasks from fallback
                structure_nodes = {}
                
                # Create structure elements
                for structure_element in initialization_data.get('structure', []):
                    structure_node = TaskNode(
                        description=structure_element.get('name', 'Unknown Structure'),
                        parent_id=self.tree_manager.root_id,
                        node_type=structure_element.get('type', 'phase'),
                        attributes={
                            "details": structure_element.get('description', ''),
                            "justification": structure_element.get('justification', ''),
                            "fallback_created": True
                        }
                    )
                    node_id = self.tree_manager.add_node(structure_node)
                    structure_nodes[structure_element.get('name', 'Unknown')] = node_id
                
                # Add initial tasks
                initial_tasks = initialization_data.get('initial_tasks', [])
                for task_data in initial_tasks:
                    parent_name = task_data.get('parent', 'root')
                    
                    if parent_name == 'root':
                        parent_id = self.tree_manager.root_id
                    else:
                        parent_id = structure_nodes.get(parent_name, self.tree_manager.root_id)
                    
                    task_node = TaskNode(
                        description=task_data.get('description', 'Unknown task'),
                        parent_id=parent_id,
                        tool_used=task_data.get('tool_suggestion'),
                        priority=task_data.get('priority', 5),
                        risk_level=task_data.get('risk_level', 'low'),
                        attributes={'rationale': task_data.get('rationale', ''), 'fallback_created': True}
                    )
                    self.tree_manager.add_node(task_node)
                
                print(f"\n{Fore.GREEN}Agent Mode initialized with fallback structure: {len(initialization_data.get('structure', []))} elements, {len(initial_tasks)} tasks.{Style.RESET_ALL}")
                print(f"\n{Fore.CYAN}Initial Task Tree:{Style.RESET_ALL}")
                print(self.tree_manager.to_natural_language())
                return True
            except Exception as fallback_error:
                print(f"{Fore.RED}Fallback initialization also failed: {fallback_error}{Style.RESET_ALL}")
            
            return False
    
    async def run_autonomous_loop(self) -> None:
        """Run the main autonomous agent loop."""
        print(f"\n{Fore.CYAN}Starting autonomous penetration test...{Style.RESET_ALL}")
        if self.max_iterations == 0:
            print(f"{Fore.YELLOW}Running until goal achieved or no more actions available{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}Iteration limit: {self.max_iterations} iterations{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Press Ctrl+C to pause at any time.{Style.RESET_ALL}\n")
        
        # Set effective limit - use a high number for "unlimited" but still have a safety limit
        effective_limit = self.max_iterations if self.max_iterations > 0 else 500
        
        while self.iteration_count < effective_limit and not self.goal_achieved:
            try:
                if self.paused:
                    await self._handle_pause()
                    if self.paused:  # Still paused after handling
                        break
                
                # Increment iteration count at the beginning
                self.iteration_count += 1
                
                # Display current progress
                self._display_progress()
                
                # Get next action from PTT
                next_action = await self._select_next_action()
                if not next_action:
                    print(f"{Fore.YELLOW}No viable next actions found. Checking goal status...{Style.RESET_ALL}")
                    await self._check_goal_achievement()
                    break
                
                # Execute the selected action
                await self._execute_action(next_action)
                
                # Check goal achievement after every iteration
                await self._check_goal_achievement()
                
                # If goal is achieved, stop the loop
                if self.goal_achieved:
                    break
                
                # Brief pause between actions
                await asyncio.sleep(2)
                
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}Pausing agent mode...{Style.RESET_ALL}")
                self.paused = True
            except Exception as e:
                print(f"{Fore.RED}Error in autonomous loop: {e}{Style.RESET_ALL}")
                await asyncio.sleep(5)
        
        # Display final reason for stopping
        if self.goal_achieved:
            print(f"\n{Fore.GREEN}Autonomous execution stopped: Goal achieved!{Style.RESET_ALL}")
        elif self.iteration_count >= effective_limit:
            print(f"\n{Fore.YELLOW}Autonomous execution stopped: Iteration limit reached ({effective_limit}){Style.RESET_ALL}")
        elif self.paused:
            print(f"\n{Fore.YELLOW}Autonomous execution stopped: User paused{Style.RESET_ALL}")
        else:
            print(f"\n{Fore.YELLOW}Autonomous execution stopped: No more viable actions{Style.RESET_ALL}")
        
        # Final summary
        self._display_final_summary()
    
    async def _select_next_action(self) -> Optional[Dict[str, Any]]:
        """Select the next action based on PTT state."""
        # Get available tools
        available_tools = [server.name for server in self.connected_servers]
        
        # Get prioritized candidate tasks
        candidates = self.tree_manager.get_candidate_tasks()
        if not candidates:
            return None
        
        prioritized = self.tree_manager.prioritize_tasks(candidates)
        
        print(f"\n{Fore.CYAN}Selecting next action...{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Available tools: {', '.join(available_tools)}{Style.RESET_ALL}")
        
        # Query LLM for action selection
        selection_prompt = self.reasoning_module.get_next_action_prompt(available_tools)
        
        try:
            result = await self.run_agent_func(
                selection_prompt,
                self.connected_servers,
                history=self.conversation_manager.get_history(),
                streaming=True,  # Use streaming=True since it works in other modes
                kb_instance=self.kb_instance
            )
            
            # Handle response format variations
            response_text = None
            if hasattr(result, "final_output"):
                response_text = result.final_output
            elif hasattr(result, "output"):
                response_text = result.output
            elif isinstance(result, str):
                response_text = result
            
            if response_text:
                action_data = self.reasoning_module.parse_next_action_response(response_text, available_tools)
                
                if action_data:
                    # Get the selected task
                    task_index = action_data.get('selected_task_index', 1) - 1
                    if 0 <= task_index < len(prioritized):
                        selected_task = prioritized[task_index]
                        
                        return {
                            'task': selected_task,
                            'command': action_data.get('command'),
                            'tool': action_data.get('tool'),
                            'rationale': action_data.get('rationale'),
                            'expected_outcome': action_data.get('expected_outcome')
                        }
        
        except Exception as e:
            print(f"{Fore.RED}Error selecting next action: {e}{Style.RESET_ALL}")
        
        # Fallback to first prioritized task
        if prioritized:
            return {'task': prioritized[0], 'command': None, 'tool': None}
        
        return None
    
    async def _execute_action(self, action: Dict[str, Any]) -> None:
        """Execute a selected action."""
        task = action['task']
        command = action.get('command')
        tool = action.get('tool')
        available_tools = [server.name for server in self.connected_servers]
        
        print(f"\n{Fore.CYAN}Executing: {task.description}{Style.RESET_ALL}")
        if action.get('rationale'):
            print(f"{Fore.WHITE}Rationale: {action['rationale']}{Style.RESET_ALL}")
        if command:
            print(f"{Fore.WHITE}Command: {command}{Style.RESET_ALL}")
        if tool:
            print(f"{Fore.WHITE}Using tool: {tool}{Style.RESET_ALL}")
        
        # Check if suggested tool is available
        if tool and tool not in available_tools and tool != 'manual':
            print(f"{Fore.YELLOW}Tool '{tool}' not available. Available: {', '.join(available_tools)}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Asking AI to adapt approach with available tools...{Style.RESET_ALL}")
            
            # Let AI figure out how to adapt
            adaptation_query = f"""The task "{task.description}" was planned to use "{tool}" but that tool is not available.
            
Available tools: {', '.join(available_tools)}

Please adapt this task to work with the available tools. How would you accomplish this objective using {', '.join(available_tools)}?
Be creative and think about alternative approaches that achieve the same security testing goal."""
            
            command = adaptation_query
        
        # Update task status to in-progress
        self.tree_manager.update_node(task.id, {'status': NodeStatus.IN_PROGRESS.value})
        
        # Execute via agent
        execution_query = command if command else f"Perform the following task: {task.description}"
        
        try:
            result = await self.run_agent_func(
                execution_query,
                self.connected_servers,
                history=self.conversation_manager.get_history(),
                streaming=True,
                kb_instance=self.kb_instance
            )
            
            # Handle response format variations
            response_text = None
            if hasattr(result, "final_output"):
                response_text = result.final_output
            elif hasattr(result, "output"):
                response_text = result.output
            elif isinstance(result, str):
                response_text = result
            
            if response_text:
                # Update conversation history
                self.conversation_manager.add_dialogue(execution_query)
                self.conversation_manager.update_last_response(response_text)
                
                # Update PTT based on results
                await self._update_tree_from_results(
                    task,
                    response_text,
                    command or execution_query
                )
        
        except Exception as e:
            print(f"{Fore.RED}Error executing action: {e}{Style.RESET_ALL}")
            self.tree_manager.update_node(task.id, {
                'status': NodeStatus.FAILED.value,
                'findings': f"Execution failed: {str(e)}"
            })
    
    async def _update_tree_from_results(self, task: TaskNode, output: str, command: str) -> None:
        """Update the PTT based on execution results."""
        try:
            # Create update prompt
            update_prompt = self.reasoning_module.get_tree_update_prompt(output, command, task)
            
            # Get LLM analysis
            result = await self.run_agent_func(
                update_prompt,
                self.connected_servers,
                history=self.conversation_manager.get_history(),
                streaming=True,
                kb_instance=self.kb_instance
            )
            
            # Handle response format variations
            response_text = None
            if hasattr(result, "final_output"):
                response_text = result.final_output
            elif hasattr(result, "output"):
                response_text = result.output
            elif isinstance(result, str):
                response_text = result
            
            if response_text:
                node_updates, new_tasks = self.reasoning_module.parse_tree_update_response(response_text)
                
                # Update the executed node
                if node_updates:
                    node_updates['timestamp'] = datetime.now().isoformat()
                    node_updates['command_executed'] = command
                    self.tree_manager.update_node(task.id, node_updates)
                
                # Check if goal might be achieved before adding new tasks
                preliminary_goal_check = await self._quick_goal_check()
                
                # Only add new tasks if goal is not achieved and they align with original goal
                if not preliminary_goal_check and new_tasks:
                    # Filter tasks to ensure they align with the original goal
                    filtered_tasks = self._filter_tasks_by_goal_scope(new_tasks)
                    
                    for new_task_data in filtered_tasks:
                        parent_phase = new_task_data.get('parent_phase', 'Phase 2')
                        parent_node = self._find_phase_node(parent_phase)
                        
                        if parent_node:
                            new_task = TaskNode(
                                description=new_task_data.get('description'),
                                parent_id=parent_node.id,
                                tool_used=new_task_data.get('tool_suggestion'),
                                priority=new_task_data.get('priority', 5),
                                risk_level=new_task_data.get('risk_level', 'low'),
                                attributes={'rationale': new_task_data.get('rationale', '')}
                            )
                            self.tree_manager.add_node(new_task)
                    
                    if filtered_tasks:
                        print(f"{Fore.GREEN}PTT updated with {len(filtered_tasks)} new goal-aligned tasks.{Style.RESET_ALL}")
                    if len(filtered_tasks) < len(new_tasks):
                        print(f"{Fore.YELLOW}Filtered out {len(new_tasks) - len(filtered_tasks)} tasks that exceeded goal scope.{Style.RESET_ALL}")
                elif preliminary_goal_check:
                    print(f"{Fore.GREEN}Goal appears to be achieved - not adding new tasks.{Style.RESET_ALL}")
        
        except Exception as e:
            print(f"{Fore.RED}Error updating PTT: {e}{Style.RESET_ALL}")
            # Default to marking as completed if update fails
            self.tree_manager.update_node(task.id, {
                'status': NodeStatus.COMPLETED.value,
                'timestamp': datetime.now().isoformat()
            })
    
    def _filter_tasks_by_goal_scope(self, tasks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Filter tasks to ensure they align with the original goal scope."""
        goal_lower = self.tree_manager.goal.lower()
        filtered_tasks = []
        
        # Define scope expansion keywords that should be avoided for simple goals
        expansion_keywords = ["exploit", "compromise", "attack", "penetrate", "shell", "backdoor", "privilege", "escalat"]
        
        # Check if the original goal is simple information gathering
        info_keywords = ["check", "identify", "determine", "find", "discover", "enumerate", "list", "version", "banner"]
        is_simple_info_goal = any(keyword in goal_lower for keyword in info_keywords)
        
        for task in tasks:
            task_desc_lower = task.get('description', '').lower()
            
            # If it's a simple info goal, avoid adding exploitation tasks
            if is_simple_info_goal and any(keyword in task_desc_lower for keyword in expansion_keywords):
                print(f"{Fore.YELLOW}Skipping task that exceeds goal scope: {task.get('description', '')}{Style.RESET_ALL}")
                continue
            
            filtered_tasks.append(task)
        
        return filtered_tasks
    
    async def _quick_goal_check(self) -> bool:
        """Quick check if goal might be achieved based on completed tasks."""
        # Simple heuristic: if we have completed tasks with findings for info gathering goals
        goal_lower = self.tree_manager.goal.lower()
        info_keywords = ["check", "identify", "determine", "find", "discover", "enumerate", "list", "version", "banner"]
        
        if any(keyword in goal_lower for keyword in info_keywords):
            # For info gathering goals, check if we have relevant findings
            for node in self.tree_manager.nodes.values():
                if node.status == NodeStatus.COMPLETED and node.findings:
                    # Basic keyword matching for goal completion
                    if "version" in goal_lower and "version" in node.findings.lower():
                        return True
                    if "banner" in goal_lower and "banner" in node.findings.lower():
                        return True
                    if any(keyword in goal_lower and keyword in node.description.lower() for keyword in info_keywords):
                        return True
        
        return False
    
    async def _check_goal_achievement(self) -> None:
        """Check if the primary goal has been achieved."""
        goal_prompt = self.reasoning_module.get_goal_check_prompt()
        
        try:
            result = await self.run_agent_func(
                goal_prompt,
                self.connected_servers,
                history=self.conversation_manager.get_history(),
                streaming=True,  # Use streaming=True
                kb_instance=self.kb_instance
            )
            
            # Handle response format variations
            response_text = None
            if hasattr(result, "final_output"):
                response_text = result.final_output
            elif hasattr(result, "output"):
                response_text = result.output
            elif isinstance(result, str):
                response_text = result
            
            if response_text:
                goal_status = self.reasoning_module.parse_goal_check_response(response_text)
                
                if goal_status.get('goal_achieved', False):
                    confidence = goal_status.get('confidence', 0)
                    if confidence >= 80:
                        print(f"\n{Fore.GREEN}{'='*60}{Style.RESET_ALL}")
                        print(f"{Fore.GREEN}GOAL ACHIEVED! (Confidence: {confidence}%){Style.RESET_ALL}")
                        print(f"{Fore.WHITE}Evidence: {goal_status.get('evidence', 'N/A')}{Style.RESET_ALL}")
                        print(f"{Fore.GREEN}{'='*60}{Style.RESET_ALL}\n")
                        self.goal_achieved = True
                    else:
                        print(f"{Fore.YELLOW}Goal possibly achieved but confidence is low ({confidence}%). Continuing...{Style.RESET_ALL}")
                else:
                    remaining = goal_status.get('remaining_objectives', 'Unknown')
                    print(f"{Fore.YELLOW}Goal not yet achieved. Remaining: {remaining}{Style.RESET_ALL}")
        
        except Exception as e:
            print(f"{Fore.RED}Error checking goal achievement: {e}{Style.RESET_ALL}")
    
    def _display_progress(self) -> None:
        """Display current progress and statistics."""
        stats = self.tree_manager.get_statistics()
        elapsed = datetime.now() - self.start_time if self.start_time else None
        
        print(f"\n{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Iteration {self.iteration_count} | Elapsed: {elapsed}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Tasks - Total: {stats['total_nodes']} | "
              f"Completed: {stats['status_counts'].get('completed', 0)} | "
              f"In Progress: {stats['status_counts'].get('in_progress', 0)} | "
              f"Pending: {stats['status_counts'].get('pending', 0)}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Vulnerabilities Found: {stats['status_counts'].get('vulnerable', 0)}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*60}{Style.RESET_ALL}")
    
    def _display_final_summary(self) -> None:
        """Display final summary of the agent mode execution."""
        print(f"\n{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}AGENT MODE EXECUTION SUMMARY{Style.RESET_ALL}")
        print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
        
        summary = self.reasoning_module.generate_strategic_summary()
        print(f"{Fore.WHITE}{summary}{Style.RESET_ALL}")
        
        # Calculate effective limit
        effective_limit = self.max_iterations if self.max_iterations > 0 else 500
        
        # Execution Statistics
        if self.start_time:
            elapsed = datetime.now() - self.start_time
            print(f"\n{Fore.WHITE}Execution Statistics:{Style.RESET_ALL}")
            print(f"Total Execution Time: {elapsed}")
            print(f"Iterations Completed: {self.iteration_count}/{effective_limit}")
            
            if self.iteration_count > 0:
                avg_time_per_iteration = elapsed.total_seconds() / self.iteration_count
                print(f"Average Time per Iteration: {avg_time_per_iteration:.1f} seconds")
                
                # Calculate efficiency
                completion_rate = (self.iteration_count / effective_limit) * 100
                print(f"Completion Rate: {completion_rate:.1f}%")
                
                # Estimate remaining time if stopped early
                if self.iteration_count < effective_limit and not self.goal_achieved:
                    remaining_iterations = effective_limit - self.iteration_count
                    estimated_remaining_time = remaining_iterations * avg_time_per_iteration
                    print(f"Estimated Time for Full Run: {elapsed.total_seconds() + estimated_remaining_time:.0f} seconds")
        
        print(f"{Fore.WHITE}Total Iterations: {self.iteration_count}{Style.RESET_ALL}")
        
        if self.goal_achieved:
            print(f"\n{Fore.GREEN}PRIMARY GOAL ACHIEVED!{Style.RESET_ALL}")
            efficiency = "Excellent" if self.iteration_count <= 10 else "Good" if self.iteration_count <= 20 else "Extended"
            print(f"{Fore.GREEN}Efficiency: {efficiency} (achieved in {self.iteration_count} iterations){Style.RESET_ALL}")
        else:
            print(f"\n{Fore.YELLOW}Primary goal not fully achieved within iteration limit.{Style.RESET_ALL}")
            if self.iteration_count >= effective_limit:
                print(f"{Fore.YELLOW}Consider increasing iteration limit for more thorough testing.{Style.RESET_ALL}")
        
        print(f"{Fore.CYAN}{'='*70}{Style.RESET_ALL}")
    
    async def _handle_pause(self) -> None:
        """Handle pause state and user options."""
        print(f"\n{Fore.YELLOW}Agent Mode Paused{Style.RESET_ALL}")
        
        # Calculate effective limit
        effective_limit = self.max_iterations if self.max_iterations > 0 else 500
        
        # Display current progress
        print(f"\n{Fore.MAGENTA}Progress Statistics:{Style.RESET_ALL}")
        print(f"Iterations: {self.iteration_count}/{effective_limit}")
        elapsed = datetime.now() - self.start_time if self.start_time else None
        if elapsed:
            print(f"Elapsed Time: {elapsed}")
            if self.iteration_count > 0:
                avg_time = elapsed.total_seconds() / self.iteration_count
                print(f"Average per Iteration: {avg_time:.1f} seconds")
        
        print("\nOptions:")
        print("1. Resume execution")
        print("2. View current PTT")
        print("3. View detailed statistics")
        print("4. Save PTT state")
        print("5. Add manual task")
        print("6. Modify iteration limit")
        print("7. Exit agent mode")
        
        while self.paused:
            choice = input(f"\n{Fore.GREEN}Select option (1-7): {Style.RESET_ALL}").strip()
            
            if choice == '1':
                self.paused = False
                print(f"{Fore.GREEN}Resuming agent mode...{Style.RESET_ALL}")
            elif choice == '2':
                print(f"\n{Fore.CYAN}Current PTT State:{Style.RESET_ALL}")
                print(self.tree_manager.to_natural_language())
            elif choice == '3':
                self._display_progress()
                print(self.reasoning_module.generate_strategic_summary())
            elif choice == '4':
                self._save_ptt_state()
            elif choice == '5':
                await self._add_manual_task()
            elif choice == '6':
                self._modify_iteration_limit()
            elif choice == '7':
                print(f"{Fore.YELLOW}Exiting agent mode...{Style.RESET_ALL}")
                break
            else:
                print(f"{Fore.RED}Invalid choice.{Style.RESET_ALL}")
    
    def _modify_iteration_limit(self) -> None:
        """Allow user to modify the iteration limit during execution."""
        try:
            print(f"\n{Fore.CYAN}Modify Iteration Limit{Style.RESET_ALL}")
            print(f"Current limit: {self.max_iterations}")
            print(f"Iterations completed: {self.iteration_count}")
            print(f"Iterations remaining: {self.max_iterations - self.iteration_count}")
            
            new_limit_input = input(f"New iteration limit (current: {self.max_iterations}): ").strip()
            
            if new_limit_input:
                try:
                    new_limit = int(new_limit_input)
                    
                    # Ensure new limit is at least the number of iterations already completed
                    min_limit = self.iteration_count + 1  # Allow at least 1 more iteration
                    if new_limit < min_limit:
                        print(f"{Fore.YELLOW}Minimum limit is {min_limit} (iterations already completed + 1){Style.RESET_ALL}")
                        new_limit = min_limit
                    
                    # Apply reasonable maximum
                    new_limit = min(new_limit, 200)
                    
                    self.max_iterations = new_limit
                    print(f"{Fore.GREEN}Iteration limit updated to: {new_limit}{Style.RESET_ALL}")
                    
                except ValueError:
                    print(f"{Fore.RED}Invalid input. Please enter a number.{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}No change made.{Style.RESET_ALL}")
                
        except Exception as e:
            print(f"{Fore.RED}Error modifying iteration limit: {e}{Style.RESET_ALL}")
    
    async def _add_manual_task(self) -> None:
        """Allow user to manually add a task to the PTT."""
        try:
            print(f"\n{Fore.CYAN}Add Manual Task{Style.RESET_ALL}")
            
            # Get task details from user
            description = input("Task description: ").strip()
            if not description:
                print(f"{Fore.RED}Task description required.{Style.RESET_ALL}")
                return
            
            print("Select phase:")
            print("1. Phase 1: Reconnaissance")
            print("2. Phase 2: Vulnerability Assessment") 
            print("3. Phase 3: Exploitation")
            print("4. Phase 4: Post-Exploitation")
            
            phase_choice = input("Phase (1-4): ").strip()
            phase_map = {
                '1': 'Phase 1',
                '2': 'Phase 2', 
                '3': 'Phase 3',
                '4': 'Phase 4'
            }
            
            phase = phase_map.get(phase_choice, 'Phase 2')
            parent_node = self._find_phase_node(phase)
            
            if not parent_node:
                print(f"{Fore.RED}Phase not found.{Style.RESET_ALL}")
                return
            
            # Get priority
            try:
                priority = int(input("Priority (1-10, default 5): ").strip() or "5")
                priority = max(1, min(10, priority))
            except:
                priority = 5
            
            # Get risk level
            print("Risk level:")
            print("1. Low")
            print("2. Medium")
            print("3. High")
            risk_choice = input("Risk (1-3, default 2): ").strip()
            risk_map = {'1': 'low', '2': 'medium', '3': 'high'}
            risk_level = risk_map.get(risk_choice, 'medium')
            
            # Create the task
            from core.task_tree_manager import TaskNode
            manual_task = TaskNode(
                description=description,
                parent_id=parent_node.id,
                tool_used='manual',
                priority=priority,
                risk_level=risk_level,
                attributes={'manual_addition': True, 'added_by_user': True}
            )
            
            self.tree_manager.add_node(manual_task)
            print(f"{Fore.GREEN}Manual task added to {phase}.{Style.RESET_ALL}")
            
        except Exception as e:
            print(f"{Fore.RED}Error adding manual task: {e}{Style.RESET_ALL}")
    
    def _save_ptt_state(self) -> None:
        """Save the current PTT state to file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"reports/ptt_state_{timestamp}.json"
        
        try:
            import os
            os.makedirs("reports", exist_ok=True)
            
            with open(filename, 'w') as f:
                f.write(self.tree_manager.to_json())
            
            print(f"{Fore.GREEN}PTT state saved to: {filename}{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}Failed to save PTT state: {e}{Style.RESET_ALL}")
    
    def _find_phase_node(self, phase_description: str) -> Optional[TaskNode]:
        """Find a structure node by description (phase, category, etc.)."""
        for node in self.tree_manager.nodes.values():
            # Look for any non-task node that matches the description
            if node.node_type != "task" and phase_description.lower() in node.description.lower():
                return node
        
        # If no exact match, try to find any suitable parent node
        # Return root if no structure nodes exist
        return self.tree_manager.nodes.get(self.tree_manager.root_id)
    
    def get_ptt_for_reporting(self) -> TaskTreeManager:
        """Get the PTT for report generation."""
        return self.tree_manager 

    def _get_fallback_initialization(self, target: str, available_tools: List[str]) -> Dict[str, Any]:
        """Return minimal fallback initialization when LLM fails."""
        print(f"{Fore.YELLOW}Using minimal fallback initialization. The system will rely on dynamic task generation.{Style.RESET_ALL}")
        
        return {
            'analysis': 'Fallback initialization - LLM will determine structure dynamically during execution',
            'structure': [],
            'initial_tasks': []
        } 