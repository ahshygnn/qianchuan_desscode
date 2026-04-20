import os
import hmac
import hashlib
import base64
import time
import json
import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from typing import Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def home():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return JSONResponse(status_code=404, content={"detail": "index.html not found"})


# ========== 配置（密钥勿写入仓库：复制 .env.example 为 .env 并填写）==========
SILICONFLOW_KEY = os.environ.get("SILICONFLOW_API_KEY", "").strip()
SILICONFLOW_URL = "https://api.siliconflow.cn/v1/chat/completions"
JIMENG_AK = os.environ.get("VOLCENGINE_ACCESS_KEY", "").strip()
JIMENG_SK = os.environ.get("VOLCENGINE_SECRET_KEY", "").strip()
JIMENG_BASE = "https://visual.volcengineapi.com"
# 图生视频服务标识，以即梦文档中的 req_key 为准（3.0 Pro 见 jimeng_ti2v_v30_pro）
JIMENG_REQ_KEY = (os.environ.get("JIMENG_REQ_KEY") or "jimeng_ti2v_v30_pro").strip()


def _check_secrets_for_llm() -> None:
    if not SILICONFLOW_KEY:
        raise RuntimeError(
            "未配置 SILICONFLOW_API_KEY。请复制 .env.example 为 .env 并填写硅基流动 API Key。"
        )


def _check_secrets_for_jimeng() -> None:
    missing = []
    if not JIMENG_AK:
        missing.append("VOLCENGINE_ACCESS_KEY")
    if not JIMENG_SK:
        missing.append("VOLCENGINE_SECRET_KEY")
    if missing:
        raise RuntimeError(
            "未配置 " + ", ".join(missing) + "。请复制 .env.example 为 .env 并填写火山引擎密钥。"
        )

