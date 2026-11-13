"""决策报告内容增强服务
   基于个人画像与规则模板，为每条路径生成 优势 / 风险 / 行动建议"""
import json
from typing import Dict, Any, List, Optional

from ..models import User

# 硬约束未通过时的修复建议
REPAIR_TIPS = {
    "报名截止": "本年度报名已截止，可将该路径转入下一年度规划，先积累条件",
    "预算上限": "压缩报班支出，改用公开课/二手资料，或申请奖助学金补差",
    "时间投入": "当前备考时间不足，建议延长准备周期或降低目标档次",
    "学历门槛": "避开要求硕士的岗位/院校，或先读研再启动该路径",
}

# —— 性别专属行动建议（按 路径 × 专业大类 组合给出）——
# 注意：这些建议是基于历史匿名样本的统计规律（招录比例、行业结构等），
#       只作为决策参考，不构成性别刻板印象或歧视性结论。
GENDER_ACTION_TIPS = {
    "女": {
        "P_KAOY": {
            "default": [
                "保持每天 4-6 小时稳定复习节奏，情绪波动时不强行加码，每周给自己留半天缓冲",
                "优先报考导师研究方向与你兴趣高度匹配的院校/专业，避免盲目冲热门大牛组",
                "提前联系目标院校在读的同性别师姐，了解导师风格与课题组氛围",
            ],
            "计算机类": [
                "理工科女生考研复试普遍有加分（录取比高于报考比），初试分数达标后重点准备科研项目陈述",
                "导师选择时优先看近三年有女学生顺利毕业并继续深造的课题组",
            ],
            "文法类": [
                "文法类女生考研达成率略高于男生，可冲击更高档次院校（如 C9/Top2）",
                "公共管理/教育学/语言学方向导师对女生接受度高，可优先筛选",
            ],
            "理工类": [
                "部分工科专业课题组女生占比偏低，可提前邮件联系导师，展示扎实的数学/基础功底以打破偏见",
            ],
        },
        "P_KAOG": {
            "default": [
                "公共服务类岗位（民政/教育/卫生/妇联）女性招录占比普遍达 60%+，可优先筛选这些系统",
                "面试阶段注重展现沟通协调与服务意识，这是女生在公考中的普遍优势项",
                "关注「妇女工作专员」「儿童福利岗」等定向岗位，竞争比显著低于普通岗",
            ],
            "文法类": [
                "法检、教育、民政系统对文法女生需求量大，且面试打分中文字表达优势明显",
                "选调生报考时，女生可关注妇联/团委/教育口的定向选调，分配和发展更友好",
            ],
            "计算机类": [
                "政务信息化、大数据局、网安等部门每年招计算机女生，但名额少，需行测申论双 75+ 才稳",
            ],
            "理工类": [
                "三不限岗位中男生比例高，女生报考此类岗位面试需加强形象管理和结构化训练",
                "可关注应急管理、市场监管等部门的技术岗，招录时性别限制相对少",
            ],
        },
        "P_JIUY": {
            "default": [
                "简历中强化「合作/沟通/跨部门协调」类关键词（STAR 结构），这些是女生在非技术岗的普遍优势",
                "准备作品集/项目文档，用可验证的产出替代纯文字描述，减少简历筛选中的隐性门槛",
                "优先争取内推渠道（LinkedIn/学姐介绍），内推可绕过部分招聘系统的关键词过滤",
                "目标公司可先查 Glassdoor/脉脉上的性别构成与产假政策，选择对女性友好的平台",
            ],
            "计算机类": [
                "工科女生求职存在隐性门槛：简历关键词必须精确匹配 JD（如「高并发」「微服务」）",
                "LeetCode 刷到 Medium 30 题通过率 ≥ 60%，笔试环节可抵消性别偏见",
                "腾讯/阿里/字节每年有女性工程师专项招聘通道，关注「程序媛」专场",
                "面试时主动展示 GitHub 开源贡献或技术博客，代码产出是最硬的敲门砖",
            ],
            "经管类": [
                "四大会计师事务所、咨询公司、互联网 PM 岗对女生录取率高于男生，可作为主攻方向",
                "投行/VC 对性别偏见较明显，除非背景极强（清北复交海外），否则建议主攻买方/FA/企业投融资",
            ],
            "理工类": [
                "传统制造/建筑行业性别偏见较强，可转向新能源/智能制造/生物医药等新兴行业",
                "或通过转产品/项目管理/技术销售来绕开纯技术岗的性别门槛",
            ],
        },
    },
    "男": {
        "P_KAOY": {
            "default": [
                "考研中男生达成率略低于女生，初试目标分需上浮 5-10 分才能进同等档次院校复试",
                "保持稳定作息是男生考研最大的挑战，建议用 Pomodoro 番茄工作法强制固定每天 6 小时有效时间",
            ],
        },
        "P_KAOG": {
            "default": [
                "男生在公考中的优势岗位集中在公安/司法/消防/应急等系统，这些岗位体能要求是加分项",
                "行测数量关系男生普遍得分高，可把这一模块练到 80%+ 正确率，形成差异化优势",
            ],
        },
        "P_JIUY": {
            "default": [
                "制造业/基建/传统能源行业对男生需求大，可作为保底方向",
                "互联网大厂技术岗男女录取比接近，但销售/商务岗男生门槛略高（需更强抗压/出差意愿表现）",
            ],
        },
    },
}


