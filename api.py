# api.py - FastAPI wrapper layer
from contextlib import asynccontextmanager
import asyncio
import json
import logging
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from config import Config
from logic_layer.assistant_service import (
    answer_medication_question,
    prepare_medication_context,
    save_conversation_result,
)
from logic_layer.health_check import (
    get_liveness_diagnostics,
    get_readiness_diagnostics,
)
from logic_layer.kg_service import MedicalKG
from logic_layer.llm_service import stream_safety_response
from logic_layer.session import create_session_id, normalize_session_id
from logic_layer.vector_store import VectorStore
from medsafety.catalog import KnowledgeCatalog
from medsafety.entity_resolution import V1EntityResolver
from medsafety.explanation import EvidenceGroundedExplainer
from medsafety.ollama_planner import OllamaExplanationPlanner
from medsafety.observability import normalize_request_id, structured_event
from medsafety.query_service import SafetyQueryService
from medsafety.safety_engine import SafetyEngine


V1_DATA_DIRECTORY = Path(__file__).resolve().parent / "data/v1"
logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    session_id: str = Field(default_factory=create_session_id)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value):
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()

    @field_validator("session_id")
    @classmethod
    def session_id_must_not_be_blank(cls, value):
        return normalize_session_id(value)


class SafetyCheckRequest(BaseModel):
    medications: list[str] = Field(..., min_length=1)
    contexts: list[str] = Field(default_factory=list)

    @field_validator("medications")
    @classmethod
    def medications_must_not_be_blank(cls, values):
        normalized = [value.strip() for value in values if value.strip()]
        if not normalized:
            raise ValueError("at least one non-blank medication is required")
        return normalized

    @field_validator("contexts")
    @classmethod
    def normalize_contexts(cls, values):
        return [value.strip() for value in values if value.strip()]


class SafetyExplainRequest(SafetyCheckRequest):
    use_llm_plan: bool = True


class NaturalLanguageSafetyRequest(BaseModel):
    question: str = Field(..., min_length=1)
    use_llm_plan: bool = True

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value):
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()


def build_v1_catalog():
    return KnowledgeCatalog.from_directory(V1_DATA_DIRECTORY)


def build_safety_engine(catalog=None):
    return SafetyEngine(catalog or build_v1_catalog())


def build_entity_resolver(catalog=None):
    return V1EntityResolver(catalog or build_v1_catalog())


def build_safety_explainer():
    planner = OllamaExplanationPlanner(
        host=Config.OLLAMA_URL,
        model=Config.OLLAMA_MODEL,
        timeout_seconds=Config.OLLAMA_EXPLANATION_TIMEOUT_SECONDS,
    )
    return EvidenceGroundedExplainer(planner)


@asynccontextmanager
async def lifespan(app: FastAPI):
    catalog = build_v1_catalog()
    app.state.safety_engine = build_safety_engine(catalog)
    app.state.entity_resolver = build_entity_resolver(catalog)
    app.state.safety_explainer = build_safety_explainer()
    app.state.vector_store = VectorStore()
    try:
        yield
    finally:
        vector_store = getattr(app.state, "vector_store", None)
        if vector_store is not None:
            vector_store.close()


