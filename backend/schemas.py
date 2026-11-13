"""Pydantic 请求/响应模型（对应 I-01 ~ I-07 接口字段）"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ---------- 统一响应包装 ----------
class ApiResponse(BaseModel):
    code: int = 0
    msg: str = "ok"
    data: Any = None


# ---------- I-01 创建匿名档案 ----------
class ProfileCreate(BaseModel):
    school_tier: str = Field(..., description="985/211/一本/二本")
    major_category: str = Field(..., description="计算机类/经管类等")
    gpa_range: str = Field(..., description="如 3.0-3.5")
    budget_range: Optional[str] = None
    target_province: Optional[str] = None
    time_input: str = Field(..., description="每月可投入时长")
    gender: Optional[str] = Field(default=None, description="男/女/其他（可选，匿名统计用）")
    tags: Optional[List[str]] = Field(default=None, description="特色标签（自然语言解析产出）")
    raw_text: Optional[str] = Field(default=None, description="自然语言建档原文")
    psych: Optional[Dict[str, Any]] = Field(default=None, description="心理测评结果（phq9/gad7 作答）")
    holland: Optional[List[int]] = Field(default=None, description="霍兰德 18 题作答（1-5）")


class ProfileOut(BaseModel):
    user_id: str
    archive_code: str
    gender: Optional[str] = None
    tags: List[str] = []


# ---------- I-08 自然语言建档解析 ----------
class ParseIn(BaseModel):
    text: str = Field(..., min_length=5, description="用户自然语言自我描述")


class ParseOut(BaseModel):
    fields: Dict[str, Optional[str]]
    tags: List[str]
    missing: List[str]
    notes: List[str]
    emotion: Optional[Dict[str, Any]] = None


# ---------- I-02 路径元数据 ----------
class PathOut(BaseModel):
    path_id: str
    name: str
    category: str


# ---------- I-03 三路径概率模拟 ----------
class ProbabilityIn(BaseModel):
    user_id: str


class ProbabilityItem(BaseModel):
    path_id: str
    path_name: str
    prob: float
    lower: float
    upper: float
    n: int
    source: str
    feasible: bool
    reason: Optional[str] = None


class ProbabilityOut(BaseModel):
    items: List[ProbabilityItem]


# ---------- I-04 同辈统计 ----------
class PeerStat(BaseModel):
    path_name: str
    success: int
    fail: int
    pending: int
    total: int
    rate: float


class PeersOut(BaseModel):
    total: int
    stats: List[PeerStat]
    features: Dict[str, Any]
    self_position: Dict[str, Any] = {}
    profiles: Dict[str, Any] = {}
    gaps: Dict[str, Any] = {}
    gender_gaps: Dict[str, Any] = {}
    gender_comparison: Dict[str, Any] = {}
    key_actions: Dict[str, Any] = {}
    most_similar_core: List[Dict[str, Any]] = []
    community_feed: Dict[str, Any] = {}
    top_matches: List[Dict[str, Any]] = []
    confidence: Dict[str, Any] = {}
    gender_split: Dict[str, Any] = {}


# ---------- I-05 硬约束校验 ----------
class ConstraintIn(BaseModel):
    user_id: str


class RuleCheck(BaseModel):
    rule_id: str
    constraint_item: str
    threshold: str
    is_hard: int
    passed: bool
    detail: str


class ConstraintOut(BaseModel):
    feasible: bool
    violated_rules: List[RuleCheck]
    summary: str


# ---------- I-06 决策报告 ----------
class ReportCard(BaseModel):
    path_name: str
    path_id: Optional[str] = None
    probability: Optional[float]
    lower: Optional[float]
    upper: Optional[float]
    sample_size: int
    feasible: bool
    conclusion: str
    badge: str
    strengths: List[str] = []
    risks: List[str] = []
    actions: List[str] = []
    fit_score: Optional[float] = Field(default=None, description="霍兰德兴趣匹配度 0-100")
    peer_rate: Optional[float] = Field(default=None, description="相似同辈该路径达成率")
    peer_success: Optional[int] = Field(default=None, description="相似同辈达成人数")
    peer_total: Optional[int] = Field(default=None, description="相似同辈该路径样本数")
    gap: List[Dict[str, Any]] = Field(default=[], description="我与达成目标同辈的量化差距")
    composite: Optional[float] = Field(default=None, description="综合得分：概率0.65+匹配度0.35")
    gender_split: Dict[str, Any] = Field(default={}, description="按性别分组的该路径同辈达成率")


class ReportOut(BaseModel):
    record_id: str
    user_id: str
    archive_code: Optional[str] = None
    conclusion: str
    tags: List[str] = []
    cards: List[ReportCard]
    peers_evidence: Dict[str, Any] = {}
    evidence: Dict[str, Any]
    psych: Optional[Dict[str, Any]] = None
    holland: Optional[Dict[str, Any]] = None
    compare: List[Dict[str, Any]] = Field(default=[], description="三路径横向对比矩阵")
    what_if: Dict[str, Any] = Field(default={}, description="敏感度/What-if 分析")
    confidence: Dict[str, Any] = Field(default={}, description="同辈样本可信度")
    created_at: str


# ---------- I-10 心理状态自评（PHQ-9 / GAD-7） ----------
class PsychIn(BaseModel):
    phq9: List[int] = Field(..., description="9 题作答，每題 0-3")
    gad7: List[int] = Field(..., description="7 题作答，每题 0-3")
    user_id: Optional[str] = Field(default=None, description="已建档用户可传入以保存")


# ---------- I-11 霍兰德职业兴趣测评 ----------
class HollandIn(BaseModel):
    answers: List[int] = Field(..., description="18 题作答，每题 1-5")
    user_id: Optional[str] = None


class HollandOut(BaseModel):
    scores: Dict[str, int]
    normalized: Dict[str, float]
    top_code: str
    top_dimensions: List[Dict[str, Any]]
    path_fit: Dict[str, float]
    reasons: List[str]


# ---------- I-12 选定路径并生成执行方案 ----------
class DecisionIn(BaseModel):
    user_id: str
    path_id: str = Field(..., description="P_KAOY / P_KAOG / P_JIUY")


class DecisionOut(BaseModel):
    decision_id: str
    path_id: str
    path_name: str
    created_at: str
    plan: Dict[str, Any]


# ---------- I-09 个人特色存档 ----------
class ArchiveReportItem(BaseModel):
    record_id: str
    created_at: str
    conclusion: str


class ArchiveDecisionItem(BaseModel):
    decision_id: str
    path_name: str
    created_at: str


class ArchiveCredentialItem(BaseModel):
    credential_id: str
    path_name: str
    result: str
    proof_type: str
    review_status: str
    review_score: Optional[float] = None
    auto_integrated: bool = False
    created_at: str


class ArchiveOut(BaseModel):
    archive_code: str
    profile: Dict[str, Any]
    tags: List[str]
    raw_text: Optional[str]
    psych: Optional[Dict[str, Any]] = None
    holland: Optional[Dict[str, Any]] = None
    decisions: List[ArchiveDecisionItem] = []
    credentials: List[ArchiveCredentialItem] = []
    created_at: str
    reports: List[ArchiveReportItem]


# ---------- I-07 匿名回填 ----------
class FeedbackIn(BaseModel):
    path_id: str
    school_tier: str
    major_category: str
    gpa_range: str
    target_province: Optional[str] = None
    result: str = Field(..., description="达成/未达成/未行动")


class FeedbackOut(BaseModel):
    sample_id: str


# ---------- 事件回流：行为埋点 ----------
class EventLogIn(BaseModel):
    """前端行为埋点，直接入库"""
    user_id: str
    event_type: str = Field(..., description="credential_upload/report_view/link_click/path_selected/profile_created")
    path_id: Optional[str] = None
    target: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None


class EventSettleIn(BaseModel):
    """行为回流入样：把用户所有行为聚合成一条同辈样本"""
    user_id: str
    final_path: str = Field(..., description="最终路径 P_KAOY/P_KAOG/P_JIUY")
    final_result: str = Field(..., description="达成/未达成")
    note: Optional[str] = None


# ---------- 文本版凭证上传（OCR 不可用时用户粘贴文字） ----------
class CredentialTextIn(BaseModel):
    """用户粘贴的 offer/成绩单 文字版"""
    user_id: str
    path_id: str
    result: str = Field(..., description="达成/未达成")
    proof_text: str = Field(..., min_length=10, description="粘贴的 offer/成绩单 原文")
    proof_type: Optional[str] = Field(default=None, description="offer/录取通知书/成绩单/其他")
    note: Optional[str] = None


# ---------- 同辈社区动态 ----------
class CommunityFeedItem(BaseModel):
    path_id: str
    path_name: str
    items: List[Dict[str, Any]] = []
