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
SHEET_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ_3z3yvdog2hJlJTw_dJ07j9VIGnZsV4tOd3oeGWVLQ6Hv3HCAbAIWcnL2Nr7dvzmFb-O78ZKO195a/pub?output=csv"

@st.cache_data(ttl=600)
def load_tickers(url):
    try:
        df = pd.read_csv(url)
        tickers = df.iloc[:, 0].dropna().astype(str).str.strip().str.upper().tolist()
        return [t for t in tickers if t]
    except Exception as e:
        st.error(f"讀取 CSV 發生錯誤：\n{e}")
        return []

st.sidebar.header("📋 觀察清單狀態")
with st.sidebar:
    with st.spinner("正在載入股票清單..."):
        ticker_list = load_tickers(SHEET_URL)

    if ticker_list:
        st.success(f"成功載入 {len(ticker_list)} 檔股票！")
        with st.expander("查看目前追蹤的股票清單"):
            st.write(ticker_list)
    else:
        st.warning("無法載入股票，使用預設清單。")
        ticker_list = ["NVDA", "AMD", "AAPL", "MSFT", "TSLA", "PLTR"]
        st.write(ticker_list)

# ==========================================
# 建立分頁 (Tabs)
# ==========================================
tab1, tab2, tab3 = st.tabs(["📊 第一階段：日線掃描 (盤前)", "🚀 第二階段：盤中監控 (盤中)", "✅ 策略驗證：昨日訊號追蹤"])

# ==========================================
# Tab 1: 日線拉回與量縮掃描
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
            
            trend_ok = latest["EMA10"] > latest["EMA20"]
            
            near_ema10 = (abs(latest["Close"] - latest["EMA10"]) / latest["EMA10"]) <= 0.015
            near_ema20 = (abs(latest["Close"] - latest["EMA20"]) / latest["EMA20"]) <= 0.015
            touch_ema = (latest["Low"] <= latest["EMA10"] and latest["Close"] >= latest["EMA10"]) or \
                        (latest["Low"] <= latest["EMA20"] and latest["Close"] >= latest["EMA20"])
            
            is_pullback = near_ema10 or near_ema20 or touch_ema
            
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
            pass
        
        progress_bar.progress((i + 1) / len(tickers))
        
    status_text.empty()
    progress_bar.empty()
    return watch_list, pd.DataFrame(results_data)

with tab1:
    st.header("第一階段：日線拉回量縮掃描")
    st.markdown("建議於**每日美股開盤前**執行，找出『均線多頭、回測 10/20 日均線、且成交量大幅萎縮』的潛在飆股。")
    if st.button("開始執行日線掃描", key="btn_scan_daily"):
        with st.spinner("下載數據並計算中，請稍候..."):
            valid_pullbacks, df_results = scan_daily_pullback(ticker_list)
            st.session_state['valid_pullbacks'] = valid_pullbacks
            
            if not df_results.empty:
                st.success(f"找到 {len(valid_pullbacks)} 檔符合條件的股票！(已自動帶入盤中監控)")
                st.dataframe(df_results, use_container_width=True)
            else:
                st.info("今日無符合拉回條件的標的，建議保持現金觀望。")

# ==========================================
# Tab 2: 盤中 15 分鐘 VWAP 突破監控
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
                    "相對量增": f"{latest['Volume'] / latest['Vol_SMA20']:.1f} 倍",
                    "時間": latest.name.strftime("%H:%M:%S")
                })
        except Exception:
            pass
            
        progress_bar.progress((i + 1) / len(tickers))
        
    status_text.empty()
    progress_bar.empty()
    return pd.DataFrame(signals_data)

with tab2:
    st.header("第二階段：盤中 VWAP 監控")
    st.markdown("針對第一階段選出的名單，於**美股開盤期間**監控是否出現『帶量突破 VWAP』的攻擊訊號。")
    if st.button("開始執行盤中監控", key="btn_scan_intraday"):
        if 'valid_pullbacks' not in st.session_state or not st.session_state['valid_pullbacks']:
            st.warning("請先至『第一階段』執行日線掃描，或目前沒有符合條件的股票可供監控。")
        else:
            with st.spinner("即時分析 15 分鐘線 VWAP 中..."):
                df_signals = monitor_intraday_vwap(st.session_state['valid_pullbacks'])
                
                if not df_signals.empty:
                    st.balloons()
                    st.success("🚨 發現買進訊號！")
                    st.dataframe(df_signals, use_container_width=True)
                else:
                    st.info("目前觀察清單中，尚未出現突破 VWAP 的訊號。請稍後再試。")

