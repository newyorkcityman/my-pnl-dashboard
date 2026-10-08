import streamlit as st
import ccxt
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import plotly.graph_objects as go

# --- 1. 페이지 설정 (제목 텍스트 모두 제거) ---
st.set_page_config(page_title="Dashboard", layout="wide", initial_sidebar_state="collapsed")

# --- 2. 사진과 동일한 디자인을 위한 커스텀 CSS (검은 배경, 글씨체) ---
st.markdown("""
    <style>
    /* 전체 배경을 완전한 검은색/어두운 회색으로 변경 */
    .stApp {
        background-color: #0b0e11;
        color: #eaeaec;
    }
    /* 불필요한 기본 헤더 숨기기 */
    header {visibility: hidden;}
    
    /* 최상단 대형 총 자산 텍스트 */
    .big-asset {
        font-size: 42px !important;
        font-weight: 800;
        margin-bottom: 0px;
        line-height: 1.2;
    }
    .sub-asset {
        font-size: 16px;
        color: #848e9c;
        margin-top: 0px;
        margin-bottom: 30px;
    }
    
    /* PNL 텍스트 스타일 */
    .pnl-title {
        font-size: 13px;
        color: #848e9c;
        border-bottom: 1px dashed #5e6673;
        display: inline-block;
        margin-bottom: 5px;
    }
    .pnl-val-red {
        font-size: 20px;
        font-weight: bold;
        color: #f6465d; /* 사진의 붉은색 */
    }
    .pnl-val-green {
        font-size: 20px;
        font-weight: bold;
        color: #0ecb81; /* 사진의 초록색 */
    }
    .pnl-val-neutral {
        font-size: 20px;
        font-weight: bold;
        color: #eaeaec;
    }
    </style>
""", unsafe_allow_html=True)

# --- 3. 데이터베이스(장부) 및 함수 ---
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

# PNL 색상을 결정하는 헬퍼 함수
def format_pnl(val):
    if val > 0:
        return f"<div class='pnl-val-green'>+{val:,.2f} USD</div>"
    elif val < 0:
        return f"<div class='pnl-val-red'>{val:,.2f} USD</div>"
    else:
        return f"<div class='pnl-val-neutral'>{val:,.2f} USD</div>"

# --- 4. 메인 로직 ---
# 사이드바 비밀번호 (가장 작고 심플하게)
st.sidebar.caption("🔒 잠금 해제")
MY_PASSWORD = "1234"
entered_password = st.sidebar.text_input("Password", type="password", label_visibility="collapsed")

if entered_password == MY_PASSWORD:
    try:
        api_key = st.secrets["BITGET_API_KEY"]
        secret_key = st.secrets["BITGET_SECRET_KEY"]
        passphrase = st.secrets["BITGET_PASSPHRASE"]
        
        # 데이터 연동
        exchange_spot = ccxt.bitget({'apiKey': api_key, 'secret': secret_key, 'password': passphrase, 'enableRateLimit': True})
        exchange_swap = ccxt.bitget({'apiKey': api_key, 'secret': secret_key, 'password': passphrase, 'enableRateLimit': True, 'options': {'defaultType': 'swap'}})

        spot_balance = exchange_spot.fetch_balance()
        swap_balance = exchange_swap.fetch_balance()
        current_total_asset = spot_balance['total'].get('USDT', 0) + swap_balance['total'].get('USDT', 0)

        conn = init_db()
        save_today_asset(conn, current_total_asset)

        # 과거 자산 조회
        asset_1d = get_past_asset(conn, 1) or current_total_asset
        asset_7d = get_past_asset(conn, 7) or current_total_asset
        asset_30d = get_past_asset(conn, 30) or current_total_asset

        pnl_1d = current_total_asset - asset_1d
        pnl_7d = current_total_asset - asset_7d
        pnl_30d = current_total_asset - asset_30d

        # --- 5. 화면 출력 (사진과 동일한 레이아웃) ---
        
        # 총 자산 대형 텍스트
        st.markdown(f"<div class='big-asset'>{current_total_asset:,.2f} USDT</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='sub-asset'>≈ {current_total_asset:,.2f} USD</div>", unsafe_allow_html=True)
        
        # PNL 요약 3컬럼
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("<div class='pnl-title'>Today's PnL</div>", unsafe_allow_html=True)
            st.markdown(format_pnl(pnl_1d), unsafe_allow_html=True)
        with col2:
            st.markdown("<div class='pnl-title'>7D PnL</div>", unsafe_allow_html=True)
            st.markdown(format_pnl(pnl_7d), unsafe_allow_html=True)
        with col3:
            st.markdown("<div class='pnl-title'>30D PnL</div>", unsafe_allow_html=True)
            st.markdown(format_pnl(pnl_30d), unsafe_allow_html=True)
            
        st.write("")
        st.write("")
        
        # --- 6. Plotly 차트 그리기 ---
        # 장부 데이터 불러오기
        df = pd.read_sql_query("SELECT date, total_asset FROM daily_assets ORDER BY date ASC", conn)
        df['Daily_PnL'] = df['total_asset'].diff().fillna(0)
        
        tab1, tab2 = st.tabs(["Total PnL (누적)", "Daily PnL (일일)"])
        
        # 차트 공통 레이아웃 설정 (배경 투명화 및 글씨 색상)
        chart_layout = dict(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color='#848e9c'),
            margin=dict(l=0, r=0, t=30, b=0),
            xaxis=dict(showgrid=False, zeroline=False),
            yaxis=dict(showgrid=True, gridcolor='#2b3139', zeroline=False, tickprefix="$")
        )

        with tab1:
            # 1번째 사진의 하늘색 라인 차트
            fig_total = go.Figure()
            fig_total.add_trace(go.Scatter(
                x=df['date'], y=df['total_asset'],
                mode='lines',
                line=dict(color='#00d1c1', width=3), # 사진의 하늘색 라인
                fill='tozeroy',
                fillcolor='rgba(0, 209, 193, 0.1)'
            ))
            fig_total.update_layout(**chart_layout)
            st.plotly_chart(fig_total, use_container_width=True)

        with tab2:
            # 2번째 사진의 수익(초록)/손실(빨강) 바 차트
            colors = ['#0ecb81' if val >= 0 else '#f6465d' for val in df['Daily_PnL']]
            fig_daily = go.Figure()
            fig_daily.add_trace(go.Bar(
                x=df['date'], y=df['Daily_PnL'],
                marker_color=colors
            ))
            fig_daily.update_layout(**chart_layout)
            # 0원 기준선 추가
            fig_daily.add_hline(y=0, line_color="#5e6673", line_width=1)
            st.plotly_chart(fig_daily, use_container_width=True)

    except Exception as e:
        st.error(f"오류 발생: {e}")
