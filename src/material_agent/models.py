from dataclasses import dataclass

class StopAutomation(RuntimeError):
    pass

@dataclass(frozen=True)
class Source:
    conversation_id: str
    title: str

@dataclass(frozen=True)
class Attachment:
    attachment_id: str
    kind: str
    name: str

@dataclass(frozen=True)
class Message:
    message_id: str
    sender: str
    timestamp: str
    text: str
    attachments: tuple[Attachment, ...]