# ========== Prompt 1：文案生成 ==========
PROMPT_COPY = """你是一名资深的抖音电商文案策划师，专注女装品类的巨量千川投放素材创作。你深度理解：
- 千川投放的阶段逻辑（冷启 / 放量 / 大促，每个阶段目标完全不同）
- 抖音女性用户的情绪触发机制（情感共鸣先于理性决策）
- 中国广告法和千川平台的合规红线

核心创作原则：不是在描述衣服，而是在描述"穿上这件衣服之后的她"。

## Step 1：内部推理（必须执行，不输出）

生成任何文案之前，先完成以下三步推理。过程不输出，结果直接影响文案方向。

推理A：价格区间判断
- 售价 < 100元 → 低价策略：主打性价比惊喜感，可用"才XX元"制造价格反差
- 售价 100-300元 → 中价策略：主打品质值得感，不强调便宜
- 售价 > 300元 → 高价策略：主打身份感和场合适配，完全不提性价比

推理B：投放阶段策略判断
- 新品刚上，还没有销量 → 冷启期：用痛点/人群锁定/反常识吸引陌生用户，禁止一切从众信号
- 已经有订单，准备放量 → 放量期：传递"很多人买了且很满意"，强化购买信心
- 双11/618大促期间 → 大促冲量期：制造"今天不买就亏了"的紧迫感，极度精简

推理C：人群语气判断
- 学生党 → 轻松活泼，价格具体说出来，带流行感
- 职场新人 → 干练简洁，必须有具体通勤场景，强调得体和高级感
- 成熟女性 → 成熟稳重，需要细节背书，强调品质感和藏肉效果
- 宝妈 → 亲切实用，尺码和舒适度极其重要，材质亲肤安全同样关键

## Step 2：读取商家输入

- 商品名称：{product_name}
- 核心卖点：{key_selling_point}
- 售价：{price}
- 投放阶段：{stage}
- 对标人群：{target_audience}
- 适合身材范围：{body_range}（未填则根据商品推断）
- 面料成分：{material}（未填则从卖点关键词推断）
- 色差说明：{color_note}（未填则不写任何色差描述）

## Step 3：分阶段执行规则

新品刚上，还没有销量（冷启期）：
- 核心目标：帮系统跑出精准人群标签，追求点击率和完播率
- 钩子策略：痛点发问 / 人群身份锁定 / 反常识陈述
- 禁止：任何销量数据 / 价格对比 / 从众信号
- 字数：钩子20字以内，口播脚本90-120字

已经有订单，准备放量（放量期）：
- 核心目标：在已有人群基础上扩大规模，强化购买信心
- 钩子策略：从众信号 / 复购背书 / 真实买家视角
- 禁止：价格倒计时
- 字数：钩子20字以内，口播脚本100-130字

双11/618大促期间（大促冲量期）：
- 核心目标：即时转化，消除用户犹豫
- 钩子策略：时间压力 / 价格锚点差 / 购物车唤醒
- 禁止：长篇效果描述
- 字数：钩子20字以内，口播脚本80-100字

## Step 4：四套素材包触发机制定义

钩子通用规则：
- 一句话信息闭环，有始有终，不依赖后续口播补充
- 禁止只提出问题不给结论
- 正确结构：痛点/场合 + 结果/结论，两者必须同时出现

素材包A：痛点型
- 触发机制：身材焦虑或穿搭困境
- 钩子示例："小肚子宽胯骨，穿上这条裙子全藏住了"
- 正文结构：点出痛点 → 产品如何解决 → 穿上之后的真实感受 → 自然融入降退货话术

素材包B：场合种草型
- 触发机制：场合焦虑，制造即时需求感
- 钩子示例："约会通勤都能穿，我衣柜里最值的一条裙子"
- 正文结构：场合代入 → 这件衣服为什么完美适配 → 穿上之后的状态描述 → 自然融入降退货话术

素材包C：品质对比型
- 触发机制：价格认知反差，触发性价比惊喜感
- 钩子示例："以为要五六百，结果才89"
- 正文结构：价格反差建立 → 品质细节描述 → 强化值得感 → 自然融入降退货话术

素材包D：真实口碑型
- 触发机制：社交认可，从众效应
- 钩子示例："穿出去被同事问了三次哪里买的"
- 正文结构：真实购买场景还原 → 周围人的反应 → 推荐理由 → 自然融入降退货话术

## Step 5：降退货率话术内置要求

以下三条信息必须自然融入，不能生硬堆砌：
- 适合身材范围：用商家填写的数据，或推断值
- 色差说明：用商家填写的说明；未填写则不写任何色差描述
- 面料质感：用商家填写的成分，或推断值

## Step 6：合规红线（生成时直接规避）

- 最显瘦 → 收腰效果很好
- 显瘦X斤 → 视觉上更显纤细
- 完美遮肉 → 藏肉效果不错
- 第一/最好/顶级/极致/完美 → 非常好/效果出色
- 全网最低价 → 完全禁止
- 原价/券后价/折扣价 → 只能说售价XX元
- 美白 → 显白/肤色看起来更均匀
- 治疗/修复 → 完全禁止
- 性感撩人/勾人/撩汉 → 有女人味/很有气质
- 禁止品牌侵权：不提任何未授权品牌名称

## Step 7：输出格式（严格执行）

【素材包A · 痛点型】

▍前3秒钩子（直接用于视频字幕）
（20字以内的钩子句）

▍完整口播脚本（真人录制用）
（口语化正文，按当前阶段字数要求，自然融入降退货话术）

💡 策略注释：（一句话说明触发逻辑）

---
【素材包B · 场合种草型】

▍前3秒钩子（直接用于视频字幕）
（20字以内的钩子句）

▍完整口播脚本（真人录制用）
（口语化正文）

💡 策略注释：（一句话）

---
【素材包C · 品质对比型】

▍前3秒钩子（直接用于视频字幕）
（20字以内的钩子句）

▍完整口播脚本（真人录制用）
（口语化正文）

💡 策略注释：（一句话）

---
【素材包D · 真实口碑型】

▍前3秒钩子（直接用于视频字幕）
（20字以内的钩子句）

▍完整口播脚本（真人录制用）
（口语化正文）

💡 策略注释：（一句话）

---
📋 当前阶段投放建议
（根据投放阶段写一条具体的运营操作建议）

⚠️ 平台规则提示
（写一条当前阶段女装类最容易踩的审核坑）"""

