import asyncio
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import sqlite3
import os

app = FastAPI()

# ---- पाथ कॉन्फिगरेशन ----
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
        return HTMLResponse(content=f"<h3>एरर आली: {str(e)}</h3>", status_code=500)

# 🚀 ---- कोअर रिअल-टाइम कॉपी ट्रेडिंग इंजिन ----
async def start_copy_engine():
    try:
        from metaapi_cloud_sdk import MetaApi
        
        # ⚠️ तुमचा खरा MetaAPI टोकन इथे पेस्ट करा
        API_TOKEN = "YOUR_METAAPI_TOKEN_HERE" 
        api = MetaApi(token=API_TOKEN)
        
        print("🚀 कॉपी ट्रेडिंग इंजिन बॅकग्राउंडमध्ये ॲक्टिव्ह झाले आहे...")

        # १. डेटाबेसमधून मास्टर आणि फॉलोवर डिटेल्स लोड करणे
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

        if not master_id:
            print("⏳ वाट पाहत आहे... डॅशबोर्डवर अजून 'Master Account' जोडलेला नाही.")
            return

        print(f"📡 मास्टर अकाऊंट {master_id} शी कनेक्ट होत आहे...")
        master_account = await api.metatrader_account_api.get_account(master_id)
        await master_account.wait_connected()
        
        master_connection = master_account.get_streaming_connection()
        await master_connection.connect()
        await master_connection.wait_synchronized()

        # २. फॉलोवर अकाऊंट्सचे कनेक्शन बॅकग्राउंडमध्ये तयार ठेवणे
        follower_connections = {}
        for f in followers:
            try:
                print(f"📡 फॉलोवर अकाऊंट {f['id']} कनेक्ट करत आहे...")
                f_account = await api.metatrader_account_api.get_account(f['id'])
                await f_account.wait_connected()
                f_conn = f_account.get_streaming_connection()
                await f_conn.connect()
                await f_conn.wait_synchronized()
                follower_connections[f['id']] = {"connection": f_conn, "multiplier": f['multiplier']}
            except Exception as fe:
                print(f"❌ फॉलोवर {f['id']} कनेक्ट होऊ शकला नाही: {fe}")

        # ३. मास्टर अकाऊंटवरील ट्रेड्स ट्रॅक करण्यासाठी सिंक्रोनाइझेशन लिसनर
        class TradeCopyListener:
            async def on_positions_synchronized(self, instance_index, synchronization_id):
                # मास्टरवरील सध्याच्या सर्व ओपन पोझिशन्स वाचणे
                master_positions = master_connection.terminal_state.positions
                
                for pos in master_positions:
                    symbol = pos.get('symbol')
                    position_type = pos.get('type') # 'POSITION_TYPE_BUY' किंवा 'POSITION_TYPE_SELL'
                    volume = pos.get('volume', 0)
                    
                    print(f"🔔 मास्टरवर अॅक्टिव्ह ट्रेड: {symbol} | Type: {position_type} | Volume: {volume}")
                    
                    # प्रत्येक फॉलोवरवर हा ट्रेड कॉपी करणे
                    for f_id, f_data in follower_connections.items():
                        try:
                            f_conn = f_data["connection"]
                            mult = f_data["multiplier"]
                            
                            # फॉलोवरवर आधीच हा ट्रेड सुरू आहे का ते तपासणे (डबल ट्रेड टाळण्यासाठी)
                            follower_positions = f_conn.terminal_state.positions
                            already_exists = any(p.get('symbol') == symbol and p.get('type') == position_type for p in follower_positions)
                            
                            if not already_exists:
                                # मल्टिप्लायरनुसार लॉट साईझ ठरवणे
                                target_volume = round(volume * mult, 2)
                                if target_volume < 0.01:
                                    target_volume = 0.01
                                
                                # मार्केट ऑर्डर टाईप सेट करणे
                                order_type = 'ORDER_TYPE_BUY' if position_type == 'POSITION_TYPE_BUY' else 'ORDER_TYPE_SELL'
                                
                                print(f"➡️ फॉलोवर {f_id} वर ट्रेड कॉपी केला जात आहे: Size {target_volume}")
                                await f_conn.create_market_order(symbol, order_type, target_volume)
                        except Exception as copy_err:
                            print(f"❌ फॉलोवर {f_id} वर ऑर्डर टाकताना एरर: {copy_err}")

        master_connection.add_synchronization_listener(TradeCopyListener())
        
        # सिस्टीम २४/७ चालू ठेवण्यासाठी लूप
        while True:
            await asyncio.sleep(1)

    except Exception as e:
        print(f"❌ कॉपी ट्रेडिंग इंजिनमध्ये एरर: {e}")
        await asyncio.sleep(15)
        # एरर आल्यास ऑटो-रिस्टार्ट
        asyncio.create_task(start_copy_engine())

# ---- स्टार्टअप इव्हेंट ----
@app.on_event("startup")
async def startup_event():
    asyncio.create_task(start_copy_engine())
