"""
Approval Manager for Human-in-the-Loop workflows.

Manages approval requests, responses, and state for human approval steps
in agent workflows.
"""

import asyncio
import uuid
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum


class ApprovalStatus(Enum):
    """Status of an approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class ApprovalRequest:
    """Represents a human approval request."""
    approval_id: str
    conversation_id: int
    approval_type: str  # "review", "confirmation", "feedback"
    title: str
    content: str
    blocks: list = field(default_factory=list)
    options: Dict[str, Any] = field(default_factory=dict)
    timeout: int = 300  # seconds
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: ApprovalStatus = ApprovalStatus.PENDING
    response: Optional[Dict[str, Any]] = None
    feedback: Optional[str] = None
    responded_at: Optional[datetime] = None
    future: Optional[asyncio.Future] = None
    
    def is_expired(self) -> bool:
        """Check if approval request has expired."""
        if self.status != ApprovalStatus.PENDING:
            return False
        elapsed = (datetime.utcnow() - self.created_at).total_seconds()
        return elapsed >= self.timeout
    
    def expires_at(self) -> datetime:
        """Get expiration timestamp."""
        return self.created_at + timedelta(seconds=self.timeout)


class ApprovalManager:
    """
    Manages approval requests and responses for human-in-the-loop workflows.
    
    Thread-safe approval state management with timeout support.
    """
    
    def __init__(self):
        """Initialize approval manager."""
        self._approvals: Dict[str, ApprovalRequest] = {}
        self._conversation_approvals: Dict[int, list[str]] = {}  # conversation_id -> [approval_ids]
        self._lock = asyncio.Lock()
    
    async def create_approval_request(
        self,
        conversation_id: int,
        approval_type: str,
        title: str,
        content: str,
        blocks: Optional[list] = None,
        options: Optional[Dict[str, Any]] = None,
        timeout: int = 300
    ) -> str:
        """
        Create a new approval request.
        
        Args:
            conversation_id: ID of the conversation
            approval_type: Type of approval ("review", "confirmation", "feedback")
            title: Title for the approval dialog
            content: Content to display
            blocks: Optional structured blocks
            options: Optional approval options
            timeout: Timeout in seconds
            
        Returns:
            approval_id: Unique ID for this approval request
        """
        approval_id = str(uuid.uuid4())
        
        async with self._lock:
            approval = ApprovalRequest(
                approval_id=approval_id,
                conversation_id=conversation_id,
                approval_type=approval_type,
                title=title,
                content=content,
                blocks=blocks or [],
                options=options or {},
                timeout=timeout,
                future=asyncio.Future()
            )
            
            self._approvals[approval_id] = approval
            
            # Track approvals per conversation
            if conversation_id not in self._conversation_approvals:
                self._conversation_approvals[conversation_id] = []
            self._conversation_approvals[conversation_id].append(approval_id)
        
        # Schedule timeout check
        asyncio.create_task(self._check_timeout(approval_id, timeout))
        
        print(f"✅ Created approval request {approval_id} for conversation {conversation_id}")
        return approval_id
    
    async def submit_approval_response(
        self,
        approval_id: str,
        approved: bool,
        feedback: Optional[str] = None,
        response_data: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Submit an approval response.
        
        Args:
            approval_id: ID of the approval request
            approved: Whether the request was approved
            feedback: Optional feedback text
            response_data: Optional additional response data
            
        Returns:
            bool: True if response was accepted, False if approval not found or already responded
        """
        async with self._lock:
            if approval_id not in self._approvals:
                print(f"⚠️ Approval {approval_id} not found")
                return False
            
            approval = self._approvals[approval_id]
            
            if approval.status != ApprovalStatus.PENDING:
                print(f"⚠️ Approval {approval_id} already responded (status: {approval.status})")
                return False
            
            # Update approval
            approval.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
            approval.feedback = feedback
            approval.response = response_data or {}
            approval.responded_at = datetime.utcnow()
            
            # Resolve future if exists
            if approval.future and not approval.future.done():
                approval.future.set_result({
                    "approved": approved,
                    "feedback": feedback,
                    "response_data": response_data
                })
        
        print(f"✅ Approval {approval_id} responded: {'APPROVED' if approved else 'REJECTED'}")
        return True
    
    async def wait_for_approval(
        self,
        approval_id: str,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Wait for approval response.
        
        Args:
            approval_id: ID of the approval request
            timeout: Optional override timeout (defaults to request timeout)
            
        Returns:
            Dict with approval result:
            {
                "approved": bool,
                "feedback": Optional[str],
                "response_data": Optional[Dict]
            }
            
        Raises:
            asyncio.TimeoutError: If approval times out
            ValueError: If approval not found
        """
        async with self._lock:
            if approval_id not in self._approvals:
                raise ValueError(f"Approval {approval_id} not found")
            
            approval = self._approvals[approval_id]
            
            if approval.status != ApprovalStatus.PENDING:
                # Already responded
                return {
                    "approved": approval.status == ApprovalStatus.APPROVED,
                    "feedback": approval.feedback,
                    "response_data": approval.response
                }
            
            future = approval.future
        
        # Wait for response
        wait_timeout = timeout or approval.timeout
        try:
            result = await asyncio.wait_for(future, timeout=wait_timeout)
            return result
        except asyncio.TimeoutError:
            async with self._lock:
                if approval_id in self._approvals:
                    approval = self._approvals[approval_id]
                    if approval.status == ApprovalStatus.PENDING:
                        approval.status = ApprovalStatus.TIMEOUT
                        if approval.future and not approval.future.done():
                            approval.future.set_exception(asyncio.TimeoutError("Approval request timed out"))
            
            raise asyncio.TimeoutError(f"Approval {approval_id} timed out after {wait_timeout} seconds")
    
    def get_approval(self, approval_id: str) -> Optional[ApprovalRequest]:
        """Get approval request by ID."""
        return self._approvals.get(approval_id)
    
    def get_pending_approvals(self, conversation_id: Optional[int] = None) -> list[ApprovalRequest]:
        """Get all pending approval requests, optionally filtered by conversation."""
        approvals = [
            a for a in self._approvals.values()
            if a.status == ApprovalStatus.PENDING and not a.is_expired()
        ]
        
        if conversation_id is not None:
            approvals = [a for a in approvals if a.conversation_id == conversation_id]
        
        return approvals
    
    async def cancel_approval(self, approval_id: str) -> bool:
        """Cancel a pending approval request."""
        async with self._lock:
            if approval_id not in self._approvals:
                return False
            
            approval = self._approvals[approval_id]
            
            if approval.status != ApprovalStatus.PENDING:
                return False
            
            approval.status = ApprovalStatus.CANCELLED
            
            if approval.future and not approval.future.done():
                approval.future.cancel()
        
        print(f"✅ Cancelled approval {approval_id}")
        return True
    
    async def _check_timeout(self, approval_id: str, timeout: int):
        """Background task to check for timeout."""
        await asyncio.sleep(timeout)
        
        async with self._lock:
            if approval_id not in self._approvals:
                return
            
            approval = self._approvals[approval_id]
            
            if approval.status == ApprovalStatus.PENDING and approval.is_expired():
                approval.status = ApprovalStatus.TIMEOUT
                if approval.future and not approval.future.done():
                    approval.future.set_exception(asyncio.TimeoutError("Approval request timed out"))
                print(f"⏱️ Approval {approval_id} timed out")
    
    def cleanup_expired_approvals(self, max_age_hours: int = 24):
        """Clean up expired approvals older than max_age_hours."""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        
        expired_ids = [
            approval_id for approval_id, approval in self._approvals.items()
            if approval.created_at < cutoff and approval.status != ApprovalStatus.PENDING
        ]
        
        for approval_id in expired_ids:
            del self._approvals[approval_id]
            # Clean up conversation tracking
            for conv_id, approval_ids in self._conversation_approvals.items():
                if approval_id in approval_ids:
                    approval_ids.remove(approval_id)
                    if not approval_ids:
                        del self._conversation_approvals[conv_id]
        
        if expired_ids:
            print(f"🧹 Cleaned up {len(expired_ids)} expired approvals")


# Global instance
approval_manager = ApprovalManager()

