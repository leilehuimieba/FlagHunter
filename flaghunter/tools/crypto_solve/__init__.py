"""CTF cryptography solver — delegates to Python libraries on the runtime."""

from __future__ import annotations

import base64
import json
import shlex
import textwrap
from typing import TYPE_CHECKING

from ..registry import ToolSchema, register_tool

if TYPE_CHECKING:
    from ...runtime import Runtime


# ---------------------------------------------------------------------------
# Remote script template (executed on Kali via SSHRuntime)
# ---------------------------------------------------------------------------
_REMOTE_SCRIPT = '''
import sys, json, base64, binascii, math, itertools, string, re
from collections import Counter

def rsa_small_e(c, e, n):
    m = round(c ** (1.0 / e))
    if pow(m, e, n) == c:
        return {"success": True, "plaintext_int": m, "plaintext_hex": hex(m), "plaintext_bytes": m.to_bytes((m.bit_length()+7)//8, "big").hex()}
    return {"success": False, "error": "Cube root did not yield valid plaintext"}

def rsa_wiener(e, n):
    try:
        import owiener
        d = owiener.attack(e, n)
        if d:
            return {"success": True, "d": d, "d_hex": hex(d)}
        return {"success": False, "error": "Wiener attack failed — d may not be small enough"}
    except ImportError:
        return {"success": False, "error": "owiener not installed"}

def rsa_common_modulus(c1, c2, e1, e2, n):
    def egcd(a, b):
        if a == 0: return (b, 0, 1)
        g, x1, y1 = egcd(b % a, a)
        return (g, y1 - (b // a) * x1, x1)
    _, s, t = egcd(e1, e2)
    if s < 0:
        c1 = pow(c1, -1, n)
        s = -s
    if t < 0:
        c2 = pow(c2, -1, n)
        t = -t
    m = (pow(c1, s, n) * pow(c2, t, n)) % n
    return {"success": True, "plaintext_int": m, "plaintext_bytes": m.to_bytes((m.bit_length()+7)//8, "big").hex()}

def rsa_hastad(cts, mods, e):
    from functools import reduce
    def crt(rems, mods):
        prod = reduce(lambda a, b: a*b, mods)
        total = 0
        for r, m in zip(rems, mods):
            p = prod // m
            total += r * pow(p, -1, m) * p
        return total % prod
    c = crt(cts, mods)
    m = round(c ** (1.0 / e))
    return {"success": True, "plaintext_int": m, "plaintext_bytes": m.to_bytes((m.bit_length()+7)//8, "big").hex()}

def base64_decode(data):
    try:
        return {"success": True, "decoded": base64.b64decode(data).decode("utf-8", "replace")}
    except Exception as ex:
        return {"success": False, "error": str(ex)}

def hex_decode(data):
    try:
        return {"success": True, "decoded": bytes.fromhex(data).decode("utf-8", "replace")}
    except Exception as ex:
        return {"success": False, "error": str(ex)}

def caesar_brute(data):
    results = []
    for shift in range(26):
        dec = "".join(chr((ord(c) - 65 - shift) % 26 + 65) if c.isupper() else chr((ord(c) - 97 - shift) % 26 + 97) if c.islower() else c for c in data)
        score = sum(1 for c in dec.upper() if c in "ETAOINSHRDLU")
        results.append({"shift": shift, "text": dec, "score": score})
    results.sort(key=lambda x: x["score"], reverse=True)
    return {"success": True, "top_results": results[:5]}

def rot13(data):
    import codecs
    return {"success": True, "decoded": codecs.encode(data, "rot_13")}

def xor_single_byte_brute(data_hex):
    data = bytes.fromhex(data_hex)
    best = []
    for key in range(256):
        dec = bytes([b ^ key for b in data])
        try:
            text = dec.decode("utf-8", "replace")
            score = sum(1 for c in text.upper() if c in string.ascii_uppercase + " ")
            best.append({"key": key, "key_hex": hex(key), "text": text, "score": score})
        except:
            pass
    best.sort(key=lambda x: x["score"], reverse=True)
    return {"success": True, "top_results": best[:5]}

def frequency_analysis(data):
    counts = Counter(c for c in data.upper() if c in string.ascii_uppercase)
    total = sum(counts.values())
    freq = {k: round(v/total*100, 2) for k, v in counts.most_common()}
    english = "ETAOINSHRDLUCUMWFGYPBVKJXQ"
    mapping = {k: english[i] for i, (k, _) in enumerate(counts.most_common())}
    return {"success": True, "frequencies": freq, "suggested_mapping": mapping}

def hash_identify(h):
    length = len(h)
    hints = []
    if length == 32: hints.append("MD5")
    if length == 40: hints.append("SHA1")
    if length == 64: hints.append("SHA256")
    if h.startswith("$2a$") or h.startswith("$2b$") or h.startswith("$2y$"): hints.append("bcrypt")
    return {"success": True, "length": length, "possible_algorithms": hints}

TASK = sys.argv[1]
PARAMS = json.loads(sys.argv[2])

TASKS = {
    "rsa_small_e": rsa_small_e,
    "rsa_wiener": rsa_wiener,
    "rsa_common_modulus": rsa_common_modulus,
    "rsa_hastad": rsa_hastad,
    "base64_decode": base64_decode,
    "hex_decode": hex_decode,
    "caesar_brute": caesar_brute,
    "rot13": rot13,
    "xor_single_byte_brute": xor_single_byte_brute,
    "frequency_analysis": frequency_analysis,
    "hash_identify": hash_identify,
}

fn = TASKS.get(TASK)
if not fn:
    print(json.dumps({"success": False, "error": f"Unknown task: {TASK}. Available: {list(TASKS.keys())}"}))
    sys.exit(1)

try:
    result = fn(**PARAMS)
    print(json.dumps(result, ensure_ascii=False))
except Exception as ex:
    print(json.dumps({"success": False, "error": str(ex)}, ensure_ascii=False))
'''


