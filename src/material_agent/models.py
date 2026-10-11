from dataclasses import dataclass

class StopAutomation(RuntimeError):
    def __init__(self, message, code='AUTOMATION_PAUSED'):
        super().__init__(message)
        self.code=code

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
