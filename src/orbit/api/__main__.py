"""Start the Orbit API: uv run python -m orbit.api"""

import uvicorn

from orbit.config.settings import API_HOST, API_PORT

if __name__ == "__main__":
    uvicorn.run("orbit.api.app:app", host=API_HOST, port=API_PORT, log_level="info")
