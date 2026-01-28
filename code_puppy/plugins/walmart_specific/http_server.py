from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware

from code_puppy.config import set_value

app = FastAPI()

# Enable CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/save_token")
async def save_token(puppy_token: str = Form(...)):
    """
    Accepts a puppy_token as a POST param and saves it to config using the config API.
    """
    try:
        set_value("puppy_token", puppy_token)
        return {"status": "success", "message": "Token saved."}
    except Exception as e:
        return {"status": "error", "message": str(e)}
