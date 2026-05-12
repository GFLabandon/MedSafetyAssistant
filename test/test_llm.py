# logic_layer/llm_service.py
import requests
from config import Config

def consult_llm(user_question, kg_context):
    if not kg_context or not kg_context.get("found"):
        context_str = "知识库中暂无该药物的详细禁忌记录。"
    else:
        c_list = ", ".join(
            [f"{item['condition']}(原因:{item['reason']})" for item in kg_context['contraindications']]
        )
        i_list = ", ".join(
            [f"{item['drug']}(风险:{item['risk']})" for item in kg_context['interactions']]
        )

        context_str = f"""
【已核实药品数据】：
- 药品名：{kg_context['name']}
- 类型：{kg_context['type']}
- 明确禁忌症：{c_list if c_list else '无明确记录'}
- 药物相互作用：{i_list if i_list else '无明确记录'}
"""

    system_prompt = f"""
你是一位严谨的家庭全科医生。请根据【已核实药品数据】回答用户问题。
原则：
1. 如果数据中有禁忌症，必须明确警告用户“不可服用”。
2. 如果数据中没有提及，请说明“数据库未收录，建议咨询线下医生”，不要编造。
3. 输出风格简洁、亲切、专业。

{context_str}
"""

    payload = {
        "model": Config.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_question}
        ],
        "stream": False
    }

    try:
        resp = requests.post(
            f"{Config.OLLAMA_URL}/api/chat",
            json=payload,
            timeout=120
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except Exception as e:
        return f"❌ Ollama API 调用失败：{e}"

