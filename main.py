from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
import re
import json

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "發票小幫手 API (V8 深層遞迴搜索版) 已啟動"}

def deep_search_name(data):
    """
    核心演算法：遞迴搜索 (Recursive Search)
    不管資料藏在 JSON 的第幾層，挖地三尺也要把它找出來
    """
    # 定義我們想找的 Key (優先順序)
    target_keys = [
        "營業人名稱", # 財政部最愛用
        "機關名稱",   # 基金會
        "中文名稱", 
        "商業名稱",   # 行號
        "公司名稱", 
        "名稱",
        "Company_Name", 
        "Commercial_Name"
    ]

    # 1. 遞歸終止條件：如果不是字典或列表，就停
    if isinstance(data, dict):
        # A. 先檢查當前這一層有沒有我們要的 Key
        for key in target_keys:
            if key in data and data[key]:
                # 排除過短的無效名稱 (有些 API 會回傳 "N/A" 或空字串)
                if isinstance(data[key], str) and len(data[key]) > 1:
                    return data[key]
        
        # B. 如果這一層沒有，深入下一層 (遞迴)
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                found = deep_search_name(value)
                if found: return found

    elif isinstance(data, list):
        # C. 如果是列表，檢查每一個元素
        for item in data:
            found = deep_search_name(item)
            if found: return found
            
    return None

def fetch_from_g0v(ubn: str):
    """
    策略 A: g0v (使用深層搜索)
    """
    url = f"https://company.g0v.ronny.tw/api/show/{ubn}"
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        print(f"🔍 [g0v] 正在查詢: {ubn}")
        response = requests.get(url, headers=headers, timeout=8)
        res_json = response.json()
        
        # g0v 的資料通常包在 'data' 裡面
        if "data" in res_json:
            # 啟動鑽地機
            name = deep_search_name(res_json["data"])
            if name:
                print(f"✅ [g0v] 深層搜索成功: {name}")
                return name
            else:
                # 這次真的把整包資料印出來看，如果還失敗，我們需要看這個 Log
                print(f"⚠️ [g0v] 遞迴搜尋失敗。原始資料結構: {str(res_json)[:200]}...")
        return None
    except Exception as e:
        print(f"❌ [g0v] 錯誤: {e}")
        return None

def fetch_from_mof_crawler(ubn: str):
    """
    策略 S: 財政部爬蟲 (修復 403 Forbidden)
    關鍵修正：加入 Referer 和 Origin 表頭
    """
    url = "https://www.etax.nat.gov.tw/etwmain/etw113w1/result"
    payload = {"ban": ubn}
    
    # ★ 關鍵修正：完整的瀏覽器偽裝，包含 Referer
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://www.etax.nat.gov.tw/etwmain/etw113w1/query", # 這是財政部的查詢頁面，沒這個會被擋
        "Origin": "https://www.etax.nat.gov.tw",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
    }
    
    try:
        print(f"🕷️ [財政部] 嘗試繞過防火牆爬取: {ubn} ...")
        response = requests.post(url, data=payload, headers=headers, timeout=10)
        
        if response.status_code == 200:
            html = response.text
            match = re.search(r'營業人名稱.*?<td.*?>(.*?)</td>', html, re.DOTALL)
            if match:
                name = match.group(1).strip()
                print(f"✅ [財政部] 爬取成功: {name}")
                return name
        else:
            print(f"❌ [財政部] 仍被攔截: Status {response.status_code}")
        return None
    except Exception as e:
        print(f"❌ [財政部] 爬蟲錯誤: {e}")
        return None

def fetch_from_gcis(ubn: str, type_code: str):
    """
    策略 B: 官方 API (備用)
    """
    url = "https://data.gcis.nat.gov.tw/od/data/api/" + type_code
    params = {"$format": "json", "$filter": f"Business_Accounting_NO eq {ubn}", "$skip": 0, "$top": 1}
    try:
        response = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        data = response.json()
        if isinstance(data, list) and len(data) > 0:
            name = deep_search_name(data[0]) # 這裡也用深層搜索
            if name:
                print(f"✅ [官方API] 查詢成功: {name}")
                return name
        return None
    except:
        return None

@app.get("/api/company/{ubn}")
def query_company(ubn: str):
    print(f"\n--- 收到查詢請求: {ubn} ---")

    # 1. 第一優先：g0v (速度快 + 遞迴搜索)
    # 只要 g0v 有資料，這次的遞迴邏輯一定抓得到
    result = fetch_from_g0v(ubn)
    if result: return {"name": result}

    # 2. 第二優先：財政部爬蟲 (已加強偽裝)
    result = fetch_from_mof_crawler(ubn)
    if result: return {"name": result}

    # 3. 最後嘗試：官方 API
    if result := fetch_from_gcis(ubn, "5F64D864-61CB-4D0D-8AD9-492047CC1EA6"): return {"name": result} # 公司
    if result := fetch_from_gcis(ubn, "45A17014-F975-4C3D-A614-38742F1C6339"): return {"name": result} # 行號

    print("🚫 全軍覆沒")
    return {"name": ""}