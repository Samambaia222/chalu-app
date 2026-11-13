"""三路径机构/信息源目录
   - 所有 URL 都指向公开可访问的官网或权威信息渠道
   - 前端直接 render 成可点击按钮，用户在报告页/执行方案页可以直接跳过去
   - 每类都给了「调研入口 + 操作建议」，避免只是个链接清单
"""
from typing import Dict, Any, Optional

PATH_DIRECTORY: Dict[str, Any] = {
    "P_KAOY": {
        "name": "考研",
        "official": [
            {"label": "中国研究生招生信息网", "url": "https://yz.chsi.com.cn/",
             "note": "报名/查分/调剂唯一官方入口，研招网权威数据都在这里"},
            {"label": "各高校研究生院官网", "url": "https://yz.chsi.com.cn/sch/",
             "note": "查目标院校历年分数线、报录比、复试细则"},
        ],
        "data_source": [
            {"label": "目标院校报录比 + 复试线（目标院校官网）", "url": "https://yz.chsi.com.cn/sch/info/search.do",
             "note": "按院校/专业筛，能看到近 3 年报录比和分数线，用来判断跨档幅度是否可接受"},
            {"label": "教育部考研复试基本分数线", "url": "https://yz.chsi.com.cn/kyzx/kydt/",
             "note": "34 所自划线 + 国家线，用来判断是否能进复试"},
        ],
        "community": [
            {"label": "知乎考研板块", "url": "https://www.zhihu.com/topic/19552940/hot",
             "note": "找同校同专业达成目标者经验帖"},
            {"label": "小木虫考研", "url": "http://muchong.com/bbs/kaoyan.php",
             "note": "冷门院校/专业的内部信息比知乎多"},
        ],
        "action_template": [
            "打开研招网，搜目标院校专业近 3 年报录比",
            "对照自身 GPA 档次和报录比，微调院校清单（一冲一稳一保）",
            "去小木虫/知乎找对应专业的经验帖，看「失败的人踩了哪些坑」",
        ],
    },

    "P_KAOG": {
        "name": "考公",
        "official": [
            {"label": "中央机关及其直属机构公务员录用系统（国考）",
             "url": "https://bm.scs.gov.cn/pp/gkweb/core/web/ui/business/home/gkhome.html",
             "note": "每年 10 月报名，这里能查所有岗位条件和近 3 年进面分"},
            {"label": "各省公务员录用考试公告栏",
             "url": "https://www.chinagwyw.org/",
             "note": "国考 + 省考 + 选调生公告最全的聚合站，按省份筛岗位"},
        ],
        "data_source": [
            {"label": "国考职位表（下载 Excel）", "url": "https://bm.scs.gov.cn/pp/gkweb/core/web/ui/business/download/gkdownload.html",
             "note": "按「专业目录 + 学历要求 + 是否限应届」三重筛选，找出你能报的所有岗位"},
            {"label": "近 3 年各岗位进面分", "url": "https://www.chinagwyw.org/guokao/fenshu/",
             "note": "用来判断你的行测/申论目标分要拉到多少才稳"},
        ],
        "community": [
            {"label": "QZZN 论坛", "url": "https://bbs.qzzn.com/",
             "note": "考公第一论坛，有各省市局内人分享真实工作状态"},
            {"label": "B站「公考老司机」类 up", "url": "https://search.bilibili.com/all?keyword=公考经验",
             "note": "看行测刷题方法、申论批改思路的实操视频"},
        ],
        "action_template": [
            "打开国考职位表，按专业目录筛一遍你能报的岗位数量",
            "对照进面分，算出行测/申论分别需要多少分才稳进面",
            "去 QZZN 看对应岗位的前辈吐槽，判断自己能不能接受这份工作",
        ],
    },

    "P_JIUY": {
        "name": "就业",
        "sub_paths": [
            {
                "label": "外企",
                "sites": [
                    {"label": "LinkedIn 领英", "url": "https://www.linkedin.cn/",
                     "note": "外企 JD 最全的平台，也能看公司员工构成和部门扩张情况"},
                    {"label": "各外企 Careers 官网", "url": "https://www.jobs.ac.cn/careers",
                     "note": "直接跳目标公司的全球招聘页，比第三方平台 JD 更新更及时"},
                    {"label": "猎聘海外", "url": "https://www.liepin.com/global/",
                     "note": "针对留学生/双语人才的外企岗位聚合"},
                ],
                "tips": "外企招聘周期长（简历 → 网申 → 笔试 → 群面 → 终面），提前 3 个月投递，对英语和项目经历要求极高",
            },
            {
                "label": "国企/央企",
                "sites": [
                    {"label": "国资委招聘平台", "url": "http://www.sasac.gov.cn/n258825/n258895/index.html",
                     "note": "所有央企校招公告权威入口，岗位多、门槛统一"},
                    {"label": "国聘网", "url": "https://www.iguopin.com/",
                     "note": "国企/央企集中发布，能按行业 + 地区筛"},
                    {"label": "应届生求职网国企专区", "url": "https://www.yingjiesheng.com/guoji/index.html",
                     "note": "按行业聚合，也有行业薪资调研帖"},
                ],
                "tips": "国企/央企秋招时间与考公/考研高度重叠，且流程不透明，建议秋招只投目标国企，用简历/实习做敲门砖",
            },
            {
                "label": "民企/创业公司",
                "sites": [
                    {"label": "BOSS 直聘", "url": "https://www.zhipin.com/",
                     "note": "国内最大校招社招一体平台，HR 直接聊，反馈快"},
                    {"label": "牛客网", "url": "https://www.nowcoder.com/jobs/intern",
                     "note": "技术岗实习/校招第一选择，也有笔试题库"},
                    {"label": "脉脉", "url": "https://maimai.cn/",
                     "note": "看公司真实员工评价（加班强度/晋升/薪资），offer 谈判必看"},
                ],
                "tips": "民企/创业公司薪资弹性大，也容易踩坑。offer 到手后先去脉脉查该公司该部门的真实状况，再做决策",
            },
        ],
        "action_template": [
            "先定方向（外企/国企/民企 或 技术/产品/运营），不要三条腿走路",
            "去应届生求职网按岗位 JD 关键词重写简历",
            "实习/竞赛/课程项目至少有 2 个能讲清楚 STAR 结构的经历",
        ],
    },
}


