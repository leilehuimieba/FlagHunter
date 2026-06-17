"""angr symbolic execution solver for CTF reverse engineering."""

from __future__ import annotations

import json
import shlex
from typing import TYPE_CHECKING

from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime


_REMOTE_SCRIPT = '''
import sys, json, os, traceback

def solve(binary_path, find_addrs, avoid_addrs, input_length, input_prefix, start_addr, stdin_mode, arg_mode):
    try:
        import angr
        import claripy
    except ImportError:
        return {"success": False, "error": "angr/claripy not installed. Install: pip3 install angr claripy"}

    if not os.path.exists(binary_path):
        return {"success": False, "error": f"Binary not found: {binary_path}"}

    try:
        proj = angr.Project(binary_path, auto_load_libs=False)
    except Exception as ex:
        return {"success": False, "error": f"Failed to load binary: {ex}"}

    try:
        # Build symbolic input
        prefix_bytes = input_prefix.encode() if isinstance(input_prefix, str) else b""
        sym_len = input_length - len(prefix_bytes)
        if sym_len < 0:
            sym_len = 0

        sym_data = claripy.BVS("input", 8 * sym_len) if sym_len > 0 else claripy.BVV(b"")

        # Create initial state
        kwargs = {}
        extra_options = {
            angr.options.ZERO_FILL_UNCONSTRAINED_MEMORY,
            angr.options.ZERO_FILL_UNCONSTRAINED_REGISTERS,
        }

        if stdin_mode and sym_len > 0:
            kwargs["stdin"] = angr.SimFileStream(name="stdin", content=sym_data, has_end=False)
        if arg_mode and sym_len > 0:
            if prefix_bytes:
                full_input = claripy.Concat(claripy.BVV(prefix_bytes), sym_data)
            else:
                full_input = sym_data
            kwargs["args"] = [binary_path, full_input]

        if start_addr:
            state = proj.factory.blank_state(addr=start_addr, add_options=extra_options, **kwargs)
        else:
            state = proj.factory.entry_state(add_options=extra_options, **kwargs)

        # Add printable constraints (must be added to the state solver)
        if sym_len > 0:
            for i in range(sym_len):
                byte = sym_data.get_byte(i)
                state.solver.add(
                    claripy.Or(byte == 10, claripy.And(byte >= 0x20, byte <= 0x7e))
                )

        simgr = proj.factory.simulation_manager(state)

        # Apply exploration techniques (safe fallback if CFG fails)
        try:
            simgr.use_technique(angr.exploration_techniques.LoopSeer(bound=3))
        except Exception:
            pass  # CFG may fail on complex binaries; proceed without LoopSeer

        # Convert addresses
        find = [int(a, 0) for a in find_addrs] if find_addrs else []
        avoid = [int(a, 0) for a in avoid_addrs] if avoid_addrs else []

        # Explore
        simgr.explore(find=find, avoid=avoid)

        if simgr.found:
            found_state = simgr.found[0]
            # Extract solution
            if sym_len > 0:
                sol_bytes = found_state.solver.eval(sym_data, cast_to=bytes)
                result = prefix_bytes + sol_bytes
            else:
                result = prefix_bytes

            # Also dump stdout if available
            stdout = ""
            try:
                stdout_bytes = found_state.posix.dumps(1)
                stdout = stdout_bytes.decode("utf-8", "replace")
            except:
                pass

            return {
                "success": True,
                "solution_hex": result.hex(),
                "solution_bytes": result.decode("utf-8", "replace"),
                "stdout": stdout,
                "found_at": hex(found_state.addr),
            }
        else:
            # Try to provide diagnostics
            deadended = len(simgr.deadended) if hasattr(simgr, "deadended") else 0
            return {
                "success": False,
                "error": f"No path found. Deadended states: {deadended}. Try adjusting find/avoid addresses or increasing input_length.",
                "deadended": deadended,
            }
    except Exception as ex:
        return {"success": False, "error": str(ex), "traceback": traceback.format_exc()}

if __name__ == "__main__":
    args = json.loads(sys.argv[1])
    result = solve(
        binary_path=args["binary_path"],
        find_addrs=args.get("find_addrs", []),
        avoid_addrs=args.get("avoid_addrs", []),
        input_length=args.get("input_length", 32),
        input_prefix=args.get("input_prefix", ""),
        start_addr=args.get("start_addr", ""),
        stdin_mode=args.get("stdin_mode", True),
        arg_mode=args.get("arg_mode", False),
    )
    print(json.dumps(result, ensure_ascii=False))
'''


