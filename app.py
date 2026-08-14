import streamlit as st
import pandas as pd
import yfinance as yf
import datetime

st.set_page_config(page_title="美股短線飆股量化監控系統", layout="wide")

st.title("🚀 美股短線飆股量化監控系統")
st.markdown("結合 Seeking Alpha 強勢股清單與 Python 量化技術指標的自動化工具。")

# ==========================================
# 1. 讀取 Google Sheet (專為 A 欄純股票代號清單設計)
# ==========================================
# 使用您最新的 Sheet ID: 1oa4Q0XLcQ0TLDGBSh8RuQg4r88FWjq1KPMmI3ydCjjE
SHEET_URL = "https://docs.google.com/spreadsheets/d/1oa4Q0XLcQ0TLDGBSh8RuQg4r88FWjq1KPMmI3ydCjjE/export?format=csv&gid=0"

# 設定快取時間為 60 秒 (1 分鐘)
@st.cache_data(ttl=60)
def load_tickers(url):
    try:
        # 使用 header=None 確保若 A1 就是第一個股票代號（如 NVDA）時不會被誤當成欄位標題吃掉
        df = pd.read_csv(url, header=None)
        
        # 抓取 A 欄 (第 0 欄)，清理空白、轉大寫
        raw_list = df.iloc[:, 0].dropna().astype(str).str.strip().str.upper().tolist()
        
        # 定義常見表頭文字，若是表頭則排除，否則保留
        ignore_keywords = ["TICKER", "TICKERS", "STOCK", "STOCKS", "代號", "股票", "SYMBOL", "SYMBOLS", "NAN"]
        tickers = [t for t in raw_list if t and t not in ignore_keywords and not t.startswith("UNNAMED")]
        
        return tickers
    except Exception as e:
        st.error(f"讀取 Google Sheet 發生錯誤，請確認權限是否設為『知道連結者皆可查看』：\n{e}")
        return []

st.sidebar.header("📋 觀察清單狀態")
with st.sidebar:
    if st.button("🔄 強制刷新 Google Sheet 清單"):
        st.cache_data.clear()
        st.rerun()

    with st.spinner("正在載入 A 欄股票清單..."):
        ticker_list = load_tickers(SHEET_URL)

    if ticker_list:
        st.success(f"成功載入 A 欄共 {len(ticker_list)} 檔股票！")
        with st.expander("查看目前追蹤的股票清單"):
            st.write(ticker_list)
    else:
        st.warning("無法載入股票，請確認表單共享權限設定。目前暫用預設測試清單。")
        ticker_list = ["NVDA", "AMD", "AAPL", "MSFT", "TSLA", "PLTR"]
        st.write(ticker_list)

# ==========================================
# 初始化 Session State (用來保存各分頁的計算結果)
# ==========================================
if 'df_results_tab1' not in st.session_state:
    st.session_state['df_results_tab1'] = pd.DataFrame()
if 'df_results_tab2' not in st.session_state:
    st.session_state['df_results_tab2'] = pd.DataFrame()
if 'df_results_tab3' not in st.session_state:
    st.session_state['df_results_tab3'] = pd.DataFrame()
