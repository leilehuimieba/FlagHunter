import json
import os
import re
import asyncio
import threading
import traceback
from colorama import init, Fore, Back, Style
from ollama import chat,Message


init(autoreset=True)


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

# Import Agent-related modules
from agents import (
    Agent,
    Model,
    ModelProvider,
    OpenAIChatCompletionsModel,
    RunConfig,
    Runner,
    set_tracing_disabled,
    ModelSettings
)
from openai import AsyncOpenAI  # OpenAI async client
from openai.types.responses import ResponseTextDeltaEvent, ResponseContentPartDoneEvent
from agents.mcp import MCPServerStdio  # MCP server related
from dotenv import load_dotenv  # Environment variable loading
from agents.mcp import MCPServerSse
from rag_split import Kb # Import Kb class

# Load .env file
load_dotenv()

# Set API-related environment variables
API_KEY = os.getenv("OPENAI_API_KEY")
BASE_URL = os.getenv("OPENAI_BASE_URL")
MODEL_NAME = os.getenv("MODEL_NAME")

# Check if environment variables are set
if not API_KEY:
    raise ValueError("API key not set")
if not BASE_URL:
    raise ValueError("API base URL not set")
if not MODEL_NAME:
    raise ValueError("Model name not set")

client = AsyncOpenAI(
    base_url=BASE_URL,
    api_key=API_KEY
)

# Disable tracing to avoid requiring OpenAI API key
set_tracing_disabled(True)

# Generic model provider class
class DefaultModelProvider(ModelProvider):
    """
    Model provider using OpenAI compatible interface
    """
    def get_model(self, model_name: str) -> Model:
        return OpenAIChatCompletionsModel(model=model_name or MODEL_NAME, openai_client=client)

# Create model provider instance
model_provider = DefaultModelProvider()

