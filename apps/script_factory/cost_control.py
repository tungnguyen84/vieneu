"""Cost Controller and Audit Logger for Script Factory V1.

Strict rules:
- Logs every operation to script_factory/logs/generation_log.jsonl.
- NEVER logs API keys or sensitive authorization tokens.
- Tracks tokens, latency, provider, model, estimated cost.
- Enforces budgets: per-episode limit, daily limit, max batch size.
- Raises BudgetExceededError when thresholds are breached.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("VieNeu.CostControl")

LOGS_DIR = Path("script_factory/logs")
LOGS_FILE = LOGS_DIR / "generation_log.jsonl"


class BudgetExceededError(Exception):
    """Raised when an operation would exceed configured spending or batch budget."""
    pass


@dataclass
class CostUsageRecord:
    timestamp: float
    operation: str
    episode_id: Optional[str]
    provider: str
    model: str
    status: str
    latency_sec: float
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CostController:
    """Manages token tracking, cost estimation, budget limits, and audit logs."""

    # Approximate pricing per 1k tokens (USD)
    MODEL_PRICING: Dict[str, Dict[str, float]] = {
        "gpt-4o": {"input": 0.005, "output": 0.015},
        "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
        "gemini-1.5-pro": {"input": 0.0035, "output": 0.0105},
        "gemini-1.5-flash": {"input": 0.000075, "output": 0.0003},
        "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
        "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
        "local-mock": {"input": 0.0, "output": 0.0},
    }

    def __init__(
        self,
        daily_budget_usd: float = 10.0,
        per_episode_budget_usd: float = 2.0,
        max_batch_size: int = 100,
        log_file: Optional[Path] = None,
    ):
        self.daily_budget_usd = daily_budget_usd
        self.per_episode_budget_usd = per_episode_budget_usd
        self.max_batch_size = max_batch_size
        self.log_file = Path(log_file) if log_file else LOGS_FILE
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def calculate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Calculates cost in USD based on model pricing."""
        pricing = self.MODEL_PRICING.get(model, {"input": 0.001, "output": 0.002})
        cost = (input_tokens / 1000.0) * pricing["input"] + (output_tokens / 1000.0) * pricing["output"]
        return round(cost, 6)

    def check_budget_pre_flight(self, episode_id: Optional[str] = None, batch_size: int = 1) -> None:
        """Checks if current spending or batch size breaches limits."""
        if batch_size > self.max_batch_size:
            raise BudgetExceededError(f"BUDGET_BLOCKED: Requested batch size {batch_size} exceeds max limit {self.max_batch_size}.")

        daily_spend = self.get_daily_spend_usd()
        if daily_spend >= self.daily_budget_usd:
            raise BudgetExceededError(f"BUDGET_BLOCKED: Daily budget ${self.daily_budget_usd:.2f} reached (Current: ${daily_spend:.2f}).")

        if episode_id:
            ep_spend = self.get_episode_spend_usd(episode_id)
            if ep_spend >= self.per_episode_budget_usd:
                raise BudgetExceededError(f"BUDGET_BLOCKED: Episode {episode_id} budget ${self.per_episode_budget_usd:.2f} reached (Current: ${ep_spend:.2f}).")

    def record_operation(
        self,
        operation: str,
        episode_id: Optional[str],
        provider: str,
        model: str,
        status: str,
        latency_sec: float,
        input_tokens: int,
        output_tokens: int,
        error: Optional[str] = None,
    ) -> CostUsageRecord:
        """Records an operation to generation_log.jsonl without leaking sensitive data."""
        cost = self.calculate_cost(model, input_tokens, output_tokens)
        rec = CostUsageRecord(
            timestamp=time.time(),
            operation=operation,
            episode_id=episode_id,
            provider=provider,
            model=model,
            status=status,
            latency_sec=round(latency_sec, 3),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated_cost_usd=cost,
            error=str(error) if error else None,
        )

        # Sanitize error to prevent leaking api keys
        if rec.error:
            for secret_key in ["sk-", "api_key", "bearer"]:
                if secret_key in rec.error.lower():
                    rec.error = "[REDACTED_API_KEY_ERROR]"

        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"[CostController] Failed to write log: {e}")

        return rec

    def get_logs(self, limit: int = 200) -> List[Dict[str, Any]]:
        """Reads recent log entries."""
        if not self.log_file.exists():
            return []
        records = []
        try:
            with open(self.log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except Exception:
            pass
        return records[-limit:]

    get_audit_records = get_logs

    def get_daily_spend_usd(self) -> float:
        """Returns total spend in USD for the last 24 hours."""
        now = time.time()
        one_day_ago = now - 86400
        logs = self.get_logs(limit=5000)
        return sum(item.get("estimated_cost_usd", 0.0) for item in logs if item.get("timestamp", 0) >= one_day_ago)

    def get_episode_spend_usd(self, episode_id: str) -> float:
        """Returns total spend in USD for a given episode."""
        logs = self.get_logs(limit=5000)
        return sum(item.get("estimated_cost_usd", 0.0) for item in logs if item.get("episode_id") == episode_id)

    def get_dashboard_metrics(self, current_batch_count: int = 0) -> Dict[str, Any]:
        """Provides dashboard summary metrics."""
        logs = self.get_logs(limit=1000)
        today_spend = self.get_daily_spend_usd()
        total_spend = sum(item.get("estimated_cost_usd", 0.0) for item in logs)
        total_tokens = sum(item.get("input_tokens", 0) + item.get("output_tokens", 0) for item in logs)
        return {
            "today_spend_usd": round(today_spend, 4),
            "daily_budget_usd": self.daily_budget_usd,
            "total_spend_usd": round(total_spend, 4),
            "total_tokens": total_tokens,
            "current_batch_count": current_batch_count,
            "max_batch_size": self.max_batch_size,
        }
