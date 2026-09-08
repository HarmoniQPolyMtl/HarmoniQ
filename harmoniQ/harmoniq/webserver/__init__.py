from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from .limiter import rate_limit_middleware

from pathlib import Path

from harmoniq.webserver.REST import router as api_router

ANGULAR_DIST = Path(__file__).parents[3] / "client" / "dist" / "client" / "browser"
ANGULAR_INDEX = ANGULAR_DIST / "index.html"

app = FastAPI(
    title="HarmoniQ",
    description="Outil de modélisation de production d'énergie au Québec",
    version="0.1",
    contact={
        "name": "Sébastien Dasys",
        "email": "sebastien.dasys@polymtl.ca",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
)

app.middleware("http")(rate_limit_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SPAFallbackMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        if response.status_code != 404:
            return response

        path = request.url.path.lstrip("/")

        if path.startswith("api"):
            return response

        candidate = ANGULAR_DIST / path
        if candidate.is_file():
            return FileResponse(candidate)

        if ANGULAR_INDEX.is_file():
            return FileResponse(ANGULAR_INDEX)
            
        return response


app.add_middleware(SPAFallbackMiddleware)

app.include_router(api_router)
