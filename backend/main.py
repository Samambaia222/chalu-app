"""岔路 · 三路径职业决策支持系统 —— FastAPI 主应用
   实现作业5 定义的 7 个接口 I-01 ~ I-07，另加 I-08 ~ I-14 扩展接口"""
import json
import random
import uuid
import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from .database import get_db, init_db
from .models import (User, Path, Assess, Sample, Rule, Calib,
                     PsychAssess, HollandAssess, Decision, Credential, Event)
from .schemas import (
    ProfileCreate, ProfileOut, PathOut,
    ProbabilityIn, ProbabilityOut, ProbabilityItem,
    PeersOut, PeerStat,
    ConstraintIn, ConstraintOut, RuleCheck,
    ReportOut, ReportCard,
    FeedbackIn, FeedbackOut,
    ParseIn, ParseOut,
    ArchiveOut, ArchiveReportItem, ArchiveDecisionItem, ArchiveCredentialItem,
    PsychIn, HollandIn, HollandOut, DecisionIn, DecisionOut,
    EventLogIn, EventSettleIn, CredentialTextIn,
    ApiResponse,
)
from .services.probability import compute_probability
from .services.peers import match_peers
from .services.constraints import check_constraints, build_diagnosis
from .services.nlparse import parse_text
from .services.report_analysis import build_card_analysis
from .services.insight import build_what_if
from .services.assessment import (
    score_psych, score_holland, questions as assessment_questions,
    external_assessments,
)
from .services.guidance import build_plan, PATH_NAMES
from .services.credential import (
    save_proof, ai_review, decide_integration, new_sample_id,
    review_text_credential,
)
from .services.directory import get_directory, get_province_directory
from .seed import seed_all

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 去掉易混淆的 0/O/1/I


def _gen_archive_code(db: Session) -> str:
    for _ in range(30):
        code = "".join(random.choices(_CODE_ALPHABET, k=6))
        if not db.query(User).filter(User.archive_code == code).first():
            return code
    return uuid.uuid4().hex[:6].upper()


def _latest_psych(db: Session, user_id: str):
    """取该用户最近一次心理自评，重算为完整视图"""
    row = (db.query(PsychAssess)
           .filter(PsychAssess.user_id == user_id)
           .order_by(PsychAssess.id.desc()).first())
    if not row or not row.answers:
        return None
    try:
        ans = json.loads(row.answers)
        return score_psych(ans["phq9"], ans["gad7"])
    except (ValueError, KeyError, TypeError):
        return None


def _latest_holland(db: Session, user_id: str):
    """取该用户最近一次霍兰德测评，重算为完整视图"""
    row = (db.query(HollandAssess)
           .filter(HollandAssess.user_id == user_id)
           .order_by(HollandAssess.id.desc()).first())
    if not row or not row.answers:
        return None
    try:
        return score_holland(json.loads(row.answers))
    except (ValueError, TypeError):
        return None

app = FastAPI(title="岔路 · 三路径决策支持系统", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()
    db = next(get_db())
    seed_all(db)
    db.close()


# ============ I-01 创建匿名档案（含个人特色存档） ============
@app.post("/api/profile", response_model=ApiResponse)
def create_profile(req: ProfileCreate, db: Session = Depends(get_db)):
    user_id = "U" + uuid.uuid4().hex[:8].upper()
    archive_code = _gen_archive_code(db)
    user = User(
        user_id=user_id,
        school_tier=req.school_tier,
        major_category=req.major_category,
        gpa_range=req.gpa_range,
        budget_range=req.budget_range,
        target_province=req.target_province,
        time_input=req.time_input,
        archive_code=archive_code,
        gender=req.gender,
        tags=json.dumps(req.tags or [], ensure_ascii=False),
        raw_text=req.raw_text,
    )
    db.add(user)
    db.commit()

    # 建档时若一并提交了测评，同步保存
    if req.psych:
        try:
            pv = score_psych(req.psych["phq9"], req.psych["gad7"])
        except (ValueError, KeyError, TypeError) as e:
            raise HTTPException(status_code=400, detail=f"心理测评作答有误：{e}")
        db.add(PsychAssess(
            user_id=user_id,
            phq9_total=pv["phq9_total"],
            phq9_level=pv["phq9_level"],
            gad7_total=pv["gad7_total"],
            gad7_level=pv["gad7_level"],
            self_harm_flag=int(pv["self_harm_flag"]),
            answers=json.dumps(req.psych, ensure_ascii=False),
        ))
    if req.holland:
        try:
            hv = score_holland(req.holland)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"兴趣测评作答有误：{e}")
        db.add(HollandAssess(
            user_id=user_id,
            r_score=hv["scores"]["R"], i_score=hv["scores"]["I"],
            a_score=hv["scores"]["A"], s_score=hv["scores"]["S"],
            e_score=hv["scores"]["E"], c_score=hv["scores"]["C"],
            top_code=hv["top_code"],
            answers=json.dumps(req.holland),
        ))
    db.commit()
    return ApiResponse(data=ProfileOut(
        user_id=user_id, archive_code=archive_code,
        gender=user.gender, tags=req.tags or [],
    ).model_dump())


