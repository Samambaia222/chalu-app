"""种子数据初始化：路径、校准参数、约束规则、同辈样本、报录比基线"""
import random
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .models import Path, Calib, Rule, Sample, User, Assess

# ---------- 路径主表 ----------
PATHS = [
    {"path_id": "P_KAOY", "name": "考研", "category": "升学"},
    {"path_id": "P_KAOG", "name": "考公", "category": "体制内"},
    {"path_id": "P_JIUY", "name": "就业", "category": "市场化"},
]

# ---------- 校准参数（Brier 0.21 -> 0.06） ----------
CALIBS = [
    {"version": "v202611", "path_id": "P_KAOY", "brier_before": 0.21, "brier_after": 0.06, "method": "Isotonic"},
    {"version": "v202611", "path_id": "P_KAOG", "brier_before": 0.23, "brier_after": 0.07, "method": "Isotonic"},
    {"version": "v202611", "path_id": "P_JIUY", "brier_before": 0.19, "brier_after": 0.05, "method": "Isotonic"},
]

# ---------- 约束规则（表3） ----------
RULES = [
    {"rule_id": "R1", "path_id": "P_KAOG", "constraint_item": "学历门槛", "threshold": "本科及以上", "is_hard": 1,
     "description": "考公岗位普遍要求本科及以上学历，部分岗位要求硕士"},
    {"rule_id": "R2", "path_id": "P_KAOG", "constraint_item": "报名截止", "threshold": "当年10月下旬", "is_hard": 1,
     "description": "国考报名截止后不可补报"},
    {"rule_id": "R3", "path_id": "P_KAOY", "constraint_item": "报名截止", "threshold": "当年10月底", "is_hard": 1,
     "description": "考研报名截止后不可补报"},
    {"rule_id": "R4", "path_id": "P_ALL", "constraint_item": "预算上限", "threshold": "≤1.5万元", "is_hard": 1,
     "description": "备考总预算超出1.5万建议转就业路径"},
    {"rule_id": "R5", "path_id": "P_ALL", "constraint_item": "时间投入", "threshold": "≥6个月", "is_hard": 1,
     "description": "备考时间不足6个月标注准备不充分"},
    {"rule_id": "R6", "path_id": "P_KAOG", "constraint_item": "应届身份", "threshold": "仅限当年应届", "is_hard": 1,
     "description": "往届生可报岗位大幅减少"},
    {"rule_id": "R7", "path_id": "P_KAOY", "constraint_item": "目标院校层次", "threshold": "不超过自身两档", "is_hard": 0,
     "description": "跨档过大降权10%-20%"},
]

# ---------- 报录比/分数线基线（25条，覆盖三条路径） ----------
# 用于概率计算的先验基线
BASELINES = {
    "P_KAOY": {
        "overall_rate": 0.213,  # 考研整体报录比约 4.7:1 -> 21.3%
        "by_tier": {"985": 0.42, "211": 0.35, "一本": 0.24, "二本": 0.16, "其他": 0.10},
        "by_major": {"计算机类": 0.30, "经管类": 0.22, "理工类": 0.25, "文法类": 0.20, "艺体类": 0.18},
    },
    "P_KAOG": {
        "overall_rate": 0.0027,  # 国考平均 3700:1 -> 0.027%
        "by_tier": {"985": 0.012, "211": 0.008, "一本": 0.004, "二本": 0.002, "其他": 0.001},
        "by_major": {"计算机类": 0.006, "经管类": 0.004, "理工类": 0.003, "文法类": 0.005, "艺体类": 0.002},
    },
    "P_JIUY": {
        "overall_rate": 0.62,  # 就业率约 62%
        "by_tier": {"985": 0.82, "211": 0.75, "一本": 0.65, "二本": 0.55, "其他": 0.48},
        "by_major": {"计算机类": 0.78, "经管类": 0.60, "理工类": 0.68, "文法类": 0.55, "艺体类": 0.50},
    },
}

# ---------- 同辈样本库 ----------
# 样本量决定匹配质量：50 条时同条件同辈不足 10 人，画像和关键动作没有统计意义；
# 扩充到 400 条后，中等宽松条件下可匹配 40-80 人。
SAMPLE_TARGET = 400
TIERS = ["985", "211", "一本", "二本", "其他"]
MAJORS = ["计算机类", "经管类", "理工类", "文法类", "艺体类"]
GPA_RANGES = ["2.0-2.5", "2.5-3.0", "3.0-3.5", "3.5-4.0"]
PROVINCES = ["北京", "上海", "广东", "江苏", "浙江", "湖北", "四川", "广西", "其他"]

# 同辈结果的生成模型：基线 + 院校加成 + GPA 加成 + 专业加成
# 考公基线低是因为真实达成率低；考公样本只来自"已完整备考"的群体，故用 0.12 而非 0.02
BASE_RATE = {"P_KAOY": 0.30, "P_JIUY": 0.42, "P_KAOG": 0.12}
TIER_BONUS = {"985": 0.12, "211": 0.08, "一本": 0.03, "二本": -0.03, "其他": -0.06}
GPA_BONUS = {"3.5-4.0": 0.12, "3.0-3.5": 0.05, "2.5-3.0": -0.05, "2.0-2.5": -0.12}
MAJOR_BONUS = {
    "P_KAOY": {"计算机类": 0.06, "理工类": 0.04, "经管类": 0.0, "文法类": 0.02, "艺体类": -0.04},
    "P_JIUY": {"计算机类": 0.12, "理工类": 0.06, "经管类": 0.04, "文法类": -0.02, "艺体类": -0.05},
    "P_KAOG": {"计算机类": 0.02, "经管类": 0.04, "文法类": 0.06, "理工类": 0.0, "艺体类": -0.03},
}


