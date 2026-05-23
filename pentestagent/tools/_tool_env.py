import os
import shutil
from pathlib import Path

# 本地工具目录（Windows 宿主机常见安全工具目录）
_LOCAL_TOOL_DIRS = [
    # FlagHunter 项目内置工具
    r"D:\webstudy\FlagHunter\tools\nmap",
    r"D:\webstudy\FlagHunter\tools\sqlmap",
    r"D:\webstudy\FlagHunter\tools\gobuster",
    r"D:\webstudy\FlagHunter\tools\ffuf",
    r"D:\webstudy\FlagHunter\tools\nuclei",
    r"D:\webstudy\FlagHunter\tools\dirsearch",
    # D:\webstudy\tools 子目录（用户工具库）
    r"D:\webstudy\tools\01-资产收集\nmap",
    r"D:\webstudy\tools\01-资产收集\Naabu",
    r"D:\webstudy\tools\01-资产收集\subfinder",
    r"D:\webstudy\tools\02-Web测试与漏洞验证\sqlmap",
    r"D:\webstudy\tools\03-综合扫描与渗透\afrog",
    r"D:\webstudy\tools\99-整合工具包\Online_tools打包版\OneForAll\OneForAll",
    r"D:\webstudy\tools\03-综合扫描与渗透\xray",
    r"D:\webstudy\tools\03-综合扫描与渗透\nuclei",
    r"D:\webstudy\tools\03-综合扫描与渗透\zpscan",
    # 通用
    r"C:\Program Files\Nmap",
    r"C:\Tools",
    r"C:\Tools\radare2",
    r"C:\Tools\checksec",
]

_DISCOVERED_TOOL_DIRS: list[str] = []
_WINDOWS_TOOL_SUFFIXES = (".exe", ".bat", ".cmd", ".ps1", ".py")
_TOOL_ALIASES = {
    "r2": ["radare2"],
    "checksec": ["checksec.sh"],
    "readelf": ["readelf"],
    "zpscan": ["zpscan_windows"],
    "xpoc": ["xpoc_windows_amd64"],
}

CTF_TOOL_INSTALL_HINTS: dict[str, str] = {
    "sqlmap": "pip install sqlmap  或  apt install sqlmap",
    "ffuf": "go install github.com/ffuf/ffuf/v2@latest  或  apt install ffuf",
    "gobuster": "go install github.com/OJ/gobuster/v3@latest  或  apt install gobuster",
    "nuclei": "go install github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest",
    "dirsearch": "pip install dirsearch  或  apt install dirsearch",
    "hydra": "apt install hydra",
    "john": "apt install john",
    "hashcat": "apt install hashcat",
    "radare2": "apt install radare2  或  winget install radare2",
    "checksec": "pip install checksec  或  apt install checksec",
    "pwntools": "pip install pwntools",
    "gdb": "apt install gdb  &&  pip install pwndbg",
    "wireshark": "apt install wireshark  或  winget install wireshark",
    "binwalk": "pip install binwalk  或  apt install binwalk",
    "steghide": "apt install steghide",
    "exiftool": "apt install exiftool  或  winget install exiftool",
    "foremost": "apt install foremost",
    "stegsolve": "wget https://github.com/zardus/ctf-tools/raw/master/stegsolve/install",
    "msf": (
        "apt install metasploit-framework  或  "
        "curl https://raw.githubusercontent.com/rapid7/metasploit-omnibus/master/"
        "config/templates/metasploit-framework-wrappers/msfupdate.erb > msfinstall"
    ),
    "wfuzz": "pip install wfuzz  或  apt install wfuzz",
    "feroxbuster": "cargo install feroxbuster  或  apt install feroxbuster",
}

CTF_TOOL_SIZES_MB: dict[str, int] = {
    "sqlmap": 10,
    "ffuf": 15,
    "gobuster": 12,
    "nuclei": 60,
    "dirsearch": 5,
    "hydra": 20,
    "john": 50,
    "hashcat": 200,
    "radare2": 150,
    "checksec": 2,
    "pwntools": 30,
    "gdb": 80,
    "wireshark": 200,
    "binwalk": 15,
    "steghide": 5,
    "exiftool": 10,
    "foremost": 8,
    "msf": 1800,
    "wfuzz": 10,
    "feroxbuster": 12,
}


def patch_tool_path() -> None:
    """把本地工具目录注入当前进程 PATH（幂等，重复调用安全）。"""
    current = os.environ.get("PATH", "")
    additions = []
    for d in [*_LOCAL_TOOL_DIRS, *_DISCOVERED_TOOL_DIRS]:
        if Path(d).is_dir() and d not in current:
            additions.append(d)
    if additions:
        os.environ["PATH"] = os.pathsep.join(additions) + os.pathsep + current


def suggest_missing_tool(tool_name: str) -> str:
    """返回工具安装建议，针对常见 CTF 工具。"""
    hint = CTF_TOOL_INSTALL_HINTS.get(str(tool_name).lower(), "")
    if hint:
        return f"Tool '{tool_name}' not found. Install: {hint}"
    return (
        f"Tool '{tool_name}' not found. Check your PATH or install manually."
    )


def check_disk_space(path: str = ".") -> dict:
    """检查指定路径所在磁盘的可用空间。"""
    usage = shutil.disk_usage(path)
    return {
        "total_gb": round(usage.total / 1024**3, 1),
        "used_gb": round(usage.used / 1024**3, 1),
        "free_gb": round(usage.free / 1024**3, 1),
        "free_pct": round(usage.free / usage.total * 100, 1),
    }


def get_tool_install_info(tool_name: str) -> dict:
    """返回工具的安装提示和预估大小。"""
    hint = suggest_missing_tool(tool_name)
    size_mb = CTF_TOOL_SIZES_MB.get(tool_name.lower(), 0)
    return {
        "tool": tool_name,
        "install_hint": hint,
        "estimated_mb": size_mb,
        "estimated_display": f"{size_mb} MB" if size_mb else "unknown",
    }


def _tool_candidates(name: str) -> list[str]:
    base = Path(name).name
    lowered = base.lower()
    candidates = [base]
    for suffix in _WINDOWS_TOOL_SUFFIXES:
        if lowered.endswith(suffix):
            continue
        candidates.append(f"{base}{suffix}")
    return candidates


def _discover_tool(name: str) -> str | None:
    for base_dir in _LOCAL_TOOL_DIRS:
        root = Path(base_dir)
        if not root.is_dir():
            continue

        for candidate in _tool_candidates(name):
            for match in root.rglob(candidate):
                if not match.is_file():
                    continue

                tool_dir = str(match.parent)
                if tool_dir not in _DISCOVERED_TOOL_DIRS:
                    _DISCOVERED_TOOL_DIRS.append(tool_dir)
                patch_tool_path()
                return str(match)
    return None


def find_tool(name: str) -> str | None:
    """在 PATH（含注入目录）中查找工具，返回完整路径或 None。"""
    import shutil

    patch_tool_path()
    direct = shutil.which(name)
    if direct:
        return direct

    for candidate in _tool_candidates(name):
        found = shutil.which(candidate)
        if found:
            return found

    aliases = _TOOL_ALIASES.get(Path(name).name.lower(), [])
    for alias in aliases:
        found = shutil.which(alias)
        if found:
            return found
        for candidate in _tool_candidates(alias):
            found = shutil.which(candidate)
            if found:
                return found

    discovered = _discover_tool(name)
    if discovered:
        return discovered

    for alias in aliases:
        discovered = _discover_tool(alias)
        if discovered:
            return discovered

    return None
