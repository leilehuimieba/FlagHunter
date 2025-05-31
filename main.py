#!/usr/bin/env python3
"""
GHOSTCREW - AI-driven penetration testing assistant

"""

import asyncio
import sys
from colorama import init

init(autoreset=True)

from agents import set_tracing_disabled
set_tracing_disabled(True)

from agents.mcp import MCPServerStdio, MCPServerSse


async def main():
    """Main application entry point."""
    try:
        from core.pentest_agent import PentestAgent
        
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
    asyncio.run(main())