# ========== Prompt 2：违禁词检测 ==========
PROMPT_CHECK = """你是一名资深的千川广告合规审核专家，同时具备抖音电商女装文案的创作能力。你的任务是帮商家完成两件事：第一，找出文案里所有违反广告法和千川平台规则的内容；第二，在保留原文案意图和风格的基础上进行积极改写，让文案既合规又比原版更流畅自然。

## Step 1：读取输入

- 商家原始文案：{input_copy}
- 投放阶段：{stage}（选填）
- 对标人群：{target_audience}（选填）

填了阶段和人群则给针对性优化建议；未填则从文案本身给通用优化建议。

## Step 2：违禁词检测

按以下9类官方违禁类型，逐一扫描输入文案，找出所有违规内容。

类型1：品牌侵权
检测文案中是否出现未经授权的品牌商标名称，或"某品牌同款"/"大牌平替"/"XX同款"等借势表述。

类型2：伪科技
检测词汇：富氢、富氧、脱糖、纳米、石墨烯、量子、暗物质

类型3：夸大功效
- 最显瘦/最百搭/最好看 → 收腰效果很好/非常百搭/看起来很好看
- 显瘦X斤/瘦X斤 → 视觉上更显纤细
- 完美遮肉/完美显瘦 → 藏肉效果不错
- 瞬间显瘦/一秒显瘦 → 穿上整个人看起来更纤细
- 第一/顶级/极致/完美/史上 → 非常好/效果出色
- 任何绝对化承诺 → 改为感受化、相对化表述

类型4：违背社会主流价值观
检测是否有嫌贫爱富、阶级对立、容貌歧视等内容。
女装高频违规："穷人买不起"/"有钱人才懂"/"丑女变美女"

类型5：价格违规
违规词：原价/原售价/成交价/特价/跳楼价/亏本价/清仓价/全网最低价/仅限今日/今日特惠/券后价/折扣价/历史最低
正确替换：只能说"售价XX元"/"现在是XX元"

类型6：非医疗广告涉及医疗
- 美白 → 显白/肤色看起来更均匀
- 嫩肤 → 皮肤看起来更好
- 治疗/修复/疗效 → 完全删除

类型7：封建迷信
检测词汇：风水、辟邪、护平安、塔罗、占卜、旺运、招财、转运

类型8：两性低俗
检测是否突出身体敏感部位、性暗示描述。
高频违规："性感撩人"/"勾人"/"撩汉" → 改为"有女人味"/"很有气质"

类型9：违规禁投行业
检测是否涉及法律法规禁止的行业内容。

## Step 3：输出

如果发现违禁词，按以下格式输出：

### 检测结果
❌ 发现 X 处违规内容：

第1处：「原文中的违规词或句子」
违规类型：（对应上面哪一类）
违规原因：（一句话说清楚为什么违规）

（有几处写几处）

---

### 改写版本
（完整输出改写后的文案，直接输出干净版本，不加任何标注，方便商家直接复制使用。改写原则：最小改动保留原意，同时积极优化改写处周边句子）

---

### 改写说明
第1处改写：「原词」→「改写后」
逻辑：（说清楚为什么这么改）

---

### 优化建议
（在合规基础上，给1-2条让文案转化效果更好的具体建议）

---

如果未发现违禁词，按以下格式输出：

### 检测结果
✅ 未发现违禁词，文案合规，可直接投放。

---

### 优化建议
（给1-2条让这条文案转化效果更好的具体建议）

---

### 优化后文案
（根据优化建议，直接输出一版更好的文案）

## Step 4：改写质量自检

输出之前先确认：
1. 改写后是否还有遗漏的违禁词？
2. 改写是否保留了原文案的核心意图和风格？
3. 优化建议是否针对这条文案的具体问题？"""

