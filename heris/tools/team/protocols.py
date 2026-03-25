"""Team Protocols - Inter-agent communication and coordination (s10 pattern).

Implements:
- MessageBus: JSONL inbox for agent-to-agent messaging
- ShutdownProtocol: Graceful shutdown with request_id handshake
- PlanApprovalProtocol: Lead approval workflow for plans
"""

import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
from threading import Lock


@dataclass
class Message:
    """A message in the MessageBus."""

    id: str
    type: str  # shutdown.request, shutdown.ack, plan.approval.request, etc.
    sender: str
    recipient: str  # "broadcast", "lead", or specific agent_id
    payload: dict
    timestamp: float = field(default_factory=time.time)
    read: bool = False
    request_id: Optional[str] = None  # For correlation (shutdown handshake)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        return cls(
            id=data["id"],
            type=data["type"],
            sender=data["sender"],
            recipient=data["recipient"],
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp", time.time()),
            read=data.get("read", False),
            request_id=data.get("request_id"),
        )


class MessageBus:
    """MessageBus for inter-agent communication.

    Each agent has an inbox at .messages/{agent_id}.jsonl
    Messages are append-only JSON lines for durability.
    """

    def __init__(self, messages_dir: Path):
        """Initialize MessageBus.

        Args:
            messages_dir: Directory to store message inboxes
        """
        self.dir = Path(messages_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def _inbox_path(self, agent_id: str) -> Path:
        """Get inbox path for an agent."""
        return self.dir / f"{agent_id}.jsonl"

    def send(
        self,
        msg_type: str,
        sender: str,
        recipient: str,
        payload: dict,
        request_id: Optional[str] = None,
    ) -> Message:
        """Send a message to recipient's inbox.

        Args:
            msg_type: Message type (e.g., 'shutdown.request', 'plan.approval.request')
            sender: Sender agent ID
            recipient: Recipient ('broadcast', 'lead', or agent ID)
            payload: Message payload
            request_id: Optional correlation ID for request/response patterns

        Returns:
            The sent Message
        """
        msg = Message(
            id=str(uuid.uuid4())[:8],
            type=msg_type,
            sender=sender,
            recipient=recipient,
            payload=payload,
            request_id=request_id or str(uuid.uuid4())[:8],
        )

        # Determine target inboxes
        if recipient == "broadcast":
            # Send to all agents (all existing inboxes)
            targets = [p.stem for p in self.dir.glob("*.jsonl")]
        else:
            targets = [recipient]

        with self._lock:
            for target in targets:
                inbox = self._inbox_path(target)
                with open(inbox, "a", encoding="utf-8") as f:
                    f.write(json.dumps(msg.to_dict(), ensure_ascii=False) + "\n")

        return msg

    def poll(self, agent_id: str, unread_only: bool = False) -> list[Message]:
        """Poll inbox for messages.

        Args:
            agent_id: Agent to check inbox for
            unread_only: Only return unread messages

        Returns:
            List of messages
        """
        inbox = self._inbox_path(agent_id)
        if not inbox.exists():
            return []

        messages = []
        with self._lock:
            try:
                with open(inbox, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            msg = Message.from_dict(json.loads(line))
                            if not unread_only or not msg.read:
                                messages.append(msg)
                        except json.JSONDecodeError:
                            continue
            except FileNotFoundError:
                pass

        return messages

    def mark_read(self, agent_id: str, message_id: str) -> bool:
        """Mark a message as read.

        Args:
            agent_id: Agent ID
            message_id: Message ID to mark

        Returns:
            True if found and marked, False otherwise
        """
        inbox = self._inbox_path(agent_id)
        if not inbox.exists():
            return False

        with self._lock:
            lines = []
            found = False
            with open(inbox, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("id") == message_id:
                            data["read"] = True
                            found = True
                        lines.append(json.dumps(data, ensure_ascii=False))
                    except json.JSONDecodeError:
                        lines.append(line)

            if found:
                with open(inbox, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines) + "\n")

            return found

    def clear(self, agent_id: str) -> None:
        """Clear an agent's inbox.

        Args:
            agent_id: Agent ID
        """
        inbox = self._inbox_path(agent_id)
        with self._lock:
            if inbox.exists():
                inbox.unlink()


class ShutdownProtocol:
    """Graceful shutdown protocol with request_id handshake.

    Pattern: Lead broadcasts shutdown.request with request_id.
    Agents acknowledge with shutdown.ack containing same request_id.
    Lead waits for all acks or times out.
    """

    def __init__(self, message_bus: MessageBus):
        self.bus = message_bus

    def request_shutdown(
        self,
        sender: str,
        target_agents: list[str],
        reason: str = "",
        timeout_seconds: int = 60,
    ) -> dict:
        """Request graceful shutdown from target agents.

        Args:
            sender: Requesting agent (usually lead)
            target_agents: List of agent IDs to shut down
            reason: Shutdown reason
            timeout_seconds: Timeout for acknowledgments

        Returns:
            Shutdown request details
        """
        request_id = str(uuid.uuid4())[:8]

        payload = {
            "reason": reason,
            "timeout_seconds": timeout_seconds,
            "target_agents": target_agents,
        }

        # Send to all targets
        for agent_id in target_agents:
            self.bus.send(
                msg_type="shutdown.request",
                sender=sender,
                recipient=agent_id,
                payload=payload,
                request_id=request_id,
            )

        return {
            "request_id": request_id,
            "targets": target_agents,
            "timeout_seconds": timeout_seconds,
            "reason": reason,
        }

    def acknowledge_shutdown(self, sender: str, request_id: str, lead_id: str = "lead") -> Message:
        """Acknowledge a shutdown request.

        Args:
            sender: Acknowledging agent
            request_id: The shutdown request ID being acknowledged
            lead_id: Lead agent ID

        Returns:
            Acknowledgment message
        """
        return self.bus.send(
            msg_type="shutdown.ack",
            sender=sender,
            recipient=lead_id,
            payload={"status": "acknowledged", "ready": True},
            request_id=request_id,
        )

    def check_acks(self, lead_id: str, request_id: str, expected_agents: list[str]) -> dict:
        """Check which agents have acknowledged shutdown.

        Args:
            lead_id: Lead agent ID
            request_id: Shutdown request ID
            expected_agents: Agents expected to acknowledge

        Returns:
            Status dict with acknowledged and pending lists
        """
        messages = self.bus.poll(lead_id, unread_only=True)
        acks = [
            m for m in messages
            if m.type == "shutdown.ack" and m.request_id == request_id
        ]

        acknowledged = [m.sender for m in acks]
        pending = [a for a in expected_agents if a not in acknowledged]

        # Mark acks as read
        for ack in acks:
            self.bus.mark_read(lead_id, ack.id)

        return {
            "request_id": request_id,
            "acknowledged": acknowledged,
            "pending": pending,
            "complete": len(pending) == 0,
        }


class PlanApprovalProtocol:
    """Plan approval protocol for lead approval workflow.

    Pattern: Agent creates plan, sends to lead for approval.
    Lead reviews and responds with approved/rejected.
    """

    def __init__(self, message_bus: MessageBus):
        self.bus = message_bus

    def submit_plan(
        self,
        sender: str,
        plan_content: str,
        lead_id: str = "lead",
        plan_id: Optional[str] = None,
    ) -> dict:
        """Submit a plan for approval.

        Args:
            sender: Submitting agent
            plan_content: The plan content/markdown
            lead_id: Lead agent ID
            plan_id: Optional plan ID (generated if not provided)

        Returns:
            Submission details
        """
        plan_id = plan_id or f"plan-{str(uuid.uuid4())[:8]}"

        payload = {
            "plan_id": plan_id,
            "content": plan_content,
            "status": "pending",
            "submitted_at": time.time(),
        }

        self.bus.send(
            msg_type="plan.approval.request",
            sender=sender,
            recipient=lead_id,
            payload=payload,
            request_id=plan_id,
        )

        return {
            "plan_id": plan_id,
            "status": "pending",
            "submitted_to": lead_id,
        }

    def approve_plan(
        self,
        lead_id: str,
        plan_id: str,
        submitter: str,
        approved: bool = True,
        feedback: str = "",
    ) -> Message:
        """Approve or reject a plan.

        Args:
            lead_id: Lead agent ID
            plan_id: Plan ID
            submitter: Original submitter agent ID
            approved: True to approve, False to reject
            feedback: Optional feedback message

        Returns:
            Response message
        """
        payload = {
            "plan_id": plan_id,
            "approved": approved,
            "feedback": feedback,
            "responded_at": time.time(),
        }

        return self.bus.send(
            msg_type="plan.approval.response",
            sender=lead_id,
            recipient=submitter,
            payload=payload,
            request_id=plan_id,
        )

    def get_pending_requests(self, lead_id: str) -> list[Message]:
        """Get pending approval requests for lead.

        Args:
            lead_id: Lead agent ID

        Returns:
            List of pending plan approval requests
        """
        messages = self.bus.poll(lead_id, unread_only=True)
        return [m for m in messages if m.type == "plan.approval.request"]

    def get_response(self, agent_id: str, plan_id: str) -> Optional[Message]:
        """Get approval response for a plan.

        Args:
            agent_id: Agent checking for response
            plan_id: Plan ID

        Returns:
            Response message if found, None otherwise
        """
        messages = self.bus.poll(agent_id, unread_only=True)
        for m in messages:
            if m.type == "plan.approval.response" and m.request_id == plan_id:
                self.bus.mark_read(agent_id, m.id)
                return m
        return None
