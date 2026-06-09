from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import sqlite3

app = FastAPI()

# पाथ सेट करणे
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# डेटाबेस इनिशियलायझेशन
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_name TEXT,
            equity REAL,
            pnl REAL
        )
    """)
    conn.commit()
    conn.close()

init_db()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM accounts")
    accounts = cursor.fetchall()
    conn.close()
    return templates.TemplateResponse("index.html", {"request": request, "accounts": accounts})

@app.post("/add")
async def add(account_name: str = Form(...), equity: float = Form(...)):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO accounts (account_name, equity, pnl) VALUES (?, ?, 0.0)", (account_name, equity))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)