# —— 省份 × 路径 专属官方信息源 ——
# 每个省份给出该省考公/考研/就业的核心官方入口和关键数据参考，
# 让用户在选定目标省份后，能看到该省三路径的直接对比和官方链接。
PROVINCE_DIRECTORY: Dict[str, Dict[str, Any]] = {
    "广东": {
        "name": "广东",
        "compare": {
            "P_KAOY": {"label": "考研", "desc": "华南理工/中大考研录取率约 15-20%，本地高校对广东生源有地域照顾",
                        "links": [
                            {"label": "华南理工大学研究生院", "url": "https://admission.scut.edu.cn/", "note": "985/211，广东本地工科首选"},
                            {"label": "中山大学研究生院", "url": "https://graduate.sysu.edu.cn/", "note": "985/211，医学/管理/社科强"},
                            {"label": "广东工业大学研究生院", "url": "https://admission.gdut.edu.cn/", "note": "工科性价比高，省内认可度好"},
                        ]},
            "P_KAOG": {"label": "考公", "desc": "广东省考竞争激烈（平均 25:1），珠三角岗位可入面分普遍 ≥130",
                        "links": [
                            {"label": "广东省公务员考试录用管理系统", "url": "https://www.gdzwfw.gov.cn/gwy/", "note": "省考唯一官方报名入口"},
                            {"label": "广东省选调生招录系统", "url": "https://www.gdzwfw.gov.cn/zwgk/202402/t20240223_509883.html", "note": "定向选调岗位，竞争远小于普通省考"},
                            {"label": "深圳公务员考试", "url": "https://www.sz.gov.cn/szzt2010/ztzl/zwgk/", "note": "单独招考，待遇最高但竞争也最强"},
                        ]},
            "P_JIUY": {"label": "就业", "desc": "广东 GDP 全国第一，深圳/广州制造业/互联网密集，应届生平均起薪 8-10 万",
                        "links": [
                            {"label": "广东人才市场", "url": "https://www.gdrc.com/", "note": "全省最大综合人才市场"},
                            {"label": "深圳人才网", "url": "https://www.szhr.com.cn/", "note": "深圳本地招聘信息最全"},
                            {"label": "广州高校毕业生就业网", "url": "https://www.gz.gov.cn/gzhrss/gzjob/", "note": "广州官方校招聚合"},
                        ]},
        },
    },
    "北京": {
        "name": "北京",
        "compare": {
            "P_KAOY": {"label": "考研", "desc": "北大/清华/人大等顶尖高校聚集，但报录比极低（<10%），名校光环效应强",
                        "links": [
                            {"label": "北京大学研究生招生网", "url": "https://grs.pku.edu.cn/", "note": "国内 TOP1 自划线院校，分数线高但含金量极高"},
                            {"label": "清华大学研究生招生网", "url": "https://yz.tsinghua.edu.cn/", "note": "工科/经管顶尖"},
                            {"label": "中国人民大学研究生招生网", "url": "https://grs.ruc.edu.cn/", "note": "社科/新闻/法学强校"},
                        ]},
            "P_KAOG": {"label": "考公", "desc": "国考大本营，部委岗位集中。北京市考平均竞争比 30:1，部分岗位要求硕士学历",
                        "links": [
                            {"label": "北京市公务员考试系统", "url": "https://www.bjpta.gov.cn/", "note": "北京市人事考试中心，报名唯一入口"},
                            {"label": "国家公务员局", "url": "http://www.scs.gov.cn/", "note": "国考权威发布平台"},
                        ]},
            "P_JIUY": {"label": "就业", "desc": "央企总部/互联网大厂/金融机构聚集地，应届生起薪 12-15 万，但落户/租房压力大",
                        "links": [
                            {"label": "北京人才市场", "url": "https://www.bjrc.com/", "note": "北京本地最大综合招聘平台"},
                            {"label": "前程无忧北京站", "url": "https://www.51job.com/beijing/", "note": "北京地区应届生岗位聚合"},
                        ]},
        },
    },
    "上海": {
        "name": "上海",
        "compare": {
            "P_KAOY": {"label": "考研", "desc": "复旦/交大/同济/华师 Top4，录取率 10-18%，上海本地院校就业地域优势明显",
                        "links": [
                            {"label": "复旦大学研究生招生网", "url": "https://gs.fudan.edu.cn/", "note": "国内 TOP 综合性大学"},
                            {"label": "上海交通大学研究生招生网", "url": "https://yz.sjtu.edu.cn/", "note": "工科/医科顶尖"},
                            {"label": "同济大学研究生招生网", "url": "https://yz.tongji.edu.cn/", "note": "建筑/土木/汽车强校"},
                        ]},
            "P_KAOG": {"label": "考公", "desc": "上海市考竞争比 30:1+，部分岗位要求硕士。待遇全国最高梯队之一",
                        "links": [
                            {"label": "上海市公务员考试报名系统", "url": "https://www.shanghai.gov.cn/", "note": "上海市人力资源和社会保障局下属人事考试中心"},
                        ]},
            "P_JIUY": {"label": "就业", "desc": "外企/金融/互联网总部聚集地，应届生平均起薪 10-12 万，但租房成本高",
                        "links": [
                            {"label": "上海人才服务中心", "url": "https://www.shanghai.gov.cn/", "note": "上海市官方人才服务"},
                            {"label": "应届生求职网上海专区", "url": "https://www.yingjiesheng.com/shanghai/", "note": "上海本地校招信息聚合"},
                        ]},
        },
    },
    "江苏": {
        "name": "江苏",
        "compare": {
            "P_KAOY": {"label": "考研", "desc": "南大/东大 985/211，河海/南师等强势双非，理工科整体水平高",
                        "links": [
                            {"label": "南京大学研究生招生网", "url": "https://gsas.nju.edu.cn/", "note": "985/211，文理强校"},
                            {"label": "东南大学研究生招生网", "url": "https://yz.seu.edu.cn/", "note": "985/211，工科强"},
                        ]},
            "P_KAOG": {"label": "考公", "desc": "江苏省考 A/B/C 三套卷，竞争比平均 22:1，苏州/南京待遇最优",
                        "links": [
                            {"label": "江苏省公务员考试网", "url": "http://www.jsgwyw.org/", "note": "江苏省人事考试中心下属"},
                        ]},
            "P_JIUY": {"label": "就业", "desc": "制造业发达（苏州工业园区/昆山），IT 外包和制造业岗位充足，起薪 7-9 万",
                        "links": [
                            {"label": "江苏人才网", "url": "https://www.jsrc.com/", "note": "江苏省官方人才招聘平台"},
                        ]},
        },
    },
    "浙江": {
        "name": "浙江",
        "compare": {
            "P_KAOY": {"label": "考研", "desc": "浙大 985/211 独树一帜，另有杭电/浙工大等强双非，IT 行业对口性强",
                        "links": [
                            {"label": "浙江大学研究生招生网", "url": "http://grs.zju.edu.cn/", "note": "985/211，IT/农业/医学强"},
                        ]},
            "P_KAOG": {"label": "考公", "desc": "浙江省考平均竞争比 25:1，工资待遇全国第一梯队（含公积金）",
                        "links": [
                            {"label": "浙江省公务员考试报名系统", "url": "https://www.zjks.com/", "note": "浙江省人事考试网"},
                        ]},
            "P_JIUY": {"label": "就业", "desc": "阿里巴巴/网易等互联网大厂聚集地，杭州数字经济全国领先，应届生起薪 10 万+",
                        "links": [
                            {"label": "浙江人才网", "url": "https://www.zjrc.com/", "note": "浙江省人才市场主办"},
                        ]},
        },
    },
    "湖北": {
        "name": "湖北",
        "compare": {
            "P_KAOY": {"label": "考研", "desc": "武大/华科 985/211，理工/财经/教育强校集中，竞争比 20:1",
                        "links": [
                            {"label": "武汉大学研究生院", "url": "https://gs.whu.edu.cn/", "note": "985/211，测绘/法学/经管强"},
                            {"label": "华中科技大学研究生院", "url": "http://gs.hust.edu.cn/", "note": "985/211，工科/医科强"},
                        ]},
            "P_KAOG": {"label": "考公", "desc": "湖北省考竞争比平均 20:1，武汉岗位优于地市",
                        "links": [
                            {"label": "湖北省公务员考试网", "url": "http://www.hbgwy.org/", "note": "湖北省人事考试中心"},
                        ]},
            "P_JIUY": {"label": "就业", "desc": "武汉光谷光电子/半导体产业发达，汽车工业（东风）岗位充足，起薪 6-8 万",
                        "links": [
                            {"label": "湖北人才网", "url": "https://www.hbrc.com.cn/", "note": "湖北省人才市场主办"},
                        ]},
        },
    },
    "四川": {
        "name": "四川",
        "compare": {
            "P_KAOY": {"label": "考研", "desc": "川大/电子科大 985/211，西南财经/西南交通行业认可度高",
                        "links": [
                            {"label": "四川大学研究生院", "url": "https://gs.scu.edu.cn/", "note": "985/211，综合性强校"},
                            {"label": "电子科技大学研究生院", "url": "https://gr.uestc.edu.cn/", "note": "985/211，电子/通信/计算机顶尖"},
                        ]},
            "P_KAOG": {"label": "考公", "desc": "四川省考竞争比平均 18:1，成都岗位竞争更激烈但待遇好",
                        "links": [
                            {"label": "四川省公务员考试系统", "url": "https://www.scpta.com.cn/", "note": "四川省人事考试网"},
                        ]},
            "P_JIUY": {"label": "就业", "desc": "成都数字经济/游戏产业发达，制造业向成都/德阳迁移，生活成本远低于北上广深",
                        "links": [
                            {"label": "四川人才网", "url": "https://www.scrc168.com/", "note": "四川省人才市场主办"},
                        ]},
        },
    },
    "广西": {
        "name": "广西",
        "compare": {
            "P_KAOY": {"label": "考研", "desc": "广西大学（211）为省内龙头，另有广西师范/广西医科等行业强校",
                        "links": [
                            {"label": "广西大学研究生院", "url": "https://yjsc.gxu.edu.cn/", "note": "211 院校，土木/农学强"},
                            {"label": "广西师范大学研究生院", "url": "https://www.gxnu.edu.cn/", "note": "文科/师范类强校"},
                        ]},
            "P_KAOG": {"label": "考公", "desc": "广西省考竞争比 15:1 左右，是录取性价比最高的省份之一",
                        "links": [
                            {"label": "广西公务员考试系统", "url": "https://www.gxpta.com.cn/", "note": "广西人事考试网"},
                        ]},
            "P_JIUY": {"label": "就业", "desc": "北部湾经济区/东盟产业带崛起，南宁/桂林机会增多，但整体薪资偏低（起薪 5-7 万）",
                        "links": [
                            {"label": "广西人才网", "url": "https://www.gxrc.com/", "note": "广西最大人才招聘平台"},
                        ]},
        },
    },
}


def get_directory(path_id: str) -> Dict[str, Any]:
    """获取全局路径目录"""
    return PATH_DIRECTORY.get(path_id, {})


def get_province_directory(province: str) -> Dict[str, Any]:
    """获取省份专属目录（含该省三路径对比 + 官方链接）"""
    return PROVINCE_DIRECTORY.get(province, {})
