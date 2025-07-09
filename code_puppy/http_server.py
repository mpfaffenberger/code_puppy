from fastapi import FastAPI, Request, Form
from fastapi.middleware.cors import CORSMiddleware
import os

app = FastAPI()

# Enable CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CONFIG_FILENAME = "puppy.cfg"

@app.post("/save_token")
async def save_token(puppy_token: str = Form(...)):
    """
    Accepts a puppy_token as a POST param and saves it to puppy.cfg
    """
    config_path = os.path.join(os.path.expanduser("~"), CONFIG_FILENAME)
    try:
        with open(config_path, "w") as f:
            f.write(f"puppy_token={puppy_token}\n")
        return {"status": "success", "message": "Token saved."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