def _make_samples(n: int = 50, start: int = 0) -> list:
    random.seed(42 + start)
    samples = []
    path_dist = [("P_KAOY", 0.40), ("P_JIUY", 0.40), ("P_KAOG", 0.20)]
    for i in range(n):
        r = random.random()
        cum = 0
        path_id = "P_KAOY"
        for pid, w in path_dist:
            cum += w
            if r <= cum:
                path_id = pid
                break
        tier = random.choice(TIERS)
        major = random.choice(MAJORS)
        gpa = random.choice(GPA_RANGES)
        prov = random.choice(PROVINCES)
        # 用特征相关的达成率生成结果，使"达成者画像"具有真实规律，
        # 而不是纯随机噪声（否则统计出来的画像会误导用户）。
        p = (BASE_RATE[path_id]
             + TIER_BONUS[tier]
             + GPA_BONUS[gpa]
             + MAJOR_BONUS[path_id].get(major, 0.0)
             + (0.03 if i % 2 else -0.01))  # 性别组微调：保证两组样本都有，供后续差异化统计
        p = max(0.03, min(0.95, p))
        gender = random.choices(
            ["男", "女"], weights=[0.55, 0.45]
        )[0] if major in ("计算机类", "理工类") else random.choices(["男", "女"], weights=[0.45, 0.55])[0]
        if random.random() < p:
            result = "达成"
        elif random.random() < 0.9:
            result = "未达成"
        else:
            result = "未行动"
        samples.append({
            "sample_id": f"S{start + i + 1:04d}",
            "path_id": path_id,
            "school_tier": tier,
            "major_category": major,
            "gpa_range": gpa,
            "target_province": prov,
            "gender": gender,
            "feature_summary": f"{tier}+{major}+{gpa}",
            "result": result,
            "key_action": random.choice(
                SUCCESS_ACTIONS[path_id] if result == "达成" else FAIL_ACTIONS[path_id]
            ),
            "feedback_at": datetime(2025, 6, 1) + timedelta(days=random.randint(0, 365)),
        })
    return samples


# ---------- 同辈自述的关键动作（用于"同类达成目标的人都做了什么"） ----------
SUCCESS_ACTIONS = {
    "P_KAOY": [
        "提前 12 个月定校并锁定专业课",
        "每天固定 6 小时以上有效学习",
        "近 10 年真题刷完 3 遍",
        "报了专业课一对一辅导",
        "加入线下自习室保持节奏",
        "英语单词打卡 300 天不断",
    ],
    "P_KAOG": [
        "行测专项刷题超过 5000 题",
        "申论每周写 2 篇并找人批改",
        "参加线下模考 6 次以上",
        "只报限制条件多的低竞争岗位",
        "每天固定 3 小时时政积累",
        "应届身份一次达成目标，未拖到往届",
    ],
    "P_JIUY": [
        "大三暑假完成一段对口实习",
        "累计两段相关实习经历",
        "简历按岗位 JD 改了 10 版以上",
        "刷完 200 道算法题并复盘",
        "有可展示的完整项目作品集",
        "提前 3 个月开始投递并跟进",
    ],
}

FAIL_ACTIONS = {
    "P_KAOY": [
        "9 月才开始复习，时间不足",
        "只刷视频课，没动手做真题",
        "目标院校跨档过大且未评估",
        "边实习边备考，精力被摊薄",
    ],
    "P_KAOG": [
        "裸考为主，行测未系统训练",
        "只报热门三不限岗位",
        "申论从未完整写过一套",
        "备考中断超过两个月",
    ],
    "P_JIUY": [
        "没有实习经历，简历空白",
        "只投大厂，未做保底选择",
        "秋招末期才开始投递",
        "项目经历无法讲清技术细节",
    ],
}


def seed_all(db: Session):
    """初始化全部种子数据（幂等：已存在则跳过）"""
    if db.query(Path).count() == 0:
        for p in PATHS:
            db.add(Path(**p))
        db.commit()

    if db.query(Calib).count() == 0:
        for c in CALIBS:
            db.add(Calib(**c))
        db.commit()

    if db.query(Rule).count() == 0:
        for r in RULES:
            db.add(Rule(**r))
        db.commit()

    existing = db.query(Sample).count()
    if existing < SAMPLE_TARGET:
        for s in _make_samples(SAMPLE_TARGET - existing, start=existing):
            db.add(Sample(**s))
        db.commit()

    # 老库回填：给历史样本补上 key_action（迁移新增列后为 NULL）
    missing = db.query(Sample).filter(Sample.key_action.is_(None)).all()
    if missing:
        for s in missing:
            pool = SUCCESS_ACTIONS[s.path_id] if s.result == "达成" else FAIL_ACTIONS[s.path_id]
            s.key_action = random.choice(pool)
        db.commit()