# ==========================================
# Tab 3: 策略驗證 (昨日訊號與今日表現)
# ==========================================
def verify_yesterday_signals(tickers):
    results = []
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, ticker in enumerate(tickers):
        status_text.text(f"正在回測昨日訊號: {ticker} ({i+1}/{len(tickers)})")
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period="60d", interval="1d")
            
            if len(df) < 3: # 至少需要前天、昨天、今天
                continue
                
            df["EMA10"] = df["Close"].ewm(span=10, adjust=False).mean()
            df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
            df["Vol_SMA20"] = df["Volume"].rolling(window=20).mean()
            
            today = df.iloc[-1]
            yesterday = df.iloc[-2]
            day_before_yesterday = df.iloc[-3]
            
            # --- 判斷『昨日』是否符合拉回量縮買進條件 ---
            trend_ok = yesterday["EMA10"] > yesterday["EMA20"]
            near_ema10 = (abs(yesterday["Close"] - yesterday["EMA10"]) / yesterday["EMA10"]) <= 0.015
            near_ema20 = (abs(yesterday["Close"] - yesterday["EMA20"]) / yesterday["EMA20"]) <= 0.015
            touch_ema = (yesterday["Low"] <= yesterday["EMA10"] and yesterday["Close"] >= yesterday["EMA10"]) or \
                        (yesterday["Low"] <= yesterday["EMA20"] and yesterday["Close"] >= yesterday["EMA20"])
            is_pullback = near_ema10 or near_ema20 or touch_ema
            
            vol_ratio = yesterday["Volume"] / yesterday["Vol_SMA20"]
            prev_vol_ratio = day_before_yesterday["Volume"] / day_before_yesterday["Vol_SMA20"]
            volume_contracted = (vol_ratio <= 0.6) or (prev_vol_ratio <= 0.6)
            
            # 如果昨日觸發了訊號，則檢視今日的績效
            if trend_ok and is_pullback and volume_contracted:
                buy_price = yesterday["Close"]
                today_high = today["High"]
                today_close = today["Close"]
                
                # 計算損益 (%)
                max_profit_pct = ((today_high - buy_price) / buy_price) * 100
                close_profit_pct = ((today_close - buy_price) / buy_price) * 100
                
                # 判定表現 (若盤中最高有拉升超過 1.5% 視為發動成功)
                status = "🟢 成功發動" if max_profit_pct >= 1.5 else "🟡 橫盤震盪"
                if close_profit_pct < -2.0:
                    status = "🔴 跌破停損"
                
                results.append({
                    "股票": ticker,
                    "狀態": status,
                    "昨日收盤 (進場參考)": round(buy_price, 2),
                    "今日最高價": round(today_high, 2),
                    "今日收盤價": round(today_close, 2),
                    "最大潛在獲利": f"{max_profit_pct:.2f}%",
                    "收盤帳面損益": f"{close_profit_pct:.2f}%"
                })
        except Exception:
            pass
            
        progress_bar.progress((i + 1) / len(tickers))
        
    status_text.empty()
    progress_bar.empty()
    return pd.DataFrame(results)

with tab3:
    st.header("策略驗證：昨日訊號今日表現")
    st.markdown("自動回測清單中的股票：**『如果我昨天在收盤前因為拉回條件買進，今天會賺還是賠？』**")
    st.info("💡 說明：此功能會檢查昨日符合『拉回且量縮』的股票，並與今日的【最高價】與【最新收盤價】進行對比，讓您驗證策略勝率。")
    
    if st.button("執行昨日訊號驗證", key="btn_verify_yesterday"):
        with st.spinner("正在回測計算歷史數據..."):
            df_verification = verify_yesterday_signals(ticker_list)
            
            if not df_verification.empty:
                st.success(f"昨日共有 {len(df_verification)} 檔股票觸發拉回訊號，以下為今日表現：")
                st.dataframe(df_verification, use_container_width=True)
            else:
                st.warning("昨日清單中【沒有】任何股票觸發拉回買進條件，因此今日無回測數據。")