def _tags(user: User) -> set:
    try:
        return set(json.loads(user.tags or "[]"))
    except (ValueError, TypeError):
        return set()


def _gpa_lo(user: User) -> float:
    try:
        return float(user.gpa_range.split("-")[0])
    except (ValueError, IndexError, AttributeError):
        return 3.0


def gender_analysis(user: User, path_id: str) -> List[str]:
    """返回该用户性别 × 路径 × 专业组合的专属行动建议列表。
       若用户性别未知（None/其他），返回空列表。"""
    g = user.gender
    if g not in ("男", "女"):
        return []
    path_tips = GENDER_ACTION_TIPS.get(g, {}).get(path_id, {})
    if not path_tips:
        return []
    tips = []
    default = path_tips.get("default", [])
    tips.extend(default)
    major_specific = path_tips.get(user.major_category, [])
    tips.extend(major_specific)
    # 去重
    seen = set()
    result = []
    for t in tips:
        if t not in seen:
            seen.add(t)
            result.append(t)
    return result


def build_card_analysis(user: User, path_id: str, feasible: bool,
                        violated: List[Dict[str, Any]],
                        psych: Optional[Dict[str, Any]] = None,
                        holland: Optional[Dict[str, Any]] = None) -> Dict[str, List[str]]:
    tags = _tags(user)
    gpa = _gpa_lo(user)
    strengths: List[str] = []
    risks: List[str] = []
    actions: List[str] = []

    if path_id == "P_KAOY":
        if user.school_tier in ("985", "211"):
            strengths.append("院校背景在复试与调剂中占优")
        if gpa >= 3.0:
            strengths.append("GPA 处于优势区间，专业基础扎实")
        if user.time_input in ("6-12月", "≥12月"):
            strengths.append("备考时间充裕，可支撑 2-3 轮系统复习")
        if "英语优势" in tags:
            strengths.append("英语已过六级，可将更多时间分配给专业课")
        if user.school_tier in ("二本", "其他"):
            risks.append("院校背景在复试中不占优，需用初试高分弥补")
        if gpa < 3.0:
            risks.append("GPA 偏低，专业课复习压力较大")
        if user.time_input in ("<3月", "3-6月"):
            risks.append("备考时间紧张，建议降低目标院校档次")
        if "跨专业" in tags:
            risks.append("跨考专业课零基础，需额外预留约 3 个月")
        actions = ["9 月前完成数学/专业课一轮复习，锁定 2 所目标院校（一冲一稳）",
                   "关注研招网与目标院校报录比，10 月正式报名",
                   "12 月进入真题模拟阶段，每周复盘进度"]
        if "跨专业" in tags:
            actions.insert(0, "暑假前通读目标专业 2 本核心教材，建立知识框架")

    elif path_id == "P_KAOG":
        if "党员身份" in tags:
            strengths.append("党员身份可报限党员岗位，竞争比显著更低")
        if "学生干部" in tags:
            strengths.append("符合选调生报考条件，多一条达成目标通道")
        if user.major_category == "文法类":
            strengths.append("专业对口岗位多，选岗空间大")
        if user.major_category == "经管类":
            strengths.append("财税/审计/经济管理类岗位招录量大")
        if user.school_tier == "985":
            strengths.append("可关注定向选调，竞争小于普通省考")
        if user.major_category in ("艺体类", "理工类"):
            risks.append("可报岗位有限，多集中在「三不限」，竞争激烈")
        if user.target_province in ("北京", "上海"):
            risks.append("一线城市岗位竞争激烈，部分要求硕士学历")
        actions = ["行测分模块刷题，优先突破言语、判断推理、资料分析",
                   "每周写 1 篇申论并对照参考答案修改",
                   "同步关注国考与省考公告，合理错峰报考"]
        if "党员身份" in tags and "学生干部" in tags:
            actions.insert(0, "优先准备选调生考试，竞争强度低于普通岗位")

    elif path_id == "P_JIUY":
        if user.major_category == "计算机类":
            strengths.append("目标行业岗位需求量大，秋招机会多")
        if "实践经历丰富" in tags:
            strengths.append("实习/项目经历是简历核心加分项")
        if user.target_province in ("广东", "浙江", "江苏"):
            strengths.append("目标省份产业密集，岗位供给充足")
        if gpa < 2.5:
            risks.append("部分企业会筛选成绩单，需在笔面试环节弥补")
        if "实践经历丰富" not in tags:
            risks.append("缺乏实习背书，简历初筛通过率偏低")
        if user.school_tier in ("二本", "其他"):
            risks.append("部分大厂卡学历门槛，建议中小厂与内推渠道并行")
        actions = ["秋招（9-11 月）前完成简历与作品集，目标投递 50 家",
                   "优先争取实习转正通道，其次校招正式批",
                   "准备 2 分钟自我介绍与项目经历的 STAR 描述"]
        if user.major_category == "计算机类":
            actions.append("刷 LeetCode 热题 100 道，应对笔试环节")

    # 硬约束命中：写入风险并给修复建议
    for v in violated:
        risks.append(f"硬约束未通过：{v['constraint_item']}（{v['detail']}）")
        tip = REPAIR_TIPS.get(v["constraint_item"])
        if tip:
            actions.append(tip)
    if not feasible and not violated:
        risks.append("存在未通过的硬约束，该路径本年度不可行")

    # 兴趣匹配度
    if holland:
        fit = holland["path_fit"].get(path_id)
        if fit is not None:
            if fit >= 65:
                strengths.append(f"霍兰德兴趣匹配度 {fit:.0f}/100（前三码 {holland['top_code']}），内在动机较强")
            elif fit < 40:
                risks.append(f"兴趣匹配度仅 {fit:.0f}/100（前三码 {holland['top_code']}），长期坚持需要额外设计正反馈")

    # 情绪状态影响
    if psych:
        lv = psych.get("advice", {}).get("level", "平稳")
        if lv == "高危":
            risks.insert(0, "心理自评显示情绪负荷较重，当前不宜启动高强度计划")
            actions.insert(0, "先预约学校心理咨询中心，稳定状态 2-4 周后再执行本路径")
        elif lv == "关注":
            risks.insert(0, "存在中度情绪困扰，可能影响备考/求职的持续性")
            actions.insert(0, "把每日任务量下调约 20%，每周固定一次与咨询师或信任的人沟通")

    # 性别专属建议（追加到 actions 末尾，不覆盖通用建议）
    gender_actions = gender_analysis(user, path_id)
    if gender_actions:
        actions.extend(gender_actions)

    return {"strengths": strengths, "risks": risks, "actions": actions}
