import sys

from flaghunter.tools import loader
from flaghunter.tools.registry import clear_tools


_LOADER_MODULES = {
    "flaghunter.tools",
    "flaghunter.tools.executor",
    "flaghunter.tools.loader",
    "flaghunter.tools.registry",
}


def _unload_concrete_tool_modules():
    removed = {}
    for name in list(sys.modules):
        if name.startswith("flaghunter.tools.") and name not in _LOADER_MODULES:
            removed[name] = sys.modules.pop(name)
    clear_tools()
    return removed


def _restore_modules(removed):
    sys.modules.update(removed)


def test_list_tool_index_is_name_description_only_and_does_not_load_every_tool():
    removed = _unload_concrete_tool_modules()
    try:
        discovered = set(loader.discover_tools())

        index = loader.list_tool_index()

        assert index
        assert {"name": "terminal", "description": "Execute shell commands."} in index
        assert all(set(item) == {"name", "description"} for item in index)
        assert all("properties" not in item for item in index)

        loaded_tool_modules = {
            name.removeprefix("flaghunter.tools.")
            for name in sys.modules
            if name.startswith("flaghunter.tools.") and name not in _LOADER_MODULES
        }
        assert loaded_tool_modules != discovered
        assert "terminal" not in loaded_tool_modules
    finally:
        _restore_modules(removed)


def test_load_tool_schema_loads_one_tool_schema_on_demand():
    removed = _unload_concrete_tool_modules()
    try:
        schema = loader.load_tool_schema("terminal")

        assert schema["type"] == "object"
        assert schema["required"] == ["command"]
        assert schema["properties"]["command"]["type"] == "string"
        assert "flaghunter.tools.terminal" in sys.modules
    finally:
        _restore_modules(removed)
