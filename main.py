import asyncio
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import sqlite3
import os

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))
DB_PATH = os.path.join(BASE_DIR, "database.db")

# ग्लोबल व्हेरिएबल - जुने चालू असलेले इंजिन टास्क ट्रॅक करण्यासाठी
current_copy_task = None

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

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id, user_type, metaapi_account_id, multiplier FROM accounts")
        accounts = cursor.fetchall()
        conn.close()
        return templates.TemplateResponse(request=request, name="index.html", context={"accounts": accounts})
    except Exception as e:
        return HTMLResponse(content=f"<h3>डेटाबेस किंवा टेम्पलेट एरर: {str(e)}</h3>", status_code=500)

@app.post("/add-account")
async def add_account(user_type: str = Form(...), metaapi_account_id: str = Form(...), multiplier: float = Form(...)):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO accounts (user_type, metaapi_account_id, multiplier) VALUES (?, ?, ?)", (user_type, metaapi_account_id, multiplier))
        conn.commit()
        conn.close()
        
        # 🔥 नवीन अकाऊंट जोडताच कॉपी इंजिनला बॅकग्राउंडमध्ये रिस्टार्ट करणे
        global current_copy_task
        if current_copy_task and not current_copy_task.done():
            current_copy_task.cancel()
        current_copy_task = asyncio.create_task(start_copy_engine())
        
        return RedirectResponse(url="/", status_code=303)
    except Exception as e:
        return HTMLResponse(content=f"<h3>एरर आली: {str(e)}</h3>", status_code=500)

