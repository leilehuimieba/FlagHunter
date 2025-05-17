# Project Name: GHOSTCREW

This is an intelligent cybersecurity assistant using large language models with MCP and RAG architecture. It aims to help users perform penetration testing tasks, query security information, analyze network traffic, and more through natural language interaction.

## Features

- **Natural Language Interaction**: Users can ask questions and give instructions to the AI assistant using natural language.
- **MCP Server Integration**: Through the `mcp.json` configuration file, multiple MCP servers can be flexibly integrated and managed to extend the assistant's capabilities.
- **Tool Management**: Configure, connect to, and manage MCP tools through an interactive menu, including the ability to clear all configurations.
- **Improved Input Handling**: Support for both single-line and multi-line input modes to accommodate complex queries.
- **Tool Invocation**: The AI assistant can call tools provided by configured MCP servers (such as: nmap, metasploit, ffuf, etc.) based on user requests.
- **Conversation History**: Supports multi-turn dialogues, remembering previous interaction content.
- **Streaming Output**: AI responses can be streamed for a better user experience.
- **Knowledge Base Enhancement (Optional)**: Supports enhancing AI responses through a local knowledge base RAG (`knowledge` directory).
- **Configurable Models**: Supports configuration of different language model parameters.

### Startup Effect
<p align="center">
  <img width="650" alt="GHOSTCREW Terminal Startup Screen" src="https://github.com/user-attachments/assets/ae70a6cf-7712-4455-bed5-56ed45a1ed8f">
  <br>
  <em>GHOSTCREW's terminal startup interface</em>
</p>

### Metasploit Tool Call
<p align="center">
  <img width="800" alt="GHOSTCREW Metasploit Integration" src="https://github.com/user-attachments/assets/d788b88e-bdd6-457b-a54f-63c773dd85f6">
  <br>
  <em>Example of GHOSTCREW invoking Metasploit Framework</em>
</p>

## Installation Guide

1. **Clone Repository**:
   ```bash
   git clone https://github.com/GH05TCREW/GHOSTCREW.git
   cd agent
   ```

2. **Create and Activate Virtual Environment** (recommended):
   ```bash
   python -m venv .venv
   ```
   - Windows:
     ```bash
     .venv\Scripts\activate
     ```
   - macOS/Linux:
     ```bash
     source .venv/bin/activate
     ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Install `uv` (important)**:
   This project uses `uv` as a Python package runner and installer in some scenarios.
   - The `start.bat` script will automatically try to install `uv` for you.
   - If you want to install it manually or use it in another environment, you can run:
     ```bash
     pip install uv
     ```
     or refer to the official `uv` documentation for installation.
   Make sure `uv` is successfully installed and can be called from the command line.

## Usage

1. **Configure MCP Servers**: 
   - Run the application and select "Configure or connect MCP tools" when prompted
   - Use the interactive tool configuration menu to add, configure, or clear MCP tools
   - The configuration is stored in the `mcp.json` file

2. **Prepare Knowledge Base (Optional)**:
   If you want to use the knowledge base enhancement feature, place relevant text files (e.g., `.txt`) in the `knowledge` folder.

3. **Run the Main Program**:
   ```bash
   python main.py
   ```
   After the program starts, you can:
   - Choose whether to use the knowledge base
   - Configure or activate MCP tools
   - Enter your questions or instructions according to the prompts
   - Use 'multi' command to enter multi-line input mode for complex queries
   - Enter 'quit' to exit the program

## Input Modes

GHOSTCREW supports two input modes:
- **Single-line mode** (default): Type your query and press Enter to submit
- **Multi-line mode**: Type 'multi' and press Enter, then type your query across multiple lines. Press Enter on an empty line to submit.

## MCP Tool Management

When starting the application, you can:
1. Connect to specific tools
2. Configure new tools
3. Connect to all tools
4. Skip connection
5. Clear all tools (resets mcp.json)

## Available MCP Tools

GHOSTCREW supports integration with the following security tools through the MCP protocol:

1. **AlterX** - Subdomain permutation and wordlist generation tool
2. **FFUF Fuzzer** - Fast web fuzzing tool for discovering hidden content
3. **Masscan** - High-speed network port scanner
4. **Metasploit** - Penetration testing framework providing exploit execution, payload generation, and session management
5. **Nmap Scanner** - Network discovery and security auditing tool
6. **Nuclei Scanner** - Template-based vulnerability scanner
7. **SQLMap** - Automated SQL injection detection and exploitation tool
8. **SSL Scanner** - Analysis tool for SSL/TLS configurations and security issues
9. **Wayback URLs** - Tool for discovering historical URLs from the Wayback Machine archive

Each tool can be configured through the interactive configuration menu by selecting "Configure new tools" from the MCP tools menu.

## File Structure

```
agent/
├── .venv/                  # Python virtual environment (ignored by .gitignore)
├── knowledge/             # Knowledge base documents directory
│   └── ...
├── .gitignore              # Git ignore file configuration
├── main.py                 # Main program entry
├── configure_mcp.py        # MCP tool configuration utility
├── mcp.json                # MCP server configuration file
├── rag_embedding.py        # RAG embedding related (if used)
├── rag_split.py            # RAG text splitting related (if used)
├── README.md               # Project documentation
├── requirements.txt        # Python dependency list
├── LICENSE                 # Project license
└── ... (other scripts or configuration files)
```

## Configuration File (`.env`)
```
# OpenAI API configurations
OPENAI_API_KEY=your_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL_NAME=gpt-4o
```

This configuration uses OpenAI's API for both the language model and embeddings (when using the knowledge base RAG feature).

## Configuration File (`mcp.json`)

This file is used to define MCP servers that the AI assistant can connect to and use. Most MCP servers require Node.js to be installed on your system. Each server entry should include:
- `name`: Unique name of the server.
- `params`: Parameters needed to start the server, usually including `command` and `args`.
- `cache_tools_list`: Whether to cache the tools list.

**MCP Example Server Configuration**:

**stdio**
```json
{
  "name": "Nmap Scanner",
  "params": {
    "command": "npx",
    "args": [
      "-y", 
      "gc-nmap-mcp"
    ],
    "env": {
      "NMAP_PATH": "C:\\Program Files (x86)\\Nmap\\nmap.exe"
    }
  },
  "cache_tools_list": true
}
```
Make sure to replace the path to the Nmap executable with your own installation path.

**sse**
```json
{"name":"mcpname",
  "url":"http://127.0.0.1:8009/sse"
},
```

## Knowledge Base Configuration
Simply add the corresponding files to knowledge
