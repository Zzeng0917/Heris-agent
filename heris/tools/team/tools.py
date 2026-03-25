"""Team tools - Integration with Heris Agent.

Provides tools for team communication and coordination.
"""

from typing import Any, Optional
from pathlib import Path

from ..base import Tool, ToolResult
from .protocols import MessageBus, ShutdownProtocol, PlanApprovalProtocol


# Global instance (initialized once and shared)
_message_bus: Optional[MessageBus] = None
_shutdown_protocol: Optional[ShutdownProtocol] = None
_plan_protocol: Optional[PlanApprovalProtocol] = None


def init_team_system(workspace_dir: Path) -> tuple[MessageBus, ShutdownProtocol, PlanApprovalProtocol]:
    """Initialize the team communication system.

    Args:
        workspace_dir: Base workspace directory

    Returns:
        Tuple of (MessageBus, ShutdownProtocol, PlanApprovalProtocol)
    """
    global _message_bus, _shutdown_protocol, _plan_protocol

    if _message_bus is None:
        messages_dir = workspace_dir / ".messages"

        _message_bus = MessageBus(messages_dir)
        _shutdown_protocol = ShutdownProtocol(_message_bus)
        _plan_protocol = PlanApprovalProtocol(_message_bus)

    return _message_bus, _shutdown_protocol, _plan_protocol


def get_team_system() -> tuple[Optional[MessageBus], Optional[ShutdownProtocol], Optional[PlanApprovalProtocol]]:
    """Get the global team system instances."""
    return _message_bus, _shutdown_protocol, _plan_protocol


# =============================================================================
# Messaging Tools
# =============================================================================

class MessageSendTool(Tool):
    """Send a message to another agent."""

    @property
    def name(self) -> str:
        return "message_send"

    @property
    def description(self) -> str:
        return """Send a message to another agent or broadcast to all.

Use this for inter-agent communication and coordination.
Messages are stored in the recipient's inbox and can be polled."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "msg_type": {"type": "string", "description": "Message type identifier"},
                "recipient": {"type": "string", "description": "Recipient agent ID or 'broadcast'"},
                "payload": {"type": "object", "description": "Message payload/data"},
                "sender": {"type": "string", "description": "Your agent ID"},
            },
            "required": ["msg_type", "recipient", "payload", "sender"],
        }

    async def execute(
        self,
        msg_type: str,
        recipient: str,
        payload: dict,
        sender: str,
    ) -> ToolResult:
        try:
            bus, _, _ = get_team_system()
            if bus is None:
                return ToolResult(success=False, error="Team system not initialized")

            msg = bus.send(msg_type, sender, recipient, payload)
            return ToolResult(
                success=True,
                content=f"Sent {msg_type} message to {recipient} (id: {msg.id})",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class MessagePollTool(Tool):
    """Poll inbox for messages."""

    @property
    def name(self) -> str:
        return "message_poll"

    @property
    def description(self) -> str:
        return """Check your inbox for messages.

Use this to receive messages from other agents.
Optionally filter to only unread messages."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Your agent ID"},
                "unread_only": {"type": "boolean", "description": "Only show unread messages"},
            },
            "required": ["agent_id"],
        }

    async def execute(
        self,
        agent_id: str,
        unread_only: bool = False,
    ) -> ToolResult:
        try:
            bus, _, _ = get_team_system()
            if bus is None:
                return ToolResult(success=False, error="Team system not initialized")

            messages = bus.poll(agent_id, unread_only)
            if not messages:
                return ToolResult(success=True, content="No messages.")

            lines = [f"## Inbox for {agent_id}", ""]
            for m in messages:
                status = "📬" if not m.read else "📭"
                lines.append(f"{status} [{m.type}] from {m.sender} (id: {m.id})")
                if m.payload:
                    import json
                    payload_str = json.dumps(m.payload, indent=2)
                    lines.append(f"   Payload: {payload_str}")

            return ToolResult(success=True, content="\n".join(lines))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class MessageReadTool(Tool):
    """Mark a message as read."""

    @property
    def name(self) -> str:
        return "message_read"

    @property
    def description(self) -> str:
        return """Mark a message as read in your inbox."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Your agent ID"},
                "message_id": {"type": "string", "description": "Message ID to mark as read"},
            },
            "required": ["agent_id", "message_id"],
        }

    async def execute(self, agent_id: str, message_id: str) -> ToolResult:
        try:
            bus, _, _ = get_team_system()
            if bus is None:
                return ToolResult(success=False, error="Team system not initialized")

            success = bus.mark_read(agent_id, message_id)
            if success:
                return ToolResult(success=True, content=f"Marked message {message_id} as read")
            else:
                return ToolResult(success=False, error=f"Message {message_id} not found")
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# =============================================================================
# Shutdown Protocol Tools
# =============================================================================

class ShutdownRequestTool(Tool):
    """Request graceful shutdown of target agents."""

    @property
    def name(self) -> str:
        return "shutdown_request"

    @property
    def description(self) -> str:
        return """Request graceful shutdown from target agents.

