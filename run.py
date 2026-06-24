#!/usr/bin/env python3
"""Entry point: `python run.py` starts the server."""
import uvicorn
from app.core.config import settings


def main():
    mode = "real LLM" if settings.can_use_real_llm else "MOCK (no API key)"
    print(f"\n  LangGraph Multi-Agent Chat")
    print(f"  ─────────────────────────────────")
    print(f"  Model : {settings.model_name}")
    print(f"  Mode  : {mode}")
    print(f"  URL   : http://{settings.host}:{settings.port}\n")
    uvicorn.run("app.api:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
