"""
Application service boundary for the medication assistant.

Phase 2 moves the Streamlit request pipeline here incrementally so UI code can
eventually focus on rendering while this module owns backend orchestration.
"""

from logic_layer.entity_utils import exact_entity_extraction
from logic_layer.kg_service import MedicalKG
from logic_layer.llm_service import generate_safety_response, extract_entities_with_llm
from logic_layer.router_service import decide_tools

DEFAULT_SESSION_ID = "shared"


def answer_medication_question(prompt, session_id=DEFAULT_SESSION_ID, vector_store=None, kg=None):
    """
    Run the backend medication-safety pipeline for one user prompt.

    The returned dictionary preserves the current app's intermediate values so
    Streamlit can be migrated to this service without losing UI detail.
    """
    owns_kg = kg is None
    kg = kg or MedicalKG()

    try:
        route = decide_tools(prompt)

        history_context = ""
        if route in ("search_history", "both") and vector_store and vector_store.redis_client:
            history_context = vector_store.get_conversation_context(prompt, session_id, top_k=3)

        exact_drugs = []
        exact_conditions = []
        llm_drugs = []
        llm_conditions = []
        final_drugs = []
        final_conditions = []
        risks = []
        drug_infos = []

        if route in ("query_kg", "both"):
            exact_drugs, exact_conditions = exact_entity_extraction(prompt)
            llm_drugs, llm_conditions = extract_entities_with_llm(prompt)

            final_drugs = list(set(exact_drugs + llm_drugs))
            final_conditions = list(set(exact_conditions + llm_conditions))

            if final_drugs or final_conditions:
                risks = kg.check_safety(final_drugs, final_conditions)
                drug_infos = kg.get_drug_info(final_drugs)

        response_text = generate_safety_response(prompt, risks, drug_infos, history_context)

        conversation_saved = False
        save_error = None
        if vector_store and vector_store.redis_client:
            try:
                vector_store.store_conversation(prompt, response_text, session_id)
                conversation_saved = True
            except Exception as exc:
                save_error = str(exc)

        return {
            "route": route,
            "history_context": history_context,
            "exact_drugs": exact_drugs,
            "exact_conditions": exact_conditions,
            "llm_drugs": llm_drugs,
            "llm_conditions": llm_conditions,
            "final_drugs": final_drugs,
            "final_conditions": final_conditions,
            "risks": risks,
            "drug_infos": drug_infos,
            "response_text": response_text,
            "conversation_saved": conversation_saved,
            "save_error": save_error,
        }
    finally:
        if owns_kg:
            kg.close()
