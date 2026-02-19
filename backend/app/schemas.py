from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class SuspiciousAccount(BaseModel):
    account_id: str
    suspicion_score: float = Field(ge=0.0, le=100.0)
    detected_patterns: List[str]
    ring_id: str


PatternType = Literal["cycle", "fan_in", "fan_out", "shell"]


class FraudRing(BaseModel):
    ring_id: str
    member_accounts: List[str]
    pattern_type: PatternType
    risk_score: float = Field(ge=0.0, le=100.0)


class Summary(BaseModel):
    total_accounts_analyzed: int
    suspicious_accounts_flagged: int
    fraud_rings_detected: int
    processing_time_seconds: float


class AnalysisResult(BaseModel):
    suspicious_accounts: List[SuspiciousAccount]
    fraud_rings: List[FraudRing]
    summary: Summary


class GraphNode(BaseModel):
    id: str
    label: str
    suspicion_score: Optional[float] = None
    detected_patterns: List[str] = []


class GraphEdge(BaseModel):
    id: str
    source: str
    target: str
    amount: float
    timestamp: datetime


class GraphData(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]


class FullAnalysisResponse(BaseModel):
    result: AnalysisResult
    graph: GraphData

