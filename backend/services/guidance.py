"""路径执行指导服务
   用户选定一条路径后，基于其画像、测评结果与风险项，
   生成可执行的分阶段计划、里程碑、风险预警、心理支持与 Plan B。"""
import json
from typing import Dict, Any, List, Optional

from ..models import User

PATH_NAMES = {"P_KAOY": "考研", "P_KAOG": "考公", "P_JIUY": "就业"}

PLANS = {
    "P_KAOY": {
        "phases": [
            {
                "name": "第一阶段 · 定校与启动",
                "period": "第 1-4 周",
                "goals": ["锁定 2-3 所目标院校（一冲一稳一保）", "备齐真题与参考书", "建立可持续的每日学习节奏"],
                "actions": [
                    "查近三年报录比、复试线与专业课大纲，排除明显不可能的院校",
                    "收集目标院校 5 年真题，按题型分类整理",
                    "固定每天 4-6 小时有效学习时段，先保证连续 21 天不断档",
                ],
            },
            {
                "name": "第二阶段 · 基础与强化",
                "period": "第 2-4 个月",
                "goals": ["完成数学/专业课一轮复习", "英语词汇与阅读形成稳定输出", "建立错题本"],
                "actions": [
                    "数学按章节推进，每章配套 20-30 道题并及时复盘",
                    "专业课通读教材后画出知识框架图，再进入背诵",
                    "英语每天 50 个新词 + 2 篇精读，周末回顾错题",
                ],
            },
            {
                "name": "第三阶段 · 真题冲刺",
                "period": "考前 2 个月",
                "goals": ["真题成套模拟达到目标线", "完成报名与现场确认", "调整作息与心态"],
                "actions": [
                    "每周 2 套真题严格计时，记录各科分数曲线",
                    "10 月完成正式报名，核对报考点与材料",
                    "考前两周只做回顾与调整，不再开新内容",
                ],
            },
        ],
        "milestones": [
            {"when": "第 4 周末", "target": "目标院校与专业确定，资料齐全", "check": "能否说清 3 所院校的报录比与复试线"},
            {"when": "第 8 周末", "target": "一轮复习完成，自测正确率 ≥ 60%", "check": "随机抽一章做 20 题，正确率作为硬指标"},
            {"when": "考前 4 周", "target": "真题模拟总分达到去年复试线 ±10 分", "check": "两次成套模拟取平均分对比"},
        ],
        "risks": [
            ("时间投入不足", "把每日最小有效学习时长降到 3 小时，优先保数学与专业课两门拉分科目"),
            ("跨专业基础薄弱", "先补 2 门核心先修课，必要时报单科网课，不要全面铺开"),
            ("院校背景偏弱", "初试分数目标上浮 10-15 分，复试提前准备科研/项目经历"),
        ],
        "plan_b": {
            "trigger": "考前 1 个月真题模拟连续两次低于目标线 15 分以上",
            "fallback": "同步准备春招简历，考研结束后立即进入就业通道；或调整为下一年度二战并先积累实习",
        },
    },
    "P_KAOG": {
        "phases": [
            {
                "name": "第一阶段 · 岗位研判与基础",
                "period": "第 1-4 周",
                "goals": ["明确可报岗位范围", "完成行测摸底", "建立申论素材库"],
                "actions": [
                    "对照专业目录筛选可报岗位，列出近三年进面分数线",
                    "做 2 套行测真题摸底，找出最弱与最强的 2 个模块",
                    "每周积累 5 个申论热点与官方表述",
                ],
            },
            {
                "name": "第二阶段 · 模块突破",
                "period": "第 2-4 个月",
                "goals": ["行测三大得分模块稳定在 70% 正确率", "申论形成固定答题结构"],
                "actions": [
                    "言语、判断、资料分析每天各 30 题，限时训练",
                    "数量关系只保基础题型，不死磕难题",
                    "每周写 1 篇完整申论并对照参考答案逐段修改",
                ],
            },
            {
                "name": "第三阶段 · 套题与面试",
                "period": "考前 6 周及之后",
                "goals": ["成套模考稳定发挥", "完成报名与资格审查", "提前准备面试"],
                "actions": [
                    "每周 3 套完整行测+1 套申论，严格按考试时间",
                    "关注国考/省考/事业单位公告，错峰报考增加机会",
                    "笔试结束后立即开始结构化面试与无领导小组练习",
                ],
            },
        ],
        "milestones": [
            {"when": "第 4 周末", "target": "确定 3-5 个目标岗位及对应分数线", "check": "每个岗位能说出招录人数、专业要求、进面分"},
            {"when": "第 10 周末", "target": "行测三大模块正确率 ≥ 70%", "check": "限时 30 题一组，连续 3 组达标"},
            {"when": "考前 2 周", "target": "成套模考总分稳定在目标岗位进面线以上", "check": "3 次模考取中位数"},
        ],
        "risks": [
            ("专业岗位受限", "扩大报考范围到三不限与基层岗位，同时关注事业单位与选调生"),
            ("竞争过于激烈", "避开热门省市热门岗，优先选择限制条件多、竞争比低的岗位"),
            ("备考周期长易疲惫", "设置每周固定休息半天，用模考成绩的正反馈维持动力"),
        ],
        "plan_b": {
            "trigger": "国考/省考笔试均未进面",
            "fallback": "转向事业单位、国企校招或就业通道；保留行测能力，次年再战成本较低",
        },
    },
    "P_JIUY": {
        "phases": [
            {
                "name": "第一阶段 · 简历与作品集",
                "period": "第 1-4 周",
                "goals": ["完成一份可投递的简历", "沉淀 2 个可讲清楚的项目", "补齐岗位技能短板"],
                "actions": [
                    "按目标岗位 JD 反推关键词，重写简历的项目与技能描述",
                    "把课程项目/实习整理成 STAR 结构，每项准备 2 分钟口述版本",
                    "针对目标岗位补 1 项核心技能（如 SQL、LeetCode、原型工具）",
                ],
            },
            {
                "name": "第二阶段 · 投递与笔试",
                "period": "第 2-3 个月",
                "goals": ["累计投递 50+ 家", "笔试通过率形成稳定输出", "拿到 3 个以上面试机会"],
                "actions": [
                    "按「大厂冲刺 + 中厂主力 + 小厂保底」三层投递，避免只盯头部",
                    "每周固定投递 15 家，记录投递-笔试-面试转化率",
                    "笔试前刷目标公司高频题型，形成题型清单",
                ],
            },
            {
                "name": "第三阶段 · 面试与 Offer 决策",
                "period": "拿到面试起至签约",
                "goals": ["面试通过率 ≥ 30%", "拿到 2 个以上 Offer 可比较", "完成签约决策"],
                "actions": [
                    "每次面试后 24 小时内复盘，记录被问倒的问题",
                    "准备「为什么选我们」「职业规划」等高频问题的个性化答案",
                    "对比 Offer 时综合考虑城市、成长性、薪资与加班强度，不只看起薪",
                ],
            },
        ],
        "milestones": [
            {"when": "第 4 周末", "target": "简历定稿 + 2 个项目可完整讲述", "check": "找同学做一次模拟面试，能否流畅讲完 2 分钟自我介绍"},
            {"when": "第 8 周末", "target": "投递 30 家，获得 3 个以上笔试机会", "check": "投递记录表统计转化率"},
            {"when": "第 12 周末", "target": "获得至少 1 个 Offer", "check": "Offer 邮件或意向书"},
        ],
        "risks": [
            ("缺乏实习背书", "用课程项目、开源贡献、竞赛作品替代，突出可验证的产出"),
            ("学历门槛受限", "主攻中小厂与内推渠道，避开明确卡学历的岗位，减少无效投递"),
            ("面试经验不足", "先投 5 家非首选公司练手，把首选公司放在手感最好时投"),
        ],
        "plan_b": {
            "trigger": "秋招结束仍未拿到满意 Offer",
            "fallback": "进入春招补录；同时可先接受实习转正或中小厂 offer 积累经验，一年后再跳槽",
        },
    },
}


