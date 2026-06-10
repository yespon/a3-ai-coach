from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.api.router import api_router
from app.core.config import STATIC_DIR
from app.core.logger import attach_request_logging_middleware, get_component_logger, setup_logging
from app.services.context_service import MATERIALS_CONTEXT_CACHE
from app.services.session_service import SESSIONS

setup_logging()


app = FastAPI(title="Gangbiao Chatbot", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

LOGGER = get_component_logger(component="chatbot")

attach_request_logging_middleware(app, LOGGER)
app.include_router(api_router, prefix="/api")
app.include_router(api_router, prefix="/api/v1")


@app.get("/")
async def index() -> FileResponse:
    html = STATIC_DIR / "index.html"
    if not html.exists():
        raise HTTPException(status_code=404, detail="前端页面不存在")
    return FileResponse(html)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=2088, reload=True)