async def _run_on_runtime(
    runtime: "Runtime",
    task: str,
    params: dict,
    timeout: int = 60,
) -> dict:
    """Generate a remote Python script and execute it via the runtime."""
    import tempfile
    from pathlib import Path
    from uuid import uuid4

    remote_base = f"/tmp/flaghunter_crypto_{uuid4().hex}"
    remote_script = f"{remote_base}/solve.py"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(_REMOTE_SCRIPT)
        local_path = Path(f.name)

    try:
        await runtime.execute_command(f"mkdir -p {shlex.quote(remote_base)}", timeout=10)

        # Copy script to remote
        if hasattr(runtime, "copy_to_container"):
            await runtime.copy_to_container(local_path, remote_script)
        else:
            # Fallback: base64 encode and write via echo
            content = local_path.read_bytes()
            b64 = base64.b64encode(content).decode()
            await runtime.execute_command(
                f"mkdir -p {shlex.quote(remote_base)} && echo {shlex.quote(b64)} | base64 -d > {shlex.quote(remote_script)}",
                timeout=10,
            )

        params_json = json.dumps(params, ensure_ascii=False)
        venv_python = "$HOME/ctf-tools/bin/python3"
        cmd = (
            f"cd {shlex.quote(remote_base)} && "
            f"({venv_python} {shlex.quote('solve.py')} {shlex.quote(task)} {shlex.quote(params_json)} 2>/dev/null || "
            f"python3 {shlex.quote('solve.py')} {shlex.quote(task)} {shlex.quote(params_json)})"
        )
        result = await runtime.execute_command(cmd, timeout=timeout)

        # Parse JSON output from last line
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
    name="crypto_solve",
    description=(
        "Solve common CTF cryptography challenges using Python libraries on the target runtime. "
        "Tasks: rsa_small_e (m^e < n), rsa_wiener (small d), rsa_common_modulus, rsa_hastad (broadcast), "
        "base64_decode, hex_decode, caesar_brute, rot13, xor_single_byte_brute, frequency_analysis, hash_identify. "
        "Returns structured JSON with results or error."
    ),
    schema=ToolSchema(
        properties={
            "task": {
                "type": "string",
                "description": "Task name. Available: rsa_small_e, rsa_wiener, rsa_common_modulus, rsa_hastad, base64_decode, hex_decode, caesar_brute, rot13, xor_single_byte_brute, frequency_analysis, hash_identify",
            },
            "params": {
                "type": "object",
                "description": "Task-specific parameters. For rsa_small_e: {c, e, n}. For base64_decode: {data}. For caesar_brute: {data}. For xor_single_byte_brute: {data_hex}. See knowledge base for full parameter lists.",
            },
            "timeout": {
                "type": "integer",
                "description": "Execution timeout in seconds (default: 60)",
                "default": 60,
            },
        },
        required=["task", "params"],
    ),
    category="ctf",
)
async def crypto_solve(arguments: dict, runtime: "Runtime") -> str:
    result = await _run_on_runtime(
        runtime=runtime,
        task=arguments["task"],
        params=arguments.get("params", {}),
        timeout=arguments.get("timeout", 60),
    )
    return json.dumps(result, ensure_ascii=False, indent=2)
