"""
Application service boundary for the medication assistant.

The Streamlit UI and FastAPI BFF both call this module. UI code should render
results; this module owns backend orchestration.
"""

import logging

from logic_layer.entity_utils import exact_entity_extraction
from logic_layer.kg_service import MedicalKG
from logic_layer.llm_service import generate_safety_response, extract_entities_with_llm
from logic_layer.router_service import decide_tools
from logic_layer.session import normalize_session_id


logger = logging.getLogger(__name__)


def _effective_session_id(session_id):
    return normalize_session_id(session_id)


def prepare_medication_context(prompt, session_id=None, vector_store=None, kg=None):
    """
    Run retrieval, routing, entity extraction, and KG checks without generating
    the final answer. This lets streaming APIs emit metadata before answer text.
    """
    session_id = _effective_session_id(session_id)
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

        final_drugs = list(dict.fromkeys(exact_drugs + llm_drugs))
        final_conditions = list(dict.fromkeys(exact_conditions + llm_conditions))

        if final_drugs or final_conditions:
            risks = kg.check_safety(final_drugs, final_conditions)
            drug_infos = kg.get_drug_info(final_drugs)

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
    }


def save_conversation_result(vector_store, prompt, response_text, session_id=None):
    session_id = _effective_session_id(session_id)
    conversation_saved = False
    save_error = None
    if vector_store and vector_store.redis_client:
        try:
            conversation_saved = bool(
                vector_store.store_conversation(
                    prompt,
                    response_text,
                    session_id,
                )
            )
            if not conversation_saved:
                save_error = "conversation_store_rejected"
        except Exception as exc:
            logger.warning(
                "conversation store unavailable (%s)",
                type(exc).__name__,
            )
            save_error = "conversation_store_unavailable"

    return {
        "conversation_saved": conversation_saved,
        "save_error": save_error,
    }


def answer_medication_question(prompt, session_id=None, vector_store=None, kg=None):
    """
    Run the backend medication-safety pipeline for one user prompt.

    The returned dictionary preserves the app's intermediate values so UIs can
    render route decisions, entities, risks, evidence, and persistence status.
    """
    session_id = _effective_session_id(session_id)
    owns_kg = kg is None
    kg = kg or MedicalKG()

    try:
        context = prepare_medication_context(
            prompt,
            session_id=session_id,
            vector_store=vector_store,
            kg=kg,
        )
        response_text = generate_safety_response(
            prompt,
            context["risks"],
            context["drug_infos"],
            context["history_context"],
        )
        save_result = save_conversation_result(
            vector_store,
            prompt,
            response_text,
            session_id,
        )
        return {
            **context,
            "response_text": response_text,
            **save_result,
        }
    finally:
        if owns_kg:
            kg.close()
