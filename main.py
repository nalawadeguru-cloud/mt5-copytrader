import asyncio
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import sqlite3
import os

app = FastAPI()

# ---- पाथ कॉन्फिगरेशन (Render सर्व्हरसाठी अत्यंत महत्त्वाचे) ----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
DB_PATH = os.path.join(BASE_DIR, "database.db")

# ---- डेटाबेस सुरू करणे ----
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

# ॲप्लिकेशन सुरू होताच डेटाबेस टेबल तयार होईल
init_db()

# ---- होम पेज (डॅशबोर्ड UI) ----
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_type, metaapi_account_id, multiplier FROM accounts")
        accounts = cursor.fetchall()
        conn.close()
        
        # Jinja2 च्या नवीन व्हर्जननुसार अचूक फॉरमॅट
        return templates.TemplateResponse(
            request=request, 
            name="index.html", 
            context={"accounts": accounts}
        )
    except Exception as e:
        return HTMLResponse(content=f"<h3>डेटाबेस किंवा टेम्पलेट एरर: {str(e)}</h3>", status_code=500)

# ---- नवीन MT5 अकाऊंट जोडणे ----
@app.post("/add-account")
async def add_account(
    user_type: str = Form(...), 
    metaapi_account_id: str = Form(...), 
    multiplier: float = Form(...)
):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO accounts (user_type, metaapi_account_id, multiplier) VALUES (?, ?, ?)",
            (user_type, metaapi_account_id, multiplier)
        )
        conn.commit()
        conn.close()
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        return HTMLResponse(content=f"<h3>डेटा सेव्ह करताना एरर आली: {str(e)}</h3>", status_code=500)