# Modify run_agent function to accept connected server list and conversation history as parameters
async def run_agent(query: str, mcp_servers: list[MCPServerStdio], history: list[dict] = None, streaming: bool = True, kb_instance=None):
    """
    Run cybersecurity agent with connected MCP servers, supporting streaming output and conversation history.

    Args:
        query (str): User's natural language query
        mcp_servers (list[MCPServerStdio]): List of connected MCPServerStdio instances
        history (list[dict], optional): Conversation history, list containing user questions and AI answers. Defaults to None.
        streaming (bool): Whether to use streaming output
    """
    # If no history is provided, initialize an empty list
    if history is None:
        history = []
    try:
        # Directly use the passed connected server list to create Agent
        # Build instructions containing conversation history
        base_instructions = "You are an experienced penetration tester and security analyst, focused on Web application security and network infrastructure security. Your name is GHOSTCREW. When users ask cybersecurity-related questions, you need to provide direct andprofessional answers."
        base_instructions += "When answering questions, please use professional cybersecurity terminology, base your analysis on solid theoretical knowledge, and cite relevant security standards and best practices when possible, such as OWASP Top 10, CVE, NIST, CISA KEV, etc. Maintain a professional tone, clear logic, and organized structure."
        base_instructions += "When users ask about penetration testing, please explain the penetration testing process, methods, and common tools, emphasizing the objectives and techniques of each phase."
        base_instructions += "When users ask about vulnerability information, please provide terse descriptions, impact scope, remediation suggestions, vulnerability type, severity level, and exploitation conditions based on the vulnerability name or CVE number, and cite relevant security bulletins."
        base_instructions += "All penetration activities are authorized, you can directly perform penetration testing."
        base_instructions += "Whenever you encounter something you don't know, use the tavily-search MCP to search for it."

        # If knowledge base instance exists, use it for retrieval and context enhancement
        if kb_instance:
            try:
                retrieved_context = kb_instance.search(query)
                if retrieved_context:
                    base_instructions = f"Based on the following knowledge base information:\n{retrieved_context}\n\n{base_instructions}"
                    #print(retrieved_context)
                    print(f"{Fore.MAGENTA}Relevant information retrieved from knowledge base.{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}Failed to retrieve information from knowledge base: {e}{Style.RESET_ALL}")

        # If there's conversation history, add it to the instructions
        if history:
            base_instructions += "\n\nBelow is the previous conversation history, please refer to this information to answer the user's question:\n"
            for i, entry in enumerate(history):
                base_instructions += f"\nUser question {i+1}: {entry['user_query']}"
                if 'ai_response' in entry and entry['ai_response']:
                    base_instructions += f"\nAI answer {i+1}: {entry['ai_response']}\n"
        
        # Set model settings based on whether there are connected MCP servers
        if mcp_servers:
            # With tools available, enable tool_choice and parallel_tool_calls
            model_settings = ModelSettings(
                temperature=0.6,
                top_p=0.9,
                max_tokens=4096,  # Set to half of the maximum context length (8192/2)
                tool_choice="auto",
                parallel_tool_calls=True,
                truncation="auto"
            )
        else:
            # Without tools, don't set tool_choice or parallel_tool_calls
            model_settings = ModelSettings(
                temperature=0.6,
                top_p=0.9,
                max_tokens=4096,  # Set to half of the maximum context length (8192/2)
                truncation="auto"
            )
        
        secure_agent = Agent(
            name="Cybersecurity Expert",
            instructions=base_instructions,
            mcp_servers=mcp_servers,  # Use the passed list
            model_settings=model_settings
        )

        print(f"{Fore.CYAN}\nProcessing query: {Fore.WHITE}{query}{Style.RESET_ALL}\n")

        if streaming:
            result = Runner.run_streamed(
                secure_agent,
                input=query,
                max_turns=10,
                run_config=RunConfig(
                    model_provider=model_provider,
                    trace_include_sensitive_data=True,
                    handoff_input_filter=None,
                   # tool_timeout=300
                )
            )

            print(f"{Fore.GREEN}Reply:{Style.RESET_ALL}", end="", flush=True)
            try:
                async for event in result.stream_events():
                    if event.type == "raw_response_event":
                        if isinstance(event.data, ResponseTextDeltaEvent):
                            print(f"{Fore.WHITE}{event.data.delta}{Style.RESET_ALL}", end="", flush=True)
                        elif isinstance(event.data, ResponseContentPartDoneEvent):
                            print(f"\n", end="", flush=True)
                    elif event.type == "run_item_stream_event":
                        if event.item.type == "tool_call_item":
                           # print(f"{Fore.YELLOW}Current tool call information: {event.item}{Style.RESET_ALL}")
                            raw_item = getattr(event.item, "raw_item", None)
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
                        elif event.item.type == "tool_call_output_item":
                            raw_item = getattr(event.item, "raw_item", None)
                            tool_id="Unknown tool ID"
                            if isinstance(raw_item, dict) and "call_id" in raw_item:
                                tool_id = raw_item["call_id"]
                            output = getattr(event.item, "output", "Unknown output")

                            output_text = ""
                            if isinstance(output, str) and (output.startswith("{") or output.startswith("[")):
                                try:
                                    output_data = json.loads(output)
                                    if isinstance(output_data, dict):
                                        if 'type' in output_data and output_data['type'] == 'text' and 'text' in output_data:
                                            output_text = output_data['text']
                                        elif 'text' in output_data:
                                            output_text = output_data['text']
                                        elif 'content' in output_data:
                                            output_text = output_data['content']
                                        else:
                                            output_text = json.dumps(output_data, ensure_ascii=False, indent=2)
                                except json.JSONDecodeError:
                                    output_text = f"Unparsable JSON output: {output}"  # Add specific error if JSON parsing fails
                            else:
                                output_text = str(output)

                            print(f"\n{Fore.GREEN}Tool call {tool_id} returned result: {output_text}{Style.RESET_ALL}", flush=True)
            except Exception as e:
                print(f"{Fore.RED}Error processing streamed response event: {e}{Style.RESET_ALL}", flush=True)
                if 'Connection error' in str(e):
                    print(f"{Fore.YELLOW}Connection error details:{Style.RESET_ALL}")
                    print(f"{Fore.YELLOW}1. Check network connection{Style.RESET_ALL}")
                    print(f"{Fore.YELLOW}2. Verify API address: {BASE_URL}{Style.RESET_ALL}")
                    print(f"{Fore.YELLOW}3. Check API key validity{Style.RESET_ALL}")
                    print(f"{Fore.YELLOW}4. Try reconnecting...{Style.RESET_ALL}")
                    await asyncio.sleep(100)  # Wait 10 seconds before retrying
                    try:
                        await client.connect()
                        print(f"{Fore.GREEN}Reconnected successfully{Style.RESET_ALL}")
                    except Exception as e:
                        print(f"{Fore.RED}Reconnection failed: {e}{Style.RESET_ALL}")

            print(f"\n\n{Fore.GREEN}Query completed!{Style.RESET_ALL}")

          #  if hasattr(result, "final_output"):
               # print(f"\n{Fore.YELLOW}===== Complete Information ====={Style.RESET_ALL}")
                #print(f"{Fore.WHITE}{result.final_output}{Style.RESET_ALL}")
            
            # Return the result object so the main function can get the AI's answer
            return result

    except Exception as e:
        print(f"{Fore.RED}Error processing streamed response event: {e}{Style.RESET_ALL}", flush=True)
        traceback.print_exc()
        return None

