"""Comprehensive logging utility for interview orchestrator debugging."""

import logging
import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class InterviewLogger:
    """Dedicated logger for interview orchestrator with file output."""
    
    def __init__(self, interview_id: int):
        self.interview_id = interview_id
        self.log_dir = Path("logs/interviews")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"interview_{interview_id}.log"
        self._ensure_file_header()
    
    def _ensure_file_header(self):
        """Write header if file is new."""
        if not self.log_file.exists():
            with open(self.log_file, 'w') as f:
                f.write(f"=== Interview {self.interview_id} Debug Log ===\n")
                f.write(f"Started: {datetime.utcnow().isoformat()}\n")
                f.write("=" * 80 + "\n\n")
    
    def _write_log(self, level: str, section: str, data: Any):
        """Write structured log entry."""
        timestamp = datetime.utcnow().isoformat()
        entry = {
            "timestamp": timestamp,
            "level": level,
            "section": section,
            "interview_id": self.interview_id,
            "data": data
        }
        
        try:
            with open(self.log_file, 'a') as f:
                f.write(json.dumps(entry, indent=2, default=str) + "\n")
                f.write("-" * 80 + "\n\n")
        except Exception as e:
            logger.error(f"Failed to write interview log: {e}")
    
    def log_state(self, node_name: str, state: Dict[str, Any]):
        """Log complete state at a node."""
        # Filter out sensitive data and serialize properly
        safe_state = self._sanitize_state(state.copy())
        self._write_log("INFO", f"STATE_{node_name}", safe_state)
    
    def log_intent_detection(self, user_response: str, detected_intent: Dict[str, Any]):
        """Log intent detection."""
        self._write_log("INFO", "INTENT_DETECTION", {
            "user_response": user_response,
            "detected": detected_intent
        })
    
    def log_decision(self, decision_context: Dict[str, Any], chosen_action: str, reasoning: Optional[str] = None):
        """Log decision node execution."""
        self._write_log("INFO", "DECISION", {
            "context": decision_context,
            "chosen_action": chosen_action,
            "reasoning": reasoning
        })
    
    def log_llm_call(self, node_name: str, prompt: str, response: Any, model: str = "gpt-4o-mini"):
        """Log LLM API calls."""
        self._write_log("INFO", f"LLM_CALL_{node_name}", {
            "model": model,
            "prompt": prompt[:1000],  # Truncate very long prompts
            "response": str(response)[:1000] if response else None
        })
    
    def log_checkpoint(self, checkpoint_data: Dict[str, Any], operation: str):
        """Log checkpoint operations."""
        self._write_log("INFO", f"CHECKPOINT_{operation}", checkpoint_data)
    
    def log_context_injection(self, node_name: str, context_data: Dict[str, Any]):
        """Log what context was injected into LLM."""
        self._write_log("INFO", f"CONTEXT_INJECTION_{node_name}", context_data)
    
    def log_error(self, node_name: str, error: Exception, context: Optional[Dict[str, Any]] = None):
        """Log errors with context."""
        self._write_log("ERROR", f"ERROR_{node_name}", {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context
        })
    
    def log_conversation_turn(self, turn_number: int, user_message: Optional[str], assistant_message: Optional[str]):
        """Log conversation turn."""
        self._write_log("INFO", "CONVERSATION_TURN", {
            "turn": turn_number,
            "user": user_message,
            "assistant": assistant_message
        })
    
    def _sanitize_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Remove sensitive or overly large data from state."""
        safe = {}
        for key, value in state.items():
            # Skip internal/metadata fields
            if key.startswith("_") or key in ["metadata", "raw_data"]:
                continue
            
            # Truncate long strings
            if isinstance(value, str) and len(value) > 500:
                safe[key] = value[:500] + "... (truncated)"
            # Limit list sizes
            elif isinstance(value, list) and len(value) > 20:
                safe[key] = value[:20] + [f"... ({len(value) - 20} more items)"]
            else:
                safe[key] = value
        
        return safe