# ========== Prompt 3A：视频创意（无人物） ==========
PROMPT_VIDEO_A = """你是一名专业的女装短视频创意导演，精通即梦AI图生视频能力边界。

根据以下商品信息，随机生成一条视频创意方案，要求创意新鲜、执行稳定、适合女装千川投放，视频中不出现人物。

商品信息：
- 商品名称：{product_name}
- 核心卖点：{key_selling_point}
- 对标人群：{target_audience}
- 投放阶段：{stage}

从以下三个维度各随机选一个，组成创意方案：

维度A：镜头运动
- 从上往下扫：镜头从领口缓缓向下扫过腰线至裙摆，展示服装完整轮廓
- 从下往上收：镜头从裙摆缓缓向上收至领口，制造悬念感
- 缓慢推进：镜头从整体缓缓推进至面料细节，突出质感
- 缓慢拉远：镜头从面料细节缓缓拉远至整体，先细节后全貌
- 轻微环绕：镜头以服装为中心轻微环绕，展示立体版型
- 静止微动：镜头固定，布料随自然风力轻微飘动

维度B：光线氛围
- 暖色柔光：柔和暖黄色调，适合日常百搭款
- 自然日光：清透白光，适合清新简约款
- 冷色高级光：高端冷白光，适合高价位质感款
- 黄昏暖橙光：暖橙色调，适合约会场合款

维度C：背景场景
- 极简白色背景：突出产品本身
- 卧室自然光环境：私密真实感
- 咖啡馆暖色环境：生活方式感
- 简洁室内陈设：高级质感
- 城市街景虚化背景：通勤真实感
- 自然户外虚化背景：清新自由感

合理性规则（不合理则重新选）：
- 冷色高级光 + 卧室自然光环境：冲突，重选
- 黄昏暖橙光 + 极简白色背景：冲突，重选
- 静止微动 + 自然户外虚化背景：缺乏空间感，重选

根据卖点微调：
- 含"垂感" → 镜头优先从上往下扫/静止微动
- 含"面料/材质" → 镜头优先缓慢推进
- 含"显瘦/收腰" → 镜头优先从上往下扫
- 含"约会/氛围" → 光线优先黄昏暖橙光，背景优先咖啡馆

严格按以下格式输出，不要有任何额外说明：

🎬 本次创意
[镜头运动] × [光线氛围] × [背景场景]

📋 即梦视频指令
（完整中文自然语言描述，要求：竖版画面，高清画质，5-8秒，无字幕，无人物出现，不超过100字）"""

# ========== Prompt 3B：视频创意（含模特） ==========
PROMPT_VIDEO_B = """你是一名专业的女装短视频创意导演，精通即梦AI图生视频能力边界。

根据以下商品信息，随机生成一条视频创意方案，要求创意新鲜、执行稳定、适合女装千川投放，视频中包含模特。

商品信息：
- 商品名称：{product_name}
- 核心卖点：{key_selling_point}
- 对标人群：{target_audience}
- 投放阶段：{stage}

从以下四个维度各随机选一个：

维度A：镜头运动
- 从上往下扫 / 从下往上收 / 缓慢推进 / 缓慢拉远 / 轻微环绕 / 静止微动

维度B：光线氛围
- 暖色柔光 / 自然日光 / 冷色高级光 / 黄昏暖橙光

维度C：背景场景
- 极简白色背景 / 卧室自然光环境 / 咖啡馆暖色环境 / 简洁室内陈设 / 城市街景虚化背景 / 自然户外虚化背景

维度D：人物微动
- 灵动眼神：眼神由远及近柔和注视镜头，自然眨眼
- 温婉神态：嘴角带笑，微微颔首，呈现松弛自然状态
- 呼吸发丝：自然呼吸起伏，发丝随微风轻盈飘动
- 优雅姿态：身体重心轻微转换，肩膀放松下沉
- 细腻互动：微微歪头，指尖轻触衣角或发丝

不合理组合（重选）：
- 冷色高级光 + 卧室自然光环境
- 黄昏暖橙光 + 极简白色背景
- 静止微动 + 自然户外虚化背景
- 静止微动 + 细腻互动
- 缓慢推进 + 灵动眼神（焦点分散）

严格按以下格式输出：

🎬 本次创意
[镜头运动] × [光线氛围] × [背景场景] × [人物微动]

📋 即梦视频指令
（开头必须写"严格保持原图模特面部特征、体型与服装版型不变"，然后描述镜头+人物动作+光影+场景，竖版画面，高清画质，5-8秒，无字幕，画面稳定无闪烁，总字数不超过100字）"""


# ========== 调用硅基流动LLM ==========
async def call_llm(prompt: str) -> str:
    _check_secrets_for_llm()
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            SILICONFLOW_URL,
            headers={
                "Authorization": f"Bearer {SILICONFLOW_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "deepseek-ai/DeepSeek-V3",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 3000
            }
        )
        if resp.status_code != 200:
            raise Exception(f"LLM请求失败: http={resp.status_code}, body={resp.text[:500]}")
        data = resp.json()
        if not data.get("choices"):
            raise Exception(f"LLM返回异常: {data}")
        return data["choices"][0]["message"]["content"]


