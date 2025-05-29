import json
import os
import shutil
import subprocess
import platform
from pathlib import Path
from colorama import init, Fore, Style

init(autoreset=True)

def find_tool_path(tool_name):
    """Auto-discover tool path using system commands"""
    try:
        if platform.system() == "Windows":
            # Use 'where' command on Windows
            result = subprocess.run(['where', tool_name], 
                                  capture_output=True, text=True, check=False)
            if result.returncode == 0:
                # Get first valid path from results
                paths = result.stdout.strip().split('\n')
                for path in paths:
                    path = path.strip()
                    if path and os.path.exists(path):
                        return path
        else:
            # Use 'which' command on Linux/Mac
            path = shutil.which(tool_name)
            if path and os.path.exists(path):
                return path
    except Exception:
        pass
    return None

def get_tool_search_variants(exe_name):
    """Get different variants of tool names to search for"""
    if not exe_name:
        return []
    
    # For Windows, just search for the base name - 'where' will find the actual executable
    base_name = exe_name.replace('.exe', '').replace('.py', '')
    variants = [base_name]
    
    # Also try the exact name if it's different
    if exe_name != base_name:
        variants.append(exe_name)
    
    return variants

def auto_discover_tool_path(server):
    """Auto-discover tool path with user confirmation"""
    if not server.get('exe_name'):
        return None
        
    print(f"{Fore.CYAN}Searching for {server['name']}...{Style.RESET_ALL}")
    
    # Get search variants
    search_variants = get_tool_search_variants(server['exe_name'])
    
    # Try to find the tool
    found_path = None
    for variant in search_variants:
        found_path = find_tool_path(variant)
        if found_path:
            break
    
    if found_path:
        print(f"{Fore.GREEN}Found: {found_path}{Style.RESET_ALL}")
        choice = input(f"   Use this path? (yes/no): ").strip().lower()
        if choice == 'y' or choice == 'yes':
            return found_path
        # If user says no, fall through to manual input
    else:
        print(f"{Fore.YELLOW}{server['name']} not found in PATH{Style.RESET_ALL}")
    
    # Fallback to manual input
    manual_path = input(f"   Enter path to {server['exe_name']} manually (or press Enter to skip): ").strip()
    return manual_path if manual_path else None