async def _run_angr_on_runtime(
    runtime: "Runtime",
    binary_path: str,
    find_addrs: list[str],
    avoid_addrs: list[str],
    input_length: int,
    input_prefix: str,
    start_addr: str,
    stdin_mode: bool,
    arg_mode: bool,
    timeout: int = 120,
) -> dict:
    """Generate remote angr script and execute via runtime."""
    import base64
    import tempfile
    from pathlib import Path
    from uuid import uuid4

    remote_base = f"/tmp/flaghunter_angr_{uuid4().hex}"
    remote_script = f"{remote_base}/solve.py"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(_REMOTE_SCRIPT)
        local_path = Path(f.name)

    try:
        await runtime.execute_command(f"mkdir -p {shlex.quote(remote_base)}", timeout=10)

        if hasattr(runtime, "copy_to_container"):
            await runtime.copy_to_container(local_path, remote_script)
        else:
            content = local_path.read_bytes()
            b64 = base64.b64encode(content).decode()
            await runtime.execute_command(
                f"echo {shlex.quote(b64)} | base64 -d > {shlex.quote(remote_script)}",
                timeout=10,
            )

        args = {
            "binary_path": binary_path,
            "find_addrs": find_addrs,
            "avoid_addrs": avoid_addrs,
            "input_length": input_length,
            "input_prefix": input_prefix,
            "start_addr": start_addr,
            "stdin_mode": stdin_mode,
            "arg_mode": arg_mode,
        }
        args_json = json.dumps(args, ensure_ascii=False)
        venv_python = "$HOME/ctf-tools/bin/python3"
        cmd = (
            f"cd {shlex.quote(remote_base)} && "
            f"({venv_python} {shlex.quote('solve.py')} {shlex.quote(args_json)} 2>/dev/null || "
            f"python3 {shlex.quote('solve.py')} {shlex.quote(args_json)})"
        )
        result = await runtime.execute_command(cmd, timeout=timeout)

        stdout = result.stdout or ""
        for line in reversed(stdout.strip().splitlines()):
            line = line.strip()
            if line:
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return {"success": False, "error": f"No JSON output. stdout:\n{stdout}\nstderr:\n{result.stderr or ''}"}
    finally:
        try:
            await runtime.execute_command(f"rm -rf {shlex.quote(remote_base)}", timeout=10)
        except Exception:
            pass


@register_tool(
    name="angr_solve",
    description=(
        "Use angr symbolic execution to automatically solve CTF reverse engineering challenges. "
        "Finds an input that reaches a target address while avoiding forbidden addresses. "
        "Best for: crackme, keygen, VM challenges with clear success/failure paths. "
        "Requires angr installed on the target runtime (Kali VM)."
    ),
    schema=ToolSchema(
        properties={
            "binary_path": {
                "type": "string",
                "description": "Absolute path to binary on remote system",
            },
            "find_addrs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Hex addresses to reach (e.g., ['0x401234', '0x401250']). At least one must be reached. NOTE: For PIE binaries use virtual addresses (angr default base for 64-bit PIE is 0x400000 + file offset).",
            },
            "avoid_addrs": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Hex addresses to avoid (e.g., ['0x401000'] for failure path)",
                "default": [],
            },
            "input_length": {
                "type": "integer",
                "description": "Total input length in bytes (default: 32)",
                "default": 32,
            },
            "input_prefix": {
                "type": "string",
                "description": "Known prefix of input (e.g., 'flag{'). This part is fixed, only remaining bytes are symbolic.",
                "default": "",
            },
            "start_addr": {
                "type": "string",
                "description": "Optional start address. Empty = entry point.",
                "default": "",
            },
            "stdin_mode": {
                "type": "boolean",
                "description": "Feed input via stdin (default: True)",
                "default": True,
            },
            "arg_mode": {
                "type": "boolean",
                "description": "Feed input via argv[1] (default: False)",
                "default": False,
            },
            "timeout": {
                "type": "integer",
                "description": "Execution timeout in seconds (default: 120)",
                "default": 120,
            },
        },
        required=["binary_path", "find_addrs"],
    ),
    category="ctf",
)
async def angr_solve(arguments: dict, runtime: "Runtime") -> str:
    result = await _run_angr_on_runtime(
        runtime=runtime,
        binary_path=arguments["binary_path"],
        find_addrs=arguments.get("find_addrs", []),
        avoid_addrs=arguments.get("avoid_addrs", []),
        input_length=arguments.get("input_length", 32),
        input_prefix=arguments.get("input_prefix", ""),
        start_addr=arguments.get("start_addr", ""),
        stdin_mode=arguments.get("stdin_mode", True),
        arg_mode=arguments.get("arg_mode", False),
        timeout=arguments.get("timeout", 120),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)
