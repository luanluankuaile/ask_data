"""Start the web page and the API on one server."""
import uvicorn

from back_end.app import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
