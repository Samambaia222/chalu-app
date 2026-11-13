"""决策洞察：What-if 敏感度分析
   固定其他条件，单独抬升一个可控变量，重算概率，
   回答"现在最值得投入的改进方向是什么"。"""
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from ..models import User
from .probability import compute_probability

GPA_NEXT = {"2.0-2.5": "2.5-3.0", "2.5-3.0": "3.0-3.5",
            "3.0-3.5": "3.5-4.0", "3.5-4.0": None}
TIER_NEXT = {"其他": "二本", "二本": "一本", "一本": "211", "211": "985", "985": None}
TIME_NEXT = {"<3月": "3-6月", "3-6月": "6-12月", "6-12月": "≥12月", "≥12月": None}

PATH_LABEL = {"P_KAOY": "考研", "P_KAOG": "考公", "P_JIUY": "就业"}


def _clone(user: User, **kw) -> User:
    """构造一个未入库的 User 副本，仅用于重算概率"""
    return User(
        user_id=user.user_id,
        school_tier=kw.get("school_tier", user.school_tier),
        major_category=user.major_category,
        gpa_range=kw.get("gpa_range", user.gpa_range),
        budget_range=user.budget_range,
        target_province=user.target_province,
        time_input=kw.get("time_input", user.time_input),
    )


def _probs(user: User, db: Session) -> Dict[str, float]:
    return {p["path_id"]: p["prob"] for p in compute_probability(user, db)}


def build_what_if(user: User, db: Session,
                  feasible_ids: Optional[List[str]] = None) -> Dict[str, Any]:
    base = _probs(user, db)
    if feasible_ids is None:
        feasible_ids = list(base.keys())

    scenarios = []
    spec = [
        ("GPA 提升一档", GPA_NEXT.get(user.gpa_range),
         f"{user.gpa_range} → {GPA_NEXT.get(user.gpa_range)}", {"gpa_range": GPA_NEXT.get(user.gpa_range)}),
        ("院校层次提升一档", TIER_NEXT.get(user.school_tier),
         f"{user.school_tier} → {TIER_NEXT.get(user.school_tier)}", {"school_tier": TIER_NEXT.get(user.school_tier)}),
        ("备考时间延长一档", TIME_NEXT.get(user.time_input),
         f"{user.time_input} → {TIME_NEXT.get(user.time_input)}", {"time_input": TIME_NEXT.get(user.time_input)}),
    ]

    for label, target, change_text, kw in spec:
        if target is None:
            continue
        alt = _probs(_clone(user, **kw), db)
        impact = []
        for pid in feasible_ids:
            before = base.get(pid, 0.0)
            after = alt.get(pid, 0.0)
            impact.append({
                "path_id": pid,
                "path_name": PATH_LABEL.get(pid, pid),
                "from": round(before, 4),
                "to": round(after, 4),
                "delta": round(after - before, 4),
            })
        impact.sort(key=lambda x: -x["delta"])
        if impact and impact[0]["delta"] > 0.001:
            scenarios.append({
                "label": label,
                "change": change_text,
                "impact": impact,
                "best_gain": impact[0]["delta"],
                "best_path": impact[0]["path_name"],
            })

    scenarios.sort(key=lambda x: -x["best_gain"])

    if scenarios:
        top = scenarios[0]
        advice = (f"如果{top['label'].replace('提升', '能提升').replace('延长', '能延长')}"
                  f"（{top['change']}），{top['best_path']}概率约提升 "
                  f"{round(top['best_gain'] * 100)} 个百分点，是当前性价比最高的调整方向。")
    else:
        advice = "你的可控条件已接近上限，继续提升概率更多依赖执行质量而非条件改变。"

    return {
        "base": {PATH_LABEL.get(k, k): round(v, 4) for k, v in base.items()},
        "scenarios": scenarios[:3],
        "advice": advice,
    }