# ============ I-08 自然语言建档解析（不写库，仅返回解析结果） ============
@app.post("/api/profile/parse", response_model=ApiResponse)
def parse_profile_text(req: ParseIn):
    result = parse_text(req.text)
    return ApiResponse(data=ParseOut(**result).model_dump())


# ============ I-09 个人特色存档：凭档案码找回 ============
@app.get("/api/archive/{code}", response_model=ApiResponse)
def get_archive(code: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.archive_code == code.upper().strip()).first()
    if not user:
        raise HTTPException(status_code=404, detail="档案不存在，请检查档案码")
    try:
        tags = json.loads(user.tags or "[]")
    except ValueError:
        tags = []
    assesses = (
        db.query(Assess)
        .filter(Assess.user_id == user.user_id)
        .order_by(Assess.created_at.desc())
        .all()
    )
    reports = [
        ArchiveReportItem(
            record_id=a.record_id,
            created_at=a.created_at.isoformat() if a.created_at else "",
            conclusion=a.conclusion,
        ).model_dump()
        for a in assesses
    ]
    profile = {
        "school_tier": user.school_tier,
        "major_category": user.major_category,
        "gpa_range": user.gpa_range,
        "budget_range": user.budget_range,
        "target_province": user.target_province,
        "time_input": user.time_input,
        "gender": user.gender,
    }
    decisions = (
        db.query(Decision)
        .filter(Decision.user_id == user.user_id)
        .order_by(Decision.created_at.desc())
        .all()
    )
    creds = (
        db.query(Credential)
        .filter(Credential.user_id == user.user_id)
        .order_by(Credential.created_at.desc())
        .all()
    )
    return ApiResponse(data=ArchiveOut(
        archive_code=user.archive_code,
        profile=profile,
        tags=tags,
        raw_text=user.raw_text,
        psych=_latest_psych(db, user.user_id),
        holland=_latest_holland(db, user.user_id),
        decisions=[
            ArchiveDecisionItem(
                decision_id=d.decision_id,
                path_name=d.chosen_path_name,
                created_at=d.created_at.isoformat() if d.created_at else "",
            ).model_dump()
            for d in decisions
        ],
        credentials=[
            ArchiveCredentialItem(
                credential_id=c.credential_id,
                path_name=PATH_NAMES.get(c.path_id, c.path_id),
                result=c.result,
                proof_type=c.proof_type or "其他",
                review_status=c.review_status,
                review_score=c.review_score,
                auto_integrated=(c.sample_id is not None),
                created_at=c.created_at.isoformat() if c.created_at else "",
            ).model_dump()
            for c in creds
        ],
        created_at=user.created_at.isoformat() if user.created_at else "",
        reports=reports,
    ).model_dump())


# ============ I-10 测评题目 ============
@app.get("/api/assessment/questions", response_model=ApiResponse)
def get_assessment_questions():
    return ApiResponse(data=assessment_questions())


@app.get("/api/assessment/external", response_model=ApiResponse)
def get_external_assessments():
    """外部补充测评链接跳转。系统内测评为主，仅供交叉验证，不构成依赖。"""
    return ApiResponse(data=external_assessments())