if 'valid_pullbacks' not in st.session_state:
    st.session_state['valid_pullbacks'] = []

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
    
    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("開始執行日線掃描", key="btn_scan_daily"):
            with st.spinner("下載數據並計算中，請稍候..."):
                valid_pullbacks, df_results = scan_daily_pullback(ticker_list)
                st.session_state['valid_pullbacks'] = valid_pullbacks
                st.session_state['df_results_tab1'] = df_results
                
    with col2:
        if not st.session_state['df_results_tab1'].empty:
            st.success(f"找到 {len(st.session_state['valid_pullbacks'])} 檔符合條件的股票！(已自動帶入盤中監控)")
            
    if not st.session_state['df_results_tab1'].empty:
        st.dataframe(st.session_state['df_results_tab1'], use_container_width=True)
    elif st.session_state.get('btn_scan_daily', False) and st.session_state['df_results_tab1'].empty:
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
        if not st.session_state['valid_pullbacks']:
            st.warning("請先至『第一階段』執行日線掃描，或目前沒有符合條件的股票可供監控。")
        else:
            with st.spinner("即時分析 15 分鐘線 VWAP 中..."):
                df_signals = monitor_intraday_vwap(st.session_state['valid_pullbacks'])
                st.session_state['df_results_tab2'] = df_signals
                
                if not df_signals.empty:
                    st.balloons()

    if not st.session_state['df_results_tab2'].empty:
        st.success("🚨 發現買進訊號！")
        st.dataframe(st.session_state['df_results_tab2'], use_container_width=True)
    elif st.session_state.get('btn_scan_intraday', False) and st.session_state['df_results_tab2'].empty:
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
            
            if len(df) < 3:
                continue
                
            df["EMA10"] = df["Close"].ewm(span=10, adjust=False).mean()
            df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
            df["Vol_SMA20"] = df["Volume"].rolling(window=20).mean()
            
            today = df.iloc[-1]
            yesterday = df.iloc[-2]
            day_before_yesterday = df.iloc[-3]
            
            trend_ok = yesterday["EMA10"] > yesterday["EMA20"]
            near_ema10 = (abs(yesterday["Close"] - yesterday["EMA10"]) / yesterday["EMA10"]) <= 0.015
            near_ema20 = (abs(yesterday["Close"] - yesterday["EMA20"]) / yesterday["EMA20"]) <= 0.015
            touch_ema = (yesterday["Low"] <= yesterday["EMA10"] and yesterday["Close"] >= yesterday["EMA10"]) or \
                        (yesterday["Low"] <= yesterday["EMA20"] and yesterday["Close"] >= yesterday["EMA20"])
            is_pullback = near_ema10 or near_ema20 or touch_ema
            
            vol_ratio = yesterday["Volume"] / yesterday["Vol_SMA20"]
            prev_vol_ratio = day_before_yesterday["Volume"] / day_before_yesterday["Vol_SMA20"]
            volume_contracted = (vol_ratio <= 0.6) or (prev_vol_ratio <= 0.6)
            
            if trend_ok and is_pullback and volume_contracted:
                buy_price = yesterday["Close"]
                today_high = today["High"]
                today_close = today["Close"]
                
                max_profit_pct = ((today_high - buy_price) / buy_price) * 100
                close_profit_pct = ((today_close - buy_price) / buy_price) * 100
                
                status = "🟢 成功發動" if max_profit_pct >= 1.5 else "🟡 橫盤震盪"
                if close_profit_pct < -2.0:
                    status = "🔴 跌破停損"
                
                max_profit_dollar = (max_profit_pct / 100) * 1000
                close_profit_dollar = (close_profit_pct / 100) * 1000
                
                results.append({
                    "股票": ticker,
                    "狀態": status,
                    "昨日收盤 (進場參考)": round(buy_price, 2),
                    "今日最高價": round(today_high, 2),
                    "今日收盤價": round(today_close, 2),
                    "最大潛在獲利(%)": round(max_profit_pct, 2),
                    "收盤帳面損益(%)": round(close_profit_pct, 2),
                    "最大潛在金額($)": round(max_profit_dollar, 2),
                    "收盤帳面金額($)": round(close_profit_dollar, 2)
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
    st.info("💡 說明：此功能會檢查昨日符合『拉回且量縮』的股票，並與今日的【最高價】與【最新收盤價】進行對比。")
    
    if st.button("執行昨日訊號驗證", key="btn_verify_yesterday"):
        with st.spinner("正在回測計算歷史數據..."):
            df_verification = verify_yesterday_signals(ticker_list)
            st.session_state['df_results_tab3'] = df_verification

    if not st.session_state['df_results_tab3'].empty:
        df_show = st.session_state['df_results_tab3']
        st.success(f"昨日共有 {len(df_show)} 檔股票觸發拉回訊號，以下為今日表現：")
        
        df_styled = df_show.copy()
        df_styled['最大潛在獲利(%)'] = df_styled['最大潛在獲利(%)'].astype(str) + "%"
        df_styled['收盤帳面損益(%)'] = df_styled['收盤帳面損益(%)'].astype(str) + "%"
        df_styled['最大潛在金額($)'] = "$" + df_styled['最大潛在金額($)'].astype(str)
        df_styled['收盤帳面金額($)'] = "$" + df_styled['收盤帳面金額($)'].astype(str)
        
        st.dataframe(df_styled, use_container_width=True)
        
        avg_max_profit_pct = df_show['最大潛在獲利(%)'].mean()
        avg_close_profit_pct = df_show['收盤帳面損益(%)'].mean()
        
        total_max_dollar = df_show['最大潛在金額($)'].sum()
        total_close_dollar = df_show['收盤帳面金額($)'].sum()
        total_capital_invested = len(df_show) * 1000
        
        st.markdown("### 📊 總體驗證績效統計")
        
        st.markdown("#### 1. 投資組合平均報酬率 (平均分配資金之真實 %)")
        col1, col2 = st.columns(2)
        with col1:
            st.metric(label="投資組合：最大潛在【平均】獲利 (%)", value=f"{avg_max_profit_pct:.2f}%")
        with col2:
            st.metric(label="投資組合：收盤帳面【平均】損益 (%)", value=f"{avg_close_profit_pct:.2f}%")
            
        st.markdown(f"#### 2. 實質金額模擬 (假設每檔投入 $1,000 美金，總投入 $\$1,000 \times {len(df_show)} = \$ {total_capital_invested:,}$ 美金)")
        col3, col4 = st.columns(2)
        with col3:
            st.metric(label="假設每筆買 $1,000：最大潛在【累積總獲利】 ($)", value=f"${total_max_dollar:,.2f}")
        with col4:
            st.metric(label="假設每筆買 $1,000：收盤帳面【累積總損益】 ($)", value=f"${total_close_dollar:,.2f}")
            
    elif st.session_state.get('btn_verify_yesterday', False) and st.session_state['df_results_tab3'].empty:
        st.warning("昨日清單中【沒有】任何股票觸發拉回買進條件，因此今日無回測數據。")
