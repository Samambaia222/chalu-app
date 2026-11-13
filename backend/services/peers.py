"""S2 同伴结果追踪与匹配服务 —— 自省定位版
   加权欧氏相似度 sim = 1 - sqrt(0.30·d1² + 0.25·d2² + 0.25·d3² + 0.20·d4²)
   Top-K=200，阈值 0.6

   三个核心问题（自省定位，非焦虑叙事）：
   - 我在同类（院校×专业×GPA×省份）同辈中处于什么位置
   - 同性别同辈走这条路的达成率是多少，差距在哪
   - 他们做对了什么（只给参考，不给对比焦虑）

   注意：性别故意不进入相似度计算（避免歧视），
         性别只在分析层体现为「同性别子群统计」。"""
import math
from collections import Counter
from typing import Dict, Any, List, Optional, Tuple
from sqlalchemy.orm import Session
from ..models import User, Sample

WEIGHTS = {"school_tier": 0.30, "major_category": 0.25, "gpa_range": 0.25, "target_province": 0.20}
THRESHOLD = 0.6
TOP_K = 200

TIER_ORDER = {"985": 0, "211": 1, "一本": 2, "二本": 3, "其他": 4}
GPA_ORDER = {"2.0-2.5": 0, "2.5-3.0": 1, "3.0-3.5": 2, "3.5-4.0": 3}
GPA_MID = {"2.0-2.5": 2.25, "2.5-3.0": 2.75, "3.0-3.5": 3.25, "3.5-4.0": 3.75}
PATH_NAMES = {"P_KAOY": "考研", "P_KAOG": "考公", "P_JIUY": "就业"}


def _norm_diff(user_val: str, sample_val: str, order: Dict[str, int]) -> float:
    """归一化差异：两个有序类别间的距离 / 最大可能距离"""
    if user_val == sample_val:
        return 0.0
    u = order.get(user_val, 2)
    s = order.get(sample_val, 2)
    max_dist = len(order) - 1
    return abs(u - s) / max_dist if max_dist > 0 else 0.0


def similarity(user: User, sample: Sample) -> float:
    d1 = _norm_diff(user.school_tier, sample.school_tier, TIER_ORDER)
    d2 = 0.0 if user.major_category == sample.major_category else 1.0
    d3 = _norm_diff(user.gpa_range, sample.gpa_range, GPA_ORDER)
    # 省份：相同给 0，不同给 0.5（同区域仍有参考价值，不一票否决）
    if not user.target_province or not sample.target_province:
        d4 = 0.3
    elif user.target_province == sample.target_province:
        d4 = 0.0
    else:
        d4 = 0.5
    dist = math.sqrt(
        WEIGHTS["school_tier"] * d1 * d1
        + WEIGHTS["major_category"] * d2 * d2
        + WEIGHTS["gpa_range"] * d3 * d3
        + WEIGHTS["target_province"] * d4 * d4
    )
    return round(1.0 - dist, 4)


def _top(items: List[Sample], key: str) -> str:
    vals = [getattr(s, key) for s in items if getattr(s, key)]
    if not vals:
        return "样本不足"
    return Counter(vals).most_common(1)[0][0]


def _rank_position(my_val: float, peer_vals: List[float]) -> Dict[str, Any]:
    """计算我的数值在同辈中的百分位排名。
       返回 {rank, total, percentile, desc}，percentile=100 表示排第一。"""
    if not peer_vals:
        return {"rank": None, "total": 0, "percentile": None, "desc": "样本不足，无法定位"}
    better = sum(1 for v in peer_vals if v > my_val + 0.001)
    total = len(peer_vals) + 1  # 包括自己
    rank = better + 1
    pct = round((total - rank) / total * 100)
    if pct >= 70:
        desc = f"比 {pct}% 的同辈条件更好"
    elif pct >= 40:
        desc = f"处于同辈的中间位置（优于 {pct}% 同辈）"
    elif pct >= 15:
        desc = f"比大部分同辈条件稍弱（优于 {pct}%）"
    else:
        desc = f"条件弱于多数同辈，但这意味着提升空间最大"
    return {"rank": rank, "total": total, "percentile": pct, "desc": desc}


def _self_position(user: User, matched: List[Tuple[float, Sample]]) -> Dict[str, Any]:
    """自省定位：我在同类同辈中的位置（院校×专业×GPA×省份 维度）。
       不做焦虑对比，只客观陈述排名和自省方向。"""
    items = [s for _, s in matched]
    if not items:
        return {"gpa_rank": None, "note": "匹配样本不足，无法定位"}

    # GPA 维度排名
    peer_gpas = [GPA_MID[s.gpa_range] for s in items if s.gpa_range in GPA_MID]
    my_gpa = GPA_MID.get(user.gpa_range, 3.25)
    gpa_rank = _rank_position(my_gpa, peer_gpas)

    # 院校层次排名
    peer_tiers = [TIER_ORDER[s.school_tier] for s in items if s.school_tier in TIER_ORDER]
    my_tier = TIER_ORDER.get(user.school_tier, 2)
    # 注意：TIER_ORDER 数字越小院校越好，所以排名逻辑反转
    if peer_tiers:
        better = sum(1 for t in peer_tiers if t < my_tier)
        tier_pct = round((len(peer_tiers) - better) / (len(peer_tiers) + 1) * 100)
        if tier_pct >= 70:
            tier_desc = f"院校层次优于 {tier_pct}% 的同类同辈"
        elif tier_pct >= 40:
            tier_desc = f"院校层次处于同类同辈中间水平"
        else:
            tier_desc = f"院校层次弱于多数同辈，可用 GPA/实习/项目经历补足"
    else:
        tier_desc = "样本不足"

    return {
        "gpa": {"my": user.gpa_range, "position": gpa_rank},
        "school_tier": {"my": user.school_tier, "desc": tier_desc},
        "note": "自省定位按相似度加权匹配后计算，仅展示你在同类条件中的相对位置，无优劣评判。",
    }


