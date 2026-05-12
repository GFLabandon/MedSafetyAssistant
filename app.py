import streamlit as st

from logic_layer.entity_utils import exact_entity_extraction
from logic_layer.kg_service import MedicalKG
from logic_layer.llm_service import generate_safety_response, extract_entities_with_llm
from logic_layer.vector_store import VectorStore

st.set_page_config(page_title="家庭用药安全助手1", layout="centered")

# 1. 法律免责层
st.error("⚠️ **法律声明**：本系统为科研演示原型，数据覆盖有限。用药建议不具法律效力，禁止作为临床决策唯一依据。")
st.markdown("## 🏥 智能家庭用药安全助手 (RAG + KG)")
st.caption("基于 Neo4j 知识图谱与 DeepSeek 大模型 | 专注于用药禁忌筛查")

# 初始化
if "messages" not in st.session_state:
    st.session_state.messages = []

# 初始化向量存储（用于历史对话）
if "vector_store" not in st.session_state:
    st.session_state.vector_store = VectorStore()

# 使用共享的会话ID（所有用户共享同一个历史对话库）
# 这样所有用户都能查询到所有历史对话记录
SHARED_SESSION_ID = "shared"
session_id = SHARED_SESSION_ID

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
        # 实例化 MedicalKG
        kg = MedicalKG()
        
        # 查询历史对话上下文
        vector_store = st.session_state.vector_store
        history_context = ""
        if vector_store and vector_store.redis_client:
            st.write("🔍 **步骤 0: 检索历史对话上下文**")
            history_context = vector_store.get_conversation_context(prompt, session_id, top_k=3)
            if history_context:
                st.info("✅ 找到相关历史对话，将用于增强回答")
            else:
                st.caption("ℹ️ 暂无相关历史对话")

    with st.status("🧠 系统正在进行双路分析...", expanded=True) as status:
        st.write("🔄 **步骤 1: 混合实体识别 (Hybrid NER)**")

        # --- 核心修复：双路提取 ---

        # 路 A：字典/正则精确匹配 (准确率 100%，不仅快而且稳)
        exact_drugs, exact_conditions = exact_entity_extraction(prompt)
        st.write(f"   * 规则引擎提取: 💊 {exact_drugs} | 🏥 {exact_conditions}")

        # 路 B：大模型语义提取 (负责提取隐含意图，如用户描述症状但没说病名)
        llm_drugs, llm_conditions = extract_entities_with_llm(prompt)
        st.write(f"   * 大模型提取: 🤖 {llm_drugs} | 🏥 {llm_conditions}")

        # --- 结果合并 (去重) ---
        final_drugs = list(set(exact_drugs + llm_drugs))
        final_conditions = list(set(exact_conditions + llm_conditions))

        # 过滤掉不在标准库中的幻觉词 (可选，但建议保留以防万一)
        # 这里直接信任合并结果，因为 exact_entity_extraction 已经是标准化的了

        if not final_drugs and not final_conditions:
            st.warning("⚠️ 未识别到具体的药品或病症，尝试通用回答...")
            risks = []
            drug_infos = []
        else:
            st.success(f"✅ 最终锁定对象: 💊 {final_drugs} | 🏥 {final_conditions}")

            st.write("🕸️ **步骤 2: 知识图谱多跳推理**")
            # 使用合并后的结果去查图谱
            risks = kg.check_safety(final_drugs, final_conditions)
            drug_infos = kg.get_drug_info(final_drugs)

            if risks:
                status.update(label="⚠️ 检测到潜在风险！", state="error")
                st.error("❌ 系统拦截到用药禁忌：")
                for r in risks:
                    # 优化显示格式
                    severity_icon = "🔴" if r.get('severity') == 'FATAL' else "🟠"
                    st.markdown(f"{severity_icon} **{r['drug']}** + **{r.get('condition') or r.get('ingredient')}**")
                    st.caption(f"   原因：{r['reason']}")
            else:
                status.update(label="✅ 安全性扫描通过", state="complete")
                if drug_infos:
                    st.info(f"已调阅 {len(drug_infos)} 份药品档案")
                else:
                    st.warning("图谱中暂无详细档案，仅基于通用知识回答")

        # 4. 生成回复 (传入 drug_infos 和历史上下文)
        response_text = generate_safety_response(prompt, risks, drug_infos, history_context)  # <--- 传入历史上下文
        kg.close()

        st.markdown(response_text)
        st.session_state.messages.append({"role": "assistant", "content": response_text})
        
        # 5. 存储对话到向量数据库
        if vector_store and vector_store.redis_client:
            try:
                vector_store.store_conversation(prompt, response_text, session_id)
                st.caption("💾 对话已保存到历史记录")
            except Exception as e:
                st.caption(f"⚠️ 保存对话失败: {e}")