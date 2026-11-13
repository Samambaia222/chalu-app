"""自然语言建档解析服务
   用规则 + 关键词把用户的一段话转成结构化档案字段与特色标签
   （课程原型：不依赖大模型，解析过程完全可解释、可答辩演示）"""
import re
from typing import Dict, List, Any, Optional

TIERS = ["985", "211", "一本", "二本", "其他"]
MAJORS = ["计算机类", "经管类", "理工类", "文法类", "艺体类"]
GPAS = ["2.0-2.5", "2.5-3.0", "3.0-3.5", "3.5-4.0"]
BUDGETS = ["<5千", "5千-1万", "1万-1.5万", ">1.5万"]
PROVINCES = ["北京", "上海", "广东", "江苏", "浙江", "湖北", "四川", "广西", "其他"]
TIMES = ["<3月", "3-6月", "6-12月", "≥12月"]

FIELD_NAMES = {
    "school_tier": "院校层次",
    "major_category": "专业大类",
    "gpa_range": "GPA 区间",
    "budget_range": "预算区间",
    "target_province": "意向省份",
    "time_input": "时间投入",
}

MAJOR_KEYS = {
    "计算机类": ["计算机", "软件", "人工智能", "数据科学", "大数据", "网络", "信息安全", "物联网"],
    "经管类": ["会计", "金融", "经济", "电子商务", "工商", "财务", "管理", "市场", "国贸", "审计", "财政"],
    "理工类": ["机械", "电子", "电气", "土木", "自动化", "材料", "化学", "物理", "数学", "生物", "环境", "通信", "能源"],
    "文法类": ["法学", "法律", "中文", "汉语言", "新闻", "传播", "英语", "外语", "历史", "哲学", "教育", "政治", "社会"],
    "艺体类": ["美术", "音乐", "体育", "设计", "舞蹈", "影视", "动画"],
}

CITY_TO_PROV = {
    "杭州": "浙江", "宁波": "浙江", "温州": "浙江",
    "南京": "江苏", "苏州": "江苏", "无锡": "江苏",
    "广州": "广东", "深圳": "广东", "珠海": "广东",
    "武汉": "湖北", "成都": "四川",
    "南宁": "广西", "桂林": "广西", "柳州": "广西",
}

CN_NUM = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

TAG_RULES = [
    ("跨专业", ["跨考", "跨专业", "转专业"]),
    ("二战考生", ["二战", "三战", "再战"]),
    ("在职备考", ["在职", "边工作边", "工作几年"]),
    ("脱产备考", ["脱产", "全职备考"]),
    ("应届毕业生", ["应届", "大四", "即将毕业"]),
    ("实践经历丰富", ["实习", "项目经验", "竞赛", "获奖", "大创", "项目经历"]),
    ("英语优势", ["六级", "雅思", "托福", "英语好", "专八", "四级"]),
    ("党员身份", ["预备党员", "党员"]),
    ("学生干部", ["学生干部", "学生会", "班长", "团支书", "部长"]),
    ("地域偏好强", ["不想离家", "离家近", "留在本地", "回老家", "回乡"]),
    ("薪资导向", ["高薪", "赚钱", "薪资", "搞钱"]),
    ("偏好稳定", ["稳定", "铁饭碗", "体制内", "编制"]),
    ("决策焦虑", ["迷茫", "纠结", "焦虑", "不知道怎么办", "犹豫"]),
]

# 情绪维度关键词（自然语言中的情绪线索，会与量表结果互相印证）
EMOTION_RULES = [
    ("情绪低落", ["抑郁", "低落", "提不起劲", "没意思", "想哭", "难过", "绝望", "开心不起来", "压抑"]),
    ("焦虑紧张", ["紧张", "焦虑", "心慌", "坐立不安", "害怕", "担忧", "压力大", "崩溃", "喘不过气"]),
    ("睡眠困扰", ["失眠", "睡不着", "早醒", "多梦", "熬夜", "睡眠不好"]),
    ("自我否定", ["自卑", "没用", "配不上", "我不行", "很失败", "否定自己", "没价值"]),
    ("社交回避", ["不想社交", "不想见人", "孤独", "独来独往", "回避"]),
    ("躯体不适", ["头疼", "头痛", "没胃口", "食欲", "心慌", "胸闷", "乏力"]),
]

# 自伤/危机信号：命中即触发紧急提示（不做任何概率判断）
CRISIS_WORDS = [
    "不想活", "活不下去", "想死", "自杀", "轻生", "结束生命",
    "伤害自己", "自残", "没有意义活着",
]


def analyze_emotion(text: str) -> Dict[str, Any]:
    """识别自然语言中的情绪线索与危机信号"""
    tags = [tag for tag, keys in EMOTION_RULES if any(k in text for k in keys)]
    crisis = any(w in text for w in CRISIS_WORDS)

    if crisis:
        return {
            "tags": tags + ["危机信号"],
            "risk_flag": True,
            "severity": "high",
            "message": (
                "你提到的内容让我很在意。请先照顾好自己：可拨打全国心理援助热线 12356 "
                "或北京心理危机干预中心 010-82951332，也可以马上联系学校心理咨询中心，"
                "或告诉一位你信任的人。职业决策可以稍后再谈，你的安全最重要。"
            ),
        }
    # 多个情绪维度同时命中，视为需要关注
    severity = "medium" if len(tags) >= 2 else ("low" if tags else "none")
    message = ""
    if severity == "medium":
        message = "你的描述里出现了多方面情绪困扰，建议先完成 PHQ-9 / GAD-7 自评，系统会据此调整路径建议与执行节奏。"
    elif severity == "low":
        message = "你提到了一些情绪感受，已记录到档案。可在测评中心完成心理自评，让建议更贴合你的状态。"

    return {"tags": tags, "risk_flag": False, "severity": severity, "message": message}


