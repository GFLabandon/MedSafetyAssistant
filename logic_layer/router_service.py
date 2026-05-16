import json
import ollama
from config import Config


ollama_client = ollama.Client(host=Config.OLLAMA_URL)


def decide_tools(user_query: str) -> str:
    """
    最小 Agent 路由：由 LLM 决定本轮优先工具。

    Returns:
        query_kg | search_history | both
    """
    prompt = f"""
你是医疗问答系统的工具路由器。请根据用户问题选择最合适的工具路径。

可选值：
- query_kg：当问题需要药品禁忌/相互作用/成分与疾病关系等事实判断
- search_history：当问题明显是在追问、改写、引用前文上下文
- both：两者都需要或无法明确判断时

只输出 JSON：{{"route": "query_kg|search_history|both"}}

用户问题："{user_query}"
"""

    try:
        response = ollama_client.generate(
            model=Config.OLLAMA_MODEL,
            prompt=prompt,
            options={"temperature": 0.0},
        )
        content = response.get("response", "").strip()
        content = content.replace("```json", "").replace("```", "").strip()
        route = json.loads(content).get("route", "both")
        if route in {"query_kg", "search_history", "both"}:
            return route
        return "both"
    except Exception:
        return "both"
