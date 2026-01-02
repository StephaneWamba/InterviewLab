"""Service for tracking code execution metrics and analytics."""

from typing import List, Dict, Any
from datetime import datetime
from collections import defaultdict


class CodeMetrics:
    """Service for tracking and analyzing code execution metrics."""

    def __init__(self):
        self.metrics: Dict[str, Any] = defaultdict(list)

    def record_execution(
        self,
        user_id: int,
        interview_id: int,
        code: str,
        language: str,
        execution_result: Dict[str, Any],
        code_quality: Dict[str, Any],
    ):
        """
        Record a code execution for analytics.

        Args:
            user_id: User ID
            interview_id: Interview ID
            code: Code that was executed
            language: Programming language
            execution_result: Execution result from sandbox
            code_quality: Code quality analysis
        """
        metric = {
            "user_id": user_id,
            "interview_id": interview_id,
            "timestamp": datetime.utcnow().isoformat(),
            "language": language,
            "code_length": len(code),
            "execution_success": execution_result.get("success", False),
            "execution_time_ms": execution_result.get("execution_time_ms", 0),
            "exit_code": execution_result.get("exit_code", -1),
            "quality_score": code_quality.get("quality_score", 0.0),
            "correctness_score": code_quality.get("correctness_score", 0.0),
            "efficiency_score": code_quality.get("efficiency_score", 0.0),
            "readability_score": code_quality.get("readability_score", 0.0),
            "best_practices_score": code_quality.get("best_practices_score", 0.0),
        }

        self.metrics[f"user_{user_id}"].append(metric)
        self.metrics[f"interview_{interview_id}"].append(metric)

    def get_user_metrics(self, user_id: int) -> Dict[str, Any]:
        """Get aggregated metrics for a user."""
        user_metrics = self.metrics.get(f"user_{user_id}", [])

        if not user_metrics:
            return {
                "total_submissions": 0,
                "average_quality": 0.0,
                "success_rate": 0.0,
                "average_execution_time": 0.0,
            }

        total = len(user_metrics)
        successful = sum(1 for m in user_metrics if m["execution_success"])
        avg_quality = sum(m["quality_score"] for m in user_metrics) / total
        avg_time = sum(m["execution_time_ms"] for m in user_metrics) / total

        # Language breakdown
        languages = defaultdict(int)
        for m in user_metrics:
            languages[m["language"]] += 1

        return {
            "total_submissions": total,
            "average_quality": avg_quality,
            "success_rate": successful / total if total > 0 else 0.0,
            "average_execution_time_ms": avg_time,
            "language_breakdown": dict(languages),
            "quality_trend": [m["quality_score"] for m in user_metrics[-10:]],  # Last 10
        }

    def get_interview_metrics(self, interview_id: int) -> Dict[str, Any]:
        """Get aggregated metrics for an interview."""
        interview_metrics = self.metrics.get(f"interview_{interview_id}", [])

        if not interview_metrics:
            return {
                "total_submissions": 0,
                "average_quality": 0.0,
                "success_rate": 0.0,
            }

        total = len(interview_metrics)
        successful = sum(1 for m in interview_metrics if m["execution_success"])
        avg_quality = sum(m["quality_score"] for m in interview_metrics) / total

        # Quality breakdown
        quality_ranges = {
            "excellent": sum(1 for m in interview_metrics if m["quality_score"] >= 0.8),
            "good": sum(1 for m in interview_metrics if 0.6 <= m["quality_score"] < 0.8),
            "fair": sum(1 for m in interview_metrics if 0.4 <= m["quality_score"] < 0.6),
            "needs_improvement": sum(1 for m in interview_metrics if m["quality_score"] < 0.4),
        }

        return {
            "total_submissions": total,
            "average_quality": avg_quality,
            "success_rate": successful / total if total > 0 else 0.0,
            "quality_breakdown": quality_ranges,
            "submissions": interview_metrics,
        }

    def get_global_stats(self) -> Dict[str, Any]:
        """Get global statistics across all users."""
        all_metrics = []
        for key, metrics in self.metrics.items():
            if key.startswith("user_"):
                all_metrics.extend(metrics)

        if not all_metrics:
            return {
                "total_submissions": 0,
                "average_quality": 0.0,
                "success_rate": 0.0,
            }

        total = len(all_metrics)
        successful = sum(1 for m in all_metrics if m["execution_success"])
        avg_quality = sum(m["quality_score"] for m in all_metrics) / total

        return {
            "total_submissions": total,
            "average_quality": avg_quality,
            "success_rate": successful / total if total > 0 else 0.0,
            "unique_users": len(set(m["user_id"] for m in all_metrics)),
            "unique_interviews": len(set(m["interview_id"] for m in all_metrics)),
        }


# Global metrics instance (in production, use Redis or database)
_global_metrics = CodeMetrics()


def get_code_metrics() -> CodeMetrics:
    """Get global code metrics instance."""
    return _global_metrics




