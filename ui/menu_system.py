"""Menu system and user interface components for GHOSTCREW."""

from typing import Optional, List, Tuple, Dict, Any
from colorama import Fore, Style
from config.constants import (
    MAIN_MENU_TITLE, INTERACTIVE_OPTION, AUTOMATED_OPTION, 
    EXIT_OPTION, MULTI_LINE_PROMPT, MULTI_LINE_END_MARKER
)


class MenuSystem:
    """Handles all menu displays and user input for GHOSTCREW."""
    
    @staticmethod
    def display_main_menu(workflows_available: bool, has_connected_servers: bool) -> None:
        """Display the main application menu."""
        print(f"\n{MAIN_MENU_TITLE}")
        print(f"1. {INTERACTIVE_OPTION}")
        
        # Check if automated mode should be available
        if workflows_available and has_connected_servers:
            print(f"2. {AUTOMATED_OPTION}")
        elif workflows_available and not has_connected_servers:
            print(f"2. {Fore.LIGHTBLACK_EX}Automated Penetration Testing (requires MCP tools){Style.RESET_ALL}")
        else:
            print(f"2. {Fore.LIGHTBLACK_EX}Automated Penetration Testing (workflows.py not found){Style.RESET_ALL}")
        
        # Agent mode option
        if has_connected_servers:
            print(f"3. {Fore.YELLOW}Agent Mode{Style.RESET_ALL}")
        else:
            print(f"3. {Fore.LIGHTBLACK_EX}Agent Mode (requires MCP tools){Style.RESET_ALL}")
        
        print(f"4. {EXIT_OPTION}")
    
    @staticmethod
    def get_menu_choice(max_option: int = 4) -> str:
        """Get user's menu selection."""
        return input(f"\n{Fore.GREEN}Select mode (1-{max_option}): {Style.RESET_ALL}").strip()
    
    @staticmethod
    def display_interactive_mode_intro() -> None:
        """Display introduction for interactive chat mode."""
        print(f"\n{Fore.CYAN}INTERACTIVE CHAT MODE{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Type your questions or commands. Use 'multi' for multi-line input.{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Type 'menu' to return to main menu.{Style.RESET_ALL}\n")
    
    @staticmethod
    def display_agent_mode_intro() -> None:
        """Display introduction for agent mode."""
        print(f"\n{Fore.CYAN}AGENT MODE - Autonomous PTT-based Penetration Testing{Style.RESET_ALL}")
        print(f"{Fore.WHITE}{'='*60}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}The AI agent will autonomously conduct a penetration test{Style.RESET_ALL}")
        print(f"{Fore.WHITE}using a dynamic Pentesting Task Tree (PTT) for strategic{Style.RESET_ALL}")
        print(f"{Fore.WHITE}decision making and maintaining context throughout the test.{Style.RESET_ALL}")
        print(f"{Fore.WHITE}{'='*60}{Style.RESET_ALL}\n")
    
    @staticmethod
    def get_agent_mode_params() -> Optional[Dict[str, Any]]:
        """Get parameters for agent mode initialization."""
        print(f"{Fore.CYAN}Agent Mode Setup{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Please provide the following information:{Style.RESET_ALL}\n")
        
        # Get goal
        print(f"{Fore.YELLOW}1. Primary Goal{Style.RESET_ALL}")
        print(f"{Fore.WHITE}What is the main objective of this penetration test?{Style.RESET_ALL}")
        print(f"{Fore.LIGHTBLACK_EX}Example: 'Gain administrative access to the target system'{Style.RESET_ALL}")
        print(f"{Fore.LIGHTBLACK_EX}Example: 'Identify and exploit vulnerabilities in the web application'{Style.RESET_ALL}")
        goal = input(f"{Fore.GREEN}Goal: {Style.RESET_ALL}").strip()
        
        if not goal:
            print(f"{Fore.RED}Goal is required.{Style.RESET_ALL}")
            return None
        
        # Get target
        print(f"\n{Fore.YELLOW}2. Target Information{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Specify the target system, network, or application.{Style.RESET_ALL}")
        print(f"{Fore.LIGHTBLACK_EX}Example: '192.168.1.100' or 'example.com' or '192.168.1.0/24'{Style.RESET_ALL}")
        target = input(f"{Fore.GREEN}Target: {Style.RESET_ALL}").strip()
        
        if not target:
            print(f"{Fore.RED}Target is required.{Style.RESET_ALL}")
            return None
        
        # Get constraints
        constraints = {}
        print(f"\n{Fore.YELLOW}3. Constraints/Scope (Optional){Style.RESET_ALL}")
        print(f"{Fore.WHITE}Any limitations or specific requirements?{Style.RESET_ALL}")
        
        # Iteration limit
        print(f"\n{Fore.WHITE}Iteration Limit:{Style.RESET_ALL}")
        print("How many iterations should the agent run?")
        print("Each iteration involves task selection, execution, and tree updates.")
        print("Recommended: 10-30 iterations for thorough testing")
        print("Set to 0 to run until goal is achieved or no more actions available")
        iteration_limit_input = input(f"{Fore.GREEN}Iteration limit (default: 20): {Style.RESET_ALL}").strip()
        
        try:
            iteration_limit = int(iteration_limit_input) if iteration_limit_input else 20
            # Allow 0 for unlimited, but cap maximum at 200 for safety
            iteration_limit = max(0, min(200, iteration_limit))
            constraints['iteration_limit'] = iteration_limit
        except ValueError:
            constraints['iteration_limit'] = 20
            print(f"{Fore.YELLOW}Invalid input, using default: 20{Style.RESET_ALL}")
        
        # Additional notes
        notes = input(f"{Fore.GREEN}Additional notes/constraints (optional): {Style.RESET_ALL}").strip()
        if notes:
            constraints['notes'] = notes
        
        # Confirm
        print(f"\n{Fore.CYAN}Configuration Summary:{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Goal: {goal}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Target: {target}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Iteration Limit: {constraints['iteration_limit']}{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Constraints: {constraints}{Style.RESET_ALL}")
        
        confirm = input(f"\n{Fore.YELLOW}Proceed with agent mode? (yes/no): {Style.RESET_ALL}").strip().lower()
        if confirm != 'yes':
            print(f"{Fore.YELLOW}Agent mode cancelled.{Style.RESET_ALL}")
            return None
        
        return {
            'goal': goal,
            'target': target,
            'constraints': constraints
        }
    
    @staticmethod
    def get_user_input() -> str:
        """Get user input with prompt."""
        print(f"\n{Fore.GREEN}[>]{Style.RESET_ALL} ", end="")
        return input().strip()
    
    @staticmethod
    def get_multi_line_input() -> Optional[str]:
        """Get multi-line input from user."""
        print(f"{Fore.CYAN}Entering multi-line mode. Type your query across multiple lines.{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Press Enter on empty line to submit.{Style.RESET_ALL}")
        
        lines = []
        while True:
            line = input()
            if line == "":  # Empty line ends input
                break
            lines.append(line)
        
        # Only proceed if they actually entered something
        if not lines:
            print(f"{Fore.YELLOW}No query entered in multi-line mode.{Style.RESET_ALL}")
            return None
        
        return "\n".join(lines)
    
    @staticmethod
    def display_no_query_message() -> None:
        """Display message when no query is entered."""
        print(f"{Fore.YELLOW}No query entered. Please type your question.{Style.RESET_ALL}")
    
    @staticmethod
    def display_ready_message() -> None:
        """Display ready for next query message."""
        print(f"\n{Fore.CYAN}Ready for next query. Type 'quit', 'multi' for multi-line, or 'menu' for main menu.{Style.RESET_ALL}")
    
    @staticmethod
    def display_exit_message() -> None:
        """Display exit message."""
        print(f"\n{Fore.CYAN}Thank you for using GHOSTCREW, exiting...{Style.RESET_ALL}")
    
    @staticmethod
    def display_workflow_requirements_message() -> None:
        """Display message about automated workflow requirements."""
        print(f"\n{Fore.YELLOW}Automated penetration testing requires MCP tools to be configured and connected.{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Without real security tools, the AI would only generate simulated responses.{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Please configure MCP tools to use this feature.{Style.RESET_ALL}")
        input(f"{Fore.CYAN}Press Enter to continue...{Style.RESET_ALL}")
    
    @staticmethod
    def display_agent_mode_requirements_message() -> None:
        """Display message about agent mode requirements."""
        print(f"\n{Fore.YELLOW}Agent Mode requires MCP tools to be configured and connected.{Style.RESET_ALL}")
        print(f"{Fore.WHITE}The autonomous agent needs real security tools to execute PTT tasks.{Style.RESET_ALL}")
        print(f"{Fore.WHITE}Please configure MCP tools to use this feature.{Style.RESET_ALL}")
        input(f"{Fore.CYAN}Press Enter to continue...{Style.RESET_ALL}")
    
    @staticmethod
    def get_workflow_target() -> Optional[str]:
        """Get target input for workflow execution."""
        target = input(f"{Fore.YELLOW}Enter target (IP, domain, or network): {Style.RESET_ALL}").strip()
        if not target:
            print(f"{Fore.RED}Target is required.{Style.RESET_ALL}")
            return None
        return target
    
    @staticmethod
    def confirm_workflow_execution(workflow_name: str, target: str) -> bool:
        """Confirm workflow execution with user."""
        confirm = input(f"{Fore.YELLOW}Execute '{workflow_name}' on {target}? (yes/no): {Style.RESET_ALL}").strip().lower()
        return confirm == 'yes'
    
    @staticmethod
    def display_workflow_cancelled() -> None:
        """Display workflow cancelled message."""
        print(f"{Fore.YELLOW}Workflow cancelled.{Style.RESET_ALL}")
    
    @staticmethod
    def display_workflow_completed() -> None:
        """Display workflow completion message."""
        print(f"\n{Fore.GREEN}Workflow completed successfully!{Style.RESET_ALL}")
    
    @staticmethod
    def ask_generate_report() -> bool:
        """Ask if user wants to generate a report."""
        response = input(f"\n{Fore.CYAN}Generate markdown report? (yes/no): {Style.RESET_ALL}").strip().lower()
        return response == 'yes'
    
    @staticmethod
    def ask_save_raw_history() -> bool:
        """Ask if user wants to save raw conversation history."""
        response = input(f"{Fore.YELLOW}Save raw conversation history? (yes/no, default: no): {Style.RESET_ALL}").strip().lower()
        return response == 'yes'
    
    @staticmethod
    def display_report_generated(report_path: str) -> None:
        """Display report generation success message."""
        print(f"\n{Fore.GREEN}Report generated: {report_path}{Style.RESET_ALL}")
        print(f"{Fore.CYAN}Open the markdown file in any markdown viewer for best formatting{Style.RESET_ALL}")
    
    @staticmethod
    def display_report_error(error: Exception) -> None:
        """Display report generation error message."""
        print(f"\n{Fore.RED}Error generating report: {error}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Raw workflow data is still available in conversation history{Style.RESET_ALL}")
    
    @staticmethod
    def display_invalid_choice() -> None:
        """Display invalid choice message."""
        print(f"{Fore.RED}Invalid choice. Please select a valid option.{Style.RESET_ALL}")
    
    @staticmethod
    def display_invalid_input() -> None:
        """Display invalid input message."""
        print(f"{Fore.RED}Invalid input. Please enter a number.{Style.RESET_ALL}")
    
    @staticmethod
    def display_operation_cancelled() -> None:
        """Display operation cancelled message."""
        print(f"\n{Fore.YELLOW}Operation cancelled.{Style.RESET_ALL}")
    
    @staticmethod
    def press_enter_to_continue() -> None:
        """Wait for user to press enter."""
        input(f"\n{Fore.CYAN}Press Enter to continue...{Style.RESET_ALL}") 