def _gender_comparison(user: User, items: List[Sample], path_id: str) -> Dict[str, Any]:
    """同性别 vs 异性别同辈在这条路径上的对比。
       返回客观统计 + 自省方向，不做「谁好谁坏」的价值判断。"""
    if not items or user.gender not in ("男", "女"):
        return {"my_gender_rate": None, "other_gender_rate": None, "direction": ""}

    same = [s for s in items if s.gender == user.gender]
    other = [s for s in items if s.gender not in (user.gender, None, "")]

    def _rate(arr):
        if not arr:
            return None, 0, 0
        succ = sum(1 for s in arr if s.result == "达成")
        return round(succ / len(arr), 3), succ, len(arr)

    my_rate, my_succ, my_tot = _rate(same)
    other_rate, ot_succ, ot_tot = _rate(other)

    direction = ""
    if my_rate is not None and other_rate is not None:
        diff = round((my_rate - other_rate) * 100, 1)
        path_zh = PATH_NAMES.get(path_id, path_id)
        if abs(diff) < 3:
            direction = f"在{path_zh}路径上，你的性别与异性别同辈达成率差异不大，重点看自身条件"
        elif diff < 0:
            direction = (f"在{path_zh}路径上，你的性别同辈达成率比异性别低 {abs(diff):.0f}%。"
                         f"可参考下方的同性别自省建议，看差距在哪里，针对性补强")
        else:
            direction = (f"在{path_zh}路径上，你的性别同辈达成率略高于异性别 {diff:.0f}%。"
                         f"这意味着方向选对了，可在此路径上加大投入")
    elif my_rate is not None:
        path_zh = PATH_NAMES.get(path_id, path_id)
        direction = f"同性别走{path_zh}路径的同辈达成率 {(my_rate * 100):.0f}%（{my_succ}/{my_tot} 人）"

    return {
        "my_gender": user.gender,
        "my_gender_rate": my_rate,
        "my_gender_success": my_succ,
        "my_gender_total": my_tot,
        "other_gender_rate": other_rate,
        "other_gender_success": ot_succ,
        "other_gender_total": ot_tot,
        "direction": direction,
    }


def _self_gap(user: User, items: List[Sample], path_name: str,
              same_gender_only: bool = False) -> List[Dict[str, Any]]:
    """自省差距：我在这条路径上与参考同辈（可限定同性别）的量化对比。
       完全去掉「达成目标 vs 未达成」的焦虑叙事，只陈述事实 + 自省方向。"""
    ref = items if not same_gender_only else [s for s in items if s.gender == user.gender]
    if not ref:
        return []

    rows = []

    gpas = [GPA_MID[s.gpa_range] for s in ref if s.gpa_range in GPA_MID]
    if gpas:
        ref_gpa = round(sum(gpas) / len(gpas), 2)
        my_gpa = GPA_MID.get(user.gpa_range, 3.25)
        diff = round(my_gpa - ref_gpa, 2)
        if diff > 0.15:
            advice = f"你的 GPA（{my_gpa}）比参考同辈均值高 {diff}，这是加分项，在材料中突出"
        elif diff < -0.15:
            advice = f"你的 GPA（{my_gpa}）比参考同辈均值低 {abs(diff)}，建议用实习/作品/竞赛补足"
        else:
            advice = f"你的 GPA（{my_gpa}）与参考同辈均值基本持平，不是短板也不需额外强化"
        rows.append({"item": "GPA", "me": f"{my_gpa}", "peer": f"{ref_gpa}", "advice": advice})

    tiers = [TIER_ORDER[s.school_tier] for s in ref if s.school_tier in TIER_ORDER]
    if tiers:
        ref_tier_score = sum(tiers) / len(tiers)
        my_tier = TIER_ORDER.get(user.school_tier, 2)
        ref_name = min(TIER_ORDER, key=lambda k: abs(TIER_ORDER[k] - ref_tier_score))
        # tier 数字越小越好
        if my_tier - ref_tier_score > 0.4:
            advice = f"参考同辈多来自{ref_name}，你的院校背景偏弱，可靠项目/实习/提前准备弥补"
        elif ref_tier_score - my_tier > 0.4:
            advice = f"你的院校层次（{user.school_tier}）高于参考同辈均值（{ref_name}），可在简历/面试中强调"
        else:
            advice = f"你的院校层次与参考同辈均值（{ref_name}）接近"
        rows.append({"item": "院校层次", "me": user.school_tier, "peer": ref_name, "advice": advice})

    prov_ref = _top(ref, "target_province")
    if prov_ref != "样本不足" and user.target_province:
        if prov_ref == user.target_province:
            rows.append({"item": "目标省份", "me": user.target_province, "peer": prov_ref,
                         "advice": "与多数参考同辈同省份，区域信息可直接复用"})
        else:
            rows.append({"item": "目标省份", "me": user.target_province, "peer": prov_ref,
                         "advice": f"参考同辈更多流向{prov_ref}，可关注该地区的岗位/院校信息作为补充"})

    return rows


