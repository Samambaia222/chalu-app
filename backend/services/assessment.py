"""心理与职业兴趣测评服务
   - PHQ-9 抑郁自评（9 题，0-27 分）
   - GAD-7 焦虑自评（7 题，0-21 分）
   - 霍兰德职业兴趣 RIASEC（18 题，六维，每维 3-15 分）
   说明：量表仅用于职业决策参考，不构成临床诊断。"""
from typing import Dict, Any, List, Optional

# ---------------- 题目定义 ----------------
PHQ9_OPTIONS = ["完全不会", "好几天", "一半以上天数", "几乎每天"]

PHQ9_QUESTIONS = [
    "做事时提不起劲或没有兴趣",
    "感到心情低落、沮丧或绝望",
    "入睡困难、睡不安稳或睡得过多",
    "感觉疲倦或没有活力",
    "食欲不振或吃太多",
    "觉得自己很糟，或觉得自己很失败，或让自己和家人失望",
    "对事物专注有困难，例如阅读或看视频时",
    "动作或说话速度缓慢到别人已经察觉；或相反，烦躁、坐立不安、动来动去",
    "有不如死掉或用某种方式伤害自己的念头",
]

GAD7_QUESTIONS = [
    "感觉紧张、焦虑或急切",
    "不能够停止或控制担忧",
    "对各种各样的事情担忧过多",
    "很难放松下来",
    "由于不安而无法静坐",
    "变得容易烦恼或急躁",
    "感到似乎将有可怕的事情发生而害怕",
]

# 霍兰德：每维 3 题，1-5 分李克特
HOLLAND_LIKERT = ["很不符合", "不太符合", "一般", "比较符合", "非常符合"]

HOLLAND_DIMENSIONS = [
    ("R", "现实型", [
        "我喜欢动手修理、组装或操作设备",
        "比起讨论，我更愿意实际动手把事情做出来",
        "我喜欢能在现实中看到具体成果的工作",
    ]),
    ("I", "研究型", [
        "我喜欢钻研事物背后的原理和规律",
        "我愿意花很长时间研究一个复杂问题",
        "我喜欢阅读专业书籍、做实验或分析数据",
    ]),
    ("A", "艺术型", [
        "我喜欢用文字、图像或音乐表达自己的想法",
        "我讨厌一成不变、高度流程化的工作",
        "我常有与众不同的创意和想法",
    ]),
    ("S", "社会型", [
        "我喜欢帮助别人解决问题",
        "我愿意倾听他人的烦恼并给予支持",
        "相比独自工作，我更享受团队协作",
    ]),
    ("E", "企业型", [
        "我喜欢说服别人接受我的观点",
        "我愿意承担带领团队、做决策的责任",
        "我对商业机会和竞争有浓厚兴趣",
    ]),
    ("C", "常规型", [
        "我喜欢按明确的规则和流程做事",
        "我做事细致，愿意整理、归档和核对",
        "我偏好稳定、可预期的工作环境",
    ]),
]

HOLLAND_DESC = {
    "R": "现实型：偏好动手实践与具体成果，适合技术、工程、运维类岗位",
    "I": "研究型：偏好钻研与分析，适合学术研究、算法、研发类方向",
    "A": "艺术型：偏好创造与表达，适合设计、内容、产品创意类方向",
    "S": "社会型：偏好助人与协作，适合教育、公共服务、人力类方向",
    "E": "企业型：偏好影响与领导，适合市场、销售、管理、创业类方向",
    "C": "常规型：偏好规范与秩序，适合行政、财务、体制内岗位",
}

# 三条路径的霍兰德权重（六大维度归一化后加权求和）
PATH_HOLLAND_WEIGHTS = {
    "P_KAOY": {"I": 0.50, "C": 0.25, "R": 0.15, "S": 0.10},
    "P_KAOG": {"C": 0.45, "S": 0.30, "E": 0.15, "I": 0.10},
    "P_JIUY": {"E": 0.35, "R": 0.25, "A": 0.20, "I": 0.20},
}

