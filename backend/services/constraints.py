"""S3 硬约束可行性过滤服务

在"一票否决"之外，额外输出四类诊断信息：
  1. matrix      —— 三路径 × 全规则矩阵（通过项也展示，不再只列红叉）
  2. bottlenecks —— 卡点排序（哪条规则卡掉了最多路径）
  3. unlock      —— 最小解锁方案（还差什么、改到什么程度就能可行）
  4. timeline    —— 时间轴冲突（考研初试 / 国考 / 秋招 的关键期重叠）
"""
from datetime import date
from typing import Any, Dict, List, Tuple

from sqlalchemy.orm import Session

from ..models import Rule, User

PATH_IDS = ["P_KAOY", "P_KAOG", "P_JIUY"]
PATH_NAMES = {"P_KAOY": "考研", "P_KAOG": "考公", "P_JIUY": "就业"}

# 各路径的关键时间窗口（月份，用于并行冲突检测）
TIMELINE = {
    "P_KAOY": [(9, 12, "报名 + 初试冲刺"), (3, 4, "复试")],
    "P_KAOG": [(10, 11, "国考笔试"), (3, 4, "省考")],
    "P_JIUY": [(9, 11, "秋招"), (3, 5, "春招")],
}


def check_constraints(user: User, db: Session) -> Dict[str, Any]:
    """主入口：返回每条路径的约束校验结果（保持原有字段以兼容报告链路）"""
    rules = db.query(Rule).all()
    today = date.today()

    results_by_path: Dict[str, List[Dict[str, Any]]] = {p: [] for p in PATH_IDS}

    for rule in rules:
        applicable = PATH_IDS if rule.path_id == "P_ALL" else [rule.path_id]
        for pid in applicable:
            if pid not in results_by_path:
                continue
            results_by_path[pid].append(_evaluate_rule(rule, user, pid, today))

    feasibility: Dict[str, Any] = {}
    for pid in PATH_IDS:
        checks = results_by_path[pid]
        violated_hard = [c for c in checks
                         if c["is_hard"] == 1 and c["status"] == "fail"]
        passed_count = sum(1 for c in checks if c["status"] != "fail")
        feasible = len(violated_hard) == 0

        if feasible:
            summary = "可行" if not any(c["status"] == "warn" for c in checks) \
                else "可行（有前置条件需注意）"
        else:
            reasons = "、".join(c["constraint_item"] for c in violated_hard)
            summary = f"不可行（硬约束未通过：{reasons}）"

        feasibility[pid] = {
            "path_name": PATH_NAMES[pid],
            "feasible": feasible,
            "violated_rules": violated_hard,
            "all_checks": checks,
            "passed_count": passed_count,
            "total_count": len(checks),
            "summary": summary,
        }

    return feasibility


def build_diagnosis(feasibility: Dict[str, Any],
                    probabilities: Dict[str, float] | None = None) -> Dict[str, Any]:
    """把逐路径结果聚合成矩阵、卡点、解锁方案、时间轴冲突与优先级方向建议。
       probabilities: 各路径校准后的可行概率（0-1），用于冲突时排序权重。"""
    tl_raw = _build_timeline()
    recommendations = _build_timeline_recommendations(feasibility, probabilities)
    return {
        "matrix": _build_matrix(feasibility),
        "bottlenecks": _build_bottlenecks(feasibility),
        "unlock": _build_unlock(feasibility),
        "timeline": {
            "conflicts": tl_raw,
            "direction_recommendations": recommendations,
        },
    }


# ---------------- 规则判定 ----------------

