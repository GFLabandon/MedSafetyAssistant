import streamlit as st

from logic_layer.assistant_service import answer_medication_question, create_session_id
from logic_layer.vector_store import VectorStore

st.set_page_config(page_title="家庭用药安全助手1", layout="centered")

# 1. 法律免责层
st.error("⚠️ **法律声明**：本系统为科研演示原型，数据覆盖有限。用药建议不具法律效力，禁止作为临床决策唯一依据。")
st.markdown("## 🏥 智能家庭用药安全助手 (RAG + KG)")
st.caption("基于 Neo4j 知识图谱与 Ollama 大模型 | 专注于用药禁忌筛查")

# 初始化
if "messages" not in st.session_state:
    st.session_state.messages = []

# 初始化向量存储（用于历史对话）
if "vector_store" not in st.session_state:
    st.session_state.vector_store = VectorStore()

# 每个 Streamlit 浏览器会话使用独立命名空间，避免历史记录跨用户串线。
if "session_id" not in st.session_state:
    st.session_state.session_id = create_session_id()
session_id = st.session_state.session_id

# 聊天记录
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 输入框
if prompt := st.chat_input("请输入您的用药问题..."):
    # 1. 立即初始化/清空状态
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        vector_store = st.session_state.vector_store

        with st.status("🧠 系统正在进行双路分析...", expanded=True) as status:
            result = answer_medication_question(prompt, session_id=session_id, vector_store=vector_store)
            route = result["route"]
            risks = result["risks"]
            drug_infos = result["drug_infos"]

            st.caption(f"🧭 路由决策: `{route}`")

            if route in ("search_history", "both") and vector_store and vector_store.redis_client:
                st.write("🔍 **步骤 0: 检索历史对话上下文**")
                if result["history_context"]:
                    st.info("✅ 找到相关历史对话，将用于增强回答")
                else:
                    st.caption("ℹ️ 暂无相关历史对话")
            elif route == "query_kg":
                st.caption("ℹ️ 本轮路由优先知识图谱查询，跳过历史检索")

            if route in ("query_kg", "both"):
                st.write("🔄 **步骤 1: 混合实体识别 (Hybrid NER)**")
                st.write(
                    f"   * 规则引擎提取: 💊 {result['exact_drugs']} | 🏥 {result['exact_conditions']}"
                )
                st.write(
                    f"   * 大模型提取: 🤖 {result['llm_drugs']} | 🏥 {result['llm_conditions']}"
                )

                if not result["final_drugs"] and not result["final_conditions"]:
                    st.warning("⚠️ 未识别到具体的药品或病症，尝试通用回答...")
                else:
                    st.success(
                        f"✅ 最终锁定对象: 💊 {result['final_drugs']} | 🏥 {result['final_conditions']}"
                    )

                    st.write("🕸️ **步骤 2: 知识图谱多跳推理**")
                    if risks:
                        status.update(label="⚠️ 检测到潜在风险！", state="error")
                        st.error("❌ 系统拦截到用药禁忌：")
                        for r in risks:
                            severity_icon = "🔴" if r.get('severity') == 'FATAL' else "🟠"
                            st.markdown(
                                f"{severity_icon} **{r['drug']}** + **{r.get('condition') or r.get('ingredient')}**"
                            )
                            st.caption(f"   原因：{r['reason']}")
                    else:
                        status.update(label="✅ 安全性扫描通过", state="complete")
                        if drug_infos:
                            st.info(f"已调阅 {len(drug_infos)} 份药品档案")
                        else:
                            st.warning("图谱中暂无详细档案，仅基于通用知识回答")
            else:
                st.caption("ℹ️ 本轮路由优先历史上下文，不执行图谱检索")

        response_text = result["response_text"]

        st.markdown(response_text)
        st.session_state.messages.append({"role": "assistant", "content": response_text})

        if result["conversation_saved"]:
            st.caption("💾 对话已保存到历史记录")
        elif result["save_error"]:
            st.caption(f"⚠️ 保存对话失败: {result['save_error']}")
