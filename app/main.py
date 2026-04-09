from fastapi import Depends, FastAPI, HTTPException

from app.dependencies import get_engine, get_session_store
from app.engine.lesson_engine import LessonEngine
from app.exceptions import LessonAlreadyCompletedError, SessionNotFoundError
from app.models.schemas import (
    LessonMessageRequest,
    LessonMessageResponse,
    LessonStartRequest,
    LessonStartResponse,
    LessonStateResponse,
)
from app.protocols import SessionStoreProtocol

app = FastAPI(title="Charlie AI", description="English lesson engine for kids")


def _build_state_response(state) -> LessonStateResponse:
    return LessonStateResponse(
        stage=state.stage.value,
        current_word=state.current_word,
        progress=state.progress,
        is_finished=state.is_finished,
    )


@app.post("/lesson/start", response_model=LessonStartResponse)
async def start_lesson(
    request: LessonStartRequest,
    engine: LessonEngine = Depends(get_engine),
):
    if not request.word_list:
        raise HTTPException(status_code=422, detail="word_list cannot be empty")

    session_id, greeting, state = await engine.start_lesson(
        word_list=request.word_list,
        child_name=request.child_name,
    )

    return LessonStartResponse(
        session_id=session_id,
        charlie_response=greeting,
        lesson_state=_build_state_response(state),
    )


@app.post("/lesson/message", response_model=LessonMessageResponse)
async def send_message(
    request: LessonMessageRequest,
    engine: LessonEngine = Depends(get_engine),
):
    try:
        response_text, state = await engine.handle_message(
            session_id=request.session_id,
            child_text=request.text,
        )
    except SessionNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    except LessonAlreadyCompletedError:
        raise HTTPException(status_code=400, detail="Lesson already completed")

    return LessonMessageResponse(
        charlie_response=response_text,
        lesson_state=_build_state_response(state),
    )


@app.get("/lesson/{session_id}/status", response_model=LessonStateResponse)
async def get_status(
    session_id: str,
    store: SessionStoreProtocol = Depends(get_session_store),
):
    state = store.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return _build_state_response(state)