def _evaluate_rule(rule: Rule, user: User, pid: str, today: date) -> Dict[str, Any]:
    """单条规则判定，返回带可解性的结构化结果"""
    item = rule.constraint_item
    base = {
        "rule_id": rule.rule_id,
        "constraint_item": item,
        "threshold": rule.threshold,
        "is_hard": rule.is_hard,
        "path_id": pid,
        "status": "pass",
        "passed": True,
        "detail": "满足要求",
        "solvability": None,
        "fix": None,
        "weight_impact": 0.0,
    }

    if item == "学历门槛":
        needs_master = user.target_province in ("北京", "上海")
        if needs_master:
            base.update({
                "status": "fail", "passed": False,
                "detail": f"{user.target_province}部分岗位要求硕士，本科不可报",
                "solvability": "changeable",
                "fix": f"改报其他省份，或先读研再报考{user.target_province}岗位",
            })
        else:
            base["detail"] = "本科满足基本学历要求"
        return base

    if item == "报名截止":
        return _check_deadline(base, pid, today)

    if item == "预算上限":
        try:
            budget_val = float(str(user.budget_range)
                               .replace("万", "").replace(">", "").replace("<", "")
                               .split("-")[0])
        except (ValueError, TypeError):
            base["detail"] = "预算未填写，默认通过"
            return base

        if budget_val <= 1.5:
            base["detail"] = f"预算{user.budget_range}，未超 1.5 万上限"
        else:
            base.update({
                "status": "fail", "passed": False,
                "detail": f"预算{user.budget_range}，超出 1.5 万上限",
                "solvability": "changeable",
                "fix": "压缩备考支出：改用免费网课 + 二手资料，或申请助学贷款/兼职补足差额",
            })
        return base

    if item == "时间投入":
        ok = user.time_input in ("6-12月", "≥12月")
        if ok:
            base["detail"] = f"时间投入{user.time_input}，满足 6 个月要求"
        else:
            base.update({
                "status": "fail", "passed": False,
                "detail": f"时间投入{user.time_input}，不足 6 个月",
                "solvability": "changeable",
                "fix": "把每日投入提到 4 小时以上，或改为「先就业再在职备考」的两段式方案",
            })
        return base

    if item == "应届身份":
        base["detail"] = "应届身份满足"
        return base

    if item == "目标院校层次":
        base.update({
            "status": "warn",
            "detail": "目标院校层次高于自身两档以上，软约束降权（不影响可行性）",
            "solvability": "changeable",
            "fix": "下调一档目标院校，或补充科研/竞赛成果对冲本科背景劣势",
            "weight_impact": -4.0,
        })
        return base

    base["detail"] = "默认通过"
    return base


def _check_deadline(base: Dict[str, Any], pid: str, today: date) -> Dict[str, Any]:
    """报名截止：按当前月份与路径报名窗口动态判断，而不是写死不可行"""
    m = today.month

    if pid == "P_KAOY":
        if m in (9, 10):
            base["detail"] = "报名窗口开放中（9-10 月），可参加本年度初试"
        elif m in (11, 12, 1, 2):
            base.update({
                "status": "fail", "passed": False,
                "detail": "本年度报名已于 10 月截止，只能在明年 9 月报下一次",
                "solvability": "wait",
                "fix": "转「二战」时间线：明年 9 月报名、12 月初试。这 10 个月可用于实习或工作积累",
            })
        else:
            base["detail"] = f"距下一年度报名（9 月）还有约 {9 - m} 个月，时间充足"
        return base

    if pid == "P_KAOG":
        if m in (10, 11):
            base.update({
                "status": "warn", "passed": True,
                "detail": "国考报名已截止，但省考 3 月报名仍开放，可转省考",
                "solvability": "changeable",
                "fix": "改走省考/选调生：3 月报名、4 月笔试，备考周期约 4 个月",
            })
        elif m in (2, 3):
            base["detail"] = "省考报名窗口开放中"
        else:
            base["detail"] = "下一轮省考（3 月）尚有充足准备时间"
        return base

    # 就业：秋招 9-11 月进行中
    if m in (9, 10, 11):
        base["detail"] = "秋招进行中，可立即投递"
    elif m in (3, 4, 5):
        base["detail"] = "春招进行中，可立即投递"
    else:
        base["detail"] = "处于招聘淡季，可提前准备简历与实习"
    return base


# ---------------- 诊断聚合 ----------------

def _build_matrix(feasibility: Dict[str, Any]) -> List[Dict[str, Any]]:
    """三路径 × 全规则矩阵
    按「约束项」合并同行：同一条约束（如报名截止）在不同路径下可能是
    不同规则记录，合并后才能直观看出它对三条路径的影响差异。"""
    rows: List[Dict[str, Any]] = []
    index: Dict[str, Dict[str, Any]] = {}

    for pid in PATH_IDS:
        for c in feasibility[pid]["all_checks"]:
            key = c["constraint_item"]
            if key not in index:
                row = {
                    "constraint_item": key,
                    "rule_ids": [],
                    "threshold": c["threshold"],
                    "is_hard": c["is_hard"],
                    "cells": {},
                }
                index[key] = row
                rows.append(row)
            index[key]["rule_ids"].append(c["rule_id"])
            index[key]["cells"][pid] = {
                "status": c["status"],
                "detail": c["detail"],
                "solvability": c["solvability"],
            }
    return rows


