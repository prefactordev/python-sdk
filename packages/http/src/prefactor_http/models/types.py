"""Shared type definitions for Prefactor API models."""

from __future__ import annotations

from typing import Literal

AgentStatus = Literal[
    "pending", "active", "complete", "failed", "cancelled", "terminated"
]
AgentInstanceStatus = Literal[
    "preparing",
    "pending",
    "active",
    "complete",
    "failed",
    "cancelled",
    "terminated",
]
FinishStatus = Literal["complete", "failed", "cancelled"]
InstancePurpose = Literal["live", "smoke_test", "eval"]
JudgeTrigger = Literal["on_demand", "on_completion"]
