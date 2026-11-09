"""
Antigravity Pool Account Switcher - MCP Server for Antigravity CLI
Connects Antigravity CLI directly to Antigravity Tools / Antigravity Manager
Executable: D:\\PooL_quota\\Antigravity Tools\\antigravity-server.exe
"""

import subprocess
from pathlib import Path
from mcp.server.mcpserver import MCPServer

ANTIGRAVITY_SERVER_BIN = Path(r"D:\PooL_quota\Antigravity Tools\antigravity-server.exe")

server = MCPServer(
    name="antigravity-pool",
    version="1.0.0",
    description="MCP Server to monitor, query, and switch Google/Antigravity accounts via Antigravity Tools"
)

def _run_server_cmd(*args: str) -> str:
    """Helper to run command against antigravity-server.exe"""
    if not ANTIGRAVITY_SERVER_BIN.exists():
        return f"Error: Binary not found at {ANTIGRAVITY_SERVER_BIN}"
    
    cmd = [str(ANTIGRAVITY_SERVER_BIN)] + list(args)
    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10
        )
        return res.stdout.strip() if res.stdout else res.stderr.strip()
    except Exception as e:
        return f"Exception executing command {cmd}: {str(e)}"

@server.tool()
def get_current_account() -> str:
    """
    Get the currently active account for Antigravity CLI (agy).
    Returns the email and surface status.
    """
    out = _run_server_cmd("current")
    return out

@server.tool()
def list_accounts() -> str:
    """
    List all Google/Antigravity accounts available in the Antigravity Tools pool.
    Shows index, email, alias (e.g. Cậu Vàng, Paul Sean), and health status.
    """
    out = _run_server_cmd("list")
    return out

@server.tool()
def switch_account(target: str) -> str:
    """
    Switch Antigravity CLI to a specific account by index or email.
    Args:
        target: Account index (e.g. '1', '2') or email (e.g. 'seanpaul1402@gmail.com').
    """
    out = _run_server_cmd("switch", str(target).strip())
    return out

@server.tool()
def rotate_next_account() -> str:
    """
    Automatically rotate Antigravity CLI to the next available account in the pool.
    Useful when encountering quota limits (429 / resource exhausted).
    """
    out = _run_server_cmd("switch")
    return out

if __name__ == "__main__":
    server.run(transport="stdio")