def _build_bottlenecks(feasibility: Dict[str, Any]) -> List[Dict[str, Any]]:
    """统计每条硬约束卡掉了几条路径，按影响面排序"""
    agg: Dict[str, Dict[str, Any]] = {}
    for pid in PATH_IDS:
        for c in feasibility[pid]["all_checks"]:
            if c["is_hard"] != 1 or c["status"] != "fail":
                continue
            item = c["constraint_item"]
            if item not in agg:
                agg[item] = {
                    "constraint_item": item,
                    "blocked_count": 0,
                    "blocked_paths": [],
                    "solvability": c["solvability"],
                    "fix": c["fix"],
                }
            agg[item]["blocked_count"] += 1
            agg[item]["blocked_paths"].append(PATH_NAMES[pid])

    result = sorted(agg.values(), key=lambda x: (-x["blocked_count"], x["constraint_item"]))
    for i, b in enumerate(result, 1):
        b["rank"] = i
    return result


def _build_unlock(feasibility: Dict[str, Any]) -> List[Dict[str, Any]]:
    """对不可行路径给出最小解锁方案"""
    out = []
    for pid in PATH_IDS:
        f = feasibility[pid]
        if f["feasible"]:
            continue
        blockers = f["violated_rules"]
        if not blockers:
            continue

        if len(blockers) == 1:
            b = blockers[0]
            headline = f"仅差「{b['constraint_item']}」一项"
        else:
            headline = f"需同时解决 {len(blockers)} 项硬约束"

        out.append({
            "path_id": pid,
            "path_name": PATH_NAMES[pid],
            "blocker_count": len(blockers),
            "single_fix_possible": len(blockers) == 1,
            "headline": headline,
            "steps": [
                {
                    "constraint_item": b["constraint_item"],
                    "detail": b["detail"],
                    "solvability": b["solvability"],
                    "fix": b["fix"],
                    "wait": b["solvability"] == "wait",
                }
                for b in blockers
            ],
        })
    return out


def _build_timeline() -> List[Dict[str, Any]]:
    """两两路径的关键期重叠检测"""
    pairs: List[Tuple[str, str]] = [
        ("P_KAOY", "P_JIUY"),
        ("P_KAOY", "P_KAOG"),
        ("P_KAOG", "P_JIUY"),
    ]
    out = []
    for a, b in pairs:
        overlaps = []
        for s1, e1, n1 in TIMELINE[a]:
            m1 = set(range(s1, e1 + 1))
            for s2, e2, n2 in TIMELINE[b]:
                m2 = set(range(s2, e2 + 1))
                common = sorted(m1 & m2)
                if common:
                    overlaps.append({
                        "months": f"{common[0]}—{common[-1]} 月",
                        "a_task": n1,
                        "b_task": n2,
                        "month_count": len(common),
                    })

        total = sum(o["month_count"] for o in overlaps)
        if total >= 5:
            level, advice = "高", f"{PATH_NAMES[a]}与{PATH_NAMES[b]}在关键期高度重叠，不建议同期全力并行，需明确主次"
        elif total >= 3:
            level, advice = "中", f"{PATH_NAMES[a]}与{PATH_NAMES[b]}有较长重叠期，可并行但必须提前 1-2 个月错峰准备"
        elif total >= 1:
            level, advice = "低", f"{PATH_NAMES[a]}与{PATH_NAMES[b]}仅短期重叠，基本可以兼顾"
        else:
            level, advice = "无", f"{PATH_NAMES[a]}与{PATH_NAMES[b]}关键期不冲突，可并行推进"

        out.append({
            "pair": [PATH_NAMES[a], PATH_NAMES[b]],
            "level": level,
            "overlap_months": total,
            "details": overlaps,
            "advice": advice,
        })
    return out


# ---------------- 冲突优先级方向建议 ----------------

# 各路径默认时间投入需求（并行冲突时，投入需求高的应优先）
PATH_INPUT_DEMAND = {
    "P_KAOY": {"months": 9, "intensity": "高", "label": "考研全年备考，需要稳定的 6-12 个月连续投入"},
    "P_KAOG": {"months": 5, "intensity": "中", "label": "考公集中在考前 4-6 个月冲刺，笔试后还需面试"},
    "P_JIUY": {"months": 3, "intensity": "中低", "label": "秋招/春招是阶段性高强度，其他时段可灵活安排"},
}


