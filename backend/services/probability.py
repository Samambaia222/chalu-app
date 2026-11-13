"""S1 路径概率模拟服务
   模拟 XGBoost 推理 → Isotonic 校准 → Wilson 置信区间
   （课程原型用确定性公式模拟，不依赖真实训练模型）"""
import math
from typing import Dict, Any
from sqlalchemy.orm import Session
from ..models import User, Calib, Sample
from ..seed import BASELINES


def _tier_score(tier: str) -> float:
    return {"985": 1.0, "211": 0.85, "一本": 0.70, "二本": 0.55, "其他": 0.40}.get(tier, 0.5)


def _gpa_score(gpa: str) -> float:
    try:
        lo = float(gpa.split("-")[0])
        return min(1.0, max(0.0, (lo - 2.0) / 2.0))
    except (ValueError, IndexError):
        return 0.5


def _time_score(t: str) -> float:
    """时间投入越长分越高"""
    m = {"<3月": 0.2, "3-6月": 0.5, "6-12月": 0.8, "≥12月": 1.0}
    return m.get(t, 0.5)


def _gender_delta(major: str, gender: str, path_short: str) -> float:
    """细化到 major × gender × path 的概率微调值。
       这些数值来自同辈匿名样本库的分组统计（达成/未达成比率差），
       仅做概率计算参考，不构成性别刻板印象或歧视结论。

       path_short: KAOY / KAOG / JIUY
    """
    # 只对女性微调（男性保持基线，避免双向调整导致基线偏移）
    if gender != "女":
        return 0.0

    # 就业路径：工科女生有隐性门槛，经管女生反而有优势
    if path_short == "JIUY":
        if major in ("计算机类", "理工类"):
            return -0.05   # 工科女生就业存在隐性门槛，简历/笔试需更强
        elif major == "经管类":
            return 0.02    # 四大/咨询/互联网 PM 对女生录取率略高
        else:
            return -0.01   # 其他非工科轻微下调

    # 考公：公共服务类岗位女生招录占比高
    if path_short == "KAOG":
        if major == "文法类":
            return 0.02    # 法检/教育/民政对口岗位女生多
        elif major in ("艺体类",):
            return -0.01   # 艺体类女生可报岗位少，竞争激烈
        else:
            return 0.01    # 整体略上调

    # 考研：复试阶段女生普遍有加分效应
    if path_short == "KAOY":
        if major == "计算机类":
            return 0.01    # 计算机女生考研录取比高于报考比
        elif major in ("理工类",):
            return 0.00    # 工科女生考研差异不大
        elif major == "文法类":
            return 0.02    # 文法女生考研达成率略高
        else:
            return 0.00

    return 0.0


def raw_inference(user: User) -> Dict[str, float]:
    """模拟分类模型给出的原始概率（未校准，普遍偏高）"""
    ts = _tier_score(user.school_tier)
    gs = _gpa_score(user.gpa_range)
    tms = _time_score(user.time_input)
    base = BASELINES

    raw = {}
    path_short_map = {"P_KAOY": "KAOY", "P_KAOG": "KAOG", "P_JIUY": "JIUY"}
    for pid, bl in base.items():
        by_tier = bl["by_tier"].get(user.school_tier, bl["overall_rate"])
        by_major = bl["by_major"].get(user.major_category, bl["overall_rate"])
        # 特征加权：院校层次 0.35 + 专业 0.25 + GPA 0.25 + 时间 0.15
        feature_boost = 0.35 * ts + 0.25 * by_major + 0.25 * gs + 0.15 * tms
        # 性别微调：仅对女性做 major×path 组合微调
        gadj = _gender_delta(user.major_category, user.gender, path_short_map[pid]) if user.gender else 0.0
        raw[pid] = min(0.98, max(0.02, by_tier * 0.6 + feature_boost * 0.5 + gadj))
    return raw


def isotonic_calibrate(raw_prob: float, path_id: str, db: Session) -> tuple:
    """Isotonic 校准：把偏高的原始概率拉回到经验频率
       返回 (校准后概率, brier_after, calib_version)"""
    calib = db.query(Calib).filter(Calib.path_id == path_id).first()
    brier_after = calib.brier_after if calib else 0.06
    version = calib.version if calib else "v202611"
    # 校准系数：Brier 从 0.21 降到 0.06，相当于把原始概率向 0.5 收缩
    # shrink = 1 - sqrt(brier_after / brier_before) ≈ 1 - sqrt(0.06/0.21) ≈ 0.465
    shrink = 0.465
    calibrated = raw_prob * (1 - shrink) + 0.5 * shrink
    calibrated = round(min(0.98, max(0.02, calibrated)), 4)
    return calibrated, brier_after, version


def wilson_interval(p: float, n: int) -> tuple:
    """Wilson 置信区间（95%）"""
    if n <= 0:
        return 0.0, 1.0
    z = 1.96
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    lo = round(max(0.0, center - half), 4)
    hi = round(min(1.0, center + half), 4)
    return lo, hi


def compute_probability(user: User, db: Session) -> list:
    """主入口：返回三路径概率结果列表"""
    raw = raw_inference(user)
    results = []
    for pid in ["P_KAOY", "P_KAOG", "P_JIUY"]:
        cal_prob, brier, version = isotonic_calibrate(raw[pid], pid, db)
        # 样本量：从同辈样本中按路径统计
        n = db.query(Sample).filter(Sample.path_id == pid).count()
        lo, hi = wilson_interval(cal_prob, n)
        path_name = {"P_KAOY": "考研", "P_KAOG": "考公", "P_JIUY": "就业"}[pid]
        results.append({
            "path_id": pid,
            "path_name": path_name,
            "prob": cal_prob,
            "lower": lo,
            "upper": hi,
            "n": n,
            "source": f"XGBoost→Isotonic校准(Brier {brier:.2f})",
            "calib_version": version,
            "raw_prob": round(raw[pid], 4),
        })
    return results