MCP_SERVERS = [
    {
        "name": "AlterX",
        "key": "AlterX",
        "command": "npx",
        "args": ["-y", "gc-alterx-mcp"],
        "description": "MCP server for subdomain permutation and wordlist generation using the AlterX tool.",
        "exe_name": "alterx.exe",
        "env_var": "ALTERX_PATH",
        "homepage": "https://www.npmjs.com/package/gc-alterx-mcp"
    },
    {
        "name": "Amass",
        "key": "Amass",
        "command": "npx",
        "args": ["-y", "gc-amass-mcp"],
        "description": "MCP server for advanced subdomain enumeration and reconnaissance using the Amass tool.",
        "exe_name": "amass.exe",
        "env_var": "AMASS_PATH",
        "homepage": "https://www.npmjs.com/package/gc-amass-mcp"
    },
    {
        "name": "Arjun",
        "key": "Arjun",
        "command": "npx",
        "args": ["-y", "gc-arjun-mcp"],
        "description": "MCP server for discovering hidden HTTP parameters using the Arjun tool.",
        "exe_name": "arjun",
        "env_var": "ARJUN_PATH",
        "homepage": "https://www.npmjs.com/package/gc-arjun-mcp"
    },
    {
        "name": "Assetfinder",
        "key": "Assetfinder",
        "command": "npx",
        "args": ["-y", "gc-assetfinder-mcp"],
        "description": "MCP server for passive subdomain discovery using the Assetfinder tool.",
        "exe_name": "assetfinder.exe",
        "env_var": "ASSETFINDER_PATH",
        "homepage": "https://www.npmjs.com/package/gc-assetfinder-mcp"
    },
    {
        "name": "Certificate Transparency",
        "key": "CrtSh",
        "command": "npx",
        "args": ["-y", "gc-crtsh-mcp"],
        "description": "MCP server for subdomain discovery using SSL certificate transparency logs (crt.sh).",
        "exe_name": None,  # No executable needed for this service
        "env_var": None,
        "homepage": "https://www.npmjs.com/package/gc-crtsh-mcp"
    },
    {
        "name": "FFUF Fuzzer",
        "key": "FFUF",
        "command": "npx",
        "args": ["-y", "gc-ffuf-mcp"],
        "description": "MCP server for web fuzzing operations using FFUF (Fuzz Faster U Fool) tool.",
        "exe_name": "ffuf.exe",
        "env_var": "FFUF_PATH",
        "homepage": "https://www.npmjs.com/package/gc-ffuf-mcp"
    },
    {
        "name": "httpx",
        "key": "HTTPx",
        "command": "npx",
        "args": ["-y", "gc-httpx-mcp"],
        "description": "MCP server for fast HTTP toolkit and port scanning using the httpx tool.",
        "exe_name": "httpx.exe",
        "env_var": "HTTPX_PATH",
        "homepage": "https://www.npmjs.com/package/gc-httpx-mcp"
    },
    {
        "name": "Katana",
        "key": "Katana",
        "command": "npx",
        "args": ["-y", "gc-katana-mcp"],
        "description": "MCP server for fast web crawling with JavaScript parsing using the Katana tool.",
        "exe_name": "katana.exe",
        "env_var": "KATANA_PATH",
        "homepage": "https://www.npmjs.com/package/gc-katana-mcp"
    },
    {
        "name": "Masscan",
        "key": "Masscan",
        "command": "npx",
        "args": ["-y", "gc-masscan-mcp"],
        "description": "MCP server for high-speed network port scanning with the Masscan tool.",
        "exe_name": "masscan.exe",
        "env_var": "MASSCAN_PATH",
        "homepage": "https://www.npmjs.com/package/gc-masscan-mcp"
    },
    {
        "name": "Metasploit",
        "key": "MetasploitMCP",
        "command": "uvx",
        "args": ["gc-metasploit", "--transport", "stdio"],
        "description": "MCP server for Metasploit Framework with exploit execution, payload generation, and session management.",
        "exe_name": None,  # No local executable needed - uses uvx package
        "env_var": "MSF_PASSWORD",
        "env_extra": {
            "MSF_SERVER": "127.0.0.1",
            "MSF_PORT": "55553",
            "MSF_SSL": "false",
            "PAYLOAD_SAVE_DIR": ""
        },
        "homepage": "https://github.com/GH05TCREW/MetasploitMCP"
    },
    {
        "name": "Nmap Scanner",
        "key": "Nmap",
        "command": "npx",
        "args": ["-y", "gc-nmap-mcp"],
        "description": "MCP server for interacting with Nmap network scanner to discover hosts and services on a network.",
        "exe_name": "nmap.exe",
        "env_var": "NMAP_PATH",
        "homepage": "https://www.npmjs.com/package/gc-nmap-mcp"
    },
    {
        "name": "Nuclei Scanner",
        "key": "Nuclei",
        "command": "npx",
        "args": ["-y", "gc-nuclei-mcp"],
        "description": "MCP server for vulnerability scanning using Nuclei's template-based detection engine.",
        "exe_name": "nuclei.exe",
        "env_var": "NUCLEI_PATH",
        "homepage": "https://www.npmjs.com/package/gc-nuclei-mcp"
    },
    {
        "name": "Scout Suite",
        "key": "ScoutSuite",
        "command": "npx",
        "args": ["-y", "gc-scoutsuite-mcp"],
        "description": "MCP server for cloud security auditing using the Scout Suite tool.",
        "exe_name": "scout.py",
        "env_var": "SCOUTSUITE_PATH",
        "homepage": "https://www.npmjs.com/package/gc-scoutsuite-mcp"
    },
    {
        "name": "shuffledns",
        "key": "ShuffleDNS",
        "command": "npx",
        "args": ["-y", "gc-shuffledns-mcp"],
        "description": "MCP server for high-speed DNS brute-forcing and resolution using the shuffledns tool.",
        "exe_name": "shuffledns",
        "env_var": "SHUFFLEDNS_PATH",
        "env_extra": {
            "MASSDNS_PATH": ""
        },
        "homepage": "https://www.npmjs.com/package/gc-shuffledns-mcp"
    },
    {
        "name": "SQLMap",
        "key": "SQLMap",
        "command": "npx",
        "args": ["-y", "gc-sqlmap-mcp"],
        "description": "MCP server for conducting automated SQL injection detection and exploitation using SQLMap.",
        "exe_name": "sqlmap.py",
        "env_var": "SQLMAP_PATH",
        "homepage": "https://www.npmjs.com/package/gc-sqlmap-mcp"
    },
    {
        "name": "SSL Scanner",
        "key": "SSLScan",
        "command": "npx",
        "args": ["-y", "gc-sslscan-mcp"],
        "description": "MCP server for analyzing SSL/TLS configurations and identifying security issues.",
        "exe_name": "sslscan.exe",
        "env_var": "SSLSCAN_PATH",
        "homepage": "https://www.npmjs.com/package/gc-sslscan-mcp"
    },
    {
        "name": "Wayback URLs",
        "key": "WaybackURLs",
        "command": "npx",
        "args": ["-y", "gc-waybackurls-mcp"],
        "description": "MCP server for discovering historical URLs from the Wayback Machine archive.",
        "exe_name": "waybackurls.exe",
        "env_var": "WAYBACKURLS_PATH",
        "homepage": "https://www.npmjs.com/package/gc-waybackurls-mcp"
    }
]