def _build_timeline_recommendations(
    feasibility: Dict[str, Any],
    probabilities: Dict[str, float] | None = None,
) -> List[Dict[str, Any]]:
    """综合硬约束、校准概率、冲突强度，给三路径打优先级分。
    
    优先级分 = feasibility_score × calibration_prob × (1 - conflict_penalty)
    - feasibility_score: 可行=1.0，不可行按硬约束通过率折算
    - calibration_prob: 概率服务传来的校准后可行概率，默认 0.5
    - conflict_penalty: 与其他路径的关键期重叠程度，0-1
    """
    # 1. 计算每条路径的冲突惩罚
    conflict_penalty: Dict[str, float] = {pid: 0.0 for pid in PATH_IDS}
    for pair_overlap in _build_timeline():
        pnames = pair_overlap["pair"]
        pids = [k for k, v in PATH_NAMES.items() if v in pnames]
        penalty = min(pair_overlap["overlap_months"] / 6.0, 1.0)  # 6 个月 = 最高惩罚
        for pid in pids:
            conflict_penalty[pid] = max(conflict_penalty[pid], penalty)

    # 2. 逐路径打分
    scored: List[Dict[str, Any]] = []
    for pid in PATH_IDS:
        feas = feasibility.get(pid, {})
        if feas.get("feasible"):
            fs = 1.0
        else:
            passed = feas.get("passed_count", 0)
            total = feas.get("total_count", 1)
            fs = max(passed / total, 0.2)  # 不可行但还有参考价值

        cp = (probabilities or {}).get(pid, 0.5)
        # 投入需求也加分：投入高的方向一旦选定，沉没成本更高
        input_bonus = PATH_INPUT_DEMAND[pid]["months"] / 12.0  # 9个月的考研得 0.75

        penalty = conflict_penalty[pid]
        final_score = round(fs * cp * (1 - penalty * 0.5) + input_bonus * 0.1, 4)

        reasons = []
        if feas.get("feasible"):
            reasons.append("约束全部通过")
        else:
            reasons.append(feas.get("summary", "存在约束障碍"))
        if cp >= 0.55:
            reasons.append(f"校准可行概率 {cp*100:.0f}%")
        elif cp <= 0.35:
            reasons.append(f"校准可行概率 {cp*100:.0f}%，需大幅加码")
        if penalty >= 0.5:
            reasons.append(f"与其他路径存在强时间冲突")

        scored.append({
            "path_id": pid,
            "path_name": PATH_NAMES[pid],
            "priority_score": final_score,
            "feasibility_score": round(fs, 3),
            "calibration_prob": round(cp, 3),
            "conflict_penalty": round(penalty, 3),
            "input_demand": PATH_INPUT_DEMAND[pid]["label"],
            "reasons": reasons,
        })

    # 3. 排序并给建议文案
    scored.sort(key=lambda x: x["priority_score"], reverse=True)
    top = scored[0]
    others = scored[1:]

    # 侧重建议
    if top["priority_score"] - others[0]["priority_score"] >= 0.15:
        top["direction"] = "建议侧重此方向"
        top["suggestion"] = (
            f"该方向综合优先级最高，建议作为主线投入 70-80% 的时间。"
            f"在【{PATH_INPUT_DEMAND[top['path_id']]['months']}个月关键期】"
            f"集中冲刺，其他方向降级为「保底计划」，错开关键期或只做最低限度的信息收集。"
        )
    elif top["priority_score"] - others[0]["priority_score"] >= 0.05:
        top["direction"] = "可作为主要方向"
        top["suggestion"] = (
            f"该方向优先级略高，建议投入 55-65% 主力资源。"
            f"可与 {others[0]['path_name']} 并行，但必须提前错峰 1-2 个月，"
            f"避免在【9-11月秋招+考研报名+国考】这类多线重叠期同时全力推进。"
        )
    else:
        top["direction"] = "方向接近，可并行"
        top["suggestion"] = (
            f"三方向综合分差距很小，说明各有优劣势。"
            f"建议按【时间投入门槛】选主线：考研需连续备考 {PATH_INPUT_DEMAND['P_KAOY']['months']} 个月，"
            f"投入最高；考公次之；就业阶段性最强。如果时间紧张，优先选投入门槛最低的方向，"
            f"把最确定的一条先跑通，再考虑第二条。"
        )

    # 次方向建议
    for s in others:
        s["direction"] = "降级为保底 / 次要方向"
        if s["conflict_penalty"] >= 0.5:
            s["suggestion"] = (
                f"与主线时间冲突较大，建议错峰："
                f"在主线的关键期（如 9-12 月考研初试冲刺 / 秋招 / 国考）只做最低限度准备，"
                f"把该方向的关键窗口推迟到主线结束后再启动。"
            )
        else:
            s["suggestion"] = (
                f"与主线时间冲突不大，可并行做辅助准备："
                f"每周投入 5-8 小时（约总时间的 20-30%），保持信息跟进，不做全力冲刺。"
            )

    # 整体汇总
    overall = {
        "summary": f"在三路径存在并行冲突的情况下，建议优先侧重【{top['path_name']}】方向，{others[0]['path_name']}作为保底。",
        "tradeoff": (
            "冲突解决策略：先跑通主线再看第二条。"
            "因为时间是稀缺资源，把分散在三条线上的精力集中到优先级最高的一条，"
            "比每条线都做一半更可能拿到可执行的结果。"
        ),
    }

    return {"overall": overall, "paths": scored}
