from enum import Enum
from pydantic import BaseModel


class Confidence(str, Enum):
    CONFIRMED = "confirmed"
    LIKELY = "likely"
    UNLIKELY = "unlikely"
    FALSE_POSITIVE = "false-positive"


class Vulnerability(BaseModel):
    type: str
    bugClass: str
    bugMethod: str
    bugLine: int
    bugSig: str
    sinkClass: str
    sinkMethod: str
    sinkSig: str
    callTree: dict


class ScanResult(BaseModel):
    vulnerabilities: list[Vulnerability]


class AuditState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
