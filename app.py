import streamlit as st
import ccxt
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import plotly.graph_objects as go

# --- 1. 페이지 설정 ---
st.set_page_config(page_title="Dashboard", layout="wide")

# --- 2. 커스텀 CSS (다크 테마) ---
st.markdown("""
    <style>
    .stApp { background-color: #0b0e11; color: #eaeaec; }
    header { visibility: hidden; }
    .big-asset { font-size: 42px !important; font-weight: 800; margin-bottom: 0px; line-height: 1.2; }
    .sub-asset { font-size: 16px; color: #848e9c; margin-top: 0px; margin-bottom: 30px; }
    .pnl-title { font-size: 13px; color: #848e9c; border-bottom: 1px dashed #5e6673; display: inline-block; margin-bottom: 5px; }
    .pnl-val-red { font-size: 20px; font-weight: bold; color: #f6465d; }
    .pnl-val-green { font-size: 20px; font-weight: bold; color: #0ecb81; }
    .pnl-val-neutral { font-size: 20px; font-weight: bold; color: #eaeaec; }
    /* 라디오 버튼(기간 선택) 스타일 조정 */
    div.row-widget.stRadio > div { flex-direction: row; align-items: center; }
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

def get_past_asset(conn, days_ago):
    target_date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d')
    c = conn.cursor()
    c.execute("SELECT total_asset FROM daily_assets WHERE date <= ? ORDER BY date DESC LIMIT 1", (target_date,))
    result = c.fetchone()
    return result[0] if result else None

def format_pnl(val):
    if val > 0: return f"<div class='pnl-val-green'>+{val:,.2f} USD</div>"
    elif val < 0: return f"<div class='pnl-val-red'>{val:,.2f} USD</div>"
    else: return f"<div class='pnl-val-neutral'>{val:,.2f} USD</div>"

# --- 4. 메인 로직 ---
try:
    api_key = st.secrets["BITGET_API_KEY"]
    secret_key = st.secrets["BITGET_SECRET_KEY"]
    passphrase = st.secrets["BITGET_PASSPHRASE"]
    
    # 거래소 연결
    exchange_spot = ccxt.bitget({'apiKey': api_key, 'secret': secret_key, 'password': passphrase, 'enableRateLimit': True})
    exchange_swap = ccxt.bitget({'apiKey': api_key, 'secret': secret_key, 'password': passphrase, 'enableRateLimit': True, 'options': {'defaultType': 'swap'}})

    # 잔고 및 현재 가격(Ticker) 가져오기
    spot_balance = exchange_spot.fetch_balance()
    swap_balance = exchange_swap.fetch_balance()
    
    try:
        tickers = exchange_spot.fetch_tickers()
    except:
        tickers = {}

    # 현물 및 선물 모든 코인을 실시간 USDT 가치로 환산하여 총 자산 구하기
    total_usdt_value = 0
    
    # 현물(Spot) 환산
    for coin, amount in spot_balance['total'].items():
        if amount > 0:
            if coin == 'USDT':
                total_usdt_value += amount
            else:
                ticker_key = f"{coin}/USDT"
                if ticker_key in tickers and 'last' in tickers[ticker_key]:
                    total_usdt_value += amount * tickers[ticker_key]['last']

    # 선물(Futures) 환산
    for coin, amount in swap_balance['total'].items():
        if amount > 0:
            if coin == 'USDT':
                total_usdt_value += amount
            else:
                ticker_key = f"{coin}/USDT"
                if ticker_key in tickers and 'last' in tickers[ticker_key]:
                    total_usdt_value += amount * tickers[ticker_key]['last']

    current_total_asset = total_usdt_value

    # DB 기록 및 PNL 계산
    conn = init_db()
    save_today_asset(conn, current_total_asset)

    asset_1d = get_past_asset(conn, 1) or current_total_asset
    asset_7d = get_past_asset(conn, 7) or current_total_asset
    asset_30d = get_past_asset(conn, 30) or current_total_asset

    # --- 5. 상단 화면 (자산 및 요약) ---
    st.markdown(f"<div class='big-asset'>{current_total_asset:,.2f} USDT</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='sub-asset'>≈ {current_total_asset:,.2f} USD</div>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("<div class='pnl-title'>Today's PnL</div>", unsafe_allow_html=True)
        st.markdown(format_pnl(current_total_asset - asset_1d), unsafe_allow_html=True)
    with col2:
        st.markdown("<div class='pnl-title'>7D PnL</div>", unsafe_allow_html=True)
        st.markdown(format_pnl(current_total_asset - asset_7d), unsafe_allow_html=True)
    with col3:
        st.markdown("<div class='pnl-title'>30D PnL</div>", unsafe_allow_html=True)
        st.markdown(format_pnl(current_total_asset - asset_30d), unsafe_allow_html=True)
        
    st.write("")
    st.divider()

    # --- 6. 기간 설정 버튼 및 차트 (사진과 동일한 UI) ---
    # 버튼 그룹과 날짜 선택기 배치
    col_period, col_date, col_dummy = st.columns([4, 3, 3])
    with col_period:
        period = st.radio("기간 선택", ["7D", "30D", "90D", "180D", "Custom"], horizontal=True, label_visibility="collapsed")
    
    with col_date:
        if period == "Custom":
            date_range = st.date_input("날짜 지정", [datetime.now().date() - timedelta(days=7), datetime.now().date()], label_visibility="collapsed")
        else:
            date_range = None

    # 데이터베이스에서 장부 불러오기
    df = pd.read_sql_query("SELECT date, total_asset FROM daily_assets ORDER BY date ASC", conn)
    df['date_obj'] = pd.to_datetime(df['date']).dt.date
    today = datetime.now().date()

    # 선택된 기간에 맞게 데이터 자르기
    if period == "7D":
        start_date = today - timedelta(days=7)
    elif period == "30D":
        start_date = today - timedelta(days=30)
    elif period == "90D":
        start_date = today - timedelta(days=90)
    elif period == "180D":
        start_date = today - timedelta(days=180)
    elif period == "Custom" and date_range and len(date_range) == 2:
        start_date = date_range[0]
        today = date_range[1] # 끝나는 날짜
    else:
        start_date = today - timedelta(days=7)
        
    mask = (df['date_obj'] >= start_date) & (df['date_obj'] <= today)
    filtered_df = df.loc[mask].copy()

    # 차트 상단에 선택된 기간의 Total PnL 표시
    if not filtered_df.empty:
        period_pnl = filtered_df['total_asset'].iloc[-1] - filtered_df['total_asset'].iloc[0]
        pnl_color = "#0ecb81" if period_pnl >= 0 else "#f6465d"
        pnl_sign = "+" if period_pnl > 0 else ""
        st.markdown(f"<div style='font-size:14px; color:#848e9c; margin-top:20px;'>Total PnL ({period})</div><div style='font-size:20px; font-weight:bold; margin-bottom:10px; color:{pnl_color};'>{pnl_sign}{period_pnl:,.2f} USD</div>", unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["Total PnL", "Daily PnL"])
    chart_layout = dict(plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)', font=dict(color='#848e9c'), margin=dict(l=0, r=0, t=10, b=0), xaxis=dict(showgrid=False, zeroline=False), yaxis=dict(showgrid=True, gridcolor='#2b3139', zeroline=False, tickprefix="$"))

    with tab1:
        fig_total = go.Figure()
        if not filtered_df.empty:
            fig_total.add_trace(go.Scatter(x=filtered_df['date'], y=filtered_df['total_asset'], mode='lines', line=dict(color='#00d1c1', width=3), fill='tozeroy', fillcolor='rgba(0, 209, 193, 0.1)'))
        fig_total.update_layout(**chart_layout)
        st.plotly_chart(fig_total, use_container_width=True)

    with tab2:
        if not filtered_df.empty:
            filtered_df['Daily_PnL'] = filtered_df['total_asset'].diff().fillna(0)
            colors = ['#0ecb81' if val >= 0 else '#f6465d' for val in filtered_df['Daily_PnL']]
            fig_daily = go.Figure()
            fig_daily.add_trace(go.Bar(x=filtered_df['date'], y=filtered_df['Daily_PnL'], marker_color=colors))
            fig_daily.update_layout(**chart_layout)
            fig_daily.add_hline(y=0, line_color="#5e6673", line_width=1)
            st.plotly_chart(fig_daily, use_container_width=True)

    # --- 7. 세부 포지션 현황 표 (오류 방지를 위해 한 줄의 HTML 문자열로 결합) ---
    st.markdown("<h3 style='color: #eaeaec; margin-top: 50px; margin-bottom: 15px; font-size: 20px;'>📋 현재 포지션 및 자산 현황</h3>", unsafe_allow_html=True)
    
    # 띄어쓰기(들여쓰기)로 인한 글 상자(코드 블록) 인식 오류를 막기 위해 HTML을 빈틈없이 이어붙입니다.
    html_table = "<table style='width:100%; border-collapse: collapse; text-align: left; color: #eaeaec; font-size: 14px;'>"
    html_table += "<thead><tr style='border-bottom: 1px solid #2b3139; color: #848e9c; font-
