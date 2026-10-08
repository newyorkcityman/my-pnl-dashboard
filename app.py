import streamlit as st
import ccxt
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import plotly.graph_objects as go

# =====================================================================
# 🌟 [사용자 설정] 나의 투자 원금, 현물 평단가, 과거 수익금 입력 🌟
# =====================================================================

# 1. 올해 처음 투입한 총 원금 (USDT 기준)
# (이 금액이 자동으로 올해 1월 1일의 시작 자산으로 차트에 기록됩니다)
INITIAL_INVESTMENT = 2100.0 

# 2. 보유 중인 현물(Spot) 코인 평단가
SPOT_AVG_PRICES = {
    "RSNDK": 1656.68, 
    "BTC": 65000.0,
}

# 3. 과거 기간별 누적 수익금(PnL) 직접 입력
# (YTD(올해 누적)는 INITIAL_INVESTMENT를 기준으로 시스템이 '자동' 계산하므로 뺐습니다!)
HISTORICAL_PNL = {
    7: -26.12,     # 7일간 누적 수익
    30: 254.26,    # 30일간 누적 수익
    90: 1152.1,    # 90일간 누적 수익 
    180: 1824.32,  # 180일간 누적 수익
}
# =====================================================================

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="Dashboard", layout="wide")

# --- 2. 커스텀 CSS ---
st.markdown("""
    <style>
    .stApp { background-color: #0b0e11; color: #eaeaec; }
    header { visibility: hidden; }
    .est-title { font-size: 24px; font-weight: 600; color: #eaeaec; margin-bottom: 5px; margin-top: 10px; }
    .big-asset { font-size: 42px !important; font-weight: 800; margin-bottom: 0px; line-height: 1.2; }
    .sub-asset { font-size: 16px; color: #848e9c; margin-top: 0px; margin-bottom: 30px; }
    .ytd-title { font-size: 14px; color: #848e9c; margin-bottom: 5px; }
    .pnl-title { font-size: 13px; color: #848e9c; border-bottom: 1px dashed #5e6673; display: inline-block; margin-bottom: 5px; }
    .pnl-val-red { font-size: 20px; font-weight: bold; color: #f6465d; }
    .pnl-val-green { font-size: 20px; font-weight: bold; color: #0ecb81; }
    .pnl-val-neutral { font-size: 20px; font-weight: bold; color: #eaeaec; }
    div.row-widget.stRadio > div { flex-direction: row; align-items: center; }
    [data-testid="stStatusWidget"] { display: none !important; }
    .stApp [data-testid="stAppViewBlockContainer"] { opacity: 1 !important; filter: none !important; transition: none !important; }
    </style>
""", unsafe_allow_html=True)

# --- 3. 데이터베이스 함수 ---
def init_db():
    conn = sqlite3.connect('my_pnl_ledger.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS daily_assets (date TEXT PRIMARY KEY, total_asset REAL)''')
    conn.commit()
    return conn

def save_today_asset(conn, total_asset):
    today_str = datetime.now().strftime('%Y-%m-%d')
    c = conn.cursor()
    c.execute("REPLACE INTO daily_assets (date, total_asset) VALUES (?, ?)", (today_str, total_asset))
    conn.commit()

def format_pnl(val):
    if val > 0: return f"<div class='pnl-val-green'>+{val:,.2f} USD</div>"
    elif val < 0: return f"<div class='pnl-val-red'>{val:,.2f} USD</div>"
    else: return f"<div class='pnl-val-neutral'>{val:,.2f} USD</div>"

# --- 4. API 데이터 캐싱 ---
@st.cache_data(ttl=30, show_spinner=False)
def get_exchange_data(api_key, secret_key, passphrase):
    exchange_spot = ccxt.bitget({'apiKey': api_key, 'secret': secret_key, 'password': passphrase, 'enableRateLimit': True})
    exchange_swap = ccxt.bitget({'apiKey': api_key, 'secret': secret_key, 'password': passphrase, 'enableRateLimit': True, 'options': {'defaultType': 'swap'}})

    spot_balance = exchange_spot.fetch_balance()
    swap_balance = exchange_swap.fetch_balance()
    try: tickers = exchange_spot.fetch_tickers()
    except: tickers = {}
    positions = exchange_swap.fetch_positions()
    
    return spot_balance, swap_balance, tickers, positions