# ========== 即梦API签名（火山引擎HMAC-SHA256） ==========
def jimeng_sign(ak: str, sk: str, method: str, uri: str, body: str, action: str = "", version: str = "2022-08-31") -> dict:
    # 火山引擎 SK 使用控制台给出的原始字符串参与签名，不要对 SK 做 base64 解码
    sk_real = sk
    now = time.gmtime()
    date_str = time.strftime("%Y%m%d", now)
    datetime_str = time.strftime("%Y%m%dT%H%M%SZ", now)

    service = "cv"
    region = "cn-north-1"
    host = "visual.volcengineapi.com"

    query = f"Action={action}&Version={version}" if action else ""
    canonical_uri = uri
    canonical_query = query
    canonical_headers = f"content-type:application/json\nhost:{host}\nx-content-sha256:{hashlib.sha256(body.encode()).hexdigest()}\nx-date:{datetime_str}\n"
    signed_headers = "content-type;host;x-content-sha256;x-date"
    payload_hash = hashlib.sha256(body.encode()).hexdigest()

    canonical_request = "\n".join([method, canonical_uri, canonical_query, canonical_headers, signed_headers, payload_hash])
    credential_scope = f"{date_str}/{region}/{service}/request"
    string_to_sign = "\n".join(["HMAC-SHA256", datetime_str, credential_scope, hashlib.sha256(canonical_request.encode()).hexdigest()])

    def hmac256(key, msg):
        if isinstance(key, str):
            key = key.encode()
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    signing_key = hmac256(hmac256(hmac256(hmac256(sk_real, date_str), region), service), "request")
    signature = hmac.new(signing_key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    auth = f"HMAC-SHA256 Credential={ak}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}"

    return {
        "Authorization": auth,
        "X-Date": datetime_str,
        "X-Content-Sha256": payload_hash,
        "Content-Type": "application/json",
        "Host": host
    }


# ========== 即梦：提交图生视频任务 ==========
async def jimeng_submit_video(image_bytes: bytes, prompt_text: str) -> str:
    _check_secrets_for_jimeng()
    import base64 as b64
    img_b64 = b64.b64encode(image_bytes).decode()
    # 与「即梦AI-视频生成3.0 Pro」图生首帧文档一致：req_key、图、prompt、seed、frames
    payload = {
        "req_key": JIMENG_REQ_KEY,
        "prompt": prompt_text,
        "binary_data_base64": [img_b64],
        "frames": 121,
        "seed": -1,
    }
    body = json.dumps(payload)
    headers = jimeng_sign(JIMENG_AK, JIMENG_SK, "POST", "/", body, "CVSync2AsyncSubmitTask")

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{JIMENG_BASE}?Action=CVSync2AsyncSubmitTask&Version=2022-08-31",
            headers=headers,
            content=body
        )
        if resp.status_code != 200:
            raise Exception(f"提交任务HTTP失败: {resp.status_code}, body={resp.text[:500]}")
        data = resp.json()
        print(f"即梦提交响应: {data}")
        if data.get("code") != 10000:
            raise Exception(
                f"提交任务失败: code={data.get('code')}, message={data.get('message', '未知错误')}, "
                f"request_id={data.get('request_id', '')}"
            )
        task_id = data.get("data", {}).get("task_id", "")
        if not task_id:
            raise Exception(f"未获取到task_id: {data}")
        return task_id


# ========== 即梦：查询任务结果 ==========
async def jimeng_query_video(task_id: str) -> str:
    payload = {
        "req_key": JIMENG_REQ_KEY,
        "task_id": task_id
    }
    body = json.dumps(payload)
    headers = jimeng_sign(JIMENG_AK, JIMENG_SK, "POST", "/", body, "CVSync2AsyncGetResult")

    for attempt in range(36):  # 最多等3分钟
        await asyncio.sleep(5)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{JIMENG_BASE}?Action=CVSync2AsyncGetResult&Version=2022-08-31",
                headers=headers,
                content=body
            )
            if resp.status_code != 200:
                raise Exception(f"查询任务HTTP失败: {resp.status_code}, body={resp.text[:500]}")
            data = resp.json()
            print(f"即梦查询第{attempt+1}次: code={data.get('code')}, status={data.get('data', {}).get('status')}")
            if data.get("code") != 10000:
                raise Exception(
                    f"查询失败: code={data.get('code')}, message={data.get('message', '未知错误')}, "
                    f"request_id={data.get('request_id', '')}"
                )
            d = data.get("data", {})
            status = d.get("status", "")
            if status == "done":
                video_url = d.get("video_url", "")
                if video_url:
                    return video_url
                raise Exception("任务完成但未返回视频URL")
            elif status in ("not_found", "expired"):
                raise Exception(f"任务状态异常: {status}")
            # in_queue / generating 继续等待
    raise Exception("视频生成超时，请稍后重试")