# 🚀 ---- मुख्य रिअल-टाइम कॉपी ट्रेडिंग इंजिन ----
async def start_copy_engine():
    try:
        from metaapi_cloud_sdk import MetaApi
        
        # ⚠️ इथे तुमचा अचूक MetaAPI टोकन टाका
        API_TOKEN = "eyJhbGciOiJSUzUxMiIsInR5cCI6IkpXVCJ9.eyJfaWQiOiJkYTYwM2ZlYTEyNjMyYjFjNDNjZWRiZjYyZTYwYWY0ZCIsImFjY2Vzc1J1bGVzIjpbeyJpZCI6InRyYWRpbmctYWNjb3VudC1tYW5hZ2VtZW50LWFwaSIsIm1ldGhvZHMiOlsidHJhZGluZy1hY2NvdW50LW1hbmFnZW1lbnQtYXBpOnJlc3Q6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6Im1ldGFhcGktcmVzdC1hcGkiLCJtZXRob2RzIjpbIm1ldGFhcGktYXBpOnJlc3Q6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6Im1ldGFhcGktcnBjLWFwaSIsIm1ldGhvZHMiOlsibWV0YWFwaS1hcGk6d3M6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6Im1ldGFhcGktcmVhbC10aW1lLXN0cmVhbWluZy1hcGkiLCJtZXRob2RzIjpbIm1ldGFhcGktYXBpOndzOnB1YmxpYzoqOioiXSwicm9sZXMiOlsicmVhZGVyIiwid3JpdGVyIl0sInJlc291cmNlcyI6WyIqOiRVU0VSX0lEJDoqIl19LHsiaWQiOiJtZXRhc3RhdHMtYXBpIiwibWV0aG9kcyI6WyJtZXRhc3RhdHMtYXBpOnJlc3Q6cHVibGljOio6KiJdLCJyb2xlcyI6WyJyZWFkZXIiLCJ3cml0ZXIiXSwicmVzb3VyY2VzIjpbIio6JFVTRVJfSUQkOioiXX0seyJpZCI6InJpc2stbWFuYWdlbWVudC1hcGkiLCJtZXRob2RzIjpbInJpc2stbWFuYWdlbWVudC1hcGk6cmVzdDpwdWJsaWM6KjoqIl0sInJvbGVzIjpbInJlYWRlciIsIndyaXRlciJdLCJyZXNvdXJjZXMiOlsiKjokVVNFUl9JRCQ6KiJdfSx7ImlkIjoiY29weWZhY3RvcnktYXBpIiwibWV0aG9kcyI6WyJjb3B5ZmFjdG9yeS1hcGk6cmVzdDpwdWJsaWM6KjoqIl0sInJvbGVzIjpbInJlYWRlciIsIndyaXRlciJdLCJyZXNvdXJjZXMiOlsiKjokVVNFUl9JRCQ6KiJdfSx7ImlkIjoibXQtbWFuYWdlci1hcGkiLCJtZXRob2RzIjpbIm10LW1hbmFnZXItYXBpOnJlc3Q6ZGVhbGluZzoqOioiLCJtdC1tYW5hZ2VyLWFwaTpyZXN0OnB1YmxpYzoqOioiXSwicm9sZXMiOlsicmVhZGVyIiwid3JpdGVyIl0sInJlc291cmNlcyI6WyIqOiRVU0VSX0lEJDoqIl19LHsiaWQiOiJiaWxsaW5nLWFwaSIsIm1ldGhvZHMiOlsiYmlsbGluZy1hcGk6cmVzdDpwdWJsaWM6KjoqIl0sInJvbGVzIjpbInJlYWRlciJdLCJyZXNvdXJjZXMiOlsiKjokVVNFUl9JRCQ6KiJdfV0sImlnbm9yZVJhdGVMaW1pdHMiOmZhbHNlLCJ0b2tlbklkIjoiMjAyMTAyMTMiLCJpbXBlcnNvbmF0ZWQiOmZhbHNlLCJyZWFsVXNlcklkIjoiZGE2MDNmZWExMjYzMmIxYzQzY2VkYmY2MmU2MGFmNGQiLCJpYXQiOjE3ODA5ODQyMzgsImV4cCI6MTc4ODc2MDIzOH0.cSdMchl2jUMXiJpGV9c9h1af4Npl3634Ki1SWtKUOb7it4EJCixXcHNI0zwrSlNRZtV1lPlbVsbmIbuiZGwPVpGgJLkRf8vZM28NXdCal3Dr5fgMXy3lBhOVF9II-8vpOpYbhgf6uA3JSJa4EGEen6k1iQ9IvNiicUfQOe4JM-mPotwUpEr-lpQf7E0TvpbaLHVxv-Us4K0IISgCXdUpn6UaBwdC6nTlW9fr_b5YIs1uMqx_wbv1eLLjFNpCktjZZdfBCYnIH4oTNvzq6tAvG-_HBu2P-_PxZlRcZeL5j-Ew5SgEqhzxVLkZ6Mor6VVHvG-nOrwAUTHWVCCKvM8hlL6UCmzsbuDpYXYrPndv4dZwHJgbuDmk6BunwSrktNYMlT0J81cFY8b_dlrvfdGw6P3yQ_ZPp3fcvNHQ_pG_myNfj3IRAAmZUQ4k4I5zi8rhLS5S0zTrekJWSboZH1P2wDntollYn0Su4hDJoW674NgBuQU0Q1ER_w18c_kofKmam-fhuKej0uHZTSvXO2up7Bzkk4zqJK2L4Ej5_C-bnhEC3jmwxCPD-rn4aDRQ9WsPfBgSZYt2fvk1TX78m3mndhjOKO09-5kElgA8xvOsoHRyjZANoG6-3YuLsrVhC-d97spizagQDLKPdVI44YHzoU58l41OsloKysMjfzDD4lo" 
        api = MetaApi(token=API_TOKEN)
        
        print("🔄 डेटाबेसमधून अकाऊंट्सची माहिती गोळा करत आहे...")
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
            print("⏳ डॅशबोर्डवर अजून मास्टर अकाऊंट जोडलेला नाही. कॉपी इंजिन वेटिंगवर आहे.")
            return

        if not followers:
            print("⏳ डॅशबोर्डवर अजून कोणतेही फॉलोवर अकाऊंट नाही. ट्रेडिंग सुरू होणार नाही.")
            return

        print(f"📡 मास्टर अकाऊंट [{master_id}] कनेक्ट करत आहे...")
        master_account = await api.metatrader_account_api.get_account(master_id)
        await master_account.wait_connected()
        
        master_connection = master_account.get_streaming_connection()
        await master_connection.connect()
        await master_connection.wait_synchronized()
        print(f"✅ मास्टर अकाऊंट [{master_id}] यशस्वीरीत्या सिंक्रोनाइझ झाले!")

        # फॉलोवर अकाऊंट्सचे ऑब्जेक्ट्स तयार करणे
        follower_objects = {}
        for f in followers:
            try:
                print(f"📡 फॉलोवर अकाऊंट [{f['id']}] कनेक्ट करत आहे...")
                f_acc = await api.metatrader_account_api.get_account(f['id'])
                await f_acc.wait_connected()
                follower_objects[f['id']] = {"account": f_acc, "multiplier": f['multiplier']}
                print(f"✅ फॉलोवर [{f['id']}] ट्रेडिंगसाठी तयार आहे.")
            except Exception as fe:
                print(f"❌ फॉलोवर [{f['id']}] कनेक्शन एरर: {fe}")

        # मास्टरवरील ऑर्डर्सवर लक्ष ठेवण्यासाठी Listener
        class TradeCopyListener:
            async def on_positions_synchronized(self, instance_index, synchronization_id):
                master_positions = master_connection.terminal_state.positions
                
                if not master_positions:
                    return

                for pos in master_positions:
                    symbol = pos.get('symbol')
                    position_type = pos.get('type') # POSITION_TYPE_BUY / POSITION_TYPE_SELL
                    volume = pos.get('volume', 0)
                    master_pos_id = pos.get('id')
                    
                    # ऑर्डर प्रकार ठरवणे
                    order_type = 'ORDER_TYPE_BUY' if position_type == 'POSITION_TYPE_BUY' else 'ORDER_TYPE_SELL'
                    
                    # प्रत्येक कनेक्टेड फॉलोवरवर ट्रेड टाकणे
                    for f_id, f_data in follower_objects.items():
                        try:
                            f_acc = f_data["account"]
                            mult = f_data["multiplier"]
                            
                            # मल्टिप्लायरनुसार लॉट साइज काढणे
                            target_volume = round(volume * mult, 2)
                            if target_volume < 0.01:
                                target_volume = 0.01

                            # रेंडर लॉग्जमध्ये प्रिंट करणे
                            print(f"🔔 मास्टरवर ट्रेड सापडला! {symbol} | Type: {order_type} | Lots: {volume}")
                            print(f"➡️ फॉलोवर [{f_id}] वर कॉपी करत आहे... Size: {target_volume}")
                            
                            # MetaAPI द्वारे फॉलोवरच्या अकाऊंटवर मार्केट ऑर्डर एक्झिक्युट करणे
                            await f_acc.create_market_order(symbol, order_type, target_volume)
                            print(f"🚀 फॉलोवर [{f_id}] वर ट्रेड यशस्वीरीत्या प्लेस झाला!")
                        except Exception as copy_err:
                            # जर आधीच ट्रेड ओपन असेल तर एरर टाळण्यासाठी ट्रॅक करणे
                            if "RET_CODE_OFF_QUOTES" in str(copy_err) or "TRADE_DISABLED" in str(copy_err):
                                pass
                            print(f"❌ फॉलोवर [{f_id}] कॉपी एरर: {copy_err}")

        master_connection.add_synchronization_listener(TradeCopyListener())
        
        while True:
            await asyncio.sleep(1)

    except asyncio.CancelledError:
        print("🔄 नवीन अकाऊंट जोडल्यामुळे जुने कॉपी इंजिन बंद केले.")
    except Exception as e:
        print(f"❌ कॉपी इंजिन क्रॅश झाले: {e}")
        await asyncio.sleep(10)
        global current_copy_task
        current_copy_task = asyncio.create_task(start_copy_engine())

@app.on_event("startup")
async def startup_event():
    global current_copy_task
    current_copy_task = asyncio.create_task(start_copy_engine())
