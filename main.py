import asyncio
from fastapi import FastAPI, Request, Form, BackgroundTasks, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import sqlite3
import os

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
DB_PATH = os.path.join(BASE_DIR, "database.db")

# 🔑 तुमचा गुप्त पिन कोड इथे सेट करा (हा फक्त तुम्हाला माहीत असेल)
# तुम्ही हा बदलून दुसरा कोणताही नंबर ठेवू शकता
SECRET_PIN = "2026" 

# सेशन ट्रॅक करण्यासाठी (लॉगिन आहे की नाही)
is_authenticated = False
running_engine_id = 0

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

# 🔒 लॉगिन स्क्रीन (पिन कोड मागण्यासाठी)
@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    return templates.TemplateResponse(request=request, name="login.html", context={"error": error})

# 🔑 पिन कोड व्हेरीफाय करणे
@app.post("/verify-pin")
async def verify_pin(pin: str = Form(...)):
    global is_authenticated
    if pin == SECRET_PIN:
        is_authenticated = True
        return RedirectResponse(url="/", status_code=303)
    else:
        return RedirectResponse(url="/login?error=चुकीचा पिन कोड! पुन्हा प्रयत्न करा.", status_code=303)

# 🚪 लॉगआउट करणे
@app.get("/logout")
async def logout():
    global is_authenticated
    is_authenticated = False
    return RedirectResponse(url="/login", status_code=303)

# 🏠 सुरक्षित मुख्य डॅशबोर्ड
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    global is_authenticated
    if not is_authenticated:
        return RedirectResponse(url="/login", status_code=303)
        
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_type, metaapi_account_id, multiplier FROM accounts")
        accounts = cursor.fetchall()
        conn.close()
        return templates.TemplateResponse(request=request, name="index.html", context={"accounts": accounts})
    except Exception as e:
        return HTMLResponse(content=f"<h3>Database or Template Error: {str(e)}</h3>", status_code=500)

@app.post("/add-account")
async def add_account(
    background_tasks: BackgroundTasks,
    user_type: str = Form(...), 
    metaapi_account_id: str = Form(...), 
    multiplier: float = Form(...)
):
    global is_authenticated
    if not is_authenticated:
        raise HTTPException(status_code=403, detail="Not authenticated")
        
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO accounts (user_type, metaapi_account_id, multiplier) VALUES (?, ?, ?)", (user_type, metaapi_account_id, multiplier))
        conn.commit()
        conn.close()
        
        global running_engine_id
        running_engine_id += 1
        background_tasks.add_task(start_copy_engine, running_engine_id)
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        return HTMLResponse(content=f"<h3>Error: {str(e)}</h3>", status_code=500)

# ---- मुख्य रिअल-टाइम कॉपी ट्रेडिंग इंजिन ----
async def start_copy_engine(engine_id: int):
    global running_engine_id
    try:
        from metaapi_cloud_sdk import MetaApi
        API_TOKEN = "YOUR_METAAPI_TOKEN_HERE" 
        api = MetaApi(token=API_TOKEN)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT user_type, metaapi_account_id, multiplier FROM accounts")
        rows = cursor.fetchall()
        conn.close()

        master_id = None
        followers = []
        for row in rows:
            if row[0].lower() == 'master':
                master_id = row[1]
            else:
                followers.append({'id': row[1], 'multiplier': row[2]})

        if not master_id or not followers:
            return

        master_account = await asyncio.wait_for(api.metatrader_account_api.get_account(master_id), timeout=30)
        await asyncio.wait_for(master_account.wait_connected(), timeout=30)
        master_connection = master_account.get_streaming_connection()
        await asyncio.wait_for(master_connection.connect(), timeout=30)
        await asyncio.wait_for(master_connection.wait_synchronized(), timeout=45)

        follower_objects = {}
        for f in followers:
            try:
                if engine_id != running_engine_id: return
                f_acc = await asyncio.wait_for(api.metatrader_account_api.get_account(f['id']), timeout=30)
                await asyncio.wait_for(f_acc.wait_connected(), timeout=30)
                follower_objects[str(f['id'])] = {"account": f_acc, "multiplier": f['multiplier']}
            except Exception as fe:
                print(f"❌ Follower [{f['id']}] Error: {fe}")

        class TradeCopyListener:
            async def on_positions_synchronized(self, instance_index, synchronization_id):
                if engine_id != running_engine_id: return
                master_positions = master_connection.terminal_state.positions
                if not master_positions: return

                for pos in master_positions:
                    symbol = pos.get('symbol')
                    position_type = pos.get('type')
                    volume = pos.get('volume', 0)
                    order_type = 'ORDER_TYPE_BUY' if position_type == 'POSITION_TYPE_BUY' else 'ORDER_TYPE_SELL'
                    
                    for f_id, f_data in follower_objects.items():
                        try:
                            f_acc = f_data["account"]
                            mult = f_data["multiplier"]
                            target_volume = max(round(volume * mult, 2), 0.01)
                            await f_acc.create_market_order(symbol, order_type, target_volume)
                        except Exception as copy_err:
                            print(f"❌ Follower [{f_id}] Copy Error: {copy_err}")

        master_connection.add_synchronization_listener(TradeCopyListener())
        while engine_id == running_engine_id:
            await asyncio.sleep(1)

    except Exception as e:
        print(f"❌ [Engine {engine_id}] Crashed: {e}")
        await asyncio.sleep(10)
        if engine_id == running_engine_id:
            await start_copy_engine(engine_id)

@app.on_event("startup")
async def startup_event():
    global running_engine_id
    running_engine_id += 1
    asyncio.create_task(start_copy_engine(running_engine_id))
