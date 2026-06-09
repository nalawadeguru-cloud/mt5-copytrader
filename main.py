import asyncio
from fastapi import FastAPI, Request, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import sqlite3
import os
from pathlib import Path

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
if not (BASE_DIR / "templates").exists():
    BASE_DIR = Path(os.getcwd()).resolve()

TEMPLATES_DIR = BASE_DIR / "templates"
DB_PATH = BASE_DIR / "database.db"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

SECRET_PIN = "2026" 
is_authenticated = False
running_engine_id = 0

def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_type TEXT,
            metaapi_account_id TEXT,
            multiplier REAL DEFAULT 1.0,
            account_name TEXT DEFAULT 'Unnamed',
            broker_name TEXT DEFAULT 'Unknown',
            mt5_login TEXT DEFAULT '000000',
            max_risk REAL DEFAULT 30.0,
            equity REAL DEFAULT 0.0,
            pnl REAL DEFAULT 0.0,
            current_symbol TEXT DEFAULT 'None'
        )
    """)
    conn.commit()
    conn.close()

init_db()

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse("login.html", {"request": request, "error": error})

@app.post("/verify-pin")
async def verify_pin(pin: str = Form(...)):
    global is_authenticated
    if pin == SECRET_PIN:
        is_authenticated = True
        return RedirectResponse(url="/", status_code=303)
    else:
        return RedirectResponse(url="/login?error=चुकीचा पिन कोड! पुन्हा प्रयत्न करा.", status_code=303)

@app.get("/logout")
async def logout():
    global is_authenticated
    is_authenticated = False
    return RedirectResponse(url="/login", status_code=303)

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    global is_authenticated
    if not is_authenticated:
        return RedirectResponse(url="/login", status_code=303)
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_type, metaapi_account_id, multiplier, account_name, broker_name, mt5_login, max_risk, equity, pnl, current_symbol FROM accounts")
        accounts = cursor.fetchall()
        conn.close()
        return templates.TemplateResponse("index.html", {"request": request, "accounts": accounts})
    except Exception as e:
        return HTMLResponse(content=f"<h3>Database Error: {str(e)}</h3>", status_code=500)

# [बाकीचा ॲड-अकाउंट आणि कॉपी इंजिनचा कोड जसा आहे तसाच पुढे सुरू राहील...]