def _tier(text: str, notes: List[str]) -> Optional[str]:
    if "985" in text:
        return "985"
    if "211" in text:
        return "211"
    if "双一流" in text:
        notes.append("「双一流」按 211 层次处理，可手动调整")
        return "211"
    if "双非" in text:
        notes.append("「双非」按一本处理，若为二本请手动调整")
        return "一本"
    if "二本" in text or "三本" in text:
        return "二本"
    if "一本" in text or "普通本科" in text or "公办本科" in text:
        return "一本"
    if "专科" in text or "大专" in text or "高职" in text:
        return "其他"
    if "民办" in text or "独立学院" in text:
        return "二本"
    return None


def _major(text: str) -> Optional[str]:
    for major, keys in MAJOR_KEYS.items():
        for k in keys:
            if k in text:
                return major
    return None


def _gpa_range(text: str) -> Optional[str]:
    # 百分制：均分/平均分/加权 85分
    m = re.search(r"(?:均分|平均分|加权平均分?|成绩)\D{0,5}?(\d{2})(?:\.\d+)?\s*分?", text)
    if m:
        score = float(m.group(1))
        if score >= 85:
            return "3.5-4.0"
        if score >= 80:
            return "3.0-3.5"
        if score >= 75:
            return "2.5-3.0"
        return "2.0-2.5"
    # GPA 数值：gpa 3.2 / 绩点3.2
    val = None
    m = re.search(r"(?:gpa|绩点|学分绩)\D{0,5}?(\d(?:\.\d+)?)", text, re.IGNORECASE)
    if m:
        val = float(m.group(1))
    else:
        # 兜底：排除金额后的裸小数（如 3.2）
        cleaned = re.sub(r"\d+(?:\.\d+)?\s*[万亿千元块]", "", text)
        m = re.search(r"(?<![\d.])([2-4]\.\d{1,2})(?![\d.])", cleaned)
        if m:
            val = float(m.group(1))
    if val is None:
        if re.search(r"前\s*(?:10|15|20)\s*%", text):
            return "3.5-4.0"
        if re.search(r"前\s*(?:30|40|50)\s*%", text):
            return "3.0-3.5"
        return None
    if val > 4.0:  # 5 分制折算
        val = val / 5 * 4
    if val >= 3.5:
        return "3.5-4.0"
    if val >= 3.0:
        return "3.0-3.5"
    if val >= 2.5:
        return "2.5-3.0"
    return "2.0-2.5"


def _budget_range(text: str, notes: List[str]) -> Optional[str]:
    v = None
    m = re.search(r"(\d+(?:\.\d+)?)\s*万", text)
    if m:
        v = float(m.group(1)) * 10000
    else:
        m = re.search(r"([一二两三四五六七八九])\s*千", text)
        if m:
            v = CN_NUM[m.group(1)] * 1000
        else:
            m = re.search(r"(\d{4,})\s*(?:元|块)", text)
            if m:
                v = float(m.group(1))
    if v is None:
        if re.search(r"预算紧张|没什么钱|经济.{0,3}(紧张|困难)|家境一般", text):
            v = 4000
        elif re.search(r"预算充足|不差钱", text):
            v = 20000
    if v is None:
        return None
    if v < 5000:
        return "<5千"
    if v < 10000:
        return "5千-1万"
    if v <= 15000:
        return "1万-1.5万"
    return ">1.5万"


def _province(text: str, notes: List[str]) -> Optional[str]:
    for p in PROVINCES[:-1]:
        if p in text:
            return p
    for city, prov in CITY_TO_PROV.items():
        if city in text:
            return prov
    if "江浙沪" in text:
        notes.append("「江浙沪」按江苏处理，可手动调整")
        return "江苏"
    if "北上广" in text or "一线城市" in text:
        notes.append("「一线城市」按北京处理，可手动调整")
        return "北京"
    return None


def _time_input(text: str) -> Optional[str]:
    if re.search(r"两年|二年|一年半|两年半", text):
        return "≥12月"
    m = re.search(r"(\d{1,2})\s*(?:个)?月", text)
    if m:
        v = int(m.group(1))
        if v < 3:
            return "<3月"
        if v < 6:
            return "3-6月"
        if v <= 12:
            return "6-12月"
        return "≥12月"
    if "一年" in text or "1年" in text:
        return "6-12月"
    if "半年" in text:
        return "3-6月"
    return None


def _tags(text: str) -> List[str]:
    found = []
    for tag, keys in TAG_RULES:
        if any(k in text for k in keys):
            found.append(tag)
    return found


def parse_text(text: str) -> Dict[str, Any]:
    """主入口：返回解析出的字段、特色标签、缺失项与处理备注"""
    notes: List[str] = []
    fields = {
        "school_tier": _tier(text, notes),
        "major_category": _major(text),
        "gpa_range": _gpa_range(text),
        "budget_range": _budget_range(text, notes),
        "target_province": _province(text, notes),
        "time_input": _time_input(text),
    }
    missing = [FIELD_NAMES[k] for k, v in fields.items() if v is None]
    emotion = analyze_emotion(text)
    # 特色标签 + 情绪标签（去重保序）
    merged = list(dict.fromkeys(_tags(text) + emotion["tags"]))
    return {
        "fields": fields,
        "tags": merged,
        "missing": missing,
        "notes": notes,
        "emotion": emotion,
    }