# ---- कोअर कॉपी ट्रेडिंग इंजिन (बॅकग्राउंड लूप) ----
async def start_copy_engine():
    try:
        from metaapi_cloud_sdk import MetaApi
        
        # ⚠️ तुमचा MetaAPI चा टोकन इथे टाका
        API_TOKEN = "eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCJ9.eyJfaWQiOiJkYTYwM2ZlYTEyNjMyYjFjNDNjZWRiZjYyZTYwYWY0ZCIsImFjY2Vzc1J1bGVzIjpbeyJpZCI6InRyYWRpbmctYWNjb3VudC1tYW5hZ2VtZW50LWFwaSIsIm1ldGhvZHMiOlsidHJhZGluZy1hY2NvdW50LW1hbmFnZW1lbnQtYXBpOnJlc3Q6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6Im1ldGFhcGktcmVzdC1hcGkiLCJtZXRob2RzIjpbIm1ldGFhcGktYXBpOnJlc3Q6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6Im1ldGFhcGktcnBjLWFwaSIsIm1ldGhvZHMiOlsibWV0YWFwaS1hcGk6d3M6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6Im1ldGFhcGktcmVhbC10aW1lLXN0cmVhbWluZy1hcGkiLCJtZXRob2RzIjpbIm1ldGFhcGktYXBpOndzOnB1YmxpYzoqOioiXSwicm9sZXMiOlsicmVhZGVyIiwid3JpdGVyIl0sInJlc291cmNlcyI6WyIqOiRVU0VSX0lEJDoqIl19LHsiaWQiOiJtZXRhc3RhdHMtYXBpIiwibWV0aG9kcyI6WyJtZXRhc3RhdHMtYXBpOnJlc3Q6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6InJpc2stbWFuYWdlbWVudC1hcGkiLCJtZXRob2RzIjpbInJpc2stbWFuYWdlbWVudC1hcGk6cmVzdDpwdWJsaWM6KjoqIl0sInJvbGVzIjpbInJlYWRlciIsIndyaXRlciJdLCJyZXNvdXJjZXMiOlsiKjokVVNFUl9JRCQ6KiJdfSx7ImlkIjoiY29weWZhY3RvcnktYXBpIiwibWV0aG9kcyI6WyJjb3B5ZmFjdG9yeS1hcGk6cmVzdDpwdWJsaWM6KjoqIl0sInJvbGVzIjpbInJlYWRlciIsIndyaXRlciJdLCJyZXNvdXJjZXMiOlsiKjokVVNFUl9JRCQ6KiJdfSx7ImlkIjoibXQtbWFuYWdlci1hcGkiLCJtZXRob2RzIjpbIm10LW1hbmFnZXItYXBpOnJlc3Q6ZGVhbGluZzoqOioiLCJtdC1tYW5hZ2VyLWFwaTpyZXN0OnB1YmxpYzoqOioiXSwicm9sZXMiOlsicmVhZGVyIiwid3JpdGVyIl0sInJlc291cmNlcyI6WyIqOiRVU0VSX0lEJDoqIl19LHsiaWQiOiJiaWxsaW5nLWFwaSIsIm1ldGhvZHMiOlsiYmlsbGluZy1hcGk6cmVzdDpwdWJsaWM6KjoqIl0sInJvbGVzIjpbInJlYWRlciJdLCJyZXNvdXJjZXMiOlsiKjokVVNFUl9JRCQ6KiJdfV0sImlnbm9yZVJhdGVMaW1pdHMiOmZhbHNlLCJ0b2tlbklkIjoiMjAyMTAyMTMiLCJpbXBlcnNvbmF0ZWQiOmZhbHNlLCJyZWFsVXNlcklkIjoiZGE2MDNmZWExMjYzMmIxYzQzY2VkYmY2MmU2MGFmNGQiLCJpYXQiOjE3ODA5NzY2NDd9.Y9pKwO4B9D8wTjrEQpiYgGzd3rZq51ii9HcjCxy5XRlj35a-gTXB49F9b5gyBszlnW7rOHRgvIh40Tq3yXccDd_nJHXGCa9LX3KZiX620ITuYBiyYnt8YwxF0U2LW61zU9QDlMtLwgOrv-7LPFLfYf4duc9T-blL2nuN15lsN77pfWUtYfTq9dORZ6fqFXUE66WVmao05hMcF_FKoxrRxDavwESw5iN896EzOCVc_1BOh1OU_xmS-R1fa3vS6zmDu8-nS07osHH0K3PE7cdw6bHmnP2nVCW22yanGqFHG4ryAYKO0JSXvssZ6Fs5jnk5fH5JC21ewe6_JFa7YcQTSLz7o65IT9MsfPA4IyuPcbOFsI4aLl5-SuxeYW7LurPErso1r9ATFIKnl_n1sXDcaYkSIuLPmJdAsfROoKvN9n_S2nNI2kLzvJlqJjjb_hii7QZ5yB00-S5zJ6mrJH59bf6kGhmlptTV1ra4nb1UbcZv45LBsjOue8xEOQm5pZw5DigjYVbYpH5VIY9mTauf9Z1uatmRy1Cew8gDenKv6pYuvR86Arj6RoAYhmn3h3aoCAPzAudjLxEh_MalldvYvErmga1w5VbmToo4jkTDwfQntNf8NzYOerSRqWJfxIwDzx5PWfSBKc94ZRX5a3832pURKkzrKlD2hmWU7NxP4q4" 
        api = MetaApi(token=API_TOKEN)
        
        print("🚀 कॉपी ट्रेडिंग इंजिन बॅकग्राउंडमध्ये यशस्वीरीत्या ॲक्टिव्ह झाले आहे...")
        
        while True:
            # इथे तुमची ट्रेड कॉपी करण्याची मुख्य लॉजिक रन होईल
            await asyncio.sleep(10)
            
    except Exception as e:
        print(f"❌ कॉपी इंजिनमध्ये एरर आली: {e}")

# ---- ॲप्लिकेशन स्टार्टअप इव्हेंट ----
@app.on_event("startup")
async def startup_event():
    # सर्व्हर सुरू होताच कॉपी ट्रेडिंगचे इंजिन बॅकग्राउंडमध्ये धावणे सुरू होईल
    asyncio.create_task(start_copy_engine())