PATH_FIT_REASON = {
    "P_KAOY": {
        "I": "研究型兴趣强，读研能让你持续深耕专业问题",
        "C": "常规型特质有助于长期、有节奏的备考坚持",
        "R": "现实型特质适合需要大量练习与实操的工科专业",
        "S": "社会型特质在复试面试与导师沟通中是加分项",
    },
    "P_KAOG": {
        "C": "常规型特质与体制内规则化、流程化的工作高度契合",
        "S": "社会型特质契合公共服务、群众工作的岗位要求",
        "E": "企业型特质有助于面试表达与岗位竞争",
        "I": "研究型特质适合政策研究、文字综合类岗位",
    },
    "P_JIUY": {
        "E": "企业型特质适合市场化环境中的竞争与成长",
        "R": "现实型特质适合技术落地、工程实现类岗位",
        "A": "艺术型特质适合产品、设计、内容创意类岗位",
        "I": "研究型特质适合研发、算法等技术岗位",
    },
}


# ---------------- PHQ-9 / GAD-7 ----------------
def _phq9_level(total: int) -> str:
    if total <= 4:
        return "无"
    if total <= 9:
        return "轻度"
    if total <= 14:
        return "中度"
    if total <= 19:
        return "中重度"
    return "重度"


def _gad7_level(total: int) -> str:
    if total <= 4:
        return "无"
    if total <= 9:
        return "轻度"
    if total <= 14:
        return "中度"
    return "重度"


def score_psych(phq9: List[int], gad7: List[int]) -> Dict[str, Any]:
    if len(phq9) != 9 or len(gad7) != 7:
        raise ValueError("PHQ-9 需 9 题、GAD-7 需 7 题")
    for v in phq9 + gad7:
        if not (0 <= int(v) <= 3):
            raise ValueError("每题作答须在 0-3 之间")

    phq = sum(int(v) for v in phq9)
    gad = sum(int(v) for v in gad7)
    self_harm = int(phq9[8]) > 0
    phq_lv, gad_lv = _phq9_level(phq), _gad7_level(gad)

    # 情绪负荷 0-1，用于调整路径建议权重
    mood_load = min(1.0, (phq / 27 * 0.6 + gad / 21 * 0.4))
    if self_harm:
        mood_load = max(mood_load, 0.8)

    advice = _psych_advice(phq, phq_lv, gad, gad_lv, self_harm)
    return {
        "phq9_total": phq,
        "phq9_level": phq_lv,
        "gad7_total": gad,
        "gad7_level": gad_lv,
        "self_harm_flag": self_harm,
        "mood_load": round(mood_load, 3),
        "advice": advice,
        "disclaimer": "本结果为自评参考，不构成临床诊断。如持续困扰，请前往学校心理咨询中心或专业医疗机构。",
    }


def _psych_advice(phq: int, phq_lv: str, gad: int, gad_lv: str,
                  self_harm: bool) -> Dict[str, Any]:
    urgent = self_harm or phq >= 20
    level = "高危" if urgent else ("关注" if (phq >= 10 or gad >= 10) else "平稳")

    # 说明升级原因，避免分数与等级看起来矛盾
    if self_harm:
        reason = "PHQ-9 第 9 题（伤害自己的念头）有阳性作答，触发优先关注"
    elif phq >= 20:
        reason = f"PHQ-9 总分 {phq} 分，达到重度区间"
    elif phq >= 10 or gad >= 10:
        reason = f"PHQ-9 {phq} 分、GAD-7 {gad} 分，达到中度区间"
    else:
        reason = ""

    if self_harm:
        headline = ("虽然你的总分不高，但你提到近期出现过伤害自己的念头，这需要优先被认真对待。"
                    "职业决策可以先放一放，你的安全最重要。")
        actions = [
            "今天就联系学校心理咨询中心预约面谈，或拨打心理援助热线 12356 / 010-82951332",
            "把此刻的感受告诉一位你信任的人，尽量不要独处",
            "暂时不要在此状态下做考研/考公/就业等重大不可逆决定，先稳定状态 2-4 周",
        ]
    elif phq >= 20:
        headline = "你的抑郁自评达到重度区间，建议尽快寻求专业支持，再做职业决策。"
        actions = [
            "本周内预约学校心理咨询中心或精神科门诊评估",
            "暂缓高强度备考计划，优先恢复睡眠与作息",
            "把决策周期拉长，先做低成本的试探性行动",
        ]
    elif phq >= 10 or gad >= 10:
        headline = f"你的抑郁自评「{phq_lv}」、焦虑自评「{gad_lv}」，情绪已在影响状态，需要主动调节。"
        actions = [
            "预约学校心理咨询中心做一次评估（通常免费且保密）",
            "每天固定 30 分钟运动与规律作息，先稳住生理节律",
            "把大目标拆成周任务，用完成小事来降低失控感",
        ]
    elif phq >= 5 or gad >= 5:
        headline = f"你有轻度情绪波动（抑郁「{phq_lv}」、焦虑「{gad_lv}」），属于毕业季常见范围。"
        actions = [
            "保持规律作息与运动，每周至少 3 次 30 分钟有氧",
            "找同学或学长聊一聊，把担忧具体化而不是模糊焦虑",
            "用系统的路径对比代替反复空想，减少内耗",
        ]
    else:
        headline = "你的情绪状态整体平稳，可以放心进入路径决策。"
        actions = [
            "保持现有作息与社交节奏",
            "决策过程中如出现持续两周以上的低落或失眠，及时寻求帮助",
        ]

    return {
        "level": level,
        "urgent": urgent,
        "reason": reason,
        "headline": headline,
        "actions": actions,
        "hotline": "全国心理援助热线 12356；北京心理危机干预中心 010-82951332",
    }