# 动作 → 社媒平台映射（按「关键词」匹配，命中即推荐）
# 每个 entry: keywords(任一命中即匹配) + platforms(该动作专属的社媒/信息源)
ACTION_PLATFORMS: List[Dict[str, Any]] = [
    # ---- 考研 ----
    {"keywords": ["定校", "目标院校", "定目标", "锁定专业", "跨档", "院校过高"],
     "platforms": [
         {"name": "研招网院校库", "url": "https://yz.chsi.com.cn/sch/", "note": "官方院校目录、招生简章、报录比"},
         {"name": "知乎择校话题", "url": "https://www.zhihu.com/search?type=content&q=考研择校", "note": "择校避坑、跨档风险评估"},
     ]},
    {"keywords": ["真题", "刷题", "刷课", "刷完"],
     "platforms": [
         {"name": "王道论坛(计算机)", "url": "https://www.cskaoyan.com", "note": "计算机考研真题、专业课资料"},
         {"name": "小红书考研真题", "url": "https://www.xiaohongshu.com/search_result?keyword=考研真题", "note": "达成目标的学长姐真题笔记"},
     ]},
    {"keywords": ["英语", "单词", "打卡"],
     "platforms": [
         {"name": "扇贝单词", "url": "https://www.shanbay.com", "note": "考研词汇打卡小组"},
         {"name": "唐迟阅读(B站)", "url": "https://search.bilibili.com/all?keyword=唐迟阅读", "note": "考研英语阅读方法论"},
     ]},
    {"keywords": ["辅导", "报班", "一对一", "自习室", "节奏", "线下"],
     "platforms": [
         {"name": "考研帮论坛", "url": "https://www.kaoyan.com", "note": "辅导班评价、自习室合租"},
     ]},
    # ---- 考公 ----
    {"keywords": ["行测", "裸考", "系统训练"],
     "platforms": [
         {"name": "粉笔公考APP", "url": "https://www.fenbi.com", "note": "行测专项题库、免费模考、AI批改"},
         {"name": "华图/中公题库", "url": "https://www.huatu.com", "note": "行测各模块专项突破"},
     ]},
    {"keywords": ["申论", "批改"],
     "platforms": [
         {"name": "申论一点通", "url": "https://www.shenlun.com", "note": "申论批改、范文、高分模板"},
         {"name": "半月谈", "url": "http://www.banyuetan.org", "note": "时政素材、申论大作文论据"},
     ]},
    {"keywords": ["模考"],
     "platforms": [
         {"name": "粉笔模考", "url": "https://www.fenbi.com/mock", "note": "每周日全国模考、排名"},
     ]},
    {"keywords": ["选岗", "低竞争", "限制条件", "三不限", "热门岗位"],
     "platforms": [
         {"name": "公考雷达", "url": "https://www.gongkaoleida.com", "note": "按条件筛岗位、看历年进面分/竞争比"},
         {"name": "国家公务员局", "url": "http://www.scs.gov.cn", "note": "国考职位表、官方公告"},
     ]},
    {"keywords": ["时政", "积累"],
     "platforms": [
         {"name": "学习强国", "url": "https://www.xuexi.cn", "note": "时政要闻、评论员文章"},
     ]},
    # ---- 就业 ----
    {"keywords": ["实习", "暑假实习", "对口实习", "两段实习"],
     "platforms": [
         {"name": "实习僧", "url": "https://www.shixiseng.com", "note": "在校生实习机会聚合、大厂暑期实习"},
         {"name": "牛客网", "url": "https://www.nowcoder.com/jobs/intern", "note": "大厂实习内推、面经"},
     ]},
    {"keywords": ["简历", "JD", "简历空白"],
     "platforms": [
         {"name": "超级简历", "url": "https://www.wondercv.com", "note": "大厂简历模板、AI 优化"},
         {"name": "牛客网面经", "url": "https://www.nowcoder.com/discuss", "note": "目标公司面经、笔试题"},
     ]},
    {"keywords": ["算法", "LeetCode", "力扣"],
     "platforms": [
         {"name": "LeetCode力扣", "url": "https://leetcode.cn", "note": "高频面试题、公司真题、周赛"},
         {"name": "牛客网真题", "url": "https://www.nowcoder.com/intelligentTest", "note": "华为/阿里/字节真题集"},
     ]},
    {"keywords": ["作品集", "项目", "GitHub", "开源"],
     "platforms": [
         {"name": "GitHub", "url": "https://github.com", "note": "代码仓库、作品集展示"},
         {"name": "掘金开源", "url": "https://juejin.cn/open-source", "note": "国内开源项目实践"},
     ]},
    {"keywords": ["投递", "提前投递", "秋招末", "只投大厂", "保底"],
     "platforms": [
         {"name": "BOSS直聘", "url": "https://www.zhipin.com", "note": "企业直聊、实时反馈"},
         {"name": "应届生求职网", "url": "https://www.yingjiesheng.com", "note": "秋招宣讲会、校招信息"},
         {"name": "LinkedIn领英", "url": "https://www.linkedin.cn", "note": "外企/大厂内推"},
     ]},
    {"keywords": ["技术细节", "讲不清", "讲项目"],
     "platforms": [
         {"name": "牛客网面试题", "url": "https://www.nowcoder.com/ta", "note": "技术面高频题、项目深挖"},
         {"name": "一亩三分地", "url": "https://www.1point3acres.com", "note": "面试复盘、技术细节问答"},
     ]},
]

