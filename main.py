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

# 🔑 सुरक्षा पिन कोड
SECRET_PIN = "2026" 

is_authenticated = False
running_engine_id = 0

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 📊 सर्व आवश्यक इनपुट्स आणि लाईव्ह मॅट्रिक्ससह टेबल तयार करणे
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
    
    # जुन्या डेटाबेसमध्ये नवीन कॉलम सुरक्षितपणे जोडण्यासाठी सेफ्टी चेक्स
    columns_to_add = [
        ("account_name", "TEXT DEFAULT 'Unnamed'"),
        ("broker_name", "TEXT DEFAULT 'Unknown'"),
        ("mt5_login", "TEXT DEFAULT '000000'"),
        ("max_risk", "REAL DEFAULT 30.0"),
        ("equity", "REAL DEFAULT 0.0"),
        ("pnl", "REAL DEFAULT 0.0"),
        ("current_symbol", "TEXT DEFAULT 'None'")
    ]
    for col, col_type in columns_to_add:
        try:
            cursor.execute(f"ALTER TABLE accounts ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError:
            pass
            
    conn.commit()
    conn.close()

init_db()

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = ""):
    # 💻 फिक्स: नवीन FastAPI व्हर्जननुसार सिस्टिमॅटिक आर्गुमेंट्स पास केले आहेत
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
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # सर्व आवश्यक माहिती डेटाबेसमधून ओढणे
        cursor.execute("SELECT id, user_type, metaapi_account_id, multiplier, account_name, broker_name, mt5_login, max_risk, equity, pnl, current_symbol FROM accounts")
        accounts = cursor.fetchall()
        conn.close()
        # 💻 फिक्स: होम पेजसाठी योग्य रीतीने टेम्पलेट रिस्पॉन्स
        return templates.TemplateResponse("index.html", {"request": request, "accounts": accounts})
    except Exception as e:
        return HTMLResponse(content=f"<h3>Database Error: {str(e)}</h3>", status_code=500)

@app.post("/add-account")
async def add_account(
    background_tasks: BackgroundTasks,
    user_type: str = Form(...), 
    metaapi_account_id: str = Form(...), 
    multiplier: float = Form(...),
    account_name: str = Form(...),
    broker_name: str = Form(...),
    mt5_login: str = Form(...),
    max_risk: float = Form(...)
):
    global is_authenticated
    if not is_authenticated:
        raise HTTPException(status_code=403, detail="Not authenticated")
        
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            """INSERT INTO accounts 
            (user_type, metaapi_account_id, multiplier, account_name, broker_name, mt5_login, max_risk) 
            VALUES (?, ?, ?, ?, ?, ?, ?)""", 
            (user_type, metaapi_account_id, multiplier, account_name, broker_name, mt5_login, max_risk)
        )
        conn.commit()
        conn.close()
        
        global running_engine_id
        running_engine_id += 1
        background_tasks.add_task(start_copy_engine, running_engine_id)
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        return HTMLResponse(content=f"<h3>Error: {str(e)}</h3>", status_code=500)

async def start_copy_engine(engine_id: int):
    global running_engine_id
    try:
        from metaapi_cloud_sdk import MetaApi
        API_TOKEN = "YOUR_METAAPI_TOKEN_HERE" 
        api = MetaApi(token=API_TOKEN)
        
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_type, metaapi_account_id, multiplier, max_risk FROM accounts")
        rows = cursor.fetchall()
        conn.close()

        master_id = None
        followers = []
        for row in rows:
            if row[1].lower() == 'master':
                master_id = row[2]
            else:
                followers.append({'db_id': row[0], 'id': row[2], 'multiplier': row[3], 'max_risk': row[4]})

        if not master_id:
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
                f_conn = f_acc.get_streaming_connection()
                await f_conn.connect()
                await f_conn.wait_synchronized()
                
                follower_objects[str(f['id'])] = {
                    "account": f_acc, 
                    "connection": f_conn,
                    "multiplier": f['multiplier'],
                    "max_risk": f['max_risk'],
                    "db_id": f['db_id']
                }
            except Exception as fe:
                print(f"❌ Follower [{f['id']}] Connection Error: {fe}")

        # 🔄 बॅकग्राउंड टास्क: प्रत्येक २ सेकंदाला लाईव्ह डेटाबेस अपडेट करणे
        async def update_account_metrics():
            while engine_id == running_engine_id:
                try:
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    
                    # १. मास्टर अकाऊंट लाईव्ह आकडेवारी
                    m_state = master_connection.terminal_state
                    m_equity = m_state.account_information.get('equity', 0.0)
                    m_pnl = m_state.account_information.get('profit', 0.0)
                    m_positions = m_state.positions
                    m_sym = m_positions[0].get('symbol', 'None') if m_positions else 'None'
                    
                    cursor.execute("UPDATE accounts SET equity=?, pnl=?, current_symbol=? WHERE user_type='Master'", (m_equity, m_pnl, m_sym))
                    
                    # २. सर्व फॉलोअर्सची लाईव्ह आकडेवारी
                    for f_id, f_data in follower_objects.items():
                        f_state = f_data["connection"].terminal_state
                        f_equity = f_state.account_information.get('equity', 0.0)
                        f_pnl = f_state.account_information.get('profit', 0.0)
                        f_pos = f_state.positions
                        f_sym = f_pos[0].get('symbol', 'None') if f_pos else 'None'
                        
                        cursor.execute("UPDATE accounts SET equity=?, pnl=?, current_symbol=? WHERE id=?", (f_equity, f_pnl, f_sym, f_data["db_id"]))
                    
                    conn.commit()
                    conn.close()
                except Exception as ue:
                    print(f"Metrics Update Error: {ue}")
                await asyncio.sleep(2)

        asyncio.create_task(update_account_metrics())

        # 👑 ट्रेड कॉपी करण्याचे मूळ लॉजिक (With Advanced Risk Guard)
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
                            # 🛡️ कमाल तोटा मर्यादा (Max Risk Check) सुरक्षा कवच
                            f_state = f_data["connection"].terminal_state
                            balance = f_state.account_information.get('balance', 1.0)
                            pnl = f_state.account_information.get('profit', 0.0)
                            current_dd = (abs(pnl) / balance) * 100 if pnl < 0 else 0
                            
                            if current_dd > f_data["max_risk"]:
                                print(f"⚠️ Follower [{f_id}] Risk Limit Exceeded ({round(current_dd, 2)}%). Trade Skipped!")
                                continue
                                
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
