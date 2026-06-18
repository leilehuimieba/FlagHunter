"""Dynamic tool loader for FlagHunter."""

import ast
import copy
import importlib
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .registry import get_all_tools, get_tool


_TOOL_INDEX_CACHE: Optional[List[dict]] = None
_TOOL_MODULE_BY_NAME_CACHE: Dict[str, str] = {}
_TOOL_SCHEMA_CACHE: Dict[str, dict] = {}


def discover_tools(tools_dir: Optional[Path] = None) -> List[str]:
    """
    Discover all tool modules in the tools directory.

    Args:
        tools_dir: Path to tools directory. Defaults to package tools dir.

    Returns:
        List of discovered tool module names
    """
    if tools_dir is None:
        tools_dir = Path(__file__).parent

    discovered = []

    for item in tools_dir.iterdir():
        # Skip non-tool items
        if item.name.startswith("_"):
            continue
        if item.name in ("registry.py", "executor.py", "loader.py"):
            continue

        # Check if it's a tool module
        if item.is_dir() and (item / "__init__.py").exists():
            discovered.append(item.name)
        elif item.suffix == ".py":
            discovered.append(item.stem)

    return discovered


def load_tool_module(module_name: str, tools_dir: Optional[Path] = None) -> bool:
    """
    Load a tool module by name.

    Args:
        module_name: Name of the tool module to load
        tools_dir: Path to tools directory

    Returns:
        True if loaded successfully, False otherwise
    """
    if tools_dir is None:
        tools_dir = Path(__file__).parent

    try:
        # Build the full module path
        full_module_name = f"flaghunter.tools.{module_name}"

        # Check if already loaded
        if full_module_name in sys.modules:
            return True

        # Try to import the module
        importlib.import_module(full_module_name)
        return True

    except ImportError as e:
        print(f"Warning: Failed to load tool module '{module_name}': {e}")
        return False
    except Exception as e:
        print(f"Warning: Error loading tool module '{module_name}': {e}")
        return False


def load_all_tools(tools_dir: Optional[Path] = None) -> List[str]:
    """
    Discover and load all tool modules.

    Args:
        tools_dir: Path to tools directory

    Returns:
        List of successfully loaded tool module names
    """
    discovered = discover_tools(tools_dir)
    loaded = []

    for module_name in discovered:
        if load_tool_module(module_name, tools_dir):
            loaded.append(module_name)

    return loaded


def _tool_source_path(module_name: str, tools_dir: Optional[Path] = None) -> Path:
    if tools_dir is None:
        tools_dir = Path(__file__).parent

    package_path = tools_dir / module_name / "__init__.py"
    if package_path.exists():
        return package_path
    return tools_dir / f"{module_name}.py"


def _decorator_name(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _string_value(node: ast.AST) -> Optional[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _string_value(node.left)
        right = _string_value(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _call_arg(call: ast.Call, name: str, position: int) -> Optional[ast.AST]:
    for keyword in call.keywords:
        if keyword.arg == name:
            return keyword.value
    if len(call.args) > position:
        return call.args[position]
    return None


def _iter_tool_metadata(
    module_name: str, tools_dir: Optional[Path] = None
) -> Iterable[Tuple[str, str]]:
    source_path = _tool_source_path(module_name, tools_dir)
    if not source_path.exists():
        return

    try:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return

    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue

        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            if _decorator_name(decorator.func) != "register_tool":
                continue

            name_node = _call_arg(decorator, "name", 0)
            description_node = _call_arg(decorator, "description", 1)
            if name_node is None or description_node is None:
                continue

            tool_name = _string_value(name_node)
            description = _string_value(description_node)
            if tool_name and description:
                yield tool_name, " ".join(description.split())


def list_tool_index(tools_dir: Optional[Path] = None) -> List[dict]:
    """
    Return a lightweight tool catalog without importing tool modules.

    Each entry contains only the tool name and a compact one-line description.
    Full parameter schemas remain available via load_tool_schema().
    """
    global _TOOL_INDEX_CACHE

    use_cache = tools_dir is None
    if use_cache and _TOOL_INDEX_CACHE is not None:
        return copy.deepcopy(_TOOL_INDEX_CACHE)

    index = []
    module_by_tool_name = {}

    for module_name in discover_tools(tools_dir):
        for tool_name, description in _iter_tool_metadata(module_name, tools_dir):
            index.append({"name": tool_name, "description": description})
            module_by_tool_name[tool_name] = module_name

    known_names = {item["name"] for item in index}
    for tool in get_all_tools():
        if tool.name in known_names:
            continue
        index.append(
            {"name": tool.name, "description": " ".join(tool.description.split())}
        )

    if use_cache:
        _TOOL_INDEX_CACHE = copy.deepcopy(index)
        _TOOL_MODULE_BY_NAME_CACHE.update(module_by_tool_name)

    return index


def load_tool_schema(name: str) -> dict:
    """
    Load and return a single tool's complete parameter schema on demand.

    The loader imports only the module that declares the selected tool and caches
    the resulting schema dictionary for later calls.
    """
    if name in _TOOL_SCHEMA_CACHE:
        return copy.deepcopy(_TOOL_SCHEMA_CACHE[name])

    tool = get_tool(name)
    if tool is None:
        if not _TOOL_MODULE_BY_NAME_CACHE:
            list_tool_index()

        module_name = _TOOL_MODULE_BY_NAME_CACHE.get(name)
        if module_name is None or not load_tool_module(module_name):
            raise KeyError(f"Unknown tool: {name}")

        tool = get_tool(name)
        if tool is None:
            raise KeyError(f"Tool module did not register tool: {name}")

    schema = tool.schema.to_dict()
    _TOOL_SCHEMA_CACHE[name] = copy.deepcopy(schema)
    return copy.deepcopy(schema)


def get_tool_info() -> List[dict]:
    """
    Get information about all registered tools.

    Returns:
        List of tool info dictionaries
    """
    tools = get_all_tools()
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "category": tool.category,
            "enabled": tool.enabled,
            "parameters": (
                list(tool.schema.properties.keys()) if tool.schema.properties else []
            ),
        }
        for tool in tools
    ]


def reload_tools():
    """Reload all tool modules."""
    from .registry import clear_tools

    # Clear existing tools
    clear_tools()

    # Unload tool modules from sys.modules
    to_remove = [
        name
        for name in sys.modules
        if name.startswith("flaghunter.tools.")
        and name
        not in (
            "flaghunter.tools",
            "flaghunter.tools.registry",
            "flaghunter.tools.executor",
            "flaghunter.tools.loader",
        )
    ]

    for name in to_remove:
        del sys.modules[name]

    # Reload all tools
    return load_all_tools()