# 通用 fallback 平台（匹配不上时）
GENERIC_PLATFORMS: List[Dict[str, str]] = [
    {"name": "知乎", "url": "https://www.zhihu.com", "note": "搜「路径名+经验/复盘/攻略」"},
    {"name": "小红书", "url": "https://www.xiaohongshu.com", "note": "搜「路径名+达成目标/备考/求职」"},
    {"name": "B站", "url": "https://search.bilibili.com/all?keyword=路径名", "note": "路径名相关免费视频课/经验分享"},
    {"name": "豆瓣小组", "url": "https://www.douban.com/group/", "note": "搜「路径名小组」找圈内讨论"},
]

# 动作 → 「用户应该怎么做」的专属指导语（按关键词匹配，每条都不一样）
# 每个 entry: keywords + guidance（针对该类动作的具体可执行建议，不是泛泛而谈）
# 注意：匹配是「第一条命中即返回」，所以顺序很重要——
#       就业放最前（避免被考研的「实习」等宽词截胡），
#       同一类里更具体的词放前面（如「简历」在「实习」前）。
ACTION_GUIDANCE_TEMPLATES: List[Dict[str, str]] = [
    # ---- 考研「边实习边备考」放最前：关键词极特殊，不会误匹配就业实习 ----
    {"keywords": ["边实习边备考", "精力被摊薄", "实习摊薄", "精力摊薄"],
     "guidance": "边实习边备考的核心矛盾是精力不够。两个选择："
                 "① 实习做到 8 月底，9 月开始全职备考（适合暑期实习）；"
                 "② 如果是日常实习，跟导师申请减到每周 2 天，其余 5 天全天备考。"
                 "切忌「白天实习 8 小时晚上再学 4 小时」，两头都顾不好。"},
    # ---- 就业（放前面，避免被考研宽词截胡）----
    {"keywords": ["技术细节", "讲不清", "讲项目"],
     "guidance": "技术面「深挖项目」是大多数人的痛点。准备方法："
                 "把简历上每个项目用「STAR + 数据」结构准备一遍——"
                 "S(背景)为什么做、T(任务)你负责什么、A(行动)怎么做的、R(结果)有什么数据指标。"
                 "技术细节要能讲清：为什么选这个技术栈？遇到什么坑？怎么解决的？"
                 "如果项目是跟着教程做的，一定要自己扩展 1-2 个功能，否则一问就露馅。"},
    {"keywords": ["简历", "JD", "简历空白"],
     "guidance": "简历是 HR 筛选的第一道关，关键是「匹配度」。"
                 "每投一家公司，把 JD 里的关键词（技术栈/技能/经验）精准写进简历，通过率能翻 2 倍。"
                 "如果简历空白（无实习无项目）：立刻做 1-2 个可展示的项目（GitHub 上 fork 一个有 star 的项目，"
                 "读懂后加 1-2 个功能，写进简历），比空等有用。"},
    {"keywords": ["实习", "暑假实习", "对口实习", "两段实习"],
     "guidance": "实习是就业最硬的敲门砖。优先级：大厂实习 > 对口实习 > 任何实习。"
                 "时间线：大三暑假（7-8月）必须有一段实习，这是秋招简历的核心。"
                 "如果只有一段，至少要 2 个月以上，且能写出具体产出（做了什么、用了什么技术、结果怎样）。"
                 "两段实习的公司最好有梯度（一段大厂+一段中小厂，或两段不同方向）。"},
    {"keywords": ["算法", "LeetCode", "力扣"],
     "guidance": "算法题是大厂笔试的硬门槛。刷题路径："
                 "LeetCode 前 200 题按主题刷（数组→链表→树→图→动态规划），每题做不出来就看解法、隔 3 天重做。"
                 "刷到 200 题后，针对性刷目标公司的真题集（牛客网有各公司真题）。"
                 "面试前 2 周每天做 3 题保持手感，不要「刷完就忘」。"},
    {"keywords": ["作品集", "GitHub", "开源"],
     "guidance": "项目作品集的价值：证明你「能动手」，而不是只会说。"
                 "做 2-3 个有展示性的项目（前端可部署、后端有 GitHub README），每个项目写清楚："
                 "解决什么问题、用了什么技术栈、有什么数据/性能指标。"
                 "开源贡献门槛低但加分高：给你常用的库提个小 PR（修 bug/加文档/加测试），"
                 "简历上写「已合并 N 个 PR」是技术面的加分项。"},
    {"keywords": ["秋招末", "投递晚", "开始晚"],
     "guidance": "秋招末期才开始投递确实被动，但还有补救："
                 "① 立刻投所有还在招的中小厂（大厂基本招满了，但中小厂补录到 1 月）；"
                 "② 关注春招（3-4 月），把它当主战场；"
                 "③ 同时准备考公/考研作为退路，11 月开始备考省考完全来得及。"
                 "秋招没拿到不要慌，春招岗位量是秋招的 1/3 但竞争也小。"},
    {"keywords": ["投递", "提前投递"],
     "guidance": "投递时间点极其重要：秋招提前批（7-8 月）竞争最小，正式批（9-11 月）岗位最多，"
                 "秋招末期（11 月底-12 月）只剩补录。"
                 "策略：7 月投提前批拿 offer 保底，9-10 月投正式批冲刺，11 月只投还没招满的。"
                 "投递后 7 天没回应就主动跟 HR，很多 offer 是「跟进」出来的。"},
    {"keywords": ["只投大厂", "保底"],
     "guidance": "只投大厂等于把鸡蛋放一个篮子。正确的投递组合是「2-3-3」："
                 "2 家冲（够一够能进的大厂）+ 3 家稳（匹配度高的中厂）+ 3 家保（必能拿到 offer 的小厂）。"
                 "保底 offer 不是让你去，而是给你谈薪和心态的底气。"
                 "没有保底的人在面试中会过度紧张，反而发挥不好。"},
    # ---- 考研 ----
    {"keywords": ["跨档", "院校过高"],
     "guidance": "跨档报考（二本冲 985、211 冲 C9）失败率很高，但不是不可能。"
                 "关键是：① 提前 12 个月以上准备；② 专业课真题刷透目标院校 10 年；"
                 "③ 初试分要比复试线高 30 分以上才能抵消出身劣势。"
                 "如果时间不足 6 个月，建议降一档目标，不要硬冲。"},
    {"keywords": ["定校", "目标院校", "定目标", "锁定专业"],
     "guidance": "定校不要只看名气，用「报录比」和「复试线」两个硬指标筛："
                 "先把目标院校近 3 年报录比拉出来，如果报录比 >20:1 说明竞争激烈；"
                 "再看复试线和你当前模考分差，差距 >30 分要谨慎。"
                 "建议选 1 个冲、1 个稳、1 个保三档院校，9 月报名前最终确认。"},
    {"keywords": ["真题"],
     "guidance": "真题是命题人思维最直接的载体，模拟题不如真题。"
                 "正确做法：近 10 年真题至少刷 3 遍——"
                 "第 1 遍掐时间完整做（暴露漏洞），第 2 遍按考点归类做（把薄弱章节补起来），"
                 "第 3 遍只做前两遍错的题（消灭盲点）。每刷一遍错题本要更新。"},
    {"keywords": ["视频课", "看视频", "不动手"],
     "guidance": "只刷视频课不做题 = 无效备考。视频课只是帮你理解知识点，真正提分靠动手。"
                 "建议：看完一章视频课，立刻做对应章节的 10 道题，当天消化。"
                 "视频课每天不超过 3 小时，剩下时间留给刷题和复盘。"},
    {"keywords": ["英语", "单词", "打卡"],
     "guidance": "考研英语词汇量要求 5500，建议用「艾宾浩斯遗忘曲线」背："
                 "每天新词 50 + 复习旧词 150，3 个月过完一轮。"
                 "单词不要只背中文意思，要配例句一起记；阅读真题里的生词必须全部摘录背诵。"
                 "每天 40 分钟，坚持到考前一天。"},
    {"keywords": ["时间不足", "9 月", "复习晚", "启动晚"],
     "guidance": "9 月才开始复习确实晚了，但不等于没机会。"
                 "策略：放弃「全面复习」，改「真题驱动」——"
                 "直接从近 5 年真题入手，把每套真题的每道题考点搞透；"
                 "数学只抓高数和线代，概率论战略性放弃；"
                 "专业课只背重点章节。目标从「冲高分」降为「过线」。"},
    {"keywords": ["辅导", "报班", "一对一", "自习室", "节奏"],
     "guidance": "报班不是必须的，但如果你自律性差，报班/自习室能帮你建立外部约束。"
                 "专业课一对一的价值在于「目标院校在读学长学姐」带你划重点，比自己盲看效率高 2-3 倍。"
                 "选择标准：看达成目标学员名单的真实性，不要只看宣传。"},
    {"keywords": ["6 小时", "有效学习"],
     "guidance": "备考时长不是越长越好，关键是「有效学习时长」。"
                 "建议：用番茄工作法（25 分钟专注 + 5 分钟休息），每天记录有效学习时长。"
                 "6 小时有效学习 > 10 小时磨洋工。每周复盘：哪段时间效率最高？把最难的科目放到那段时间。"
                 "避免假努力：抄笔记、整理资料不算学习，只有「输出」（做题、背诵、默写）才算。"},
    # ---- 考公 ----
    {"keywords": ["行测", "裸考", "系统训练", "5000"],
     "guidance": "行测不要裸考，系统训练才能提速。行测核心是「放弃」："
                 "120 分钟做 135 题，平均每题 53 秒，不可能每题都认真做。"
                 "策略：言语(30题)、判断(35题)、资料(20题) 这 85 题是拿分主力，正确率拉到 80%+；"
                 "数量(15题)挑 5 道简单的做，其余全蒙 C；常识(25题) 靠平时积累，不花专门时间。"},
    {"keywords": ["申论", "批改", "每周写"],
     "guidance": "申论提分靠「写 + 改」，不是靠背模板。"
                 "每周写 1 篇大作文 + 2 道小题，写完找已达成目标的人或粉笔 AI 批改。"
                 "大作文结构：开头亮观点（30 字内）+ 2-3 个分论点（每个配 1 个案例）+ 结尾升华。"
                 "案例平时积累：半月谈、人民日报评论，每周记 3 个可用案例。"},
    {"keywords": ["申论从未", "从未写过", "不动笔"],
     "guidance": "申论不动笔是最大的坑——很多人行测 70+ 但申论 40 多分，差距全在这里。"
                 "最低要求：考前至少完整写 5 套申论真题，每套严格按 3 小时计时。"
                 "写完对照参考答案看「要点遗漏」，而不是「文采」——申论是按点给分的。"},
    {"keywords": ["模考"],
     "guidance": "模考的价值不是分数，是「时间分配」和「心态」。"
                 "建议考前每周参加一次粉笔模考，重点看：① 每模块花了多久（超时的模块要提速）；"
                 "② 涂卡是否出错；③ 连续 2 小时是否疲劳。"
                 "模考成绩不用太在意，和真实考试差 10 分很正常。"},
    {"keywords": ["选岗", "低竞争", "限制条件", "三不限", "热门岗位"],
     "guidance": "考公七分选岗三分考。选岗黄金法则：「限得越多，竞争越小」。"
                 "优先顺序：限应届 > 限专业 > 限学历 > 限户籍 > 限政治面貌。"
                 "三不限岗位竞争比通常 100:1+，能不报就不报。"
                 "用公考雷达查近 3 年该岗位进面分，比去年高 10 分以上的岗要谨慎。"},
    {"keywords": ["时政", "积累"],
     "guidance": "时政每天 30 分钟足够，用学习强国+半月谈。"
                 "重点记：近半年重大会议、政策文件、领导人讲话原文。"
                 "时政在常识题里只占 10 分，不用花太多时间，性价比不如行测三大模块。"},
    {"keywords": ["应届", "一次达成目标"],
     "guidance": "应届身份是考公最大的红利——很多岗位只招应届，竞争比只有往届的 1/5。"
                 "建议：① 国考（11月）+ 省考（3-4月）都报，两次机会；"
                 "② 不要「先试试水」，第一次就全力备考，因为应届身份只有 1-2 年有效期；"
                 "③ 应届生面试劣势不大，重点拉笔试分。"},
    {"keywords": ["中断", "备考中断"],
     "guidance": "备考中断 1 个月，之前的积累会忘 60%。避免中断的方法："
                 "① 把备考拆成最小单位——每天至少做 10 道题保持手感，实在忙也至少 30 分钟；"
                 "② 中断后不要硬接原来的进度，用 2 天把之前的笔记和错题本过一遍再继续；"
                 "③ 不要有「中断了就放弃」的心态，捡起来继续就行。"},
]