Use this as a lead agent to coordinate shutdown of team members.
Each target will receive a shutdown request with a unique request_id.
Agents should acknowledge with shutdown_ack."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sender": {"type": "string", "description": "Your agent ID (lead)"},
                "target_agents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of agent IDs to shut down",
                },
                "reason": {"type": "string", "description": "Shutdown reason"},
                "timeout_seconds": {"type": "integer", "description": "Timeout for acknowledgments"},
            },
            "required": ["sender", "target_agents"],
        }

    async def execute(
        self,
        sender: str,
        target_agents: list[str],
        reason: str = "",
        timeout_seconds: int = 60,
    ) -> ToolResult:
        try:
            _, shutdown, _ = get_team_system()
            if shutdown is None:
                return ToolResult(success=False, error="Team system not initialized")

            result = shutdown.request_shutdown(sender, target_agents, reason, timeout_seconds)
            return ToolResult(
                success=True,
                content=f"Shutdown requested (request_id: {result['request_id']}) for {len(target_agents)} agents",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ShutdownAckTool(Tool):
    """Acknowledge a shutdown request."""

    @property
    def name(self) -> str:
        return "shutdown_ack"

    @property
    def description(self) -> str:
        return """Acknowledge a shutdown request from lead.

Use this when you receive a shutdown.request message to confirm
you are ready to shut down. Include the request_id from the original request."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sender": {"type": "string", "description": "Your agent ID"},
                "request_id": {"type": "string", "description": "Request ID from shutdown request"},
                "lead_id": {"type": "string", "description": "Lead agent ID", "default": "lead"},
            },
            "required": ["sender", "request_id"],
        }

    async def execute(
        self,
        sender: str,
        request_id: str,
        lead_id: str = "lead",
    ) -> ToolResult:
        try:
            _, shutdown, _ = get_team_system()
            if shutdown is None:
                return ToolResult(success=False, error="Team system not initialized")

            shutdown.acknowledge_shutdown(sender, request_id, lead_id)
            return ToolResult(
                success=True,
                content=f"Shutdown acknowledged (request_id: {request_id})",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class ShutdownCheckTool(Tool):
    """Check shutdown acknowledgments."""

    @property
    def name(self) -> str:
        return "shutdown_check"

    @property
    def description(self) -> str:
        return """Check which agents have acknowledged shutdown.

Use this as lead to track shutdown progress."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "lead_id": {"type": "string", "description": "Your agent ID (lead)"},
                "request_id": {"type": "string", "description": "Shutdown request ID"},
                "expected_agents": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Agents expected to acknowledge",
                },
            },
            "required": ["lead_id", "request_id", "expected_agents"],
        }

    async def execute(
        self,
        lead_id: str,
        request_id: str,
        expected_agents: list[str],
    ) -> ToolResult:
        try:
            _, shutdown, _ = get_team_system()
            if shutdown is None:
                return ToolResult(success=False, error="Team system not initialized")

            result = shutdown.check_acks(lead_id, request_id, expected_agents)

            lines = [f"## Shutdown Status (request_id: {request_id})"]
            lines.append(f"Complete: {result['complete']}")
            lines.append(f"Acknowledged ({len(result['acknowledged'])}): {', '.join(result['acknowledged'])}")
            lines.append(f"Pending ({len(result['pending'])}): {', '.join(result['pending'])}")

            return ToolResult(success=True, content="\n".join(lines))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


# =============================================================================
# Plan Approval Protocol Tools
# =============================================================================

