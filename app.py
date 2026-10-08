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
    
    exchange_spot = ccxt.bitget({'apiKey': api_key, 'secret': secret_key, 'password': passphrase, 'enableRateLimit': True})
    exchange_swap = ccxt.bitget({'apiKey': api_key, 'secret': secret_key, 'password': passphrase, 'enableRateLimit': True, 'options': {'defaultType': 'swap'}})

    spot_balance = exchange_spot.fetch_balance()
    swap_balance = exchange_swap.fetch_balance()
    
    try:
        tickers = exchange_spot.fetch_tickers()
    except:
        tickers = {}

    total_usdt_value = 0
    
    for coin, amount in spot_balance['total'].items():
        if amount > 0:
            if coin == 'USDT':
                total_usdt_value += amount
            else:
                ticker_key = f"{coin}/USDT"
                if ticker_key in tickers and 'last' in tickers[ticker_key]:
                    total_usdt_value += amount * tickers[ticker_key]['last']

    for coin, amount in swap_balance['total'].items():
        if amount > 0:
            if coin == 'USDT':
                total_usdt_value += amount
            else:
                ticker_key = f"{coin}/USDT"
                if ticker_key in tickers and 'last' in tickers[ticker_key]:
                    total_usdt_value += amount * tickers[ticker_key]['last']

    current_total_asset = total_usdt_value
    conn = init_db()
    save_today_asset(conn, current_total_asset)

    asset_1d = get_past_asset(conn, 1) or current_total_asset
    asset_7d = get_past_asset(conn, 7) or current_total_asset
    asset_30d = get_past_asset(conn, 30) or current_total_asset

    # --- 5. 상단 화면 ---
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

    # --- 6. 기간 설정 버튼 및 차트 ---
    col_period, col_date, col_dummy = st.columns([4, 3, 3])
    with col_period:
        period = st.radio("기간 선택", ["7D", "30D", "90D", "180D", "Custom"], horizontal=True, label_visibility="collapsed")
    
    with col_date:
        if period == "Custom":
            date_range = st.date_input("날짜 지정", [datetime.now().date() - timedelta(days=7), datetime.now().date()], label_visibility="collapsed")
        else:
            date_range = None

    df = pd.read_sql_query("SELECT date, total_asset FROM daily_assets ORDER BY date ASC", conn)
    df['date_obj'] = pd.to_datetime(df['date']).dt.date
    today = datetime.now().date()

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
        today = date_range[1]
    else:
        start_date = today - timedelta(days=7)
        
    mask = (df['date_obj'] >= start_date) & (df['date_obj'] <= today)
    filtered_df = df.loc[mask].copy()

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

    # --- 7. 세부 포지션 현황 표 (에러 방지용 삼중 따옴표 적용) ---
    st.markdown("<h3 style='color: #eaeaec; margin-top: 50px; margin-bottom: 15px; font-size: 20px;'>📋 현재 포지션 및 자산 현황</h3>", unsafe_allow_html=True)
    
    html_parts = []
    
    # 삼중 따옴표(""")를 사용해 안전하게 줄바꿈하여 코드를 작성한 뒤, 화면에 띄울 때만 공백을 지웁니다.
    header_html = """
    <table style='width:100%; border-collapse: collapse; text-align: left; color: #eaeaec; font-size: 14px;'>
    <thead><tr style='border-bottom: 1px solid #2b3139; color: #848e9c; font-size: 13px;'>
    <th style='padding: 10px 5px;'>마켓</th>
    <th style='padding: 10px 5px;'>종목</th>
    <th style='padding: 10px 5px;'>포지션 (레버리지)</th>
    <th style='padding: 10px 5px;'>투입 금액 (Margin)</th>
    <th style='padding: 10px 5px;'>자산 비중</th>
    <th style='padding: 10px 5px;'>미실현 손익</th>
    <th style='padding: 10px 5px;'>수익률(%)</th>
    </tr></thead><tbody>
    """.replace('\n', '')
    html_parts.append(header_html)
    
    positions = exchange_swap.fetch_positions()
    for p in positions:
        if p.get('contracts', 0) > 0:
            symbol = p.get('symbol', '').split(':')[0]
            side_str = "LONG" if p.get('side') == 'long' else "SHORT"
            side_color = "#0ecb81" if side_str == "LONG" else "#f6465d"
            lev = int(p.get('leverage', 1))
            
            margin = float(p.get('initialMargin') or (float(p.get('notional', 0)) / lev))
            weight = (margin / current_total_asset * 100) if current_total_asset > 0 else 0
            
            pnl = float(p.get('unrealizedPnl', 0))
            pnl_perc = float(p.get('percentage', 0))
            pnl_color = "#0ecb81" if pnl >= 0 else "#f6465d"
            pnl_sign = "+" if pnl > 0 else ""
            
            row_html = f"""
            <tr style='border-bottom: 1px solid #2b3139;'>
            <td style='padding: 15px 5px;'><span style='background-color:rgba(0, 209, 193, 0.2); color:#00d1c1; padding:3px 8px; border-radius:4px; font-size:12px; font-weight:bold;'>Futures</span></td>
            <td style='padding: 15px 5px; font-weight:bold;'>{symbol}</td>
            <td style='padding: 15px 5px; color:{side_color}; font-weight:bold;'>{side_str} <span style='background-color:#2b3139; color:#848e9c; padding:2px 6px; border-radius:4px; font-size:12px; margin-left:6px;'>x{lev}</span></td>
            <td style='padding: 15px 5px;'>${margin:,.2f}</td>
            <td style='padding: 15px 5px;'>{weight:,.1f}%</td>
            <td style='padding: 15px 5px; color:{pnl_color}; font-weight:bold;'>{pnl_sign}${pnl:,.2f}</td>
            <td style='padding: 15px 5px; color:{pnl_color}; font-weight:bold;'>{pnl_sign}{pnl_perc:,.2f}%</td>
            </tr>
            """.replace('\n', '')
            html_parts.append(row_html)

    for coin, amount in spot_balance['total'].items():
        if amount > 0:
            value = amount if coin == 'USDT' else (amount * tickers.get(f"{coin}/USDT", {}).get('last', 0))
            if value >= 1:
                weight = (value / current_total_asset * 100) if current_total_asset > 0 else 0
                row_html = f"""
                <tr style='border-bottom: 1px solid #2b3139;'>
                <td style='padding: 15px 5px;'><span style='background-color:rgba(240, 185, 11, 0.2); color:#f0b90b; padding:3px 8px; border-radius:4px; font-size:12px; font-weight:bold;'>Spot</span></td>
                <td style='padding: 15px 5px; font-weight:bold;'>{coin}</td>
                <td style='padding: 15px 5px; color:#eaeaec;'>보유 (Hold)</td>
                <td style='padding: 15px 5px;'>${value:,.2f}</td>
                <td style='padding: 15px 5px;'>{weight:,.1f}%</td>
                <td style='padding: 15px 5px; color:#5e6673; font-size: 12px;'>(API 미지원)</td>
                <td style='padding: 15px 5px; color:#5e6673; font-size: 12px;'>-</td>
                </tr>
                """.replace('\n', '')
                html_parts.append(row_html)
                
    html_parts.append("</tbody></table>")
    final_html = "".join(html_parts)
    st.markdown(final_html, unsafe_allow_html=True)

except Exception as e:
    st.error(f"오류 발생. 관리자(본인)만 볼 수 있는 에러 메시지입니다: {e}")
