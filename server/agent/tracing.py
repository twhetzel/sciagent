"""
Simple trace collector for agent execution tracking
"""

import time
import json
from typing import List, Dict, Any, Optional
from datetime import datetime


class TraceCollector:
    """Collects and manages execution traces for the agent"""
    
    def __init__(self):
        self._traces: List[Dict[str, Any]] = []
        self._current_trace: Optional[Dict[str, Any]] = None
        self._trace_stack: List[Dict[str, Any]] = []
    
    def start_trace(self, trace_id: str, metadata: Dict[str, Any] = None) -> str:
        """
        Start a new trace
        
        Args:
            trace_id: Unique identifier for the trace
            metadata: Additional metadata for the trace
            
        Returns:
            str: The trace ID
        """
        trace = {
            "id": trace_id,
            "start_time": datetime.now().isoformat(),
            "metadata": metadata or {},
            "steps": [],
            "status": "running"
        }
        
        self._traces.append(trace)
        self._current_trace = trace
        self._trace_stack.append(trace)
        
        return trace_id
    
    def end_trace(self, trace_id: str, result: Dict[str, Any] = None):
        """
        End the current trace
        
        Args:
            trace_id: The trace ID to end
            result: Final result data
        """
        if self._current_trace and self._current_trace["id"] == trace_id:
            self._current_trace["end_time"] = datetime.now().isoformat()
            self._current_trace["status"] = "completed"
            
            if result:
                self._current_trace["result"] = result
            
            # Calculate duration
            start_time = datetime.fromisoformat(self._current_trace["start_time"])
            end_time = datetime.fromisoformat(self._current_trace["end_time"])
            duration = (end_time - start_time).total_seconds()
            self._current_trace["duration_seconds"] = duration
            
            # Pop from stack
            if self._trace_stack:
                self._trace_stack.pop()
            
            # Update current trace to parent if available
            self._current_trace = self._trace_stack[-1] if self._trace_stack else None
    
    def log_step(self, step_name: str, data: Dict[str, Any]):
        """
        Log a step in the current trace
        
        Args:
            step_name: Name of the step
            data: Step data
        """
        if self._current_trace:
            step = {
                "name": step_name,
                "timestamp": datetime.now().isoformat(),
                "data": data
            }
            self._current_trace["steps"].append(step)
    
    def log_error(self, trace_id: str, error_message: str):
        """
        Log an error for a trace
        
        Args:
            trace_id: The trace ID
            error_message: Error message
        """
        # Find the trace and mark it as failed
        for trace in self._traces:
            if trace["id"] == trace_id:
                trace["status"] = "error"
                trace["error"] = error_message
                trace["end_time"] = datetime.now().isoformat()
                break
        
        # Also log as a step if there's a current trace
        if self._current_trace:
            self.log_step("error", {
                "trace_id": trace_id,
                "error": error_message
            })
    
    def get_traces(self) -> List[Dict[str, Any]]:
        """
        Get all traces
        
        Returns:
            List of trace dictionaries
        """
        return self._traces.copy()
    
    def get_trace(self, trace_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific trace by ID
        
        Args:
            trace_id: The trace ID
            
        Returns:
            Trace dictionary or None if not found
        """
        for trace in self._traces:
            if trace["id"] == trace_id:
                return trace
        return None
    
    def clear_traces(self):
        """Clear all traces"""
        self._traces.clear()
        self._current_trace = None
        self._trace_stack.clear()
    
    def export_traces(self, filepath: str):
        """
        Export traces to a JSON file
        
        Args:
            filepath: Path to save the traces
        """
        with open(filepath, 'w') as f:
            json.dump(self._traces, f, indent=2)
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all traces
        
        Returns:
            Summary statistics
        """
        total_traces = len(self._traces)
        completed_traces = len([t for t in self._traces if t["status"] == "completed"])
        error_traces = len([t for t in self._traces if t["status"] == "error"])
        running_traces = len([t for t in self._traces if t["status"] == "running"])
        
        total_steps = sum(len(t.get("steps", [])) for t in self._traces)
        
        return {
            "total_traces": total_traces,
            "completed_traces": completed_traces,
            "error_traces": error_traces,
            "running_traces": running_traces,
            "total_steps": total_steps,
            "success_rate": completed_traces / total_traces if total_traces > 0 else 0
        }
