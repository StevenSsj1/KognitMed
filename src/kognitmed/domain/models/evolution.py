"""Domain models for Evolution API webhook events."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EvolutionMessageType(str, Enum):
    """Supported incoming message types from Evolution API."""

    CONVERSATION = "conversation"
    IMAGE = "imageMessage"
    AUDIO = "audioMessage"
    VIDEO = "videoMessage"
    DOCUMENT = "documentMessage"
    LOCATION = "locationMessage"
    CONTACT = "contactMessage"
    STICKER = "stickerMessage"
    REACTION = "reactionMessage"


class EvolutionMessageKey(BaseModel):
    """Key that uniquely identifies a message."""

    remote_jid: str = Field(alias="remoteJid")
    from_me: bool = Field(alias="fromMe")
    id: str


class EvolutionMessageData(BaseModel):
    """Parsed message data from the webhook payload."""

    key: EvolutionMessageKey
    push_name: str | None = Field(default="", alias="pushName")
    message_type: str = Field(alias="messageType")
    message: dict[str, Any] = Field(default_factory=dict)
    message_timestamp: int = Field(alias="messageTimestamp")
    instance_id: str = Field(default="", alias="instanceId")
    source: str = Field(default="")
    # The real sender JID (e.g. 593989259026@s.whatsapp.net) from the webhook
    # top-level payload. @lid JIDs are internal and can't be used to send messages.
    reply_jid: str = ""

    model_config = {"populate_by_name": True}

    @property
    def text(self) -> str | None:
        """Extract text content from the message, regardless of type."""
        if self.message_type == EvolutionMessageType.CONVERSATION:
            return self.message.get("conversation")
        if "extendedTextMessage" in self.message:
            return self.message["extendedTextMessage"].get("text")
        if self.message_type == EvolutionMessageType.IMAGE:
            return self.message.get("imageMessage", {}).get("caption")
        return None

    @property
    def sender_phone(self) -> str:
        """Extract the sender phone number from remoteJid."""
        return self.key.remote_jid.split("@")[0]

    @property
    def is_group(self) -> bool:
        """Check if the message comes from a group chat."""
        return "@g.us" in self.key.remote_jid


class EvolutionWebhookEvent(BaseModel):
    """Top-level webhook event from Evolution API."""

    event: str
    instance: str
    data: EvolutionMessageData
    destination: str = ""
    server_url: str = Field(default="", alias="server_url")
    api_key: str = Field(default="", alias="apikey")

    model_config = {"populate_by_name": True}