def _tags(user: User) -> set:
    try:
        return set(json.loads(user.tags or "[]"))
    except (ValueError, TypeError):
        return set()


def _psych_support(psych: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not psych:
        return {
            "level": "未测评",
            "headline": "你还没有做心理状态自评，建议先花 3 分钟完成 PHQ-9 / GAD-7，以便制定更贴合状态的执行节奏。",
            "actions": ["在「测评中心」完成心理自评，可获得情绪维度的路径建议"],
        }
    advice = psych.get("advice", {}) or {}
    return {
        "level": advice.get("level", "平稳"),
        "headline": advice.get("headline", ""),
        "actions": advice.get("actions", []),
        "hotline": advice.get("hotline", ""),
        "urgent": advice.get("urgent", False),
    }


def build_plan(user: User, chosen_path_id: str,
               probs: Dict[str, Dict[str, Any]],
               psych: Optional[Dict[str, Any]],
               holland: Optional[Dict[str, Any]],
               feasibility: Dict[str, Any]) -> Dict[str, Any]:
    """生成选定路径后的完整执行方案"""
    base = PLANS.get(chosen_path_id)
    if not base:
        raise ValueError("未知路径")

    tags = _tags(user)
    path_name = PATH_NAMES.get(chosen_path_id, chosen_path_id)
    chosen_prob = probs.get(chosen_path_id, {})

    # ---- 选择理由 ----
    rationale: List[str] = []
    if chosen_prob:
        rationale.append(
            f"该路径校准达成概率 {chosen_prob['prob']*100:.0f}%"
            f"（{chosen_prob['lower']*100:.0f}%-{chosen_prob['upper']*100:.0f}%，样本 {chosen_prob['n']} 人）"
        )
    if holland:
        fit = holland["path_fit"].get(chosen_path_id)
        if fit is not None:
            rationale.append(f"你的霍兰德兴趣与该路径匹配度 {fit:.0f}/100（前三码 {holland['top_code']}）")
    f = feasibility.get(chosen_path_id, {})
    if f.get("feasible"):
        rationale.append("已通过全部硬约束校验，本年度可执行")
    else:
        rationale.append(f"注意：当前仍有硬约束障碍 —— {f.get('summary', '')}，需先解决")
    if psych and (psych.get("advice", {}) or {}).get("level") in ("关注", "高危"):
        rationale.append("考虑到你当前的情绪负荷，本方案已下调单日强度、增加了阶段性休息与支持资源")
    if "实践经历丰富" in tags and chosen_path_id == "P_JIUY":
        rationale.append("你的实习/项目经历是就业通道的核心优势，应在简历与面试中重点放大")

    # ---- 基于个人画像的风险补强 ----
    risk_alerts = [{"risk": r, "response": resp} for r, resp in base["risks"]]
    if user.time_input in ("<3月", "3-6月"):
        risk_alerts.insert(0, {
            "risk": "可用备考/准备时间明显偏短",
            "response": "压缩到「只做最高权重的事」：考研保数学与专业课，考公保三大得分模块，就业保简历与高频笔试题",
        })
    if user.budget_range in ("<5千",):
        risk_alerts.append({
            "risk": "预算有限",
            "response": "优先使用公开课、图书馆与二手资料，把支出集中在最薄弱的一门单科上",
        })
    if "决策焦虑" in tags:
        risk_alerts.append({
            "risk": "决策焦虑可能反复出现",
            "response": "把「要不要换路径」的念头限定在每周固定一次复盘时段，其余时间按计划执行",
        })

    # ---- 性别相关风险补强（只加有统计依据的差异，不构成歧视） ----
    if user.gender == "女" and chosen_path_id == "P_JIUY":
        if user.major_category in ("计算机类", "理工类"):
            risk_alerts.append({
                "risk": "工科女生就业存在隐性门槛",
                "response": "简历关键词必须精确匹配 JD（如「高并发」「微服务」），准备作品集/GitHub 开源贡献，争取内推渠道",
            })
    if user.gender == "女" and chosen_path_id == "P_KAOG":
        risk_alerts.append({
            "risk": "部分三不限岗位男生占比高",
            "response": "优先筛选教育/民政/卫生/妇联等公共服务类岗位（招录女性占比 60%+），避开纯工科执法岗",
        })

    # ---- 省份相关补强 ----
    prov = user.target_province
    if prov == "广东" and chosen_path_id == "P_JIUY":
        risk_alerts.append({
            "risk": "广东就业竞争激烈（大厂集中）",
            "response": "广州/深圳大厂对学历门槛高，建议中小厂 + 内推并行，同时关注东莞/佛山制造业转移机会",
        })
    if prov in ("北京", "上海") and chosen_path_id == "P_JIUY":
        risk_alerts.append({
            "risk": "一线城市租房/落户成本高",
            "response": "offer 到手后先算清楚净收入（扣除五险一金 + 房租），不要只看起薪数字",
        })

    # ---- 阶段计划：情绪负荷高时自动降强度 ----
    phases = json.loads(json.dumps(base["phases"], ensure_ascii=False))
    if psych and (psych.get("advice", {}) or {}).get("level") == "高危":
        for p in phases:
            p["goals"] = ["先稳定睡眠与作息（本周首要目标）"] + p["goals"][:2]
            p["period"] = "节奏可延后，不设硬性截止"

    return {
        "path_id": chosen_path_id,
        "path_name": path_name,
        "rationale": rationale,
        "phases": phases,
        "milestones": base["milestones"],
        "risk_alerts": risk_alerts,
        "psych_support": _psych_support(psych),
        "plan_b": base["plan_b"],
        "note": "计划为起步版，建议每 2 周按实际进度调整一次；如情绪状态明显变化，请优先回来重做心理自评。",
    }
