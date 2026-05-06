"""Shared type definitions for Prefactor API models."""

from typing import Literal

AgentStatus = Literal[
    "pending", "active", "complete", "failed", "cancelled", "terminated"
]
FinishStatus = Literal["complete", "failed", "cancelled"]