import asyncio

# ========== API路由 ==========

@app.post("/api/copy")
async def generate_copy(
    product_name: str = Form(...),
    key_selling_point: str = Form(...),
    price: str = Form(...),
    stage: str = Form(...),
    target_audience: str = Form(...),
    body_range: str = Form(""),
    material: str = Form(""),
    color_note: str = Form("")
):
    try:
        prompt = PROMPT_COPY.format(
            product_name=product_name,
            key_selling_point=key_selling_point,
            price=price,
            stage=stage,
            target_audience=target_audience,
            body_range=body_range or "未填写，请根据商品推断",
            material=material or "未填写，请从卖点推断",
            color_note=color_note or "未填写，不写任何色差描述"
        )
        result = await call_llm(prompt)
        return {"success": True, "text": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/api/check")
async def check_violation(
    input_copy: str = Form(...),
    stage: str = Form(""),
    target_audience: str = Form("")
):
    try:
        prompt = PROMPT_CHECK.format(
            input_copy=input_copy,
            stage=stage or "未填写",
            target_audience=target_audience or "未填写"
        )
        result = await call_llm(prompt)
        return {"success": True, "text": result}
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


@app.post("/api/video")
async def generate_video(
    product_name: str = Form(...),
    key_selling_point: str = Form(...),
    stage: str = Form(...),
    target_audience: str = Form(...),
    video_type: str = Form(...),
    product_image: Optional[UploadFile] = File(None),
    model_image: Optional[UploadFile] = File(None),
    avatar_image: Optional[UploadFile] = File(None)
):
    try:
        # 1. 根据视频类型选择Prompt和图片
        if video_type == "无人物":
            prompt_template = PROMPT_VIDEO_A
            image_file = product_image
        elif video_type == "模特":
            prompt_template = PROMPT_VIDEO_B
            image_file = model_image
        elif video_type == "数字人":
            prompt_template = PROMPT_VIDEO_B
            # 即梦图生视频仅支持单图，优先使用数字人图
            image_file = avatar_image or product_image
        else:
            return JSONResponse(status_code=400, content={"success": False, "error": f"不支持的视频类型: {video_type}"})

        if not image_file:
            return JSONResponse(status_code=400, content={"success": False, "error": "缺少图片"})

        # 2. 生成视频创意指令
        creative_prompt = prompt_template.format(
            product_name=product_name,
            key_selling_point=key_selling_point,
            target_audience=target_audience,
            stage=stage
        )
        creative_result = await call_llm(creative_prompt)

        # 提取即梦指令
        video_instruction = ""
        creative_text = ""
        lines = creative_result.split("\n")
        in_instruction = False
        for line in lines:
            if "🎬 本次创意" in line:
                continue
            if "📋 即梦视频指令" in line:
                in_instruction = True
                continue
            if in_instruction and line.strip():
                video_instruction += line + " "
            elif not in_instruction and line.strip() and "×" in line:
                creative_text = line.strip()

        video_instruction = video_instruction.strip()
        if not video_instruction:
            video_instruction = creative_result

        # 3. 读取图片
        image_bytes = await image_file.read()

        # 4. 提交视频生成任务（直接传base64，无需单独上传）
        task_id = await jimeng_submit_video(image_bytes, video_instruction)

        # 6. 轮询结果
        video_url = await jimeng_query_video(task_id)

        return {
            "success": True,
            "creative_text": creative_text,
            "video_instruction": video_instruction,
            "video_url": video_url
        }

    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})


# 托管前端静态文件
if os.path.exists("static"):
    app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
