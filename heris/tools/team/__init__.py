"""Team Protocols module - Inter-agent communication and coordination (s10 pattern).

Implements team protocols for multi-agent coordination:
- MessageBus: JSONL inbox for agent-to-agent messaging
- ShutdownProtocol: Graceful shutdown with request_id handshake
- PlanApprovalProtocol: Lead approval workflow for plans

Tools provided:
- message_send: Send messages between agents
- message_poll: Check inbox for messages
- message_read: Mark messages as read
- shutdown_request: Request graceful agent shutdown
- shutdown_ack: Acknowledge shutdown request
- shutdown_check: Check shutdown acknowledgment status
- plan_submit: Submit plans for approval
- plan_approve: Approve or reject plans
- plan_list_pending: List pending approval requests
- plan_check_response: Check plan approval responses
"""

from .protocols import MessageBus, ShutdownProtocol, PlanApprovalProtocol, Message
from .tools import (
    init_team_system,
    MessageSendTool,
    MessagePollTool,
    MessageReadTool,
    ShutdownRequestTool,
    ShutdownAckTool,
    ShutdownCheckTool,
    PlanSubmitTool,
    PlanApproveTool,
    PlanListPendingTool,
    PlanCheckResponseTool,
)

__all__ = [
    # Core classes
    "MessageBus",
    "ShutdownProtocol",
    "PlanApprovalProtocol",
    "Message",
    # Initialization
    "init_team_system",
    # Messaging tools
    "MessageSendTool",
    "MessagePollTool",
    "MessageReadTool",
    # Shutdown tools
    "ShutdownRequestTool",
    "ShutdownAckTool",
    "ShutdownCheckTool",
    # Plan approval tools
    "PlanSubmitTool",
    "PlanApproveTool",
    "PlanListPendingTool",
    "PlanCheckResponseTool",
]
