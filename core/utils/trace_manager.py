"""
Aethvion Suite - Trace Manager
Generates and manages unique Trace_IDs for all transactions
"""

import secrets
import string
from datetime import datetime, timezone
from typing import Dict, Optional
from contextvars import ContextVar

# Thread-safe context variable for storing current trace ID
_current_trace_id: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)


class TraceManager:
    """
    Manages Trace_ID generation and lifecycle.
    
    Trace ID Format: MCTR-{timestamp}-{random}
    Example: MCTR-20260131225500-A7B2C9D1
    """
    
    PREFIX = "ASTR"
    TIMESTAMP_FORMAT = "%Y%m%d%H%M%S"
    RANDOM_LENGTH = 8
    
    def __init__(self):
        self._active_traces: Dict[str, Dict] = {}
    
    def generate_trace_id(self) -> str:
        """Generate a new unique Trace_ID."""
        timestamp = datetime.now(timezone.utc).strftime(self.TIMESTAMP_FORMAT)
        random_part = ''.join(
            secrets.choice(string.ascii_uppercase + string.digits)
            for _ in range(self.RANDOM_LENGTH)
        )
        trace_id = f"{self.PREFIX}-{timestamp}-{random_part}"
        return trace_id
    
    def start_trace(self, metadata: Optional[Dict] = None) -> str:
        """
        Start a new trace and set it as the current context.
        
        Args:
            metadata: Optional metadata to attach to the trace
            
        Returns:
            The generated Trace_ID
        """
        trace_id = self.generate_trace_id()
        
        # Store trace metadata
        self._active_traces[trace_id] = {
            'trace_id': trace_id,
            'started_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f') + 'Z',
            'metadata': metadata or {},
            'status': 'active'
        }
        
        # Set as current context
        _current_trace_id.set(trace_id)
        
        return trace_id
    
    def get_current_trace_id(self) -> Optional[str]:
        """Get the current Trace_ID from context."""
        return _current_trace_id.get()
    
    def end_trace(self, trace_id: str, status: str = 'completed', result: Optional[Dict] = None):
        """
        End a trace and update its status.
        
        Args:
            trace_id: The Trace_ID to end
            status: Final status (completed, failed, timeout, etc.)
            result: Optional result data
        """
        if trace_id in self._active_traces:
            self._active_traces[trace_id].update({
                'status': status,
                'ended_at': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f') + 'Z',
                'result': result
            })
        
        # Clear from context if it's the current trace
        if _current_trace_id.get() == trace_id:
            _current_trace_id.set(None)
    
    def get_trace_info(self, trace_id: str) -> Optional[Dict]:
        """Get information about a specific trace."""
        return self._active_traces.get(trace_id)
    
    def get_active_traces(self) -> Dict[str, Dict]:
        """Get all active traces."""
        return {
            tid: info for tid, info in self._active_traces.items()
            if info['status'] == 'active'
        }
    
    def cleanup_old_traces(self, max_age_hours: int = 24):
        """
        Remove old completed traces from memory.
        
        Args:
            max_age_hours: Maximum age in hours before cleanup
        """
        current_time = datetime.now()
        to_remove = []
        
        for trace_id, info in self._active_traces.items():
            if 'ended_at' in info:
                ended_at = datetime.fromisoformat(info['ended_at'])
                age_hours = (current_time - ended_at).total_seconds() / 3600
                if age_hours > max_age_hours:
                    to_remove.append(trace_id)
        
        for trace_id in to_remove:
            del self._active_traces[trace_id]
        
        return len(to_remove)


# Global singleton instance
_trace_manager = TraceManager()


def get_trace_manager() -> TraceManager:
    """Get the global TraceManager instance."""
    return _trace_manager


def generate_trace_id() -> str:
    """Convenience function to generate a new Trace_ID."""
    return _trace_manager.generate_trace_id()


def get_current_trace_id() -> Optional[str]:
    """Convenience function to get current Trace_ID from context."""
    return _trace_manager.get_current_trace_id()
