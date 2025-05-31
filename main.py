#!/usr/bin/env python3
"""
GHOSTCREW - AI-driven penetration testing assistant

Main entry point for the application.
"""

import asyncio
import sys
from colorama import init

# Initialize colorama for cross-platform colored output
init(autoreset=True)

# CRITICAL: Initialize agents library BEFORE importing modules that use MCP
# This must happen before any imports that might need MCPServerStdio/MCPServerSse
from agents import set_tracing_disabled
set_tracing_disabled(True)

# Now import MCP classes after agents library is initialized
from agents.mcp import MCPServerStdio, MCPServerSse


async def main():
    """Main application entry point."""
    try:
        # Import and run the main controller
        # Now it's safe to import modules that use MCP classes
        from core.pentest_agent import PentestAgent
        
        # Create and run the application, passing MCP classes
        agent = PentestAgent(MCPServerStdio, MCPServerSse)
        await agent.run()
        
    except ImportError as e:
        print(f"Error importing required modules: {e}")
        print("Please ensure all dependencies are installed: pip install -r requirements.txt")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nApplication interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    # Run the main application
    asyncio.run(main())