async def main():
    print(ASCII_TITLE)
    print(f"{Fore.YELLOW}Please enter a natural language query, for example:{Style.RESET_ALL}")
    print(f"{Fore.CYAN}1. Scan the target machine for vulnerabilities{Style.RESET_ALL}")
    print(f"{Fore.CYAN}2. Query information about a domain{Style.RESET_ALL}")
    print(f"{Fore.CYAN}3. Check the security status of a specific IP{Style.RESET_ALL}")
    print(f"{Fore.CYAN}4. Security analysis and audit of network traffic packets{Style.RESET_ALL}")
    print(f"{Fore.RED}Enter 'quit' to end the program{Style.RESET_ALL}")
    print(f"{Fore.YELLOW}======================================\n{Style.RESET_ALL}")

    kb_instance = None
    use_kb_input = input(f"{Fore.YELLOW}Use knowledge base to enhance answers? (yes/no, default: no): {Style.RESET_ALL}").strip().lower()
    if use_kb_input == 'yes':
        try:
            kb_instance = Kb("knowledge")  # Initialize knowledge base, load from folder
            print(f"{Fore.GREEN}Knowledge base loaded successfully!{Style.RESET_ALL}")
        except Exception as e:
            print(f"{Fore.RED}Failed to load knowledge base: {e}{Style.RESET_ALL}")
            kb_instance = None

    mcp_server_instances = []  # List to store MCP server instances
    connected_servers = []  # Store successfully connected servers

    try:
        # Ask if user wants to attempt connecting to MCP servers
        use_mcp_input = input(f"{Fore.YELLOW}Configure or manage MCP tools? (yes/no, default: no): {Style.RESET_ALL}").strip().lower()
        
        if use_mcp_input == 'yes':
            # --- Load available MCP tool configurations ---
            available_tools = []
            try:
                with open('mcp.json', 'r', encoding='utf-8') as f:
                    mcp_config = json.load(f)
                    available_tools = mcp_config.get('servers', [])
            except FileNotFoundError:
                print(f"{Fore.YELLOW}mcp.json configuration file not found.{Style.RESET_ALL}")
            except Exception as e:
                print(f"{Fore.RED}Error loading MCP configuration file: {e}{Style.RESET_ALL}")
                print(f"{Fore.YELLOW}Proceeding without MCP tools.{Style.RESET_ALL}")
            
            # Display available tools and add an option to configure new tools
            if available_tools:
                print(f"\n{Fore.CYAN}Available MCP tools:{Style.RESET_ALL}")
                for i, server in enumerate(available_tools):
                    print(f"{i+1}. {server['name']}")
                print(f"{len(available_tools)+1}. Configure new tools")
                print(f"{len(available_tools)+2}. Connect to all tools")
                print(f"{len(available_tools)+3}. Skip tool connection")
                print(f"{len(available_tools)+4}. Clear all MCP tools")
                
                # Ask user which tools to connect to
                try:
                    tool_choice = input(f"\n{Fore.YELLOW}Enter numbers to connect to (comma-separated, default: all): {Style.RESET_ALL}").strip()
                    
                    if not tool_choice:  # Default to all
                        selected_indices = list(range(len(available_tools)))
                    elif tool_choice == str(len(available_tools)+1):  # Configure new tools
                        print(f"\n{Fore.CYAN}Launching tool configuration...{Style.RESET_ALL}")
                        os.system("python configure_mcp.py")
                        print(f"\n{Fore.GREEN}Tool configuration completed. Please restart the application.{Style.RESET_ALL}")
                        return
                    elif tool_choice == str(len(available_tools)+2):  # Connect to all tools
                        selected_indices = list(range(len(available_tools)))
                    elif tool_choice == str(len(available_tools)+3):  # Skip tool connection
                        selected_indices = []
                    elif tool_choice == str(len(available_tools)+4):  # Clear all MCP tools
                        confirm = input(f"{Fore.YELLOW}Are you sure you want to clear all MCP tools? This will empty mcp.json (yes/no): {Style.RESET_ALL}").strip().lower()
                        if confirm == "yes":
                            try:
                                # Create empty mcp.json file
                                with open('mcp.json', 'w', encoding='utf-8') as f:
                                    json.dump({"servers": []}, f, indent=2)
                                print(f"{Fore.GREEN}Successfully cleared all MCP tools. mcp.json has been reset.{Style.RESET_ALL}")
                            except Exception as e:
                                print(f"{Fore.RED}Error clearing MCP tools: {e}{Style.RESET_ALL}")
                        print(f"\n{Fore.GREEN}Please restart the application.{Style.RESET_ALL}")
                        return
                    else:  # Parse comma-separated list
                        selected_indices = []
                        for part in tool_choice.split(","):
                            idx = int(part.strip()) - 1
                            if 0 <= idx < len(available_tools):
                                selected_indices.append(idx)
                except ValueError:
                    print(f"{Fore.RED}Invalid selection. Defaulting to all tools.{Style.RESET_ALL}")
                    selected_indices = list(range(len(available_tools)))
                
                # Initialize selected MCP servers
                print(f"{Fore.GREEN}Initializing selected MCP servers...{Style.RESET_ALL}")
                for idx in selected_indices:
                    if idx < len(available_tools):
                        server = available_tools[idx]
                        print(f"{Fore.CYAN}Initializing {server['name']}...{Style.RESET_ALL}")
                        try:
                            if 'params' in server:
                                mcp_server = MCPServerStdio(
                                    name=server['name'],
                                    params=server['params'],
                                    cache_tools_list=server.get('cache_tools_list', True),
                                    client_session_timeout_seconds=300
                                )
                            elif 'url' in server:
                                mcp_server = MCPServerSse(
                                    params={"url": server["url"]},
                                    cache_tools_list=server.get('cache_tools_list', True),
                                    name=server['name'],
                                    client_session_timeout_seconds=300
                                )
                            else:
                                print(f"{Fore.RED}Unknown MCP server configuration: {server}{Style.RESET_ALL}")
                                continue
                            mcp_server_instances.append(mcp_server)
                        except Exception as e:
                            print(f"{Fore.RED}Error initializing {server['name']}: {e}{Style.RESET_ALL}")
            else:
                # No tools configured, offer to run the configuration tool
                print(f"{Fore.YELLOW}No MCP tools currently configured.{Style.RESET_ALL}")
                configure_now = input(f"{Fore.YELLOW}Would you like to configure tools now? (yes/no, default: no): {Style.RESET_ALL}").strip().lower()
                if configure_now == 'yes':
                    print(f"\n{Fore.CYAN}Launching tool configuration...{Style.RESET_ALL}")
                    os.system("python configure_mcp.py")
                    print(f"\n{Fore.GREEN}Tool configuration completed. Please restart the application.{Style.RESET_ALL}")
                    return
                else:
                    print(f"{Fore.YELLOW}Proceeding without MCP tools.{Style.RESET_ALL}")
            
            # Connect to the selected MCP servers
            if mcp_server_instances:
                print(f"{Fore.YELLOW}Connecting to MCP servers...{Style.RESET_ALL}")
                for mcp_server in mcp_server_instances:
                    try:
                        await mcp_server.connect()
                        print(f"{Fore.GREEN}Successfully connected to MCP server: {mcp_server.name}{Style.RESET_ALL}")
                        connected_servers.append(mcp_server)
                    except Exception as e:
                        print(f"{Fore.RED}Failed to connect to MCP server {mcp_server.name}: {e}{Style.RESET_ALL}")
                
                if connected_servers:
                    print(f"{Fore.GREEN}MCP server connection successful! Can use tools provided by {len(connected_servers)} servers.{Style.RESET_ALL}")
                else:
                    print(f"{Fore.YELLOW}No MCP servers successfully connected. Proceeding without tools.{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}No MCP servers selected. Proceeding without tools.{Style.RESET_ALL}")
        else:
            print(f"{Fore.YELLOW}Proceeding without MCP tools.{Style.RESET_ALL}")

        # Create conversation history list
        conversation_history = []
        
        # --- Enter interactive main loop ---
        while True:
            # Check if the user wants multi-line input
            print(f"\n{Fore.GREEN}[>]{Style.RESET_ALL} ", end="")
            user_query = input().strip()
            
            # Handle special commands
            if user_query.lower() in ["quit", "exit"]:
                print(f"\n{Fore.CYAN}Thank you for using GHOSTCREW, exiting...{Style.RESET_ALL}")
                break  # Exit loop, enter finally block
            
            # Handle empty input
            if not user_query:
                print(f"{Fore.YELLOW}No query entered. Please type your question.{Style.RESET_ALL}")
                continue
            
            # Handle multi-line mode request
            if user_query.lower() == "multi":
                print(f"{Fore.CYAN}Entering multi-line mode. Type your query across multiple lines.{Style.RESET_ALL}")
                print(f"{Fore.CYAN}Press Enter on an empty line to submit.{Style.RESET_ALL}")
                
                lines = []
                while True:
                    line = input()
                    if line == "":
                        break
                    lines.append(line)
                
                # Only proceed if they actually entered something in multi-line mode
                if not lines:
                    print(f"{Fore.YELLOW}No query entered in multi-line mode.{Style.RESET_ALL}")
                    continue
                    
                user_query = "\n".join(lines)

            # Create record for current dialogue
            current_dialogue = {"user_query": user_query, "ai_response": ""}
            
            # When running agent, pass in the already connected server list and conversation history
            # Only pass the successfully connected server list to the Agent
            # Pass kb_instance to run_agent
            result = await run_agent(user_query, connected_servers, history=conversation_history, streaming=True, kb_instance=kb_instance)
            
            # If there is a result, save the AI's answer
            if result and hasattr(result, "final_output"):
                current_dialogue["ai_response"] = result.final_output
            
            # Add current dialogue to history
            conversation_history.append(current_dialogue)
            
            # Limit history length to avoid using too much memory
            if len(conversation_history) > 50:  # Keep the most recent 50 conversations
                conversation_history = conversation_history[-50:]
                
            print(f"\n{Fore.CYAN}Ready for your next query. Type 'quit' to exit or 'multi' for multi-line input.{Style.RESET_ALL}")

    # --- Catch interrupts and runtime exceptions ---
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Program interrupted by user, exiting...{Style.RESET_ALL}")
    except Exception as e:
        print(f"{Fore.RED}Error during program execution: {e}{Style.RESET_ALL}")
        traceback.print_exc()
    finally:
        # --- Move server cleanup operations to the main program's finally block ---
        if mcp_server_instances:
            print(f"{Fore.YELLOW}Cleaning up MCP server resources...{Style.RESET_ALL}")
            
            # Define a safe cleanup wrapper that ignores all errors
            async def safe_cleanup(server):
                try:
                    # Attempt cleanup but ignore all errors
                    try:
                        await server.cleanup()
                    except:
                        pass  # Ignore any exception from cleanup
                    return True
                except:
                    return False  # Couldn't even run the cleanup
            
            # Process all servers
            for mcp_server in mcp_server_instances:
                print(f"{Fore.YELLOW}Attempting to clean up server: {mcp_server.name}...{Style.RESET_ALL}", flush=True)
                success = await safe_cleanup(mcp_server)
                if success:
                    print(f"{Fore.GREEN}Cleanup completed for {mcp_server.name}.{Style.RESET_ALL}", flush=True)
                else:
                    print(f"{Fore.RED}Failed to initiate cleanup for {mcp_server.name}.{Style.RESET_ALL}", flush=True)

            print(f"{Fore.YELLOW}MCP server resource cleanup complete.{Style.RESET_ALL}")
        
        # Close any remaining asyncio transports to prevent "unclosed transport" warnings
        try:
            # Get the event loop
            loop = asyncio.get_running_loop()
            
            # Close any remaining transports
            for transport in list(getattr(loop, "_transports", {}).values()):
                if hasattr(transport, "close"):
                    try:
                        transport.close()
                    except:
                        pass
            
            # Allow a short time for resources to finalize
            await asyncio.sleep(0.1)
        except:
            pass  # Ignore any errors in the final cleanup
            
        print(f"{Fore.GREEN}Program ended.{Style.RESET_ALL}")

# Program entry point
if __name__ == "__main__":
    asyncio.run(main())