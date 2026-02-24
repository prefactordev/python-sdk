"""Shared type definitions for Prefactor API models."""

from typing import Literal

AgentStatus = Literal["pending", "active", "complete", "failed", "cancelled"]
FinishStatus = Literal["complete", "failed", "cancelled"]
