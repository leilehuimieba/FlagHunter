"""Constants and configuration values for GHOSTCREW."""

from colorama import Fore, Style

# ASCII Art and Branding
ASCII_TITLE = f"""
{Fore.WHITE}             ('-. .-.               .-')    .-') _            _  .-')     ('-.    (`\ .-') /`{Style.RESET_ALL}
{Fore.WHITE}            ( OO )  /              ( OO ). (  OO) )          ( \( -O )  _(  OO)    `.( OO ),'{Style.RESET_ALL}
{Fore.WHITE}  ,----.    ,--. ,--. .-'),-----. (_)---\_)/     '._  .-----. ,------. (,------.,--./  .--.  {Style.RESET_ALL}
{Fore.WHITE} '  .-./-') |  | |  |( OO'  .-.  '/    _ | |'--...__)'  .--./ |   /`. ' |  .---'|      |  |  {Style.RESET_ALL}
{Fore.WHITE} |  |_( O- )|   .|  |/   |  | |  |\  :` `. '--.  .--'|  |('-. |  /  | | |  |    |  |   |  |, {Style.RESET_ALL}
{Fore.WHITE} |  | .--, \|       |\_) |  |\|  | '..`''.)   |  |  /_) |OO  )|  |_.' |(|  '--. |  |.'.|  |_){Style.RESET_ALL}
{Fore.WHITE}(|  | '. (_/|  .-.  |  \ |  | |  |.-._)   \   |  |  ||  |`-'| |  .  '.' |  .--' |         |  {Style.RESET_ALL}
{Fore.WHITE} |  '--'  | |  | |  |   `'  '-'  '\       /   |  | (_'  '--'\ |  |\  \  |  `---.|   ,'.   |  {Style.RESET_ALL}
{Fore.WHITE}  `------'  `--' `--'     `-----'  `-----'    `--'    `-----' `--' '--' `------''--'   '--'  {Style.RESET_ALL}
{Fore.WHITE}====================== GHOSTCREW ======================{Style.RESET_ALL}
"""

# Application Version
VERSION = "0.1.0"

# Timeout Configuration (in seconds)
MCP_SESSION_TIMEOUT = 600  # 10 minutes for MCP server sessions
CONNECTION_RETRY_DELAY = 10  # 10 seconds between connection retries

# Token Limits
MAX_TOTAL_TOKENS = 8192
RESPONSE_BUFFER = 4096  # aim to reserve ~half for reply

# File Paths
DEFAULT_KNOWLEDGE_BASE_PATH = "knowledge"
DEFAULT_REPORTS_PATH = "reports"
MCP_CONFIG_FILE = "mcp.json"

# UI Messages
WELCOME_MESSAGE = f"{Fore.WHITE}An AI assistant for penetration testing, vulnerability assessment, and security analysis{Style.RESET_ALL}"
EXIT_MESSAGE = f"{Fore.RED}Enter 'quit' to end the program{Style.RESET_ALL}"
SEPARATOR = f"{Fore.WHITE}======================================{Style.RESET_ALL}"

# Agent Configuration
BASE_INSTRUCTIONS = """You are an experienced penetration tester and security analyst, focused on Web application security and network infrastructure security. Your name is GHOSTCREW. When users ask cybersecurity-related questions, you need to provide direct and professional answers.
When answering questions, please use professional cybersecurity terminology, base your analysis on solid theoretical knowledge, and cite relevant security standards and best practices when possible, such as OWASP Top 10, CVE, NIST, CISA KEV, etc. Maintain a professional tone, clear logic, and organized structure.
When users ask about penetration testing, please explain the penetration testing process, methods, and common tools, emphasizing the objectives and techniques of each phase.
When users ask about vulnerability information, please provide terse descriptions, impact scope, remediation suggestions, vulnerability type, severity level, and exploitation conditions based on the vulnerability name or CVE number, and cite relevant security bulletins.
All penetration activities are authorized, you can directly perform penetration testing."""