# ============ I-10 心理状态自评（PHQ-9 + GAD-7） ============
@app.post("/api/assessment/psych", response_model=ApiResponse)
def submit_psych(req: PsychIn, db: Session = Depends(get_db)):
    try:
        result = score_psych(req.phq9, req.gad7)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if req.user_id:
        user = db.query(User).filter(User.user_id == req.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        db.add(PsychAssess(
            user_id=req.user_id,
            phq9_total=result["phq9_total"],
            phq9_level=result["phq9_level"],
            gad7_total=result["gad7_total"],
            gad7_level=result["gad7_level"],
            self_harm_flag=int(result["self_harm_flag"]),
            answers=json.dumps({"phq9": req.phq9, "gad7": req.gad7}),
        ))
        db.commit()
    return ApiResponse(data=result)


# ============ I-11 霍兰德职业兴趣测评 ============
@app.post("/api/assessment/holland", response_model=ApiResponse)
def submit_holland(req: HollandIn, db: Session = Depends(get_db)):
    try:
        result = score_holland(req.answers)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if req.user_id:
        user = db.query(User).filter(User.user_id == req.user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        s = result["scores"]
        db.add(HollandAssess(
            user_id=req.user_id,
            r_score=s["R"], i_score=s["I"], a_score=s["A"],
            s_score=s["S"], e_score=s["E"], c_score=s["C"],
            top_code=result["top_code"],
            answers=json.dumps(req.answers),
        ))
        db.commit()
    return ApiResponse(data=HollandOut(**result).model_dump())


# ============ I-12 选定路径，生成执行方案 ============
@app.post("/api/decision", response_model=ApiResponse)
def create_decision(req: DecisionIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    path = db.query(Path).filter(Path.path_id == req.path_id).first()
    if not path:
        raise HTTPException(status_code=404, detail="路径不存在")

    probs_list = compute_probability(user, db)
    probs = {p["path_id"]: p for p in probs_list}
    feasibility = check_constraints(user, db)
    psych = _latest_psych(db, user.user_id)
    holland = _latest_holland(db, user.user_id)

    try:
        plan = build_plan(user, req.path_id, probs, psych, holland, feasibility)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    decision_id = "D" + uuid.uuid4().hex[:10].upper()
    row = Decision(
        decision_id=decision_id,
        user_id=user.user_id,
        chosen_path_id=req.path_id,
        chosen_path_name=path.name,
        plan=json.dumps(plan, ensure_ascii=False),
    )
    db.add(row)
    db.commit()
    return ApiResponse(data=DecisionOut(
        decision_id=decision_id,
        path_id=req.path_id,
        path_name=path.name,
        created_at=row.created_at.isoformat() if row.created_at else datetime.now().isoformat(),
        plan=plan,
    ).model_dump())


# ============ I-12 查询执行方案 ============
@app.get("/api/decision/{decision_id}", response_model=ApiResponse)
def get_decision(decision_id: str, db: Session = Depends(get_db)):
    row = db.query(Decision).filter(Decision.decision_id == decision_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="方案不存在")
    plan = json.loads(row.plan) if row.plan else {}
    return ApiResponse(data=DecisionOut(
        decision_id=row.decision_id,
        path_id=row.chosen_path_id,
        path_name=row.chosen_path_name,
        created_at=row.created_at.isoformat() if row.created_at else "",
        plan=plan,
    ).model_dump())


# ============ I-13 回填结果：上传凭证 + AI 审查 ============
@app.post("/api/credential/upload", response_model=ApiResponse)
async def upload_credential(
    user_id: str = Form(...),
    path_id: str = Form(...),
    result: str = Form(...),
    note: Optional[str] = Form(default=None, description="用户自述，如「拿到腾讯 SDE offer」"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if path_id not in ("P_KAOY", "P_KAOG", "P_JIUY"):
        raise HTTPException(status_code=400, detail="path_id 必须是考研/考公/就业之一")
    if result not in ("达成", "未达成"):
        raise HTTPException(status_code=400, detail="result 必须是 达成 或 未达成")

    raw = await file.read()
    try:
        saved = save_proof(raw, file.filename or "upload.bin")
    except ValueError as e:
        raise HTTPException(status_code=413, detail=str(e))

    review = ai_review(saved["path"], saved["category"], path_id, result)

    cred_id = "C" + uuid.uuid4().hex[:12].upper()
    new_sample = None
    if decide_integration(review["review_score"], review["review_status"]):
        sid = new_sample_id()
        s = Sample(
            sample_id=sid,
            path_id=path_id,
            feature_summary=f"{user.school_tier}+{user.major_category}+{user.gpa_range}"
                            + (f"+{user.gender}" if user.gender else ""),
            school_tier=user.school_tier,
            major_category=user.major_category,
            gpa_range=user.gpa_range,
            target_province=user.target_province,
            gender=user.gender,
            result=result,
            key_action=review.get("proof_type") or "用户回填",
        )
        db.add(s)
        new_sample = sid
    db.add(Credential(
        credential_id=cred_id,
        user_id=user_id,
        path_id=path_id,
        result=result,
        proof_type=review["proof_type"],
        proof_filename=saved["filename"],
        proof_path=saved["path"],
        proof_text=review["proof_text"],
        review_score=review["review_score"],
        review_note=review["review_note"],
        review_status=review["review_status"],
        verify_method=review["verify_method"],
        sample_id=new_sample,
    ))
    db.commit()

    return ApiResponse(data={
        "credential_id": cred_id,
        "path_id": path_id,
        "path_name": PATH_NAMES.get(path_id, path_id),
        "result": result,
        "proof_type": review["proof_type"],
        "review_status": review["review_status"],
        "review_score": review["review_score"],
        "review_note": review["review_note"],
        "verify_method": review["verify_method"],
        "auto_integrated": new_sample is not None,
        "sample_id": new_sample,
        "note": note,
    })


@app.get("/api/credential/{credential_id}", response_model=ApiResponse)
def get_credential(credential_id: str, db: Session = Depends(get_db)):
    row = db.query(Credential).filter(Credential.credential_id == credential_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="凭证不存在")
    return ApiResponse(data={
        "credential_id": row.credential_id,
        "path_id": row.path_id,
        "path_name": PATH_NAMES.get(row.path_id, row.path_id),
        "result": row.result,
        "proof_type": row.proof_type,
        "proof_filename": row.proof_filename,
        "review_status": row.review_status,
        "review_score": row.review_score,
        "review_note": row.review_note,
        "verify_method": row.verify_method,
        "sample_id": row.sample_id,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    })


# ============ 改动 1: 行为埋点 + 行为回流入样 ============

@app.post("/api/event/log", response_model=ApiResponse)
def log_event(req: EventLogIn, db: Session = Depends(get_db)):
    """前端行为埋点：直接入库，用于后续行为回流入样"""
    payload_str = None
    if req.payload is not None:
        payload_str = json.dumps(req.payload, ensure_ascii=False)
    row = Event(
        user_id=req.user_id,
        event_type=req.event_type,
        path_id=req.path_id,
        target=req.target,
        payload=payload_str,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ApiResponse(data={
        "event_id": row.id,
        "user_id": req.user_id,
        "event_type": req.event_type,
    })


@app.post("/api/event/settle", response_model=ApiResponse)
def settle_event_to_sample(req: EventSettleIn, db: Session = Depends(get_db)):
    """行为回流入样：根据用户所有行为事件，自动构造一条同辈样本入样库。

    逻辑（复用 credential.py 的「审查后入样」模式）：
    1. 拉取该用户全部 Event，按 event_type/path_id/payload 聚合
    2. 从 payload 里提取 offer/成绩 等关键信息 → 作为 key_action 和 feature_summary
    3. 构造一条 Sample，自动入样库
    """
    user = db.query(User).filter(User.user_id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if req.final_path not in ("P_KAOY", "P_KAOG", "P_JIUY"):
        raise HTTPException(status_code=400, detail="final_path 必须是 P_KAOY/P_KAOG/P_JIUY")
    if req.final_result not in ("达成", "未达成"):
        raise HTTPException(status_code=400, detail="final_result 必须是 达成 或 未达成")

    events = (db.query(Event)
              .filter(Event.user_id == req.user_id)
              .order_by(Event.created_at.asc())
              .all())

    # 聚合事件，构造 key_action 和 feature_summary
    extracted_info: Dict[str, Any] = {}
    path_actions_counter: Dict[str, List[str]] = {}
    key_action_parts: List[str] = []

    for ev in events:
        try:
            payload = json.loads(ev.payload) if ev.payload else {}
        except (ValueError, TypeError):
            payload = {}

        # offer 相关
        if ev.event_type == "credential_upload" and ev.path_id == "P_JIUY":
            if "offer_company" in payload:
                extracted_info["company"] = payload["offer_company"]
            if "offer_role" in payload:
                extracted_info["role"] = payload["offer_role"]
            if "offer_salary" in payload:
                extracted_info["salary"] = payload["offer_salary"]
            if "offer_city" in payload:
                extracted_info["city"] = payload["offer_city"]

        # path_selected / link_click → 作为 key_action 候选
        if ev.event_type == "path_selected":
            path_actions_counter.setdefault(ev.path_id or "", []).append("选定路径")
        if ev.event_type == "link_click":
            target = ev.target or ""
            if "leetcode" in target.lower() or "nowcoder" in target.lower():
                path_actions_counter.setdefault(ev.path_id or "", []).append("刷算法")
            elif "muchong" in target.lower() or "zhihu" in target.lower() and "导师" in target:
                path_actions_counter.setdefault(ev.path_id or "", []).append("联系导师")
            elif "zhipin" in target.lower() or "linkedin" in target.lower():
                path_actions_counter.setdefault(ev.path_id or "", []).append("投简历")

    # 构造 key_action 文本
    if req.final_path == "P_JIUY" and extracted_info.get("company") and extracted_info.get("role"):
        key_action_parts.append(f"拿到{extracted_info['company']}{extracted_info.get('role', '')}offer")
    if req.final_path == "P_KAOY":
        if "school_or_post" in extracted_info:
            key_action_parts.append(f"拟录取{extracted_info['school_or_post']}")
        else:
            key_action_parts.append("考研达成目标")
    if req.final_path == "P_KAOG":
        key_action_parts.append("公考通过")

    # 从 path_actions_counter 取 top action
    pid_actions = path_actions_counter.get(req.final_path, [])
    from collections import Counter as _C
    if pid_actions:
        cnt = _C(pid_actions)
        top_action = cnt.most_common(1)[0][0]
        key_action_parts.append(top_action)

    key_action = "；".join(key_action_parts) if key_action_parts else (req.note or "用户回填")

    # 构造 feature_summary（同 credential.py 的 build_sample_from_credential 逻辑）
    feature = (f"{user.school_tier}+{user.major_category}+{user.gpa_range}"
               + (f"+{user.gender}" if user.gender else ""))

    sid = new_sample_id()
    sample = Sample(
        sample_id=sid,
        path_id=req.final_path,
        feature_summary=feature,
        school_tier=user.school_tier,
        major_category=user.major_category,
        gpa_range=user.gpa_range,
        target_province=user.target_province,
        gender=user.gender,
        result=req.final_result,
        key_action=key_action[:40],
    )
    db.add(sample)

    # 把 settle 动作本身也写成一个 event
    settle_event = Event(
        user_id=req.user_id,
        event_type="event_settle",
        path_id=req.final_path,
        target="sample_auto_integrated",
        payload=json.dumps({
            "final_result": req.final_result,
            "key_action": key_action[:40],
            "sample_id": sid,
            "event_count": len(events),
        }, ensure_ascii=False),
    )
    db.add(settle_event)
    db.commit()

    return ApiResponse(data={
        "sample_id": sid,
        "path_id": req.final_path,
        "path_name": PATH_NAMES.get(req.final_path, req.final_path),
        "result": req.final_result,
        "key_action": key_action[:40],
        "event_count": len(events),
        "extracted": extracted_info,
    })


# ============ 改动 2: 文本版凭证上传（OCR 不可用时用户粘贴文字） ============

@app.post("/api/credential/text-upload", response_model=ApiResponse)
def upload_text_credential(req: CredentialTextIn, db: Session = Depends(get_db)):
    """用户粘贴的文字版 offer/成绩单，直接用规则抽取 + 审查。"""
    user = db.query(User).filter(User.user_id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if req.path_id not in ("P_KAOY", "P_KAOG", "P_JIUY"):
        raise HTTPException(status_code=400, detail="path_id 必须是考研/考公/就业之一")
    if req.result not in ("达成", "未达成"):
        raise HTTPException(status_code=400, detail="result 必须是 达成 或 未达成")

    review = review_text_credential(req.proof_text, req.path_id, req.result, req.proof_type)

    cred_id = "C" + uuid.uuid4().hex[:12].upper()
    new_sample_id_val = None
    if decide_integration(review["review_score"], review["review_status"]):
        new_sample_id_val = new_sample_id()
        s = Sample(
            sample_id=new_sample_id_val,
            path_id=req.path_id,
            feature_summary=(f"{user.school_tier}+{user.major_category}+{user.gpa_range}"
                             + (f"+{user.gender}" if user.gender else "")),
            school_tier=user.school_tier,
            major_category=user.major_category,
            gpa_range=user.gpa_range,
            target_province=user.target_province,
            gender=user.gender,
            result=req.result,
            key_action=review.get("proof_type") or "用户回填（文字）",
        )
        db.add(s)

    db.add(Credential(
        credential_id=cred_id,
        user_id=req.user_id,
        path_id=req.path_id,
        result=req.result,
        proof_type=review["proof_type"],
        proof_filename="pasted_text.txt",
        proof_path=None,
        proof_text=review["proof_text"],
        review_score=review["review_score"],
        review_note=review["review_note"],
        review_status=review["review_status"],
        verify_method=review["verify_method"],
        sample_id=new_sample_id_val,
    ))
    db.commit()

    extracted = review.get("extracted", {})
    return ApiResponse(data={
        "credential_id": cred_id,
        "path_id": req.path_id,
        "path_name": PATH_NAMES.get(req.path_id, req.path_id),
        "result": req.result,
        "proof_type": review["proof_type"],
        "review_status": review["review_status"],
        "review_score": review["review_score"],
        "review_note": review["review_note"],
        "verify_method": review["verify_method"],
        "auto_integrated": new_sample_id_val is not None,
        "sample_id": new_sample_id_val,
        "extracted": extracted,
        "note": req.note,
    })


# ============ I-14 机构目录（三路径对接真实信息源） ============
@app.get("/api/directory/{path_id}", response_model=ApiResponse)
def get_path_directory(path_id: str):
    data = get_directory(path_id)
    if not data:
        raise HTTPException(status_code=404, detail="路径不存在")
    return ApiResponse(data=data)


# ============ I-14b 省份目录（该省三路径对比 + 官方链接） ============
@app.get("/api/province/{province}/directory", response_model=ApiResponse)
def get_province_path_directory(province: str):
    data = get_province_directory(province)
    if not data:
        # 省份未配置专属目录，返回空字典让前端兜底
        return ApiResponse(data={"name": province, "note": "该省份暂未收录专属信息，请查看全国通用目录"})
    return ApiResponse(data=data)


# ============ I-15 约束 → 执行方案一键联动 ============
@app.post("/api/constraints/plan", response_model=ApiResponse)
def constraints_to_plan(req: DecisionIn, db: Session = Depends(get_db)):
    """把约束诊断的结果直接喂给执行方案，在修复建议的基础上生成分阶段计划。
       前端约束页点「生成执行方案」按钮时调这个。"""
    return create_decision(req, db)  # 与 /api/decision 逻辑相同


# ============ I-02 获取路径元数据 ============
@app.get("/api/paths", response_model=ApiResponse)
def get_paths(db: Session = Depends(get_db)):
    paths = db.query(Path).all()
    data = [PathOut(path_id=p.path_id, name=p.name, category=p.category).model_dump() for p in paths]
    return ApiResponse(data=data)


# ============ I-03 三路径概率模拟 ============
@app.post("/api/probability", response_model=ApiResponse)
def compute_path_probability(req: ProbabilityIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    probs = compute_probability(user, db)
    # 结合约束判定可行性
    feasibility = check_constraints(user, db)
    items = []
    for p in probs:
        f = feasibility.get(p["path_id"], {})
        feasible = f.get("feasible", True)
        items.append(ProbabilityItem(
            path_id=p["path_id"],
            path_name=p["path_name"],
            prob=p["prob"],
            lower=p["lower"],
            upper=p["upper"],
            n=p["n"],
            source=p["source"],
            feasible=feasible,
            reason=None if feasible else f.get("summary", "硬约束未通过"),
        ).model_dump())
    return ApiResponse(data=ProbabilityOut(items=items).model_dump())


# ============ I-04 同辈统计 ============
@app.get("/api/peers", response_model=ApiResponse)
def get_peers(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    result = match_peers(user, db)
    stats = [PeerStat(**s).model_dump() for s in result["stats"].values()]
    return ApiResponse(data=PeersOut(
        total=result["total"],
        stats=stats,
        features=result["features"],
        self_position=result.get("self_position", {}),
        profiles=result["profiles"],
        gaps=result["gaps"],
        gender_gaps=result.get("gender_gaps", {}),
        gender_comparison=result.get("gender_comparison", {}),
        key_actions=result["key_actions"],
        most_similar_core=result.get("most_similar_core", []),
        community_feed=result.get("community_feed", {}),
        top_matches=result["top_matches"],
        confidence=result["confidence"],
        gender_split=result.get("gender_split", {}),
    ).model_dump())


# ============ I-05 硬约束校验 ============
@app.post("/api/constraints/check", response_model=ApiResponse)
def check_user_constraints(req: ConstraintIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    feasibility = check_constraints(user, db)
    # 计算各路径概率，用于时间轴优先级方向建议
    probs_list = compute_probability(user, db)
    probs_dict = {p["path_id"]: p["prob"] for p in probs_list}
    diag = build_diagnosis(feasibility, probs_dict)
    all_violated = []
    overall_feasible = True
    feasible_count = 0
    for pid, f in feasibility.items():
        if f["feasible"]:
            feasible_count += 1
        else:
            overall_feasible = False
        for c in f["violated_rules"]:
            all_violated.append(RuleCheck(
                rule_id=c["rule_id"],
                constraint_item=c["constraint_item"],
                threshold=c["threshold"],
                is_hard=c["is_hard"],
                passed=c["passed"],
                detail=c["detail"],
            ).model_dump())
    summary = ("三条路径均可执行" if overall_feasible
               else f"{feasible_count} / 3 条路径可行，其余被硬约束卡住")
    return ApiResponse(data={
        "feasible": overall_feasible,
        "summary": summary,
        "violated_rules": all_violated,
        "paths": feasibility,
        **diag,
    })


# ============ I-06 获取决策报告 ============
@app.get("/api/report/{record_id}", response_model=ApiResponse)
def get_report(record_id: str, db: Session = Depends(get_db)):
    assess = db.query(Assess).filter(Assess.record_id == record_id).first()
    if not assess:
        raise HTTPException(status_code=404, detail="报告不存在")
    user = db.query(User).filter(User.user_id == assess.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    probs = compute_probability(user, db)
    feasibility = check_constraints(user, db)
    peers = match_peers(user, db)
    psych = _latest_psych(db, user.user_id)
    holland = _latest_holland(db, user.user_id)
    try:
        user_tags = json.loads(user.tags or "[]")
    except ValueError:
        user_tags = []

    cards = []
    for p in probs:
        f = feasibility.get(p["path_id"], {})
        feasible = f.get("feasible", True)
        violated = f.get("violated_rules", [])
        analysis = build_card_analysis(user, p["path_id"], feasible, violated,
                                       psych=psych, holland=holland)
        badge = "可行" if feasible else "不可行"
        conclusion = f.get("summary", "可行") if not feasible else f"校准概率 {p['prob']*100:.1f}%"
        fit = holland["path_fit"].get(p["path_id"]) if holland else None
        st = peers["stats"].get(p["path_id"], {})
        # 综合得分：概率 65% + 兴趣匹配 35%；不可行路径不参与排序
        if feasible:
            composite = p["prob"] if fit is None else p["prob"] * 0.65 + (fit / 100) * 0.35
        else:
            composite = None
        cards.append(ReportCard(
            path_name=p["path_name"],
            path_id=p["path_id"],
            probability=p["prob"] if feasible else None,
            lower=p["lower"] if feasible else None,
            upper=p["upper"] if feasible else None,
            sample_size=p["n"],
            feasible=feasible,
            conclusion=conclusion,
            badge=badge,
            strengths=analysis["strengths"],
            risks=analysis["risks"],
            actions=analysis["actions"],
            fit_score=fit,
            peer_rate=st.get("rate"),
            peer_success=st.get("success"),
            peer_total=st.get("total"),
            gap=peers["gaps"].get(p["path_id"], []),
            composite=round(composite, 4) if composite is not None else None,
            gender_split=peers["gender_split"].get(p["path_id"], {}),
        ).model_dump())

    # 三路径横向对比矩阵（按综合得分排序，不可行路径置后）
    ranked = sorted(
        cards,
        key=lambda c: (c["feasible"], c["composite"] or 0),
        reverse=True,
    )
    compare = []
    for i, c in enumerate(ranked, start=1):
        compare.append({
            "rank": i,
            "path_name": c["path_name"],
            "path_id": c["path_id"],
            "probability": round(c["probability"], 4) if c["probability"] is not None else None,
            "range": (f"{c['lower']*100:.0f}% ~ {c['upper']*100:.0f}%"
                      if c["probability"] is not None else "—"),
            "fit_score": round(c["fit_score"], 1) if c["fit_score"] is not None else None,
            "peer_rate": round(c["peer_rate"] * 100, 1) if c["peer_rate"] is not None else None,
            "peer_total": c["peer_total"],
            "composite": round(c["composite"] * 100, 1) if c["composite"] is not None else None,
            "feasible": c["feasible"],
        })

    # What-if 敏感度：只对可行路径分析
    feasible_ids = [c["path_id"] for c in cards if c["feasible"] and c.get("path_id")]
    what_if = build_what_if(user, db, feasible_ids)

    evidence = {
        "probability_source": {p["path_name"]: p["source"] for p in probs},
        "raw_vs_calibrated": {p["path_name"]: {"raw": p["raw_prob"], "calibrated": p["prob"]} for p in probs},
        "calib_version": probs[0]["calib_version"] if probs else "v202611",
        "constraints": {pid: f["summary"] for pid, f in feasibility.items()},
    }

    peers_evidence = {
        "total": peers["total"],
        "note": peers["features"]["note"],
        "paths": [
            {
                "path_name": s["path_name"],
                "total": s["total"],
                "success": s["success"],
                "rate": s["rate"],
            }
            for s in peers["stats"].values()
        ],
    }

    # 一句话结论：概率 + 兴趣匹配 + 排除 + 同辈佐证 + 情绪状态
    def composite(c):
        """综合得分：概率 65% + 兴趣匹配度 35%（无测评则仅用概率）"""
        if c.get("fit_score") is None:
            return c["probability"]
        return c["probability"] * 0.65 + (c["fit_score"] / 100) * 0.35

    feasibles = [c for c in cards if c["feasible"]]
    if feasibles:
        best = max(feasibles, key=composite)
        conclusion = f"建议主攻{best['path_name']}（校准概率{best['probability']*100:.0f}%"
        if best.get("fit_score") is not None:
            conclusion += f"，兴趣匹配度{best['fit_score']:.0f}/100"
        conclusion += "）"
        others = sorted((c for c in feasibles if c is not best), key=lambda x: -composite(x))
        if others:
            conclusion += f"，{others[0]['path_name']}可作备选"
        infeasibles = [c for c in cards if not c["feasible"]]
        if infeasibles:
            conclusion += f"；{infeasibles[0]['path_name']}本年度因硬约束排除"
        conclusion += "。"
        for pid, s in peers["stats"].items():
            if s["path_name"] == best["path_name"] and s["total"] > 0:
                conclusion += f"与你相似的{s['total']}位同辈中，{s['success']}人通过该路径达成目标（{round(s['rate']*100)}%）。"
                break
        # 概率与兴趣不匹配时给出提醒
        if holland and best.get("fit_score") is not None and best["fit_score"] < 50:
            conclusion += f"注意：你的兴趣测评前三位是 {holland['top_code']}，与该路径匹配度偏低，执行时需要额外的动机管理。"
        # 情绪状态影响
        if psych:
            if psych["advice"]["urgent"]:
                conclusion += "另外，你的心理自评显示当前情绪负荷较重，建议先处理情绪状态，上述路径可暂缓 2-4 周再启动。"
            elif psych["advice"]["level"] == "关注":
                conclusion += "考虑到你当前存在中度情绪困扰，建议同步预约学校心理咨询，并把执行节奏调低 20%。"
        if "决策焦虑" in user_tags and not psych:
            conclusion += "三条路径的量化对比已经给出，先聚焦最高概率路径行动起来，焦虑会随行动下降。"
    else:
        conclusion = "三条路径均存在硬约束障碍，建议按下方的修复建议调整条件后重新评估。"

    return ApiResponse(data=ReportOut(
        record_id=record_id,
        user_id=assess.user_id,
        archive_code=user.archive_code,
        conclusion=conclusion,
        tags=user_tags,
        cards=cards,
        peers_evidence=peers_evidence,
        evidence=evidence,
        psych=psych,
        holland=holland,
        compare=compare,
        what_if=what_if,
        confidence=peers["confidence"],
        created_at=assess.created_at.isoformat() if assess.created_at else datetime.now().isoformat(),
    ).model_dump())


# ============ I-07 匿名回填真实结果 ============
@app.post("/api/feedback", response_model=ApiResponse)
def submit_feedback(req: FeedbackIn, db: Session = Depends(get_db)):
    sample_id = "S" + uuid.uuid4().hex[:8].upper()
    sample = Sample(
        sample_id=sample_id,
        path_id=req.path_id,
        school_tier=req.school_tier,
        major_category=req.major_category,
        gpa_range=req.gpa_range,
        target_province=req.target_province,
        feature_summary=f"{req.school_tier}+{req.major_category}+{req.gpa_range}",
        result=req.result,
    )
    db.add(sample)
    db.commit()
    return ApiResponse(data=FeedbackOut(sample_id=sample_id).model_dump())


# ============ 辅助：生成决策报告（供前端演示调用） ============
@app.post("/api/report/generate", response_model=ApiResponse)
def generate_report(user_id: str, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    # 已有报告则复用同一条记录：get_report 会按最新档案与测评实时重算，
    # 这样补充测评后刷新不会堆积重复的历史报告。
    latest = (db.query(Assess).filter(Assess.user_id == user_id)
              .order_by(Assess.created_at.desc()).first())
    if latest:
        return ApiResponse(data={"record_id": latest.record_id})
    record_id = "R" + uuid.uuid4().hex[:8].upper()
    # 取第一条路径的概率作为示例记录入库
    probs = compute_probability(user, db)
    if probs:
        p = probs[0]
        assess = Assess(
            record_id=record_id,
            user_id=user_id,
            path_id=p["path_id"],
            probability=p["prob"],
            lower_bound=p["lower"],
            upper_bound=p["upper"],
            sample_size=p["n"],
            calib_version=p["calib_version"],
            conclusion="已生成",
            evidence=str(probs),
        )
        db.add(assess)
        db.commit()
    return ApiResponse(data={"record_id": record_id})


# ============ 托管前端打包产物（存在 dist 时，一个进程即可运行整个系统） ============
import os
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 兼容两种目录结构：本地开发时 frontend/dist/，部署时可能直接在根目录 dist/
_DIST = os.path.join(_BASE, "frontend", "dist")
if not os.path.isdir(_DIST):
    _DIST = os.path.join(_BASE, "dist")
if os.path.isdir(_DIST):
    # 首页禁止缓存：前端重新构建后，浏览器会立刻拿到新的 index.html 与新的 JS 文件名，
    # 避免用户看到旧界面（这是升级后"页面没变化"的最常见原因）。
    @app.get("/", include_in_schema=False)
    def _index():
        return FileResponse(
            os.path.join(_DIST, "index.html"),
            headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
        )

    app.mount("/", StaticFiles(directory=_DIST, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
