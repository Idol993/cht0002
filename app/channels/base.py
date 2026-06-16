from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
from dataclasses import dataclass


@dataclass
class ChannelResult:
    success: bool
    message: str = ""
    provider_msg_id: str = ""
    duration_ms: float = 0.0
    error_code: str = ""


class BaseChannel(ABC):
    channel_type: str = ""
    channel_name: str = ""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    @abstractmethod
    def send(
        self,
        user_id: str,
        content: str,
        title: Optional[str] = None,
        template_id: Optional[str] = None,
        template_data: Optional[Dict[str, Any]] = None,
        user_info: Optional[Dict[str, Any]] = None,
    ) -> ChannelResult:
        pass

    def is_available(self) -> bool:
        return True

    def validate_user_info(self, user_info: Optional[Dict[str, Any]]) -> bool:
        return True
