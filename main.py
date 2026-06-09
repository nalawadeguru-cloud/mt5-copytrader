from fastapi import FastAPI, Request, Form
from fastapi.templating import Jinja2Templates
from pathlib import Path
import sqlite3

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# डेटाबेस तयार करणे
def init_db():
    try:
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY, account_name TEXT, equity REAL, pnl REAL)")
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Database error: {e}")

init_db()

@app.get("/")
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})
