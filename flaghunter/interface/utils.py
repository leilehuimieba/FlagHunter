"""Interface utilities for FlagHunter."""

from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..config.constants import APP_VERSION

console = Console()


# ASCII Art Banner
ASCII_BANNER = r"""
             ('-. .-.               .-')    .-') _            _  .-')     ('-.    (`\ .-') /`
            ( OO )  /              ( OO ). (  OO) )          ( \( -O )  _(  OO)    `.( OO ),'
  ,----.    ,--. ,--. .-'),-----. (_)---\_)/     '._  .-----. ,------. (,------.,--./  .--.
 '  .-./-') |  | |  |( OO'  .-.  '/    _ | |'--...__)'  .--./ |   /`. ' |  .---'|      |  |
 |  |_( O- )|   .|  |/   |  | |  |\  :` `. '--.  .--'|  |('-. |  /  | | |  |    |  |   |  |,
 |  | .--, \|       |\_) |  |\|  | '..`''.)   |  |  /_) |OO  )|  |_.' |(|  '--. |  |.'.|  |_)
(|  | '. (_/|  .-.  |  \ |  | |  |.-._)   \   |  |  ||  |`-'| |  .  '.' |  .--' |         |
 |  '--'  | |  | |  |   `'  '-'  '\       /   |  | (_'  '--'\ |  |\  \  |  `---.|   ,'.   |
  `------'  `--' `--'     `-----'  `-----'    `--'    `-----' `--' '--' `------''--'   '--'
"""


def print_banner():
    """Print the FlagHunter banner."""
    console.print(f"[bold white]{ASCII_BANNER}[/]")
    console.print(
        "[bold white]====================== FLAGHUNTER =======================[/]"
    )
    console.print(
        f"[dim white]        AI Penetration Testing Agents  v{APP_VERSION}[/dim white]\n"
    )


def format_finding(
    title: str,
    severity: str,
    target: str,
    description: str,
    evidence: str = "",
    impact: str = "",
    remediation: str = "",
) -> Panel:
    """
    Format a security finding for display.

    Args:
        title: Finding title
        severity: Severity level
        target: Affected target
        description: Description of the finding
        evidence: Proof/evidence
        impact: Potential impact
        remediation: How to fix

    Returns:
        Rich Panel with formatted finding
    """
    severity_colors = {
        "critical": "red bold",
        "high": "red",
        "medium": "yellow",
        "low": "blue",
        "informational": "dim",
    }

    color = severity_colors.get(severity.lower(), "white")

    content = f"""
[bold]Target:[/] {target}
[{color}]Severity:[/{color}] [{color}]{severity.upper()}[/{color}]

[bold]Description:[/]
{description}
"""

    if evidence:
        content += f"\n[bold]Evidence:[/]\n{evidence}\n"

    if impact:
        content += f"\n[bold]Impact:[/]\n{impact}\n"

    if remediation:
        content += f"\n[bold]Remediation:[/]\n{remediation}\n"

    return Panel(content, title=f"[bold]{title}[/]", border_style=color)


def print_status(
    target: Optional[str] = None,
    scope: Optional[list] = None,
    agent_state: str = "idle",
    tools_count: int = 0,
    findings_count: int = 0,
):
    """
    Print current status information.

    Args:
        target: Current target
        scope: Current scope
        agent_state: Agent state
        tools_count: Number of loaded tools
        findings_count: Number of findings
    """
    table = Table(title="FlagHunter Status", show_header=False)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Target", target or "Not set")
    table.add_row("Scope", ", ".join(scope) if scope else "Not set")
    table.add_row("Agent State", agent_state)
    table.add_row("Tools Loaded", str(tools_count))
    table.add_row("Findings", str(findings_count))

    console.print(table)
