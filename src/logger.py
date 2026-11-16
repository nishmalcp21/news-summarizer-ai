"""
Structured audit logger for the News Summarizer Agent.
Logs all Think > Act > Look steps, human confirmations, and tool calls in plain Python.
"""

import sys
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from src.config import config


class AgentAuditLogger:
    def __init__(self, log_file: Path = config.log_path):
        self.log_file = log_file
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        self._logger = logging.getLogger("agent_audit")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False

        # Clear existing handlers to prevent duplicate lines
        if self._logger.hasHandlers():
            self._logger.handlers.clear()

        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

        # File handler
        file_handler = logging.FileHandler(self.log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        self._logger.addHandler(file_handler)

        # Console handler
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(errors="backslashreplace")
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)

    def log_plan(self, plan_summary: str) -> None:
        self._logger.info(f"[PLAN] {plan_summary}")

    def log_think(self, step: int, thought: str) -> None:
        self._logger.info(f"[STEP {step}] [THINK] {thought}")

    def log_act(self, step: int, action: str, args: Any) -> None:
        self._logger.info(f"[STEP {step}] [ACT] Dispatched '{action}' with args: {args}")

    def log_look(self, step: int, observation_summary: str) -> None:
        self._logger.info(f"[STEP {step}] [LOOK] Observation: {observation_summary}")

    def log_safety(self, message: str) -> None:
        self._logger.warning(f"[ASK-YOU-FIRST] {message}")

    def log_error(self, step: int, action: str, error_msg: str) -> None:
        self._logger.error(f"[STEP {step}] [ERROR] In action '{action}': {error_msg}")

    def log_finish(self, message: str) -> None:
        self._logger.info(f"[FINISH] {message}")


# Global default logger instance
logger = AgentAuditLogger()

