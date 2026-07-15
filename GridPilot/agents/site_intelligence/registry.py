"""Thread-safe dynamic tool registry for agent capability execution discovery."""
from __future__ import annotations

import threading
from typing import Any, Dict


class ToolRegistry:
    """Thread-safe catalog permitting agents to locate registered tools dynamically."""
    _registry: Dict[str, Any] = {}
    _lock = threading.Lock()

    @classmethod
    def register(cls, name: str, tool_func: Any) -> None:
        """Register a tool execution function, protected by a threading lock."""
        with cls._lock:
            cls._registry[name] = tool_func

    @classmethod
    def get(cls, name: str) -> Any:
        """Fetch a registered tool execution function by name, protected by a lock."""
        with cls._lock:
            if name not in cls._registry:
                raise KeyError(f"Tool '{name}' is not registered in the dynamic registry.")
            return cls._registry[name]
