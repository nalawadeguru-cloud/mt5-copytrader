import asyncio
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import sqlite3
import os

app = FastAPI()

# रेंडर सर्व्हरसाठी टेम्पलेट्सचा अचूक पाथ सेट करणे
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
DB_PATH = os.path.join(BASE_DIR, "database.db")

# ---- डेटाबेस तयार करणे ----
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_type TEXT,
            metaapi_account_id TEXT,
            multiplier REAL DEFAULT 1.0
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---- होम पेज (डॅशबोर्ड दाखवणे) ----
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM accounts")
        accounts = cursor.fetchall()
        conn.close()
        return templates.TemplateResponse("index.html", {"request": request, "accounts": accounts})
    except Exception as e:
        return HTMLResponse(content=f"<h3>डेटाबेस किंवा टेम्पलेट एरर: {str(e)}</h3>", status_code=500)

# ---- नवीन अकाऊंट जोडणे ----
@app.post("/add-account")
async def add_account(user_type: str = Form(...), metaapi_account_id: str = Form(...), multiplier: float = Form(...)):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO accounts (user_type, metaapi_account_id, multiplier) VALUES (?, ?, ?)",
        (user_type, metaapi_account_id, multiplier)
    )
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

# ---- कोअर कॉपी ट्रेडिंग इंजिन (बॅकग्राउंड टास्क) ----
async def start_copy_engine():
    try:
        from metaapi_cloud_sdk import MetaApi
        API_TOKEN = "तुमचा_API_TOKEN_इथे_टाका"  # <--- तुमचा टोकन इथेच राहू द्या
        api = MetaApi(token=API_TOKEN)
        print("🚀 कॉपी ट्रेडिंग इंजिन बॅकग्राउंडमध्ये ॲक्टिव्ह आहे...")
        
        while True:
            await asyncio.sleep(10)
    except Exception as e:
        print(f"❌ कॉपी इंजिन एरर: {e}")

# ---- ॲप्लिकेशन सुरू होताना बॅकग्राउंड टास्क चालू करणे ----
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(start_copy_engine())