app = FastAPI(title="MedSafetyAssistant API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_observability(request: Request, call_next):
    request_id = normalize_request_id(request.headers.get("X-Request-ID"))
    request.state.request_id = request_id
    started = perf_counter()
    response = await call_next(request)
    duration_ms = round((perf_counter() - started) * 1000, 3)
    response.headers["X-Request-ID"] = request_id
    logger.info(
        structured_event(
            "http_request_completed",
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
    )
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    request_id = getattr(getattr(request, "state", None), "request_id", None)
    logger.error(
        structured_event(
            "http_request_failed",
            request_id=request_id or "unavailable",
            error_type=type(exc).__name__,
        ),
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "detail": "An unexpected error occurred.",
            "request_id": request_id,
        },
    )


def get_vector_store(request: Request | None):
    if request is None:
        return None
    return getattr(request.app.state, "vector_store", None)


def get_safety_engine(request: Request | None):
    if request is None:
        return build_safety_engine()
    return getattr(request.app.state, "safety_engine", None) or build_safety_engine()


def get_safety_explainer(request: Request | None):
    if request is None:
        return build_safety_explainer()
    return getattr(request.app.state, "safety_explainer", None) or build_safety_explainer()


def get_entity_resolver(request: Request | None):
    if request is None:
        return build_entity_resolver()
    return getattr(request.app.state, "entity_resolver", None) or build_entity_resolver()


def get_request_id(request: Request | None):
    if request is None:
        return normalize_request_id(None)
    return normalize_request_id(getattr(request.state, "request_id", None))


def sse_event(payload):
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def stream_query_events(payload, vector_store=None):
    kg = MedicalKG()
    try:
        context = prepare_medication_context(
            payload.question,
            session_id=payload.session_id,
            vector_store=vector_store,
            kg=kg,
        )
        yield sse_event(
            {
                "type": "meta",
                "route": context["route"],
                "history_context": context["history_context"],
                "exact_drugs": context["exact_drugs"],
                "exact_conditions": context["exact_conditions"],
                "llm_drugs": context["llm_drugs"],
                "llm_conditions": context["llm_conditions"],
                "final_drugs": context["final_drugs"],
                "final_conditions": context["final_conditions"],
                "risks": context["risks"],
                "drug_infos": context["drug_infos"],
            }
        )

        answer_parts = []
        for token in stream_safety_response(
            payload.question,
            context["risks"],
            context["drug_infos"],
            context["history_context"],
        ):
            answer_parts.append(token)
            yield sse_event({"type": "token", "content": token})

        save_result = save_conversation_result(
            vector_store,
            payload.question,
            "".join(answer_parts),
            payload.session_id,
        )
        yield sse_event({"type": "done", **save_result})
    except Exception as exc:
        logger.error(
            "streaming query failed",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        yield sse_event({"type": "error", "error": "query_failed"})
    finally:
        kg.close()


@app.post("/api/query")
async def query_medication(payload: QueryRequest, request: Request = None):
    vector_store = get_vector_store(request)
    return answer_medication_question(
        payload.question,
        session_id=payload.session_id,
        vector_store=vector_store,
    )


@app.post("/api/query/stream")
async def stream_query_medication(payload: QueryRequest, request: Request = None):
    vector_store = get_vector_store(request)
    return StreamingResponse(
        stream_query_events(payload, vector_store=vector_store),
        media_type="text/event-stream",
    )


@app.delete("/api/sessions/{session_id}")
async def clear_conversation_session(session_id: str, request: Request = None):
    try:
        normalized_session_id = normalize_session_id(
            session_id,
            generate_if_blank=False,
        )
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={
                "error": "invalid_session_id",
                "detail": "session_id has an invalid format.",
            },
        )

    vector_store = get_vector_store(request)
    if vector_store is None or not vector_store.available:
        return JSONResponse(
            status_code=503,
            content={
                "error": "session_store_unavailable",
                "detail": "Conversation history is currently unavailable.",
            },
        )

    try:
        deleted_keys = vector_store.clear_session(normalized_session_id)
    except Exception as exc:
        logger.error(
            "session clear failed",
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return JSONResponse(
            status_code=503,
            content={
                "error": "session_store_unavailable",
                "detail": "Conversation history is currently unavailable.",
            },
        )
    return {
        "session_id": normalized_session_id,
        "cleared": True,
        "deleted_keys": deleted_keys,
    }


@app.get("/api/live")
async def live():
    return get_liveness_diagnostics()


@app.get("/api/ready")
async def ready():
    return await asyncio.to_thread(get_readiness_diagnostics)


@app.get("/api/health")
async def health():
    """Backward-compatible alias for the real readiness response."""

    return await ready()


@app.post("/api/v1/safety/check")
async def check_v1_safety(payload: SafetyCheckRequest, request: Request = None):
    result = get_safety_engine(request).assess(payload.medications, contexts=payload.contexts)
    return result.model_dump(mode="json")


@app.post("/api/v1/safety/explain")
async def explain_v1_safety(payload: SafetyExplainRequest, request: Request = None):
    packet = get_safety_engine(request).assess(payload.medications, contexts=payload.contexts)
    explanation = get_safety_explainer(request).explain(
        packet,
        use_llm_plan=payload.use_llm_plan,
    )
    return explanation.model_dump(mode="json")


@app.post("/api/v1/query")
async def query_v1_safety(
    payload: NaturalLanguageSafetyRequest,
    request: Request = None,
):
    service = SafetyQueryService(
        resolver=get_entity_resolver(request),
        engine=get_safety_engine(request),
        explainer=get_safety_explainer(request),
    )
    response = service.query(
        payload.question,
        use_llm_plan=payload.use_llm_plan,
        request_id=get_request_id(request),
    )
    return response.model_dump(mode="json")