def _match_guidance(action: str) -> str:
    """用关键词匹配专属指导语。命中第一条返回，没命中返回通用模板。"""
    for entry in ACTION_GUIDANCE_TEMPLATES:
        for kw in entry["keywords"]:
            if kw in action:
                return entry["guidance"]
    # 通用模板（不同动作通用，但也是具体可执行的，不是废话）
    return (
        "这件事被参考同辈中多人验证过，建议你先问自己三个问题再动手："
        "① 它和我当前目标路径（考研/考公/就业）是直接相关还是间接相关？"
        "② 我现在做这件事，3 个月后能看到可量化的结果吗？"
        "③ 如果我只做这一件事而不是另一件，机会成本有多大？"
        "想清楚后，用 1 周时间小步试做，用数据决定是否加码。"
    )


def _match_platforms(action: str, path_id: str) -> List[Dict[str, Any]]:
    """用关键词匹配专属平台。没命中返回通用平台（路径名替换进 URL）。"""
    matched = []
    for entry in ACTION_PLATFORMS:
        for kw in entry["keywords"]:
            if kw in action:
                matched.extend(entry["platforms"])
                break
    if not matched:
        matched = [dict(p) for p in GENERIC_PLATFORMS]
        path_name = PATH_NAMES.get(path_id, "目标路径")
        for p in matched:
            p["url"] = p["url"].replace("路径名", path_name)
    return matched