# ---------------- 霍兰德 RIASEC ----------------
def score_holland(answers: List[int]) -> Dict[str, Any]:
    if len(answers) != 18:
        raise ValueError("霍兰德测评需 18 题")
    for v in answers:
        if not (1 <= int(v) <= 5):
            raise ValueError("每题作答须在 1-5 之间")

    scores: Dict[str, int] = {}
    idx = 0
    for code, name, _ in HOLLAND_DIMENSIONS:
        scores[code] = sum(int(v) for v in answers[idx:idx + 3])
        idx += 3

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    top_code = "".join(c for c, _ in ranked[:3])

    norm = {c: round((s - 3) / 12, 3) for c, s in scores.items()}
    fit = {}
    for pid, weights in PATH_HOLLAND_WEIGHTS.items():
        val = sum(norm[c] * w for c, w in weights.items())
        # 未列入权重的维度给少量基础分，避免被完全忽略
        fit[pid] = round(max(0.0, min(1.0, val)) * 100, 1)

    reasons = []
    for pid, reasons_map in PATH_FIT_REASON.items():
        for c, _ in ranked[:3]:
            if c in reasons_map:
                reasons.append(f"{reasons_map[c]}（适配 {_path_name(pid)}）")

    top_dims = [
        {"code": c, "name": _dim_name(c), "score": scores[c], "desc": HOLLAND_DESC[c]}
        for c, _ in ranked[:3]
    ]
    return {
        "scores": scores,
        "normalized": norm,
        "top_code": top_code,
        "top_dimensions": top_dims,
        "path_fit": fit,
        "reasons": reasons[:4],
    }


def _dim_name(code: str) -> str:
    for c, name, _ in HOLLAND_DIMENSIONS:
        if c == code:
            return name
    return code


def _path_name(pid: str) -> str:
    return {"P_KAOY": "考研", "P_KAOG": "考公", "P_JIUY": "就业"}.get(pid, pid)


def questions() -> Dict[str, Any]:
    """返回全部题目与选项，供前端渲染"""
    return {
        "phq9": {"questions": PHQ9_QUESTIONS, "options": PHQ9_OPTIONS, "scale": "过去两周内，以下问题困扰你的频率"},
        "gad7": {"questions": GAD7_QUESTIONS, "options": PHQ9_OPTIONS, "scale": "过去两周内，以下问题困扰你的频率"},
        "holland": {
            "likert": HOLLAND_LIKERT,
            "dimensions": [
                {"code": c, "name": n, "questions": qs}
                for c, n, qs in HOLLAND_DIMENSIONS
            ],
        },
    }


