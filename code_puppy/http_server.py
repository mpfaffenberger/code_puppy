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

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".code_puppy")
CONFIG_FILENAME = "puppy.cfg"
CONFIG_PATH = os.path.join(CONFIG_DIR, CONFIG_FILENAME)

@app.post("/save_token")
async def save_token(puppy_token: str = Form(...)):
    """
    Accepts a puppy_token as a POST param and saves it to ~/.code_puppy/puppy.cfg,
    preserving other config values.
    """
    try:
        # Ensure config directory exists
        os.makedirs(CONFIG_DIR, exist_ok=True)
        config_lines = []
        found = False
        # Read existing config if it exists
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                for line in f:
                    if line.startswith("puppy_token="):
                        config_lines.append(f"puppy_token={puppy_token}\n")
                        found = True
                    else:
                        config_lines.append(line)
        if not found:
            config_lines.append(f"puppy_token={puppy_token}\n")
        with open(CONFIG_PATH, "w") as f:
            f.writelines(config_lines)
        return {"status": "success", "message": "Token saved."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
