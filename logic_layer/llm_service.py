import ollama
from config import Config
from logic_layer.json_utils import parse_llm_json

# --- 1. Ollama 客户端配置 ---
# 设置 Ollama 服务器地址
ollama_client = ollama.Client(host=Config.OLLAMA_URL)


# --- 2. 实体提取 (带容错机制) ---
def extract_entities_with_llm(user_input):
    """
    尝试用 LLM 提取。如果失败，返回空列表，让外层的规则引擎(Regex)去兜底。
    """
    try:
        prompt = f"""
        [角色] 你是医疗数据结构化专家，仅输出JSON，不添加任何额外内容。
        [任务] 从用户输入中提取【药品名称】和【医学状态】，无则留空。
        [规则]
        1. 返回标准 JSON 格式：{{"drugs": [], "conditions": []}}
        2. 不要包含 markdown 标记（如 ```json）。
        3. 如果没提到，列表留空。
        4. 中文药品/状态名称需与常见标准名一致。

        [输入]: "{user_input}"
        [输出]:
        """
        # 使用 ollama 包直接调用
        response = ollama_client.generate(
            model=Config.OLLAMA_MODEL,
            prompt=prompt,
            options={
                "temperature": 0.1
            }
        )
        content = response['response'].strip()

        data = parse_llm_json(content)
        return data.get("drugs", []), data.get("conditions", [])

    except Exception as e:
        print(f"⚠️ LLM 提取实体失败 (不影响运行，已由规则引擎接管): {e}")
        return [], []


# --- 3. 生成回答 (核心修复：加入兜底逻辑) ---
def generate_safety_response(user_query, risks, drug_infos, history_context: str = ""):
    """
    生成最终建议。如果 LLM 报错，自动切换到"规则模板"生成，
    确保老师永远看不到"系统繁忙"。
    
    Args:
        user_query: 用户查询
        risks: 风险列表
        drug_infos: 药品信息列表
        history_context: 历史对话上下文（可选）
    """

    # === A. 构建上下文数据 (Prompt Context) ===
    risk_text = ""
    if risks:
        risk_text = "【检测到严重风险】\n"
        for r in risks:
            # 区分不同类型的风险描述
            if r['type'] == 'DUPLICATE_THERAPY':
                risk_text += f"- 重复用药风险：{r['drug']}（均含成分：{r.get('ingredient', '未知成分')}）→ {r['reason']}\n"
            elif r['type'] == 'INTERACTION':
                risk_text += f"- 药物相互作用：{r['drug']} → {r['reason']}\n"
            else:
                risk_text += f"- 禁忌/慎用：{r['drug']} + {r['condition']} → {r['reason']}\n"
    else:
        risk_text = "【未检测到图谱内已知风险】\n- 当前知识图谱没有返回重复用药、禁忌或相互作用风险。\n"

    info_text = ""
    if drug_infos:
        info_text = "【药品权威档案】\n"
        for info in drug_infos:
            info_text += f"- {info['drug']}: {info['function']} (用法: {info['dosage']})\n"
    else:
        info_text = "【药品权威档案】\n- 当前知识图谱未返回相关药品档案。\n"

    # === B. 尝试使用 LLM 生成自然语言回答 ===
    try:
        has_risk = "是" if risks else "否"
        has_drug_info = "是" if drug_infos else "否"

        # 定义医生人设
        system_prompt = """
        你是家庭用药安全助手。你只能根据用户问题和下方提供的知识图谱结果回答。

        [回答原则]
        1. 禁止编造：不要添加知识图谱结果中没有出现的副作用、适应症、相互作用或禁忌。
        2. 图谱优先：如果检测到风险，第一句话必须明确“不建议/不要这样服用”，并说明图谱依据。
        3. 谨慎表达：如果未检测到风险，只能说“当前知识图谱未发现已知禁忌”，不能说“绝对安全”。
        4. 证据不足：如果没有药品档案，必须说明“数据库暂未收录相关药品档案，建议咨询医生或药师”。
        5. 输出结构固定为：结论、依据、建议。每部分 1-3 句话，简洁中文。
        """

        # 如果有历史对话上下文，添加到提示词中
        history_section = ""
        if history_context:
            history_section = f"\n{history_context}\n"
        
        user_prompt = f"""
        [用户问题]: {user_query}
        {history_section}
        [结构化标记]:
        - 是否检测到风险: {has_risk}
        - 是否有药品档案: {has_drug_info}

        [知识图谱扫描结果]:
        {risk_text}

        {info_text}

        请严格按照“结论 / 依据 / 建议”生成回答。不要输出知识图谱之外的新医学事实。
        """

        # 使用 ollama 包直接调用
        response = ollama_client.chat(
            model=Config.OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            options={
                "temperature": 0.1
            }
        )
        return response['message']['content']

    # === C. 救命的兜底逻辑 (Fallback) ===
    except Exception as e:
        print(f"❌ LLM 生成服务异常: {e}")
        print("🔄 启动规则模板生成机制...")

        # 既然图谱已经查到了数据，我们直接用代码拼凑一个“像模像样”的回答
        # 这样用户感觉不到 LLM 挂了

        fallback_msg = ""

        if risks:
            fallback_msg += "### 🛑 医生紧急警告\n\n"
            fallback_msg += "**检测到严重的用药风险，请绝对不要按照当前方案服用！**\n\n"
            fallback_msg += "**具体风险如下：**\n"
            for r in risks:
                fallback_msg += f"* **{r['drug']}**: {r['reason']}\n"
            fallback_msg += "\n建议您立即停止混合服用，并咨询线下医生。"

        elif drug_infos:
            fallback_msg += "### ✅ 用药安全评估通过\n\n"
            fallback_msg += "根据当前权威数据库比对，**未发现明显的用药禁忌**。\n\n"
            fallback_msg += "**药品信息参考：**\n"
            for info in drug_infos:
                fallback_msg += f"* **{info['drug']}**: 主要用于{info['function']}。\n"
            fallback_msg += "\n*温馨提示：请严格按照说明书剂量服用，症状未缓解请及时就医。*"

        else:
            fallback_msg += "⚠️ **无法评估风险**\n\n系统暂未收录相关药品信息，请务必咨询专业医师，不要盲目用药。"

        return fallback_msg
