# PentestMCP

This is an AI red team assistant using large language models with MCP and RAG architecture. It aims to help users perform penetration testing tasks, query security information, analyze network traffic, and more through natural language interaction.

https://github.com/user-attachments/assets/73176f92-a94d-4b66-9aa7-ee06c438a741

## Features

- **Natural Language Interaction**: Users can ask questions and give instructions to the AI assistant using natural language.
- **MCP Server Integration**: Through the `mcp.json` configuration file, multiple MCP servers can be flexibly integrated and managed to extend the assistant's capabilities.
- **Tool Management**: Configure, connect to, and manage MCP tools through an interactive menu, including the ability to clear all configurations.
- **Tool Invocation**: The AI assistant can call tools provided by configured MCP servers (such as: nmap, metasploit, ffuf, etc.) based on user requests.
- **Automated Pentesting Workflows**: Execute predefined penetration testing workflows that systematically use configured security tools to perform comprehensive assessments.
- **Report Generation**: Generate markdown reports with structured findings, evidence, and recommendations.
- **Conversation History**: Supports multi-turn dialogues, remembering previous interaction content.
- **Streaming Output**: AI responses can be streamed for a better user experience.
- **Knowledge Base Enhancement (Optional)**: Supports enhancing AI responses through a local knowledge base RAG (`knowledge` directory).
- **File-Aware Tool Integration**: AI recognizes and uses actual files from the knowledge folder (wordlists, payloads, configs) with security tools.
- **Configurable Models**: Supports configuration of different language model parameters.

## Automated Penetration Testing Workflows

PentestMCP includes automated penetration testing workflows that provide structured, systematic security assessments. These workflows require MCP tools to be configured and connected to function properly.

### Available Workflows

1. **Reconnaissance and Discovery**
   - Comprehensive information gathering and target profiling
   - Performs reconnaissance, subdomain discovery, port scanning, technology fingerprinting, and historical data analysis
   - **Steps**: 5 systematic phases

2. **Web Application Security Assessment**
   - Comprehensive web application penetration testing
   - Tests for directory traversal, SQL injection, web vulnerabilities, SSL/TLS security, authentication flaws, and file inclusion
   - **Steps**: 6 focused web security phases

3. **Network Infrastructure Penetration Test**
   - Network-focused penetration testing and exploitation
   - Includes network scanning, service enumeration, vulnerability identification, misconfiguration testing, and exploitation attempts
   - **Steps**: 6 network security phases

4. **Complete Penetration Test**
   - Full-scope penetration testing methodology
   - Comprehensive assessment covering reconnaissance, enumeration, vulnerability scanning, web testing, network exploitation, post-exploitation, and reporting
   - **Steps**: 7 complete assessment phases

### Workflow Features

- **Tool Integration**: All workflows utilize configured MCP tools (Nmap, Metasploit, Nuclei, etc.) for real security testing
- **Professional Output**: Each step provides detailed technical findings, vulnerability analysis, risk assessment, and remediation recommendations
- **Report Generation**: Automatically save reports to organized `reports/` directory with workflow-specific naming
- **Target Flexibility**: Works with IP addresses, domain names, or network ranges
- **Progress Tracking**: Real-time progress indication through each workflow step

### Usage Requirements

- **MCP Tools Required**: Automated workflows require at least one MCP security tool to be configured and connected
- **Access Control**: The system prevents workflow execution without proper tools to avoid generating simulated results
- **Professional Context**: Designed for authorized penetration testing and security assessments only

### How to Use Workflows

1. Start PentestMCP and configure MCP tools when prompted
2. Select "Automated Penetration Testing" from the main menu
3. Choose your desired workflow type
4. Enter the target (IP, domain, or network range)
5. Confirm execution and monitor progress
6. Optionally save results to file for documentation

### Startup Effect
<p align="center">
  <img width="517" alt="PentestMCP Terminal Startup Screen" src="https://github.com/user-attachments/assets/13d97cf7-5652-4c64-8e49-a3cd556b3419" />
  <br>
  <em>PentestMCP's terminal startup interface</em>
</p>

### Metasploit Tool Call
<p align="center">
  <img width="926" alt="PentestMCP Metasploit Integration" src="https://github.com/user-attachments/assets/fb5eb8cf-a3d6-486b-99ba-778be2474564" />
  <br>
  <em>Example of PentestMCP invoking Metasploit Framework</em>
</p>

## Installation Guide

1. **Clone Repository**:
   ```bash
   git clone https://github.com/GH05TCREW/PentestMCP.git
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
   If you want to use the knowledge base enhancement feature, place relevant text files (e.g., `.json`) in the `knowledge` folder.

3. **Run the Main Program**:
   ```bash
   python main.py
   ```
   After the program starts, you can:
   - Choose whether to use the knowledge base
   - Configure or activate MCP tools
   - Select between Interactive Chat Mode or Automated Penetration Testing
   - Execute workflows and generate reports
   - Use 'multi' command to enter multi-line input mode for complex queries
   - Enter 'quit' to exit the program

## Input Modes

PentestMCP supports two input modes:
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

PentestMCP supports integration with the following security tools through the MCP protocol:

1. **AlterX** - Subdomain permutation and wordlist generation tool
2. **Amass** - Advanced subdomain enumeration and reconnaissance tool
3. **Arjun** - Hidden HTTP parameters discovery tool
4. **Assetfinder** - Passive subdomain discovery tool
5. **Certificate Transparency** - SSL certificate transparency logs for subdomain discovery (no executable needed)
6. **FFUF Fuzzer** - Fast web fuzzing tool for discovering hidden content
7. **HTTPx** - Fast HTTP toolkit and port scanning tool
8. **Katana** - Fast web crawling with JavaScript parsing tool
9. **Masscan** - High-speed network port scanner
10. **Metasploit** - Penetration testing framework with exploit execution, payload generation, and session management
11. **Nmap Scanner** - Network discovery and security auditing tool
12. **Nuclei Scanner** - Template-based vulnerability scanner
13. **Scout Suite** - Cloud security auditing tool
14. **shuffledns** - High-speed DNS brute-forcing and resolution tool
15. **SQLMap** - Automated SQL injection detection and exploitation tool
16. **SSL Scanner** - Analysis tool for SSL/TLS configurations and security issues
17. **Wayback URLs** - Tool for discovering historical URLs from the Wayback Machine archive

Each tool can be configured through the interactive configuration menu by selecting "Configure new tools" from the MCP tools menu.

## Coming Soon

- BloodHound
- CrackMapExec
- Gobuster
- Hydra
- Responder
- Bettercap

## File Structure

```
agent/
├── .venv/                  # Python virtual environment (ignored by .gitignore)
├── knowledge/             # Knowledge base documents directory
│   └── ...
├── reports/               # Professional penetration test reports directory
│   ├── ghostcrew_*_*.md   # Professional markdown reports
│   └── ghostcrew_*_*_raw_history.txt  # Raw conversation history (optional)
├── .gitignore              # Git ignore file configuration
├── main.py                 # Main program entry
├── workflows.py            # Automated penetration testing workflows
├── reporting.py            # Professional report generation system
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