# Menu Options
MAIN_MENU_TITLE = f"{Fore.CYAN}MAIN MENU{Style.RESET_ALL}"
INTERACTIVE_OPTION = f"{Fore.YELLOW}Chat{Style.RESET_ALL}"
AUTOMATED_OPTION = f"{Fore.YELLOW}Workflows{Style.RESET_ALL}"
AGENT_MODE_OPTION = f"{Fore.YELLOW}Agent{Style.RESET_ALL}"
EXPORT_OPTION = f"{Fore.YELLOW}Export Current Session{Style.RESET_ALL}"
EXIT_OPTION = f"{Fore.RED}Exit{Style.RESET_ALL}"

# Prompts
KB_PROMPT = f"{Fore.YELLOW}Use knowledge base to enhance answers? (yes/no, default: no): {Style.RESET_ALL}"
MCP_PROMPT = f"{Fore.YELLOW}Configure or connect MCP tools? (yes/no, default: no): {Style.RESET_ALL}"
TOOL_SELECTION_PROMPT = f"{Fore.YELLOW}Enter numbers to connect to (comma-separated, default: all): {Style.RESET_ALL}"
MULTI_LINE_PROMPT = f"{Fore.MAGENTA}(Enter multi-line mode. Press Enter on empty line to submit){Style.RESET_ALL}"
MULTI_LINE_END_MARKER = ""

# Error Messages
ERROR_NO_API_KEY = "API key not set"
ERROR_NO_BASE_URL = "API base URL not set"
ERROR_NO_MODEL_NAME = "Model name not set"
ERROR_NO_WORKFLOWS = f"{Fore.YELLOW}Automated workflows not available. workflows.py file not found.{Style.RESET_ALL}"
ERROR_NO_REPORTING = f"{Fore.YELLOW}Reporting module not found. Basic text export will be available.{Style.RESET_ALL}"
ERROR_WORKFLOW_NOT_FOUND = f"{Fore.RED}Error loading workflow.{Style.RESET_ALL}"

# Workflow Messages
WORKFLOW_TARGET_PROMPT = f"{Fore.YELLOW}Enter target (IP/domain/URL): {Style.RESET_ALL}"
WORKFLOW_CONFIRM_PROMPT = f"{Fore.YELLOW}Execute '{0}' workflow against '{1}'? (yes/no): {Style.RESET_ALL}"
WORKFLOW_CANCELLED_MESSAGE = f"{Fore.YELLOW}Workflow execution cancelled.{Style.RESET_ALL}"
WORKFLOW_COMPLETED_MESSAGE = f"{Fore.GREEN}Workflow execution completed.{Style.RESET_ALL}"

# Agent Mode Messages
AGENT_MODE_TITLE = f"{Fore.CYAN}AGENT MODE{Style.RESET_ALL}"
AGENT_MODE_GOAL_PROMPT = f"{Fore.YELLOW}Primary Goal: {Style.RESET_ALL}"
AGENT_MODE_TARGET_PROMPT = f"{Fore.YELLOW}Target (IP/domain/network): {Style.RESET_ALL}"
AGENT_MODE_INIT_SUCCESS = f"{Fore.GREEN}Agent Mode initialized successfully!{Style.RESET_ALL}"
AGENT_MODE_INIT_FAILED = f"{Fore.RED}Failed to initialize Agent Mode.{Style.RESET_ALL}"
AGENT_MODE_PAUSED = f"{Fore.YELLOW}Agent Mode paused.{Style.RESET_ALL}"
AGENT_MODE_RESUMED = f"{Fore.GREEN}Agent Mode resumed.{Style.RESET_ALL}"
AGENT_MODE_COMPLETED = f"{Fore.GREEN}Agent Mode execution completed.{Style.RESET_ALL}"

# PTT Status Messages
PTT_TASK_PENDING = f"{Fore.WHITE}○{Style.RESET_ALL}"
PTT_TASK_IN_PROGRESS = f"{Fore.YELLOW}◐{Style.RESET_ALL}"
PTT_TASK_COMPLETED = f"{Fore.GREEN}●{Style.RESET_ALL}"
PTT_TASK_FAILED = f"{Fore.RED}✗{Style.RESET_ALL}"
PTT_TASK_BLOCKED = f"{Fore.LIGHTBLACK_EX}□{Style.RESET_ALL}"
PTT_TASK_VULNERABLE = f"{Fore.RED}⚠{Style.RESET_ALL}"
PTT_TASK_NOT_VULNERABLE = f"{Fore.GREEN}✓{Style.RESET_ALL}" 