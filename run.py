"""Convenient local entry point for CloudOpsAI."""

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8006,
        reload=True,
    )
