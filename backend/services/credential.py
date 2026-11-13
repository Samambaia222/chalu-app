"""凭证审查服务（双轨：AI 主路径 + 规则降级）

   真实 OCR/LLM 依赖外部服务，不可用时走可解释规则。
   核心设计：无论走哪条路，输出结构统一为
   {review_status, review_score, review_note, proof_type, extracted_text}
"""
import os
import re
import uuid
import json
import mimetypes
from datetime import datetime
from typing import Dict, Any, Optional

ALLOWED_IMG = {"image/jpeg", "image/png", "image/heic", "image/webp"}
ALLOWED_PDF = {"application/pdf"}
MAX_BYTES = 8 * 1024 * 1024  # 8 MB
PROOF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "proofs")


def ensure_dir() -> str:
    os.makedirs(PROOF_DIR, exist_ok=True)
    return PROOF_DIR


def save_proof(file_bytes: bytes, original_name: str) -> Dict[str, Any]:
    """保存上传文件，返回元信息"""
    if len(file_bytes) > MAX_BYTES:
        raise ValueError(f"文件过大（>{MAX_BYTES // 1024 // 1024}MB）")

    ensure_dir()
    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else "bin"
    cred_id = uuid.uuid4().hex[:12].upper()
    filename = f"{cred_id}.{ext}"
    full = os.path.join(PROOF_DIR, filename)
    with open(full, "wb") as f:
        f.write(file_bytes)

    mime, _ = mimetypes.guess_type(original_name)
    cat = "image" if mime in ALLOWED_IMG else ("pdf" if mime in ALLOWED_PDF else "unknown")

    return {
        "credential_id": cred_id,
        "filename": original_name,
        "saved": filename,
        "path": full,
        "size": len(file_bytes),
        "mime": mime or "application/octet-stream",
        "category": cat,
    }


# ---------------- AI 审查主路径 ----------------
# 可用环境变量：CHALU_LLM_ENDPOINT / CHALU_LLM_API_KEY / CHALU_OCR_ENDPOINT
# 格式示例：CHALU_LLM_ENDPOINT=https://api.deepseek.com/v1/chat/completions