def _build_action_guidance_and_platforms(actions: List[Dict[str, Any]],
                                         path_id: str) -> List[Dict[str, Any]]:
    """把 _key_actions 的输出扩展成链式方案：同辈做了X → 你应该怎么做 → 去哪找参考。
    用稳定的 action 文本作为主键，避免重排后错位（经验教训 2）。"""
    if not actions:
        return []
    for item in actions:
        action = item.get("action", "")
        item["guidance"] = _match_guidance(action)
        item["platforms"] = _match_platforms(action, path_id)
    return actions


def _key_actions_with_guidance(ref_items: List[Sample],
                               path_id: str,
                               limit: int = 4) -> List[Dict[str, Any]]:
    """带链式方案的关键动作：同辈做了什么 → 你应该怎么做 → 去哪个社媒找参考。"""
    if not ref_items:
        return []
    cnt = Counter(s.key_action for s in ref_items if s.key_action)
    total = len(ref_items)
    base = [
        {"action": a, "count": c, "ratio": round(c / total, 3), "action_id": a[:30]}
        for a, c in cnt.most_common(limit)
    ]
    return _build_action_guidance_and_platforms(base, path_id)


def _most_similar_core_actions(matched: List[tuple], top_n: int = 20) -> List[Dict[str, Any]]:
    """取最像的 Top-N 同辈（按相似度排序），聚合他们做对了什么核心动作。

    策略：
    1. 取相似度 Top-20
    2. 优先看其中 result=="达成" 的人的 key_action
    3. 如果「达成」样本不足 3 个，扩展到 Top-50 里的所有「达成」样本
    4. 按 key_action 频次排序取 Top-3
    """
    if not matched:
        return []

    # 第一步：取相似度 Top-20 的「达成」样本
    top_samples = matched[:top_n]
    succ_items = [(sim, s) for sim, s in top_samples if s.result == "达成"]

    # 如果不够，扩展到 Top-50
    if len(succ_items) < 3:
        wider = matched[:max(top_n, 50)]
        succ_items = [(sim, s) for sim, s in wider if s.result == "达成"]

    # 如果还不够（说明这个用户 profile 太少见，没达成样本参考），退回到所有 top_samples（不管 result）
    if len(succ_items) < 2:
        succ_items = top_samples

    # 统计频次
    action_cnt: Counter = Counter()
    action_by_path: Dict[str, List[str]] = {}
    for sim, s in succ_items:
        if s.key_action:
            action_cnt[s.key_action] += 1
            action_by_path.setdefault(s.path_id, []).append(s.key_action)

    if not action_cnt:
        return []

    total = len(succ_items)
    out: List[Dict[str, Any]] = []
    for action, cnt in action_cnt.most_common(3):
        paths = set()
        for pid, acts in action_by_path.items():
            if action in acts:
                paths.add(PATH_NAMES.get(pid, pid))
        out.append({
            "action_id": action[:30],
            "action": action,
            "peer_count": cnt,
            "peer_total": total,
            "ratio": round(cnt / total, 3),
            "paths_appear": list(paths),
            "note": (
                f"在最像你的 {total} 位参考同辈中，"
                f"{cnt} 个（约 {cnt/total*100:.0f}%）把这件事做对了。"
                f"这说明这不是运气，而是条件相近的人跨越门槛的共同路径。"
            ),
        })
    return out


