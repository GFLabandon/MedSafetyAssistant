# api.py - FastAPI wrapper layer
from contextlib import asynccontextmanager
import json
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from logic_layer.assistant_service import (
    DEFAULT_SESSION_ID,
    answer_medication_question,
    prepare_medication_context,
    save_conversation_result,
)
from logic_layer.health_check import get_environment_diagnostics
from logic_layer.kg_service import MedicalKG
from logic_layer.llm_service import stream_safety_response
from logic_layer.vector_store import VectorStore
from medsafety.catalog import KnowledgeCatalog
from medsafety.safety_engine import SafetyEngine


V1_DATA_DIRECTORY = Path(__file__).resolve().parent / "data/v1"
logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    session_id: str = DEFAULT_SESSION_ID

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value):
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()

    @field_validator("session_id")
    @classmethod
    def session_id_must_not_be_blank(cls, value):
        if not value.strip():
            return DEFAULT_SESSION_ID
        return value.strip()


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


def build_safety_engine():
    return SafetyEngine(KnowledgeCatalog.from_directory(V1_DATA_DIRECTORY))


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.safety_engine = build_safety_engine()
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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(
        "unhandled API exception",
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "detail": "An unexpected error occurred.",
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


@app.get("/api/health")
async def health():
    return get_environment_diagnostics()


@app.post("/api/v1/safety/check")
async def check_v1_safety(payload: SafetyCheckRequest, request: Request = None):
    result = get_safety_engine(request).assess(payload.medications, contexts=payload.contexts)
    return result.model_dump(mode="json")