def _call_llm(prompt: str) -> Optional[str]:
    endpoint = os.getenv("CHALU_LLM_ENDPOINT")
    key = os.getenv("CHALU_LLM_API_KEY")
    if not endpoint or not key:
        return None
    try:
        import urllib.request
        data = json.dumps({
            "model": os.getenv("CHALU_LLM_MODEL", "deepseek-chat"),
            "messages": [
                {"role": "system", "content": "你是一位凭证审查员，只返回 JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }).encode()
        req = urllib.request.Request(
            endpoint, data=data, method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read().decode())
        return body["choices"][0]["message"]["content"]
    except Exception:
        return None


def _ocr_image(img_path: str) -> Optional[str]:
    """OCR 主路径（环境变量 CHALU_OCR_ENDPOINT 指向 OCR 服务）"""
    endpoint = os.getenv("CHALU_OCR_ENDPOINT")
    if not endpoint:
        return None
    try:
        import urllib.request
        import base64
        with open(img_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        req = urllib.request.Request(
            endpoint,
            data=json.dumps({"image": b64}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            body = json.loads(r.read().decode())
        return body.get("text", "")
    except Exception:
        return None


def ai_review(proof_path: str, category: str,
              path_id: str, claimed_result: str) -> Dict[str, Any]:
    """AI 审查主路径，失败自动降级"""
    text = ""

    # 1. OCR / 文字提取
    if category == "image":
        text = _ocr_image(proof_path) or ""
    elif category == "pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(proof_path)
            text = "\n".join(p.extract_text() or "" for p in reader.pages[:3])
        except Exception:
            text = ""
    # 文本文件（fallback）直接读
    elif category == "text":
        try:
            with open(proof_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read(4000)
        except Exception:
            text = ""

    # 2. 让 LLM 判断
    if text:
        prompt = (
            f"请判断以下文件文本是否能证明「{PATH_LABEL[path_id]}·{RESULT_LABEL[claimed_result]}」。\n"
            "输出 JSON：{proof_type, confidence 0-1, reason, found_keywords}\n"
            "文件文本如下（若与路径不匹配也要诚实说明）：\n" + text[:2000]
        )
        llm_out = _call_llm(prompt)
        if llm_out:
            try:
                cleaned = re.search(r"\{.*\}", llm_out, re.S)
                obj = json.loads(cleaned.group() if cleaned else llm_out)
                conf = max(0.0, min(1.0, float(obj.get("confidence", 0.5))))
                return {
                    "review_status": "verified" if conf >= 0.6 else ("pending" if conf >= 0.4 else "rejected"),
                    "review_score": round(conf, 3),
                    "review_note": str(obj.get("reason", "AI 审查完成")),
                    "proof_type": str(obj.get("proof_type", "其他")),
                    "proof_text": text,
                    "verify_method": "ai_ocr",
                }
            except Exception:
                pass

    # 3. 降级：可解释规则
    return rule_fallback(text, category, path_id, claimed_result)


# ---------------- 规则降级 ----------------

PATH_LABEL = {"P_KAOY": "考研", "P_KAOG": "考公", "P_JIUY": "就业"}
RESULT_LABEL = {"达成": "已达成目标", "未达成": "尚未达成"}

KEYWORDS = {
    "P_KAOY": {"达成": ["录取通知书", "拟录取", "研究生院", "入学通知书", "master", "录取"],
               "未达成": ["调剂到", "未进入复试", "复试未通过", "成绩未达", "未达到"]},
    "P_KAOG": {"达成": ["录用通知", "拟录用", "公务员", "事业单位", "体检", "政审"],
               "未达成": ["未进入面试", "未入围", "成绩未达", "资格复审未通过"]},
    "P_JIUY": {"达成": ["offer", "录用通知书", "入职", "劳动合同", "三方协议", "已发放 offer"],
               "未达成": ["未通过面试", "简历未通过", "笔试未通过"]},
}

TYPE_GUESS = {
    "offer": ["offer", "录用", "hire", "入职"],
    "录取通知书": ["录取", "研究生院", "拟录取"],
    "成绩单": ["成绩单", "分数", "总分", "成绩查询"],
    "公务员录用": ["公务员", "事业单位", "录用"],
}


def rule_fallback(text: str, category: str,
                  path_id: str, claimed_result: str) -> Dict[str, Any]:
    """可解释规则：关键词命中数 → 可信度，永远给出一个可读结论"""
    text_lower = text.lower()
    expected = KEYWORDS.get(path_id, {}).get(claimed_result, [])
    hit = [kw for kw in expected if kw.lower() in text_lower]
    score = round(min(1.0, 0.3 + 0.2 * len(hit)), 3) if text else 0.35

    if score >= 0.7:
        status = "verified"
        reason = f"命中关键词：{', '.join(hit) or '（文件可读但关键词不明显）'}，可接受"
    elif score >= 0.4:
        status = "pending"
        reason = f"关键词命中弱（{hit or '无显式匹配'}），建议人工再确认"
    else:
        status = "pending" if text else "rejected"
        reason = "未能从文件中读到足够文字来验证，建议上传清晰图片/PDF"

    # 猜凭证类型
    ptype = "其他"
    for label, kws in TYPE_GUESS.items():
        if any(k.lower() in text_lower for k in kws):
            ptype = label
            break

    return {
        "review_status": status,
        "review_score": score,
        "review_note": reason,
        "proof_type": ptype,
        "proof_text": text[:2000],
        "verify_method": "规则" if not text else "规则+文件名判断",
    }


# ---------------- 决策是否纳入同辈样本 ----------------

def decide_integration(review_score: float, review_status: str) -> bool:
    """审查可信度 >= 0.6 且状态 verified 的凭证，才自动纳入样本库"""
    return review_status == "verified" and review_score >= 0.6


def new_sample_id() -> str:
    return "S" + uuid.uuid4().hex[:10].upper()


# ---------------- 规则化信息抽取（OCR 不可用时 / 用户粘贴文字） ----------------

# 预定义词典
COMPANY_KEYWORDS = [
    "腾讯", "阿里", "阿里巴巴", "字节跳动", "字节", "美团", "百度", "华为",
    "网易", "京东", "小米", "OPPO", "vivo", "比亚迪", "宁德时代",
    "微软", "谷歌", "Google", "Microsoft", "苹果", "Apple", "亚马逊", "Amazon",
]

ROLE_KEYWORDS = [
    "前端", "后端", "算法", "产品", "运营", "测试", "数据", "运维",
    "嵌入式", "硬件", "客户端", "Android", "iOS", "机器学习", "推荐",
    "Java", "Python", "Golang", "C++", "全栈",
]

CITY_KEYWORDS = [
    "深圳", "广州", "北京", "上海", "杭州", "成都", "武汉", "南京",
    "苏州", "西安", "长沙", "厦门", "重庆", "天津", "青岛", "郑州",
    "合肥", "济南", "福州", "无锡", "宁波",
]


def auto_extract_offer_info(text: str) -> Dict[str, Any]:
    """从上传的文字（OCR 或用户粘贴）提取 offer 信息。

    返回 {"company": ..., "role": ..., "salary": ..., "city": ...,
          "confidence": 0-1, "raw": {...命中的证据...}}
    """
    text_lower = text.lower()

    # 公司名
    found_companies = [c for c in COMPANY_KEYWORDS if c.lower() in text_lower]
    company = found_companies[0] if found_companies else ""

    # 岗位
    found_roles = [r for r in ROLE_KEYWORDS if r.lower() in text_lower]
    role = found_roles[0] if found_roles else ""

    # 薪资：正则匹配 "数字k/月" / "数字K" / "年薪数字w" / "base数字"
    salary = ""
    m = re.search(r"(\d+)\s*[kK]\s*/?\s*月?", text)
    if m:
        salary = f"{m.group(1)}k/月"
    else:
        m = re.search(r"年薪[^0-9]{0,5}(\d+)\s*[wW]", text)
        if m:
            salary = f"{m.group(1)}w/年"
        else:
            # base 后跟数字（可能是 3-6 位月薪，也可能是 2 位的 "40w" 年薪简写）
            m = re.search(r"[Bb]ase[^0-9]{0,3}(\d{2,6})", text)
            if m:
                salary = f"base {m.group(1)}"

    # 城市
    found_cities = [c for c in CITY_KEYWORDS if c in text]
    city = found_cities[0] if found_cities else ""

    # 置信度：每命中一项给 0.25 基础，再按命中项数加权
    hit_count = sum([bool(company), bool(role), bool(salary), bool(city)])
    # 还要看是否有 offer 关键词
    has_offer_kw = bool(re.search(r"offer|录用|入职|三方", text_lower))
    base = 0.15 * hit_count + (0.3 if has_offer_kw else 0.0)
    confidence = round(min(1.0, base), 3)

    return {
        "company": company,
        "role": role,
        "salary": salary,
        "city": city,
        "confidence": confidence,
        "raw": {
            "found_companies": found_companies,
            "found_roles": found_roles,
            "found_cities": found_cities,
            "has_offer_keyword": has_offer_kw,
        },
    }


# 考研 / 考公 关键词
KAOYAN_SUBJECTS = ["政治", "英语一", "英语二", "英语", "数学一", "数学二", "数学三", "数学", "专业课", "总分"]
KAOGONG_SUBJECTS = ["行测", "申论", "总分", "常识判断", "言语理解", "数量关系", "判断推理", "资料分析"]


def auto_extract_grade_info(text: str) -> Dict[str, Any]:
    """从成绩单文字提取考研 / 考公分数。"""
    text_lower = text.lower()

    # 判断类型
    is_kaoyan = any(k in text for k in ["考研", "研究生", "初试", "复试", "政治", "英语一", "英语二"])
    is_kaogong = any(k in text for k in ["行测", "申论", "公务员", "国考", "省考", "公考"])

    if is_kaoyan and not is_kaogong:
        exam_type = "kaoyan"
        subjects = KAOYAN_SUBJECTS
    elif is_kaogong and not is_kaoyan:
        exam_type = "kaogong"
        subjects = KAOGONG_SUBJECTS
    elif is_kaoyan and is_kaogong:
        exam_type = "kaoyan"  # 冲突时默认考研
        subjects = KAOYAN_SUBJECTS
    else:
        exam_type = "unknown"
        subjects = KAOYAN_SUBJECTS + KAOGONG_SUBJECTS

    # 提取分数：每个科目名后紧跟数字（允许冒号、空格、tab）
    scores: Dict[str, str] = {}
    for subj in subjects:
        # 精确匹配：科目名 → 可选冒号/空格 → 数字
        m = re.search(rf"{re.escape(subj)}\s*[:：]?\s*(\d{{2,4}}(?:\.\d+)?)", text)
        if m:
            scores[subj] = m.group(1)

    # 院校 / 岗位
    school_or_post = ""
    if exam_type == "kaoyan":
        m = re.search(r"(?:报考|目标|拟录取|录取)\s*(?:院校|学校|单位|专业)?\s*[:：]?\s*([\u4e00-\u9fa5A-Za-z]{4,30}?(?:大学|学院|研究所))", text)
        if m:
            school_or_post = m.group(1)
    elif exam_type == "kaogong":
        m = re.search(r"(?:报考|招录|岗位|职位)\s*[:：]?\s*([\u4e00-\u9fa5A-Za-z0-9]{6,40})", text)
        if m:
            school_or_post = m.group(1)

    # 置信度
    score_count = len(scores)
    has_total = "总分" in scores or any("total" in k.lower() for k in scores)
    base = min(1.0, 0.2 + 0.15 * score_count + (0.25 if has_total else 0.0))
    if exam_type == "unknown":
        base *= 0.6
    confidence = round(min(1.0, base), 3)

    return {
        "exam_type": exam_type,
        "scores": scores,
        "school_or_post": school_or_post,
        "confidence": confidence,
    }


# ---------------- 文本版凭证审查入口 ----------------

def review_text_credential(proof_text: str, path_id: str,
                           claimed_result: str,
                           proof_type: Optional[str] = None) -> Dict[str, Any]:
    """用户粘贴的文字版凭证，先用 auto_extract，再走 rule_fallback 兜底。

    这是 review_credential 流程的「文字版」分支，替代原来只能上传图片/PDF 的路径。
    """
    text = proof_text.strip()

    # 1. 先按 path_id 决定跑哪套抽取器
    extracted: Dict[str, Any] = {}
    if path_id == "P_JIUY":
        extracted = auto_extract_offer_info(text)
    elif path_id in ("P_KAOY", "P_KAOG"):
        extracted = auto_extract_grade_info(text)

    # 2. 用规则审查确定 review_status / review_score
    base = rule_fallback(text, "text", path_id, claimed_result)

    # 3. 如果抽取器给了高置信度，把 review_score 提上去
    ext_conf = extracted.get("confidence", 0.0)
    if ext_conf >= 0.7:
        base["review_score"] = round(max(base["review_score"], ext_conf), 3)
        base["review_status"] = "verified"
        base["review_note"] = (
            f"规则抽取命中（置信度 {ext_conf:.2f}），"
            + (f"提取到：{extracted}" if ext_conf >= 0.8 else "建议人工复核")
        )
    elif ext_conf >= 0.4:
        base["review_score"] = round(max(base["review_score"], 0.5), 3)
        base["review_status"] = "pending"

    # 4. 覆盖 proof_type（如果用户没指定）
    if proof_type:
        base["proof_type"] = proof_type
    elif path_id == "P_JIUY":
        # 从抽取结果猜
        if extracted.get("company") and extracted.get("role"):
            base["proof_type"] = "offer"
    elif path_id == "P_KAOY":
        if extracted.get("exam_type") == "kaoyan":
            base["proof_type"] = "成绩单"
    elif path_id == "P_KAOG":
        if extracted.get("exam_type") == "kaogong":
            base["proof_type"] = "成绩单"

    base["proof_text"] = text[:2000]
    base["verify_method"] = "规则+文字粘贴"
    base["extracted"] = extracted  # 把结构化结果也带出去，前端可以展示

    return base
