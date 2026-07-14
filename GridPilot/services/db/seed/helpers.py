"""Helper functions and logging structures for GridPilot database seeding."""
from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Any, Dict

# Stable, deterministic UUID namespace derived from build specifications
GRIDPILOT_NS = uuid.UUID('e6212c1c-1618-4eb9-942c-cdc88dac4402')


def get_user_id(email: str) -> uuid.UUID:
    """Return a deterministic UUID for a User based on their email."""
    return uuid.uuid5(GRIDPILOT_NS, f"user:{email.lower().strip()}")


def get_region_id(name: str) -> uuid.UUID:
    """Return a deterministic UUID for a UtilityRegion based on its name."""
    return uuid.uuid5(GRIDPILOT_NS, f"region:{name.strip()}")


def get_node_id(region_id: uuid.UUID, node_key: str) -> uuid.UUID:
    """Return a deterministic UUID for a GridNode based on its region and key."""
    return uuid.uuid5(GRIDPILOT_NS, f"node:{str(region_id)}:{node_key.strip()}")


def get_edge_id(region_id: uuid.UUID, from_node_key: str, to_node_key: str) -> uuid.UUID:
    """Return a deterministic UUID for a GridEdge based on endpoints and region."""
    # Ensure ordering is stable regardless of direction
    n1, n2 = sorted([from_node_key.strip(), to_node_key.strip()])
    return uuid.uuid5(GRIDPILOT_NS, f"edge:{str(region_id)}:{n1}:{n2}")


def get_project_id(name: str) -> uuid.UUID:
    """Return a deterministic UUID for a Project based on its name."""
    return uuid.uuid5(GRIDPILOT_NS, f"project:{name.strip()}")


def get_study_id(project_id: uuid.UUID) -> uuid.UUID:
    """Return a deterministic UUID for the initial Study run of a project."""
    return uuid.uuid5(GRIDPILOT_NS, f"study:{str(project_id)}:initial")


class StructuredLogger:
    """JSON structured logger outputting to stdout/stderr for log parsing."""

    def __init__(self, name: str = "gridpilot.seed") -> None:
        self.name = name

    def log(self, level: str, phase: str, message: str, **metadata: Any) -> None:
        """Log a structured JSON line."""
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level.upper(),
            "logger": self.name,
            "phase": phase,
            "message": message,
            "metadata": metadata,
        }
        sys.stdout.write(json.dumps(record) + "\n")
        sys.stdout.flush()

    def info(self, phase: str, message: str, **metadata: Any) -> None:
        self.log("INFO", phase, message, **metadata)

    def warning(self, phase: str, message: str, **metadata: Any) -> None:
        self.log("WARNING", phase, message, **metadata)

    def error(self, phase: str, message: str, **metadata: Any) -> None:
        self.log("ERROR", phase, message, **metadata)
