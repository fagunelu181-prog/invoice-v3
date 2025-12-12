from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse # 新增這行
import requests
import re
import os # 新增這行

app = FastAPI()

# 允許 CORS (雖然同源部署後其實不太需要了，但保留著方便開發)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- 核心修改：讓後端直接提供前端頁面 ---
@app.get("/")
def read_root():
    # 這裡改成直接回傳 HTML 檔案
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return {"message": "後端已啟動，但在伺服器上找不到 index.html 檔案"}

# -------------------------------------

def deep_search_name(data):
    """
    核心演算法：遞迴搜索 (Recursive Search)
    """
    target_keys = [
        "營業人名稱", "機關名稱", "中文名稱", "商業名稱", 
        "公司名稱", "名稱", "Company_Name", "Commercial_Name"
    ]

    if isinstance(data, dict):
        for key in target_keys:
            if key in data and data[key] and isinstance(data[key], str) and len(data[key]) > 1:
                return data[key]
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                found = deep_search_name(value)
                if found: return found

    elif isinstance(data, list):
        for item in data:
            found = deep_search_name(item)
            if found: return found
            
    return None

def fetch_from_g0v(ubn: str):
    url = f"https://company.g0v.ronny.tw/api/show/{ubn}"
    try:
        # 降低 Timeout 避免卡住太久
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        res_json = response.json()
        if "data" in res_json:
            return deep_search_name(res_json["data"])
        return None
    except Exception as e:
        print(f"❌ [g0v] 錯誤: {e}")
        return None

def fetch_from_mof_crawler(ubn: str):
    url = "https://www.etax.nat.gov.tw/etwmain/etw113w1/result"
    payload = {"ban": ubn}
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://www.etax.nat.gov.tw/etwmain/etw113w1/query",
        "Origin": "https://www.etax.nat.gov.tw"
    }
    try:
        response = requests.post(url, data=payload, headers=headers, timeout=6)
        if response.status_code == 200:
            match = re.search(r'營業人名稱.*?<td.*?>(.*?)</td>', response.text, re.DOTALL)
            if match: return match.group(1).strip()
        return None
    except Exception as e:
        print(f"❌ [財政部] 錯誤: {e}")
        return None

def fetch_from_gcis(ubn: str, type_code: str):
    url = "https://data.gcis.nat.gov.tw/od/data/api/" + type_code
    params = {"$format": "json", "$filter": f"Business_Accounting_NO eq {ubn}", "$skip": 0, "$top": 1}
    try:
        response = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        data = response.json()
        if isinstance(data, list) and len(data) > 0:
            return deep_search_name(data[0])
        return None
    except:
        return None

@app.get("/api/company/{ubn}")
def query_company(ubn: str):
    print(f"\n--- 收到查詢請求: {ubn} ---")
    
    # 策略順序：g0v -> 財政部 -> 官方 API
    if result := fetch_from_g0v(ubn): return {"name": result}
    if result := fetch_from_mof_crawler(ubn): return {"name": result}
    if result := fetch_from_gcis(ubn, "5F64D864-61CB-4D0D-8AD9-492047CC1EA6"): return {"name": result}
    if result := fetch_from_gcis(ubn, "45A17014-F975-4C3D-A614-38742F1C6339"): return {"name": result}

    return {"name": ""}