class PlanSubmitTool(Tool):
    """Submit a plan for approval."""

    @property
    def name(self) -> str:
        return "plan_submit"

    @property
    def description(self) -> str:
        return """Submit a plan to lead for approval.

Use this when you need lead approval before proceeding with work.
The lead will review and approve or reject your plan."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "sender": {"type": "string", "description": "Your agent ID"},
                "plan_content": {"type": "string", "description": "Plan content/markdown"},
                "lead_id": {"type": "string", "description": "Lead agent ID", "default": "lead"},
                "plan_id": {"type": "string", "description": "Optional plan ID"},
            },
            "required": ["sender", "plan_content"],
        }

    async def execute(
        self,
        sender: str,
        plan_content: str,
        lead_id: str = "lead",
        plan_id: Optional[str] = None,
    ) -> ToolResult:
        try:
            _, _, plan_proto = get_team_system()
            if plan_proto is None:
                return ToolResult(success=False, error="Team system not initialized")

            result = plan_proto.submit_plan(sender, plan_content, lead_id, plan_id)
            return ToolResult(
                success=True,
                content=f"Plan submitted (plan_id: {result['plan_id']}) to {lead_id}",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class PlanApproveTool(Tool):
    """Approve or reject a plan."""

    @property
    def name(self) -> str:
        return "plan_approve"

    @property
    def description(self) -> str:
        return """Approve or reject a pending plan.

Use this as lead to respond to plan approval requests.
Provide feedback when rejecting to guide the agent."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "lead_id": {"type": "string", "description": "Your agent ID (lead)"},
                "plan_id": {"type": "string", "description": "Plan ID"},
                "submitter": {"type": "string", "description": "Original submitter agent ID"},
                "approved": {"type": "boolean", "description": "True to approve, False to reject"},
                "feedback": {"type": "string", "description": "Optional feedback message"},
            },
            "required": ["lead_id", "plan_id", "submitter"],
        }

    async def execute(
        self,
        lead_id: str,
        plan_id: str,
        submitter: str,
        approved: bool = True,
        feedback: str = "",
    ) -> ToolResult:
        try:
            _, _, plan_proto = get_team_system()
            if plan_proto is None:
                return ToolResult(success=False, error="Team system not initialized")

            plan_proto.approve_plan(lead_id, plan_id, submitter, approved, feedback)
            status = "approved" if approved else "rejected"
            return ToolResult(
                success=True,
                content=f"Plan {plan_id} {status} and response sent to {submitter}",
            )
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class PlanListPendingTool(Tool):
    """List pending plan approval requests."""

    @property
    def name(self) -> str:
        return "plan_list_pending"

    @property
    def description(self) -> str:
        return """List pending plan approval requests.

Use this as lead to see what plans need your review."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "lead_id": {"type": "string", "description": "Your agent ID (lead)"},
            },
            "required": ["lead_id"],
        }

    async def execute(self, lead_id: str) -> ToolResult:
        try:
            _, _, plan_proto = get_team_system()
            if plan_proto is None:
                return ToolResult(success=False, error="Team system not initialized")

            requests = plan_proto.get_pending_requests(lead_id)
            if not requests:
                return ToolResult(success=True, content="No pending plan approval requests.")

            lines = ["## Pending Plan Approval Requests", ""]
            for req in requests:
                plan_id = req.payload.get("plan_id", "unknown")
                lines.append(f"Plan ID: {plan_id}")
                lines.append(f"From: {req.sender}")
                content = req.payload.get("content", "")[:100]
                if len(req.payload.get("content", "")) > 100:
                    content += "..."
                lines.append(f"Preview: {content}")
                lines.append("")

            return ToolResult(success=True, content="\n".join(lines))
        except Exception as e:
            return ToolResult(success=False, error=str(e))


class PlanCheckResponseTool(Tool):
    """Check for plan approval response."""

    @property
    def name(self) -> str:
        return "plan_check_response"

    @property
    def description(self) -> str:
        return """Check if your plan has been approved.

Use this after submitting a plan to see lead's response."""

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "agent_id": {"type": "string", "description": "Your agent ID"},
                "plan_id": {"type": "string", "description": "Plan ID"},
            },
            "required": ["agent_id", "plan_id"],
        }

    async def execute(self, agent_id: str, plan_id: str) -> ToolResult:
        try:
            _, _, plan_proto = get_team_system()
            if plan_proto is None:
                return ToolResult(success=False, error="Team system not initialized")

            response = plan_proto.get_response(agent_id, plan_id)
            if response is None:
                return ToolResult(success=True, content=f"No response yet for plan {plan_id}")

            approved = response.payload.get("approved", False)
            feedback = response.payload.get("feedback", "")
            status = "✅ APPROVED" if approved else "❌ REJECTED"

            content = f"Plan {plan_id}: {status}"
            if feedback:
                content += f"\nFeedback: {feedback}"

            return ToolResult(success=True, content=content)
        except Exception as e:
            return ToolResult(success=False, error=str(e))