def _community_feed(user: User, matched: List[tuple], path_id: str,
                    top_n: int = 3) -> List[Dict[str, Any]]:
    """根据 matched 同辈在 path_id 上的 key_action，生成社区动态链接。

    每条返回: {action, platform_name, url, note, peer_count}
    每种 action 类型从 ACTION_PLATFORMS 取对应平台，action 匹配不上时用 GENERIC_PLATFORMS。
    """
    path_samples = [s for _, s in matched if s.path_id == path_id]
    if not path_samples:
        return []

    # 统计该路径上同辈的 key_action
    cnt = Counter(s.key_action for s in path_samples if s.key_action)
    total = len(path_samples)

    out: List[Dict[str, Any]] = []
    used_urls = set()

    # 按 action 频次遍历，每个 action 用 _match_platforms 映射到专属平台
    for action, count in cnt.most_common(top_n * 2):  # 多看一些动作，确保能凑够 top_n 个好链接
        matched_plats = _match_platforms(action, path_id)

        for plat in matched_plats:
            url = plat.get("url", "")
            if url in used_urls:
                continue
            used_urls.add(url)
            ratio = round(count / total, 3) if total > 0 else 0.0
            out.append({
                "action": action,
                "platform_name": plat.get("name", ""),
                "url": url,
                "note": plat.get("note", ""),
                "peer_count": count,
                "peer_ratio": ratio,
                "why": (
                    f"{count} 位相似同辈（{ratio*100:.0f}%）在{PATH_NAMES.get(path_id, path_id)}路径上做了「{action}」，"
                    f"这个平台是圈内人聚集交流的地方"
                ),
            })
            if len(out) >= top_n:
                return out

    return out