# --- 5. 메인 로직 ---
try:
    api_key = st.secrets["BITGET_API_KEY"]
    secret_key = st.secrets["BITGET_SECRET_KEY"]
    passphrase = st.secrets["BITGET_PASSPHRASE"]
    
    spot_balance, swap_balance, tickers, positions = get_exchange_data(api_key, secret_key, passphrase)

    total_usdt_value = 0
    for coin, amount in spot_balance['total'].items():
        if amount > 0:
            if coin == 'USDT': total_usdt_value += amount
            else:
                ticker_key = f"{coin}/USDT"
                if ticker_key in tickers and 'last' in tickers[ticker_key]:
                    total_usdt_value += amount * tickers[ticker_key]['last']

    for coin, amount in swap_balance['total'].items():
        if amount > 0:
            if coin == 'USDT': total_usdt_value += amount
            else:
                ticker_key = f"{coin}/USDT"
                if ticker_key in tickers and 'last' in tickers[ticker_key]:
                    total_usdt_value += amount * tickers[ticker_key]['last']

    current_total_asset = total_usdt_value
    conn = init_db()
    save_today_asset(conn, current_total_asset)

    df_db = pd.read_sql_query("SELECT date, total_asset FROM daily_assets ORDER BY date ASC", conn)
    virtual_records = []
    today_dt = datetime.now()
    today_date = today_dt.date()
    
    # 💡 1. 7일, 30일, 90일, 180일 과거 데이터 생성
    for days_ago, pnl in HISTORICAL_PNL.items():
        past_date = (today_dt - timedelta(days=days_ago)).strftime('%Y-%m-%d')
        if past_date not in df_db['date'].values:
            virtual_records.append({'date': past_date, 'total_asset': current_total_asset - pnl})
            
    # 💡 2. YTD(올해 1월 1일) 자산을 INITIAL_INVESTMENT를 이용해 자동 기록!
    ytd_date_str = f"{today_date.year}-01-01"
    if ytd_date_str not in df_db['date'].values and INITIAL_INVESTMENT > 0:
        virtual_records.append({'date': ytd_date_str, 'total_asset': INITIAL_INVESTMENT})
            
    if virtual_records:
        df_virtual = pd.DataFrame(virtual_records)
        df = pd.concat([df_virtual, df_db]).sort_values(by='date').reset_index(drop=True)
    else:
        df = df_db.copy()
        
    df['date_obj'] = pd.to_datetime(df['date']).dt.date

    def get_past_asset_from_df(days_ago):
        target_date = today_date - timedelta(days=days_ago)
        past_df = df[df['date_obj'] <= target_date]
        if not past_df.empty:
            closest_date = past_df.iloc[-1]['date_obj']
            if days_ago == 1 and closest_date < target_date:
                return current_total_asset
            return past_df.iloc[-1]['total_asset']
        return current_total_asset

    asset_1d = get_past_asset_from_df(1)
    asset_7d = get_past_asset_from_df(7)
    asset_30d = get_past_asset_from_df(30)
    asset_90d = get_past_asset_from_df(90)
    asset_180d = get_past_asset_from_df(180)

    # --- 6. 상단 화면 ---
    st.markdown("<div class='est-title'>Est. Total Value</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='big-asset'>{current_total_asset:,.2f} USDT</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='sub-asset'>≈ {current_total_asset:,.2f} USD</div>", unsafe_allow_html=True)
    
    ytd_pnl = current_total_asset - INITIAL_INVESTMENT
    ytd_perc = (ytd_pnl / INITIAL_INVESTMENT) * 100 if INITIAL_INVESTMENT > 0 else 0
    ytd_color = "#0ecb81" if ytd_pnl >= 0 else "#f6465d"
    ytd_sign = "+" if ytd_pnl > 0 else ""
    
    st.markdown("<div class='ytd-title'>YTD PnL (올해 누적 수익)</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='font-size:24px; font-weight:bold; color:{ytd_color}; margin-bottom: 30px;'>{ytd_sign}{ytd_pnl:,.2f} USD ({ytd_sign}{ytd_perc:,.2f}%)</div>", unsafe_allow_html=True)
    
    # 요약 패널 이름도 1Y에서 YTD로 수정
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.markdown("<div class='pnl-title'>Today's PnL</div>", unsafe_allow_html=True)
        st.markdown(format_pnl(current_total_asset - asset_1d), unsafe_allow_html=True)
    with col2:
        st.markdown("<div class='pnl-title'>7D PnL</div>", unsafe_allow_html=True)
        st.markdown(format_pnl(current_total_asset - asset_7d), unsafe_allow_html=True)
    with col3:
        st.markdown("<div class='pnl-title'>30D PnL</div>", unsafe_allow_html=True)
        st.markdown(format_pnl(current_total_asset - asset_30d), unsafe_allow_html=True)
    with col4:
        st.markdown("<div class='pnl-title'>90D PnL</div>", unsafe_allow_html=True)
        st.markdown(format_pnl(current_total_asset - asset_90d), unsafe_allow_html=True)
    with col5:
        st.markdown("<div class='pnl-title'>180D PnL</div>", unsafe_allow_html=True)
        st.markdown(format_pnl(current_total_asset - asset_180d), unsafe_allow_html=True)
    with col6:
        st.markdown("<div class='pnl-title'>YTD PnL</div>", unsafe_allow_html=True)
        st.markdown(format_pnl(ytd_pnl), unsafe_allow_html=True)
        
    st.write("")
    st.divider()

    # --- 7. 기간 설정 버튼 및 차트 ---
    col_period, col_date, col_dummy = st.columns([4, 3, 3])
    with col_period:
        # 버튼 이름도 1Y -> YTD 로 변경
        period = st.radio("기간 선택", ["7D", "30D", "90D", "180D", "YTD", "Custom"], horizontal=True, label_visibility="collapsed")
    with col_date:
        if period == "Custom": date_range = st.date_input("날짜 지정", [datetime.now().date() - timedelta(days=7), datetime.now().date()], label_visibility="collapsed")
        else: date_range = None

    if period == "7D": start_date = today_date - timedelta(days=7)
    elif period == "30D": start_date = today_date - timedelta(days=30)
    elif period == "90D": start_date = today_date - timedelta(days=90)
    elif period == "180D": start_date = today_date - timedelta(days=180)
    elif period == "YTD": start_date = datetime(today_date.year, 1, 1).date() # 올해 1월 1일로 시작점 세팅
    elif period == "Custom" and date_range and len(date_range) == 2:
        start_date = date_range[0]
        today_date = date_range[1]
    else: start_date = today_date - timedelta(days=7)
        
    mask = (df['date_obj'] >= start_date) & (df['date_obj'] <= today_date)
    filtered_df = df.loc[mask].copy()

    if not filtered_df.empty:
        period_pnl = filtered_df['total_asset'].iloc[-1] - filtered_df['total_asset'].iloc[0]
        pnl_color = "#0ecb81" if period_pnl >= 0 else "#f6465d"
        pnl_sign = "+" if period_pnl > 0 else ""
        st.markdown(f"<div style='font-size:14px; color:#848e9c; margin-top:20px;'>Total PnL ({period})</div><div style='font-size:20px; font-weight:bold; margin-bottom:10px; color:{pnl_color};'>{pnl_sign}{period_pnl:,.2f} USD</div>", unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["Total PnL", "Daily PnL"])
    
    chart_layout = dict(
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#848e9c'), margin=dict(l=0, r=0, t=10, b=10), 
        xaxis=dict(showgrid=False, zeroline=False, tickformat="%Y-%m-%d", hoverformat="%Y-%m-%d"), 
        yaxis=dict(showgrid=True, gridcolor='#2b3139', zeroline=False, tickprefix="$"),
        legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5)
    )

    with tab1:
        fig_total = go.Figure()
        if not filtered_df.empty: 
            fig_total.add_trace(go.Scatter(x=filtered_df['date'], y=filtered_df['total_asset'], mode='lines', line=dict(color='#00d1c1', width=3), fill='tozeroy', fillcolor='rgba(0, 209, 193, 0.1)', name='Total PnL'))
        fig_total.update_layout(**chart_layout)
        st.plotly_chart(fig_total, use_container_width=True)

    with tab2:
        if not filtered_df.empty:
            filtered_df['Daily_PnL'] = filtered_df['total_asset'].diff().fillna(0)
            colors = ['#0ecb81' if val >= 0 else '#f6465d' for val in filtered_df['Daily_PnL']]
            fig_daily = go.Figure()
            fig_daily.add_trace(go.Bar(x=filtered_df['date'], y=filtered_df['Daily_PnL'], marker_color=colors, name='Daily PnL'))
            fig_daily.update_layout(**chart_layout)
            fig_daily.add_hline(y=0, line_color="#5e6673", line_width=1)
            st.plotly_chart(fig_daily, use_container_width=True)

    # --- 8. 세부 포지션 현황 표 ---
    
    futures_html_parts = []
    futures_header = """
    <div style='font-size: 15px; color: #848e9c; margin-top: 40px; margin-bottom: 10px; font-weight: 600;'>Futures</div>
    <table style='width:100%; border-collapse: collapse; text-align: left; color: #eaeaec; font-size: 14px;'>
    <thead><tr style='border-bottom: 1px solid #2b3139; color: #848e9c; font-size: 13px;'>
    <th style='padding: 10px 5px;'>종목</th><th style='padding: 10px 5px;'>포지션 (레버리지)</th><th style='padding: 10px 5px;'>투입 금액 (Margin)</th><th style='padding: 10px 5px;'>미실현 손익</th><th style='padding: 10px 5px;'>수익률(%)</th>
    </tr></thead><tbody>
    """.replace('\n', '')
    futures_html_parts.append(futures_header)
    
    has_futures = False
    for p in positions:
        if p.get('contracts', 0) > 0:
            has_futures = True
            symbol = p.get('symbol', '').split(':')[0]
            side_str = "LONG" if p.get('side') == 'long' else "SHORT"
            side_color = "#0ecb81" if side_str == "LONG" else "#f6465d"
            lev = int(p.get('leverage', 1))
            margin = float(p.get('initialMargin') or (float(p.get('notional', 0)) / lev))
            pnl = float(p.get('unrealizedPnl', 0))
            pnl_perc = float(p.get('percentage', 0))
            pnl_color = "#0ecb81" if pnl >= 0 else "#f6465d"
            pnl_sign = "+" if pnl > 0 else ""
            
            row_html = f"""
            <tr style='border-bottom: 1px solid #2b3139;'>
            <td style='padding: 15px 5px; font-weight:bold;'>{symbol}</td>
            <td style='padding: 15px 5px; color:{side_color}; font-weight:bold;'>{side_str} <span style='background-color:#2b3139; color:#848e9c; padding:2px 6
