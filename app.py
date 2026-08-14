import streamlit as st
import pandas as pd
import yfinance as yf
import datetime

st.set_page_config(page_title="美股短線飆股量化監控系統", layout="wide")

st.title("🚀 美股短線飆股量化監控系統")
st.markdown("結合 Seeking Alpha 強勢股清單與 Python 量化技術指標的自動化工具。")

# ==========================================
# 1. 讀取 Google Sheet (固定 CSV 網址)
# ==========================================
# 將使用者提供的 CSV 網址寫死在程式中
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ_3z3yvdog2hJlJTw_dJ07j9VIGnZsV4tOd3oeGWVLQ6Hv3HCAbAIWcnL2Nr7dvzmFb-O78ZKO195a/pub?output=csv"

@st.cache_data(ttl=600) # 快取 10 分鐘，避免重複讀取
def load_tickers(url):
    try:
        df = pd.read_csv(url)
        # 假設第一欄是股票代號，清理空白與空值
        tickers = df.iloc[:, 0].dropna().astype(str).str.strip().str.upper().tolist()
        return [t for t in tickers if t] # 過濾空字串
    except Exception as e:
        st.error(f"讀取 CSV 發生錯誤：\n{e}")
        return []

st.header("1. 觀察清單")
with st.spinner("正在載入股票清單..."):
    ticker_list = load_tickers(SHEET_URL)

if ticker_list:
    st.success(f"成功從 Google Sheet 載入 {len(ticker_list)} 檔股票！")
    with st.expander("查看目前追蹤的股票清單"):
        st.write(ticker_list)
else:
    st.warning("無法從指定的網址載入股票清單，請確認 Google Sheet 設定是否正確。")
    # 如果載入失敗，提供預設清單以防程式崩潰
    ticker_list = ["NVDA", "AMD", "AAPL", "MSFT", "TSLA", "PLTR"]
    st.info("目前使用系統預設測試清單。")

# ==========================================
# 2. 日線拉回與量縮掃描
# ==========================================
def scan_daily_pullback(tickers):
    watch_list = []
    results_data = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, ticker in enumerate(tickers):
        status_text.text(f"正在掃描日線數據: {ticker} ({i+1}/{len(tickers)})")
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="60d", interval="1d")
            
            if len(df) < 20:
                continue
                
            df["EMA10"] = df["Close"].ewm(span=10, adjust=False).mean()
            df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
            df["Vol_SMA20"] = df["Volume"].rolling(window=20).mean()
            
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 條件 1：趨勢偏多
            trend_ok = latest["EMA10"] > latest["EMA20"]
            
            # 條件 2：價格觸及或接近 10/20 EMA (極限距離 1.5% 以內)
            near_ema10 = (abs(latest["Close"] - latest["EMA10"]) / latest["EMA10"]) <= 0.015
            near_ema20 = (abs(latest["Close"] - latest["EMA20"]) / latest["EMA20"]) <= 0.015
            touch_ema = (latest["Low"] <= latest["EMA10"] and latest["Close"] >= latest["EMA10"]) or \
                        (latest["Low"] <= latest["EMA20"] and latest["Close"] >= latest["EMA20"])
            
            is_pullback = near_ema10 or near_ema20 or touch_ema
            
            # 條件 3：拉回量縮 (當日或前一日成交量 <= 20日均量的 60%)
            vol_ratio = latest["Volume"] / latest["Vol_SMA20"]
            prev_vol_ratio = prev["Volume"] / prev["Vol_SMA20"]
            volume_contracted = (vol_ratio <= 0.6) or (prev_vol_ratio <= 0.6)
            
            if trend_ok and is_pullback and volume_contracted:
                watch_list.append(ticker)
                results_data.append({
                    "股票": ticker,
                    "收盤價": round(latest['Close'], 2),
                    "10日線": round(latest['EMA10'], 2),
                    "20日線": round(latest['EMA20'], 2),
                    "量能比例": f"{vol_ratio * 100:.1f}%"
                })
        except Exception:
            pass # 忽略錯誤
        
        progress_bar.progress((i + 1) / len(tickers))
        
    status_text.text("日線掃描完成！")
    return watch_list, pd.DataFrame(results_data)

st.header("2. 第一階段：日線拉回量縮掃描 (建議開盤前執行)")
if st.button("開始執行日線掃描"):
    with st.spinner("下載數據並計算中，請稍候..."):
        valid_pullbacks, df_results = scan_daily_pullback(ticker_list)
        st.session_state['valid_pullbacks'] = valid_pullbacks # 存入 session 供盤中監控使用
        
        if not df_results.empty:
            st.success(f"找到 {len(valid_pullbacks)} 檔符合『均線多頭、回測均線、量縮』的股票！")
            st.dataframe(df_results, use_container_width=True)
        else:
            st.info("今日無符合拉回條件的標的，建議保持現金觀望。")

# ==========================================
# 3. 盤中 15 分鐘 VWAP 突破監控
# ==========================================
def monitor_intraday_vwap(tickers):
    signals_data = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, ticker in enumerate(tickers):
        status_text.text(f"正在監控盤中數據: {ticker} ({i+1}/{len(tickers)})")
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="5d", interval="15m")
            
            if df.empty:
                continue
                
            df["Date"] = df.index.date
            df["Typical_Price"] = (df["High"] + df["Low"] + df["Close"]) / 3
            df["VP"] = df["Typical_Price"] * df["Volume"]
            df["Cum_VP"] = df.groupby("Date")["VP"].cumsum()
            df["Cum_Vol"] = df.groupby("Date")["Volume"].cumsum()
            df["VWAP"] = df["Cum_VP"] / df["Cum_Vol"]
            
            df["Vol_SMA20"] = df["Volume"].rolling(window=20).mean()
            
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            crossed_vwap = (prev["Close"] <= prev["VWAP"]) and (latest["Close"] > latest["VWAP"])
            vol_spike = latest["Volume"] >= 1.5 * latest["Vol_SMA20"]
            
            if crossed_vwap and vol_spike:
                signals_data.append({
                    "股票": ticker,
                    "狀態": "🚀 觸發買進",
                    "現價": round(latest['Close'], 2),
                    "VWAP": round(latest['VWAP'], 2),
                    "相對量增": f"{latest['Volume'] / latest['Vol_SMA20']:.1f} 倍"
                })
        except Exception:
            pass
            
        progress_bar.progress((i + 1) / len(tickers))
        
    status_text.text("盤中監控完成！")
    return pd.DataFrame(signals_data)

st.header("3. 第二階段：盤中 VWAP 監控 (美股開盤期間執行)")
st.markdown("將第一階段找到的『拉回名單』進行盤中監控，尋找突破 VWAP 且帶量的發動點。")

if st.button("開始執行盤中監控"):
    if 'valid_pullbacks' not in st.session_state or not st.session_state['valid_pullbacks']:
        st.warning("請先執行上方的『日線掃描』，或是目前沒有符合拉回條件的股票可供監控。")
    else:
        with st.spinner("即時分析 15 分鐘線 VWAP 中..."):
            df_signals = monitor_intraday_vwap(st.session_state['valid_pullbacks'])
            
            if not df_signals.empty:
                st.balloons()
                st.success("🚨 發現買進訊號！")
                st.dataframe(df_signals, use_container_width=True)
            else:
                st.info("目前觀察清單中，尚未出現突破 VWAP 的訊號。請稍後再試。")