def check_npm_installed():
    """Check if npm is installed"""
    try:
        result = shutil.which("npm")
        return result is not None
    except:
        return False

def main():
    print(f"{Fore.GREEN}===================== GHOSTCREW MCP SERVER CONFIGURATION ====================={Style.RESET_ALL}")
    print(f"{Fore.YELLOW}This tool will help you configure the MCP servers for your GHOSTCREW installation.{Style.RESET_ALL}")
    print(f"{Fore.CYAN}Auto-discovery will attempt to find tools automatically in your system PATH.{Style.RESET_ALL}")
    print(f"{Fore.CYAN}You can confirm, decline, or provide custom paths as needed.{Style.RESET_ALL}")
    print()
    
    # Check if npm is installed
    if not check_npm_installed():
        print(f"{Fore.RED}Warning: npm doesn't appear to be installed. MCP servers use Node.js and npm.{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}You may need to install Node.js from: https://nodejs.org/{Style.RESET_ALL}")
        cont = input(f"{Fore.YELLOW}Continue anyway? (yes/no): {Style.RESET_ALL}").strip().lower()
        if cont != "yes":
            print(f"{Fore.RED}Configuration cancelled.{Style.RESET_ALL}")
            return
    
    # Check if mcp.json exists and load it
    mcp_config = {"servers": []}
    if os.path.exists("mcp.json"):
        try:
            with open("mcp.json", 'r') as f:
                mcp_config = json.load(f)
                print(f"{Fore.GREEN}Loaded existing mcp.json with {len(mcp_config.get('servers', []))} server configurations.{Style.RESET_ALL}")
        except:
            print(f"{Fore.RED}Error loading existing mcp.json. Starting with empty configuration.{Style.RESET_ALL}")
    
    configured_servers = []
    
    print(f"{Fore.CYAN}Available tools:{Style.RESET_ALL}")
    for i, server in enumerate(MCP_SERVERS):
        print(f"{i+1}. {server['name']} - {server['description']}")
    
    print()
    print(f"{Fore.YELLOW}Select tools to configure (comma-separated numbers, 'all' for all tools, or 'none' to skip):{Style.RESET_ALL}")
    selection = input().strip().lower()
    
    selected_indices = []
    if selection == "all":
        selected_indices = list(range(len(MCP_SERVERS)))
    elif selection != "none":
        try:
            for part in selection.split(","):
                idx = int(part.strip()) - 1
                if 0 <= idx < len(MCP_SERVERS):
                    selected_indices.append(idx)
        except:
            print(f"{Fore.RED}Invalid selection. Please enter comma-separated numbers.{Style.RESET_ALL}")
            return
    
    for idx in selected_indices:
        server = MCP_SERVERS[idx]
        print(f"\n{Fore.CYAN}Configuring {server['name']}:{Style.RESET_ALL}")
        
        # Unified tool configuration - handles all tools generically
        env_vars = {}
        
        # Handle main executable and environment variable
        if server.get('exe_name'):
            # Try to auto-discover the executable
            exe_path = auto_discover_tool_path(server)
            
            if exe_path:
                # Verify the path exists
                if not os.path.exists(exe_path):
                    print(f"{Fore.YELLOW}Warning: The specified path does not exist: {exe_path}{Style.RESET_ALL}")
                    cont = input(f"   Continue anyway? (yes/no, default: no): ").strip().lower()
                    if cont != "yes":
                        print(f"   {Fore.YELLOW}Skipping {server['name']}.{Style.RESET_ALL}")
                        continue
                
                # Set the main environment variable
                if server.get('env_var'):
                    env_vars[server['env_var']] = exe_path
            else:
                # Executable not found and user didn't provide manual path
                print(f"{Fore.YELLOW}Skipping {server['name']} - executable not found.{Style.RESET_ALL}")
                continue
        elif server.get('env_var'):
            # Tool has no executable but needs a main environment variable (like Metasploit)
            value = input(f"Enter value for {server['env_var']} (default: ): ").strip()
            
            if value:
                env_vars[server['env_var']] = value
            else:
                print(f"{Fore.YELLOW}Skipping {server['name']} - {server['env_var']} required.{Style.RESET_ALL}")
                continue
        else:
            # Tool requires no executable (like Certificate Transparency)
            print(f"{Fore.GREEN}{server['name']} requires no local executable.{Style.RESET_ALL}")
        
        # Handle additional environment variables
        if 'env_extra' in server:
            for extra_var, default_value in server['env_extra'].items():
                if extra_var == "MASSDNS_PATH":
                    # Special auto-discovery for massdns
                    print(f"\n{Fore.CYAN}Also configuring massdns for {server['name']}...{Style.RESET_ALL}")
                    print(f"{Fore.CYAN}Searching for massdns...{Style.RESET_ALL}")
                    
                    massdns_path = find_tool_path("massdns")
                    if massdns_path:
                        print(f"{Fore.GREEN}Found: {massdns_path}{Style.RESET_ALL}")
                        choice = input(f"   Use this path? (yes/no): ").strip().lower()
                        if choice != 'y' and choice != 'yes':
                            massdns_path = input(f"   Enter path to massdns manually: ").strip()
                    else:
                        print(f"{Fore.YELLOW}massdns not found in PATH{Style.RESET_ALL}")
                        massdns_path = input(f"   Enter path to massdns manually (or press Enter to skip): ").strip()
                    
                    if massdns_path:
                        env_vars[extra_var] = massdns_path
                    else:
                        print(f"{Fore.YELLOW}Skipping {server['name']} - massdns path required.{Style.RESET_ALL}")
                        continue
                else:
                    # Handle all environment variables generically
                    value = input(f"Enter value for {extra_var} (default: {default_value}): ").strip()
                    env_vars[extra_var] = value if value else default_value
        
        # Add to configured servers
        configured_servers.append({
            "name": server['name'],
            "params": {
                "command": server['command'],
                "args": server['args'],
                "env": env_vars
            },
            "cache_tools_list": True
        })
        print(f"{Fore.GREEN}{server['name']} configured successfully!{Style.RESET_ALL}")
    
    # Update mcp.json
    if "servers" not in mcp_config:
        mcp_config["servers"] = []
    
    if configured_servers:
        # Ask if user wants to replace or append
        if mcp_config["servers"]:
            replace = input(f"{Fore.YELLOW}Replace existing configurations or append new ones? (replace/append, default: append): {Style.RESET_ALL}").strip().lower()
            if replace == "replace":
                mcp_config["servers"] = configured_servers
            else:
                # Remove any duplicates by name
                existing_names = [s["name"] for s in mcp_config["servers"]]
                for server in configured_servers:
                    if server["name"] in existing_names:
                        # Replace existing configuration
                        idx = existing_names.index(server["name"])
                        mcp_config["servers"][idx] = server
                    else:
                        # Add new configuration
                        mcp_config["servers"].append(server)
        else:
            mcp_config["servers"] = configured_servers
        
        # Save to mcp.json
        with open("mcp.json", 'w') as f:
            json.dump(mcp_config, f, indent=2)
        
        print(f"\n{Fore.GREEN}Configuration saved to mcp.json with {len(mcp_config['servers'])} server configurations.{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}You can now run the main application with: python main.py{Style.RESET_ALL}")
    else:
        print(f"\n{Fore.YELLOW}No tools were configured. Keeping existing configuration.{Style.RESET_ALL}")

if __name__ == "__main__":
    main() 