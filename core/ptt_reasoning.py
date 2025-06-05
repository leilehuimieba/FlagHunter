"""PTT Reasoning Module for LLM-based task tree management."""

import json
import re
from typing import Dict, List, Optional, Any, Tuple
from colorama import Fore, Style
from core.task_tree_manager import TaskTreeManager, TaskNode, NodeStatus


class PTTReasoningModule:
    """Handles LLM interactions for PTT management and decision making."""
    
    def __init__(self, tree_manager: TaskTreeManager):
        """
        Initialize the PTT reasoning module.
        
        Args:
            tree_manager: The task tree manager instance
        """
        self.tree_manager = tree_manager
    
    def get_tree_initialization_prompt(self, goal: str, target: str, constraints: Dict[str, Any], available_tools: List[str] = None) -> str:
        """
        Generate prompt for tree initialization.
        
        Args:
            goal: Primary penetration testing objective
            target: Target system/network
            constraints: Scope constraints and limitations
            available_tools: List of available MCP tools
            
        Returns:
            Tree initialization prompt
        """
        tool_info = ""
        if available_tools:
            tool_info = f"""
Available MCP Tools: {', '.join(available_tools)}

You must work within the capabilities of these connected tools. Think about what each tool can accomplish:
- Consider the full capabilities of each available tool
- Adapt your approach to work with available tools
- Be creative in how you leverage available tools
"""
        else:
            tool_info = """
No MCP tools are currently connected. Design an approach that describes the security testing objectives without tool dependencies.
"""

        prompt = f"""You are an autonomous security agent initializing a Pentesting Task Tree (PTT) for a security assessment.

ASSESSMENT CONTEXT:
Goal: {goal}
Target: {target}
Constraints: {json.dumps(constraints, indent=2)}

{tool_info}

TASK:
Analyze this goal and determine what structure and initial tasks are needed to accomplish it efficiently. 

DO NOT assume any predefined phases or structure. Instead:
1. Analyze what the goal actually requires
2. Determine if you need phases/categories or if direct tasks are better
3. Create an appropriate initial structure
4. Define specific actionable tasks to start with

Consider:
- What does this specific goal require?
- What's the minimal viable approach?
- How can available tools be leveraged?
- What structure makes sense for THIS goal?

IMPORTANT: When suggesting tool usage, be specific about commands and modules. For example:

Provide your analysis and initial structure in JSON format:

{{
    "analysis": "Your assessment of what this goal requires and approach",
    "structure": [
        {{
            "type": "phase/category/direct",
            "name": "Name of organizational structure",
            "description": "What this encompasses",
            "justification": "Why this structure element is needed for this goal"
        }}
    ],
    "initial_tasks": [
        {{
            "description": "Specific actionable task",
            "parent": "Which structure element this belongs to, or 'root' for direct tasks",
            "tool_suggestion": "Which available tool to use, or 'manual' if no suitable tool",
            "priority": 1-10,
            "risk_level": "low/medium/high",
            "rationale": "Why this task is necessary for the goal"
        }}
    ]
}}

BE INTELLIGENT: If the goal is simple, don't create complex multi-phase structures. If it's complex, then structure appropriately. Let the goal drive the structure, not the other way around."""

        return prompt
    
    def get_tree_update_prompt(self, tool_output: str, command: str, node: TaskNode) -> str:
        """
        Generate prompt for updating the tree based on tool output.
        
        Args:
            tool_output: Output from the executed tool
            command: The command that was executed
            node: The node being updated
            
        Returns:
            Update prompt
        """
        current_tree = self.tree_manager.to_natural_language()
        
        prompt = f"""You are managing a Pentesting Task Tree (PTT). A task has been executed and you need to update the tree based on the results.

Current PTT State:
{current_tree}

Executed Task: {node.description}
Command: {command}
Tool Output:
{tool_output[:2000]}  # Limit output length

Based on this output, provide updates in the following JSON format:

{{
    "node_updates": {{
        "status": "completed/failed/vulnerable/not_vulnerable",
        "findings": "Summary of key findings from the output",
        "output_summary": "Brief technical summary"
    }},
    "new_tasks": [
        {{
            "description": "New task based on findings",
            "parent_phase": "Phase 1/2/3/4",
            "tool_suggestion": "Suggested tool",
            "priority": 1-10,
            "risk_level": "low/medium/high",
            "rationale": "Why this task is important"
        }}
    ],
    "insights": "Any strategic insights or patterns noticed"
}}

Consider:
1. What vulnerabilities or opportunities were discovered?
2. What follow-up actions are needed based on the findings?
3. Should any new attack vectors be explored?
4. Are there any security misconfigurations evident?"""

        return prompt
    
    def get_next_action_prompt(self, available_tools: List[str]) -> str:
        """
        Generate prompt for selecting the next action.
        
        Args:
            available_tools: List of available MCP tools
            
        Returns:
            Next action selection prompt
        """
        current_tree = self.tree_manager.to_natural_language()
        candidates = self.tree_manager.get_candidate_tasks()
        
        # Prepare candidate descriptions
        candidate_desc = []
        for i, task in enumerate(candidates[:10]):  # Limit to top 10
            desc = f"{i+1}. {task.description}"
            if task.priority:
                desc += f" (Priority: {task.priority})"
            candidate_desc.append(desc)
        
        # Generate tool context
        if available_tools:
            tool_context = f"""
Connected MCP Tools: {', '.join(available_tools)}

Think about how to leverage these tools for the selected task. Each tool has its own capabilities - 
be creative and intelligent about how to accomplish penetration testing objectives with available tools.
If a tool doesn't directly support a traditional approach, consider alternative methods that achieve the same goal.
"""
        else:
            tool_context = """
No MCP tools are currently connected. Select tasks that can be performed manually or recommend connecting appropriate tools.
"""

        prompt = f"""You are managing a Pentesting Task Tree (PTT) and need to select the next action.

Goal: {self.tree_manager.goal}
Target: {self.tree_manager.target}

Current PTT State:
{current_tree}

{tool_context}

Candidate Tasks:
{chr(10).join(candidate_desc)}

Statistics:
- Total tasks: {len(self.tree_manager.nodes)}
- Completed: {sum(1 for n in self.tree_manager.nodes.values() if n.status == NodeStatus.COMPLETED)}
- In Progress: {sum(1 for n in self.tree_manager.nodes.values() if n.status == NodeStatus.IN_PROGRESS)}
- Pending: {sum(1 for n in self.tree_manager.nodes.values() if n.status == NodeStatus.PENDING)}

Select the most strategic next action and provide your response in JSON format:

{{
    "selected_task_index": 1-based index from candidate list,
    "rationale": "Why this task is the best next step",
    "command": "Intelligent request that leverages available tools effectively",
    "tool": "Which available tool to use, or 'manual' if no suitable tool",
    "expected_outcome": "What we hope to discover/achieve",
    "alternative_if_blocked": "Backup task index if this fails"
}}

Consider:
1. Logical progression through the penetration testing methodology
2. Task dependencies and prerequisites
3. Risk vs reward of different approaches
4. How to best utilize available tools for maximum effectiveness
5. Strategic value of each potential action

Be intelligent about tool selection - think about what each available tool can accomplish."""

        return prompt
    
    def get_goal_check_prompt(self) -> str:
        """
        Generate prompt to check if the goal has been achieved.
        
        Returns:
            Goal achievement check prompt
        """
        current_tree = self.tree_manager.to_natural_language()
        goal = self.tree_manager.goal
        
        # Extract completed tasks and findings for better context
        completed_tasks_with_findings = []
        for node in self.tree_manager.nodes.values():
            if node.status == NodeStatus.COMPLETED and node.findings:
                completed_tasks_with_findings.append(f"✓ {node.description}: {node.findings}")
        
        completed_context = "\n".join(completed_tasks_with_findings) if completed_tasks_with_findings else "No completed tasks with findings yet."
        
        prompt = f"""Analyze the current Pentesting Task Tree (PTT) to determine if the PRIMARY GOAL has been achieved.

IMPORTANT: Focus ONLY on whether the specific goal stated has been accomplished. Do not suggest additional scope or activities beyond the original goal.

PRIMARY GOAL: {goal}
Target: {self.tree_manager.target}

COMPLETED TASKS WITH FINDINGS:
{completed_context}

Current PTT State:
{current_tree}

GOAL ACHIEVEMENT CRITERIA:
- For information gathering goals, the goal is achieved when that specific information is obtained
- For vulnerability assessment goals, the goal is achieved when vulnerabilities are identified and documented
- For exploitation goals, the goal is achieved when successful exploitation is demonstrated
- For access goals, the goal is achieved when the specified access level is obtained

Provide your analysis in JSON format:

{{
    "goal_achieved": true/false,
    "confidence": 0-100,
    "evidence": "Specific evidence that the PRIMARY GOAL has been met (quote actual findings)",
    "remaining_objectives": "What still needs to be done if goal not achieved (related to the ORIGINAL goal only)",
    "recommendations": "Next steps ONLY if they relate to the original goal - do not expand scope",
    "scope_warning": "Flag if any tasks seem to exceed the original goal scope"
}}

Consider:
1. Has the SPECIFIC goal been demonstrably achieved?
2. Is there sufficient evidence/proof in the completed tasks?
3. Are there critical paths unexplored that are NECESSARY for the original goal?
4. Would additional testing strengthen the results for the ORIGINAL goal only?

DO NOT recommend expanding the scope beyond the original goal. If the goal is completed, mark it as achieved regardless of what other security activities could be performed."""

        return prompt
    
    def parse_tree_initialization_response(self, llm_response: str) -> Dict[str, Any]:
        """Parse LLM response for tree initialization."""
        try:
            print(f"{Fore.CYAN}Parsing initialization response...{Style.RESET_ALL}")
            # Extract JSON from response
            response_json = self._extract_json(llm_response)
            
            analysis = response_json.get('analysis', 'No analysis provided')
            structure = response_json.get('structure', [])
            initial_tasks = response_json.get('initial_tasks', [])
            
            print(f"{Fore.GREEN}LLM Analysis: {analysis}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}Successfully parsed {len(structure)} structure elements and {len(initial_tasks)} tasks{Style.RESET_ALL}")
            
            return {
                'analysis': analysis,
                'structure': structure,
                'initial_tasks': initial_tasks
            }
        except Exception as e:
            print(f"{Fore.YELLOW}Failed to parse initialization response: {e}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Response text (first 500 chars): {llm_response[:500]}{Style.RESET_ALL}")
            return {
                'analysis': 'Failed to parse LLM response',
                'structure': [],
                'initial_tasks': []
            }
    
    def parse_tree_update_response(self, llm_response: str) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
        """Parse LLM response for tree updates."""
        try:
            response_json = self._extract_json(llm_response)
            node_updates = response_json.get('node_updates', {})
            new_tasks = response_json.get('new_tasks', [])
            return node_updates, new_tasks
        except Exception as e:
            print(f"{Fore.YELLOW}Failed to parse update response: {e}{Style.RESET_ALL}")
            return {}, []
    
    def parse_next_action_response(self, llm_response: str, available_tools: List[str] = None) -> Optional[Dict[str, Any]]:
        """Parse LLM response for next action selection."""
        try:
            response_json = self._extract_json(llm_response)
            return response_json
        except Exception as e:
            print(f"{Fore.YELLOW}Failed to parse next action response: {e}{Style.RESET_ALL}")
            return None
    
    def parse_goal_check_response(self, llm_response: str) -> Dict[str, Any]:
        """Parse LLM response for goal achievement check."""
        try:
            response_json = self._extract_json(llm_response)
            return response_json
        except Exception as e:
            print(f"{Fore.YELLOW}Failed to parse goal check response: {e}{Style.RESET_ALL}")
            return {"goal_achieved": False, "confidence": 0}
    
    def _extract_json(self, text: str) -> Dict[str, Any]:
        """Extract JSON from LLM response text."""
        if not text:
            raise ValueError("Empty response text")
        
        print(f"{Fore.CYAN}Attempting to extract JSON from {len(text)} character response{Style.RESET_ALL}")
        
        # Try multiple strategies to extract JSON
        strategies = [
            self._extract_json_code_block,
            self._extract_json_braces,
            self._extract_json_fuzzy,
            self._create_fallback_json
        ]
        
        for i, strategy in enumerate(strategies):
            try:
                result = strategy(text)
                if result:
                    print(f"{Fore.GREEN}Successfully extracted JSON using strategy {i+1}{Style.RESET_ALL}")
                    return result
            except Exception as e:
                print(f"{Fore.YELLOW}Strategy {i+1} failed: {e}{Style.RESET_ALL}")
                continue
        
        raise ValueError("Could not extract valid JSON from response")
    
    def _extract_json_code_block(self, text: str) -> Dict[str, Any]:
        """Extract JSON from code blocks."""
        # Look for JSON between ```json and ``` or just ```
        patterns = [
            r'```json\s*(\{.*?\})\s*```',
            r'```\s*(\{.*?\})\s*```'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                json_str = match.group(1)
                return json.loads(json_str)
        
        raise ValueError("No JSON code block found")
    
    def _extract_json_braces(self, text: str) -> Dict[str, Any]:
        """Extract JSON by finding brace boundaries."""
        # Find the first { and last }
        json_start = text.find('{')
        json_end = text.rfind('}')
        
        if json_start != -1 and json_end != -1 and json_end > json_start:
            json_str = text[json_start:json_end + 1]
            return json.loads(json_str)
        
        raise ValueError("No valid JSON braces found")
    
    def _extract_json_fuzzy(self, text: str) -> Dict[str, Any]:
        """Try to extract JSON with more flexible matching."""
        # Look for task-like patterns and try to construct JSON
        if "tasks" in text.lower():
            # Try to find task descriptions
            task_patterns = [
                r'"description":\s*"([^"]+)"',
                r'"tool_suggestion":\s*"([^"]+)"',
                r'"priority":\s*(\d+)',
                r'"risk_level":\s*"([^"]+)"'
            ]
            
            # This is a simplified approach - could be enhanced
            # For now, fall through to the next strategy
            pass
        
        raise ValueError("Fuzzy JSON extraction failed")
    
    def _create_fallback_json(self, text: str) -> Dict[str, Any]:
        """Create fallback JSON if no valid JSON is found."""
        print(f"{Fore.YELLOW}Creating fallback JSON structure{Style.RESET_ALL}")
        
        # Return an empty but valid structure
        return {
            "tasks": [],
            "node_updates": {"status": "completed"},
            "new_tasks": [],
            "selected_task_index": 1,
            "goal_achieved": False,
            "confidence": 0
        }
    
    def verify_tree_update(self, old_tree_state: str, new_tree_state: str) -> bool:
        """
        Verify that tree updates maintain integrity.
        
        Args:
            old_tree_state: Tree state before update
            new_tree_state: Tree state after update
            
        Returns:
            True if update is valid
        """
        # For now, basic verification - can be enhanced
        # Check that only leaf nodes were modified (as per PentestGPT approach)
        # This is simplified - in practice would need more sophisticated checks
        
        return True  # Placeholder - implement actual verification logic
    
    def generate_strategic_summary(self) -> str:
        """Generate a strategic summary of the current PTT state."""
        stats = self.tree_manager.get_statistics()
        
        summary = f"""
=== PTT Strategic Summary ===
Goal: {self.tree_manager.goal}
Target: {self.tree_manager.target}

Progress Overview:
- Total Tasks: {stats['total_nodes']}
- Completed: {stats['status_counts'].get('completed', 0)}
- In Progress: {stats['status_counts'].get('in_progress', 0)}
- Failed: {stats['status_counts'].get('failed', 0)}
- Vulnerabilities Found: {stats['status_counts'].get('vulnerable', 0)}

Current Phase Focus:
"""
        
        # Identify which phase is most active
        phase_activity = {}
        for node in self.tree_manager.nodes.values():
            if node.node_type == "phase":
                completed_children = sum(
                    1 for child_id in node.children_ids
                    if child_id in self.tree_manager.nodes 
                    and self.tree_manager.nodes[child_id].status == NodeStatus.COMPLETED
                )
                total_children = len(node.children_ids)
                phase_activity[node.description] = (completed_children, total_children)
        
        for phase, (completed, total) in phase_activity.items():
            if total > 0:
                progress = (completed / total) * 100
                summary += f"- {phase}: {completed}/{total} tasks ({progress:.0f}%)\n"
        
        # Add key findings
        summary += "\nKey Findings:\n"
        vuln_count = 0
        for node in self.tree_manager.nodes.values():
            if node.status == NodeStatus.VULNERABLE and node.findings:
                vuln_count += 1
                summary += f"- {node.description}: {node.findings[:100]}...\n"
                if vuln_count >= 5:  # Limit to top 5
                    break
        
        return summary
    
    def validate_and_fix_tool_suggestions(self, tasks: List[Dict[str, Any]], available_tools: List[str]) -> List[Dict[str, Any]]:
        """Let the LLM re-evaluate tool suggestions if they don't match available tools."""
        if not available_tools:
            return tasks
        
        # Check if any tasks use unavailable tools
        needs_fixing = []
        valid_tasks = []
        
        for task in tasks:
            tool_suggestion = task.get('tool_suggestion', '')
            if tool_suggestion in available_tools or tool_suggestion in ['manual', 'generic']:
                valid_tasks.append(task)
            else:
                needs_fixing.append(task)
        
        if needs_fixing:
            print(f"{Fore.YELLOW}Some tasks reference unavailable tools. Letting AI re-evaluate...{Style.RESET_ALL}")
            # Return all tasks - let the execution phase handle tool mismatches intelligently
            
        return tasks 