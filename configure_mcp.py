import json
import os
import shutil
from pathlib import Path
from colorama import init, Fore, Style

init(autoreset=True)

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
        "exe_name": "arjun.py",
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
        "exe_name": "msfconsole.exe",
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
        "exe_name": "shuffledns.exe",
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
    print(f"{Fore.YELLOW}For each tool, you'll need to provide the path to the executable.{Style.RESET_ALL}")
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
        
        # Special handling for Metasploit
        if server['key'] == "MetasploitMCP":
            print(f"{Fore.YELLOW}Metasploit requires additional configuration:{Style.RESET_ALL}")
            
            msf_password = input(f"Enter Metasploit RPC Password: ").strip()
            msf_server = input(f"Enter Metasploit RPC Server IP (default: 127.0.0.1): ").strip() or "127.0.0.1"
            msf_port = input(f"Enter Metasploit RPC Port (default: 55553): ").strip() or "55553"
            msf_ssl = input(f"Use SSL for MSF connection (yes/no, default: no): ").strip().lower()
            msf_ssl = "true" if msf_ssl == "yes" else "false"
            payload_dir = input(f"Enter path to save generated payloads: ").strip()
            
            # Add to configured servers
            configured_servers.append({
                "name": server['name'],
                "params": {
                    "command": server['command'],
                    "args": server['args'],
                    "env": {
                        "MSF_PASSWORD": msf_password,
                        "MSF_SERVER": msf_server,
                        "MSF_PORT": msf_port,
                        "MSF_SSL": msf_ssl,
                        "PAYLOAD_SAVE_DIR": payload_dir
                    }
                },
                "cache_tools_list": True
            })
            print(f"{Fore.GREEN}{server['name']} configured successfully!{Style.RESET_ALL}")
            continue
            
        # Special handling for Certificate Transparency (no executable needed)
        elif server['key'] == "CrtSh":
            print(f"{Fore.GREEN}Certificate Transparency service requires no local executable.{Style.RESET_ALL}")
            configured_servers.append({
                "name": server['name'],
                "params": {
                    "command": server['command'],
                    "args": server['args'],
                    "env": {}
                },
                "cache_tools_list": True
            })
            print(f"{Fore.GREEN}{server['name']} configured successfully!{Style.RESET_ALL}")
            continue
            
        # Special handling for shuffledns (needs both shuffledns and massdns)
        elif server['key'] == "ShuffleDNS":
            print(f"{Fore.YELLOW}shuffledns requires both shuffledns and massdns executables:{Style.RESET_ALL}")
            
            shuffledns_path = input(f"Enter path to {server['exe_name']} (or leave empty to skip): ").strip()
            if not shuffledns_path:
                print(f"{Fore.YELLOW}Skipping {server['name']}.{Style.RESET_ALL}")
                continue
                
            massdns_path = input(f"Enter path to massdns.exe: ").strip()
            
            # Configure shuffledns
            configured_servers.append({
                "name": server['name'],
                "params": {
                    "command": server['command'],
                    "args": server['args'],
                    "env": {
                        "SHUFFLEDNS_PATH": shuffledns_path,
                        "MASSDNS_PATH": massdns_path
                    }
                },
                "cache_tools_list": True
            })
            print(f"{Fore.GREEN}{server['name']} configured successfully!{Style.RESET_ALL}")
            continue
            
        # Regular tool configuration
        else:
            exe_path = input(f"Enter path to {server['exe_name']} (or leave empty to skip): ").strip()
            
            if exe_path:
                if not os.path.exists(exe_path):
                    print(f"{Fore.RED}Warning: The specified path does not exist.{Style.RESET_ALL}")
                    cont = input(f"Continue anyway? (yes/no, default: no): ").strip().lower()
                    if cont != "yes":
                        continue
                
                # Add to configured servers
                configured_servers.append({
                    "name": server['name'],
                    "params": {
                        "command": server['command'],
                        "args": server['args'],
                        "env": {
                            server['env_var']: exe_path
                        }
                    },
                    "cache_tools_list": True
                })
                print(f"{Fore.GREEN}{server['name']} configured successfully!{Style.RESET_ALL}")
            else:
                print(f"{Fore.YELLOW}Skipping {server['name']}.{Style.RESET_ALL}")
    
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