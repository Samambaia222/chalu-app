"""数据库 ORM 模型（对应作业5 表4~表7 + PATH + CALIB）"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, Float, DateTime as SA_DateTime, Text, ForeignKey, Index
from sqlalchemy.sql import func
from .database import Base


class User(Base):
    """表4 用户档案表 USER —— 匿名，不存姓名/手机号等可识别字段"""
    __tablename__ = "user"
    user_id = Column(String(12), primary_key=True, comment="匿名用户编号")
    school_tier = Column(String(20), nullable=False, comment="985/211/一本/二本")
    major_category = Column(String(30), nullable=False, comment="计算机类/经管类等")
    gpa_range = Column(String(10), nullable=False, comment="如 3.0-3.5")
    budget_range = Column(String(20), nullable=True, comment="备考可投入金额")
    target_province = Column(String(30), nullable=True, comment="目标就业/就读省份")
    time_input = Column(String(10), nullable=False, comment="每月可投入时长")
    archive_code = Column(String(8), unique=True, nullable=True, comment="档案找回码（个人特色存档）")
    gender = Column(String(6), nullable=True, comment="男/女/其他，匿名统计用，不存姓名")
    tags = Column(Text, nullable=True, comment="特色标签 JSON 数组，如 [\"跨专业\",\"二战考生\"]")
    raw_text = Column(Text, nullable=True, comment="自然语言建档原文（匿名）")
    created_at = Column(SA_DateTime, server_default=func.now())


class Path(Base):
    """路径主表 PATH"""
    __tablename__ = "path"
    path_id = Column(String(6), primary_key=True)
    name = Column(String(20), nullable=False, comment="考研/考公/就业")
    category = Column(String(20), nullable=False, comment="升学/体制内/市场化")


class Assess(Base):
    """表5 评估记录表 ASSESS"""
    __tablename__ = "assess"
    record_id = Column(String(16), primary_key=True)
    user_id = Column(String(12), ForeignKey("user.user_id"), nullable=False)
    path_id = Column(String(6), ForeignKey("path.path_id"), nullable=False)
    probability = Column(Float, nullable=False, comment="校准后概率 0.02-0.98")
    lower_bound = Column(Float, nullable=False, comment="置信区间下限")
    upper_bound = Column(Float, nullable=False, comment="置信区间上限")
    sample_size = Column(Integer, nullable=False, comment="参与计算样本数")
    calib_version = Column(String(8), nullable=False, comment="校准参数版本")
    conclusion = Column(String(60), nullable=False, comment="可行/不可行及原因")
    evidence = Column(Text, nullable=True, comment="可追溯依据链")
    created_at = Column(SA_DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_assess_user_time", "user_id", "created_at"),
    )


class Sample(Base):
    """表6 同辈样本表 SAMPLE"""
    __tablename__ = "sample"
    sample_id = Column(String(16), primary_key=True)
    path_id = Column(String(6), ForeignKey("path.path_id"), nullable=False)
    feature_summary = Column(String(80), nullable=False, comment="院校层次+专业+GPA")
    school_tier = Column(String(20), nullable=False)
    major_category = Column(String(30), nullable=False)
    gpa_range = Column(String(10), nullable=False)
    target_province = Column(String(30), nullable=True)
    gender = Column(String(6), nullable=True, comment="男/女/其他（匿名样本的性别构成，帮助分析路径差异）")
    result = Column(String(10), nullable=False, comment="达成/未达成/未行动")
    key_action = Column(String(40), nullable=True, comment="该同辈自述的关键动作，如 提前一年实习")
    feedback_at = Column(SA_DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_sample_path_result", "path_id", "result"),
    )


class Rule(Base):
    """表7 约束规则表 RULE"""
    __tablename__ = "rule"
    rule_id = Column(String(4), primary_key=True)
    path_id = Column(String(6), ForeignKey("path.path_id"), nullable=False)
    constraint_item = Column(String(20), nullable=False, comment="学历/截止/预算等")
    threshold = Column(String(30), nullable=False, comment="判定阈值")
    is_hard = Column(Integer, default=1, comment="1硬/0软")
    description = Column(String(120), nullable=True)


class Calib(Base):
    """校准参数表 CALIB"""
    __tablename__ = "calib"
    version = Column(String(8), primary_key=True, comment="校准版本号")
    path_id = Column(String(6), ForeignKey("path.path_id"), primary_key=True, comment="复合主键")
    brier_before = Column(Float, nullable=False, comment="校准前 Brier Score")
    brier_after = Column(Float, nullable=False, comment="校准后 Brier Score")
    method = Column(String(20), nullable=False, default="Isotonic")
    created_at = Column(SA_DateTime, server_default=func.now())


class PsychAssess(Base):
    """心理状态自评表 PSYCH（PHQ-9 抑郁 + GAD-7 焦虑）
       注意：仅用于决策参考，不构成临床诊断"""
    __tablename__ = "psych_assess"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(12), ForeignKey("user.user_id"), nullable=False)
    phq9_total = Column(Integer, nullable=False, comment="PHQ-9 总分 0-27")
    phq9_level = Column(String(10), nullable=False, comment="无/轻度/中度/中重度/重度")
    gad7_total = Column(Integer, nullable=False, comment="GAD-7 总分 0-21")
    gad7_level = Column(String(10), nullable=False, comment="无/轻度/中度/重度")
    self_harm_flag = Column(Integer, default=0, comment="PHQ-9 第9题>0 时为1，需优先干预")
    answers = Column(Text, nullable=True, comment="原始作答 JSON")
    created_at = Column(SA_DateTime, server_default=func.now())

    __table_args__ = (Index("ix_psych_user_time", "user_id", "created_at"),)


class HollandAssess(Base):
    """职业兴趣测评表 HOLLAND（RIASEC 六维）"""
    __tablename__ = "holland_assess"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(12), ForeignKey("user.user_id"), nullable=False)
    r_score = Column(Integer, nullable=False, comment="现实型 R 3-15")
    i_score = Column(Integer, nullable=False, comment="研究型 I")
    a_score = Column(Integer, nullable=False, comment="艺术型 A")
    s_score = Column(Integer, nullable=False, comment="社会型 S")
    e_score = Column(Integer, nullable=False, comment="企业型 E")
    c_score = Column(Integer, nullable=False, comment="常规型 C")
    top_code = Column(String(3), nullable=False, comment="前三码，如 ICE")
    answers = Column(Text, nullable=True)
    created_at = Column(SA_DateTime, server_default=func.now())

    __table_args__ = (Index("ix_holland_user_time", "user_id", "created_at"),)


class Decision(Base):
    """路径决策与执行方案表 DECISION"""
    __tablename__ = "decision"
    decision_id = Column(String(16), primary_key=True)
    user_id = Column(String(12), ForeignKey("user.user_id"), nullable=False)
    chosen_path_id = Column(String(6), ForeignKey("path.path_id"), nullable=False)
    chosen_path_name = Column(String(20), nullable=False)
    plan = Column(Text, nullable=True, comment="执行方案 JSON（阶段/里程碑/风险/心理支持/PlanB）")
    created_at = Column(SA_DateTime, server_default=func.now())

    __table_args__ = (Index("ix_decision_user_time", "user_id", "created_at"),)


class Credential(Base):
    """凭证/回填结果表 CREDENTIAL
       用户上传 offer、录取通知书、成绩单等，系统审查后决定是否纳入同辈样本库。"""
    __tablename__ = "credential"
    credential_id = Column(String(16), primary_key=True)
    user_id = Column(String(12), ForeignKey("user.user_id"), nullable=False)
    path_id = Column(String(6), ForeignKey("path.path_id"), nullable=False, comment="对应考研/考公/就业哪条路")
    result = Column(String(10), nullable=False, comment="达成/未达成")
    proof_type = Column(String(20), nullable=True, comment="offer/录取通知书/成绩单/其他")
    proof_filename = Column(String(60), nullable=True, comment="上传的原始文件名")
    proof_path = Column(String(160), nullable=True, comment="服务端存储路径（二进制不入库）")
    proof_text = Column(Text, nullable=True, comment="从凭证中抽取的可读文字（OCR 或 AI 识别）")
    review_score = Column(Float, nullable=True, comment="AI 审查可信度 0-1")
    review_note = Column(String(180), nullable=True, comment="AI 审查的自然语言结论")
    review_status = Column(String(10), nullable=False, default="pending", comment="pending/verified/rejected")
    verify_method = Column(String(20), nullable=True, comment="ai_ocr/manual_self/规则")
    sample_id = Column(String(16), nullable=True, comment="若通过审查，自动纳入的样本 ID")
    created_at = Column(SA_DateTime, server_default=func.now())

    __table_args__ = (Index("ix_cred_user", "user_id"),)


class Event(Base):
    """用户行为事件流（前端埋点 + 行为回流入样）"""
    __tablename__ = "event"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(24), index=True)
    event_type = Column(String(48), comment="credential_upload/report_view/link_click/path_selected/profile_created")
    path_id = Column(String(12), nullable=True)
    target = Column(String(128), nullable=True)
    payload = Column(Text, nullable=True, comment="JSON string，比如 {\"offer_company\":\"腾讯\",\"offer_role\":\"前端\"}")
    created_at = Column(SA_DateTime, default=datetime.utcnow)