def match_peers(user: User, db: Session) -> Dict[str, Any]:
    """主入口：返回匹配到的同辈自省定位与可行动洞察"""
    samples = db.query(Sample).all()
    matched = []
    for s in samples:
        sim = similarity(user, s)
        if sim >= THRESHOLD:
            matched.append((sim, s))
    matched.sort(key=lambda x: x[0], reverse=True)
    matched = matched[:TOP_K]

    stats = {}
    self_profile = {}   # 自省定位（替代 success_profile / fail_profile）
    self_gaps = {}      # 自省差距（替代 _gap）
    gender_gaps = {}    # 同性别自省差距
    actions = {}
    gender_cmp = {}     # 同性别 vs 异性别对比

    for pid, pname in PATH_NAMES.items():
        items = [s for _, s in matched if s.path_id == pid]
        succ = [s for s in items if s.result == "达成"]
        fail = [s for s in items if s.result == "未达成"]
        pending = sum(1 for s in items if s.result == "未行动")
        total = len(items)
        rate = round(len(succ) / total, 4) if total > 0 else 0.0
        stats[pid] = {
            "path_name": pname,
            "success": len(succ),
            "fail": len(fail),
            "pending": pending,
            "total": total,
            "rate": rate,
        }

        # 自省定位：我在同类条件同辈中的位置
        self_profile[pid] = {
            "path_name": pname,
            "reference_summary": {
                "school_tier": _top(items, "school_tier"),
                "major_category": _top(items, "major_category"),
                "gpa_range": _top(items, "gpa_range"),
                "target_province": _top(items, "target_province"),
            } if items else None,
        }

        # 自省差距（所有参考同辈 + 同性别子群）
        self_gaps[pid] = _self_gap(user, items, pname, same_gender_only=False)
        gender_gaps[pid] = _self_gap(user, items, pname, same_gender_only=True)

        # 关键动作（链式方案：同辈做了什么 → 你怎么做 → 去哪找参考）
        actions[pid] = _key_actions_with_guidance(items, pid)

        # 同性别对比
        gender_cmp[pid] = _gender_comparison(user, items, pid)

    # 自省定位总览
    self_position = _self_position(user, matched)

    # 相似度最高的同辈明细（脱敏，只展示条件组合与结果，不做好坏评判）
    top_matches = [
        {
            "similarity": sim,
            "path_id": s.path_id,
            "path_name": PATH_NAMES.get(s.path_id, s.path_id),
            "feature_summary": s.feature_summary,
            "target_province": s.target_province or "未填",
            "result": s.result,
            "key_action": s.key_action or "未填写",
            "gender": s.gender or "未填",
        }
        for sim, s in matched[:8]
    ]

    # 性别差异统计：按路径 + 性别分组的达成率
    gender_split: Dict[str, Dict[str, Dict[str, float]]] = {}
    for pid, pname in PATH_NAMES.items():
        by_g: Dict[str, List[str]] = {"男": [], "女": []}
        for s in samples:
            if s.path_id != pid:
                continue
            g = s.gender if s.gender in ("男", "女") else None
            if g is None:
                continue
            by_g[g].append(s.result)
        per = {}
        for g in ("男", "女"):
            arr = by_g[g]
            tot = len(arr)
            succ = sum(1 for r in arr if r == "达成")
            per[g] = {
                "total": tot,
                "success": succ,
                "rate": round(succ / tot, 3) if tot > 0 else None,
            }
        gender_split[pid] = per

    total_matched = len(matched)
    fallback = total_matched < 25

    # 最像的同辈做对了什么核心动作（需求3）
    most_similar_core = _most_similar_core_actions(matched)

    # 社区动态聚合：按路径取 top-3 社媒链接（改动 4）
    community_feed: Dict[str, Any] = {}
    for pid, pname in PATH_NAMES.items():
        community_feed[pid] = {
            "path_id": pid,
            "path_name": pname,
            "items": _community_feed(user, matched, pid, top_n=3),
        }

    # 可信度评估
    if total_matched >= 60:
        conf_level, conf_reason = "高", f"匹配到 {total_matched} 位条件相近的同辈，结论可参考性强"
    elif total_matched >= 25:
        conf_level, conf_reason = "中", f"匹配到 {total_matched} 位同辈，结论方向可靠，细节需结合自身判断"
    else:
        conf_level, conf_reason = "低", f"仅匹配到 {total_matched} 位同辈，样本偏少，已退回全校同路径基线"

    return {
        "total": total_matched,
        "stats": stats,
        "self_position": self_position,    # 自省定位
        "profiles": self_profile,          # 自省参考画像
        "gaps": self_gaps,                 # 自省差距（所有参考）
        "gender_gaps": gender_gaps,        # 同性别自省差距
        "gender_comparison": gender_cmp,   # 同性别vs异性别对比
        "key_actions": actions,            # 链式方案（同辈做了什么→你怎么做→社媒）
        "most_similar_core": most_similar_core,  # 最像同辈的核心动作（新增）
        "community_feed": community_feed,  # 社区动态聚合（改动 4）
        "top_matches": top_matches,
        "confidence": {"level": conf_level, "reason": conf_reason},
        "gender_split": gender_split,
        "features": {
            "school_tier": user.school_tier,
            "major_category": user.major_category,
            "gpa_range": user.gpa_range,
            "target_province": user.target_province,
            "user_gender": user.gender,
            "similarity_threshold": THRESHOLD,
            "top_k": TOP_K,
            "fallback_to_baseline": fallback,
            "note": "有效样本不足25，已退回全校同路径基线，结果仅供参考" if fallback else "匹配充足",
        },
    }