# ---------------- 外部热门测评（跳转链接，不依赖，仅供补充） ----------------
EXTERNAL_ASSESSMENTS: List[Dict[str, Any]] = [
    {
        "id": "mbtiv2",
        "name": "MBTI® 16Personalities (免费版)",
        "category": "人格偏好",
        "url": "https://www.16personalities.com/ch",
        "why": "全球最火的人格类型框架，48 题，免费；帮助理解自己的决策风格、团队角色、沟通偏好",
        "free": True,
        "time": "约 12 分钟",
        "use_case": "对「我适合做什么类型的工作方向」有模糊感时先做这个",
        "disclaimer": "不是权威人格测评，结果仅供自我探索参考",
    },
    {
        "id": "holland_cn",
        "name": "霍兰德 RIASEC 在线版（中国常模）",
        "category": "职业兴趣",
        "url": "https://www.apesk.com/holland/",
        "why": "我们系统内有霍兰德 18 题简版，这个是完整 60 题+中国大学生常模，结果更精准",
        "free": True,
        "time": "约 20 分钟",
        "use_case": "系统内的霍兰德结果如果你觉得维度接近、难以分辨主次，做完整版确认",
    },
    {
        "id": "strengthsfinder",
        "name": "盖洛普优势识别器 (CliftonStrengths)",
        "category": "优势发现",
        "url": "https://www.gallupstrengthscenter.com",
        "why": "识别你天生的 Top 5 优势，而不是短板；帮助你在三路径中选能放大优势的方向",
        "free": False,
        "time": "约 35 分钟",
        "use_case": "如果你已基本确定方向，想知道自己在该方向上最可能领先在哪，做这个",
        "disclaimer": "付费 49 美元，但结果对简历/面试/职业规划都有长期参考价值",
    },
    {
        "id": "grit",
        "name": "Grit 毅力量表",
        "category": "心理特质",
        "url": "https://angeladuckworth.com/grit-scale/",
        "why": "考研/考公的达成概率与 Grit（坚持不懈长期目标的意志力）正相关比智商更大；"
               "测完你会知道自己在哪种路径的准备期最容易垮掉",
        "free": True,
        "time": "约 5 分钟",
        "use_case": "在三路径的备考期投入长度权衡时参考——Grit 高适合考研（长周期），"
                    "Grit 中等适合考公/就业（短冲刺）",
    },
    {
        "id": "career_anchor",
        "name": "Schein 职业锚 (Career Anchors)",
        "category": "职业价值观",
        "url": "https://www.career-test.co.uk/scheins-career-anchor-test/",
        "why": "8 种职业锚（技术/管理/自主/安全/创造/服务/挑战/生活整合）；"
               "很多应届毕业生的迷茫根源是不知道自己的底线价值观——比如有人受不了被 KPI 追（不适合就业大厂），"
               "有人受不了慢（不适合体制）",
        "free": True,
        "time": "约 15 分钟",
        "use_case": "对「就业/考公/读研」的底层动机感到模糊时，先用这个帮自己锚定",
    },
    {
        "id": "51job_career",
        "name": "51job 应届生职业测评",
        "category": "就业方向",
        "url": "https://www.51job.com/campus/",
        "why": "结合 MBTI + 霍兰德 + 求职倾向，给出适合你的行业/岗位类型推荐；"
               "免费，应届生账号即可，且和实际招聘岗位有联动",
        "free": True,
        "time": "约 20 分钟",
        "use_case": "如果就业方向是选项之一但不知道投什么岗位，先做这个缩小范围",
    },
    {
        "id": "cnki_master",
        "name": "中国研究生招生网（研招网）",
        "category": "官方信息",
        "url": "https://yz.chsi.com.cn",
        "why": "考研报名、调剂、复试的唯一官方入口；查各院校报录比、招生目录、招生简章",
        "free": True,
        "time": "信息查阅不限时",
        "use_case": "确定考研目标后，第一时间去查目标院校报录比——这是最硬核的数据（比如某院校报录比 30:1 说明要换目标）",
    },
    {
        "id": "scs_gov",
        "name": "国家公务员局",
        "category": "官方信息",
        "url": "http://www.scs.gov.cn",
        "why": "国考公告、职位表、报名系统的唯一官方入口；查历年进面分数要求",
        "free": True,
        "time": "信息查阅不限时",
        "use_case": "考公选岗的核心依据：职位表→找到「限应届+限专业+限本科」的岗→查历年进面分",
    },
]


def external_assessments() -> Dict[str, Any]:
    """返回外部补充测评链接。明确说明：系统内测评为主，外部为补充，不依赖。"""
    return {
        "category": "external_assessments",
        "description": (
            "以上是业内较公认的补充测评工具，系统内的霍兰德/PHQ-9/GAD-7 是主参考，"
            "这些外部资源用于在你觉得系统内结果模糊时做交叉验证。"
            "不建议一次性全做——针对自己最模糊的 1-2 个维度选做即可。"
        ),
        "total": len(EXTERNAL_ASSESSMENTS),
        "assessments": EXTERNAL_ASSESSMENTS,
    }
