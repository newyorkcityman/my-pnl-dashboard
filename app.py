import streamlit as st
import ccxt
import pandas as pd
import sqlite3
from datetime import datetime, timedelta

# --- 1. 데이터베이스(장부) 설정 함수 ---
def init_db():
    conn = sqlite3.connect('my_pnl_ledger.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS daily_assets
                 (date TEXT PRIMARY KEY, total_asset REAL)''')
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

# --- 2. 웹사이트 기본 설정 ---
st.set_page_config(page_title="나만의 투자 대시보드", layout="wide")
st.title("📊 나의 Bitget 투자 대시보드")

# --- 3. 안전 금고(Secrets)에서 API 키 자동 불러오기 ---
try:
    api_key = st.secrets["BITGET_API_KEY"]
    secret_key = st.secrets["BITGET_SECRET_KEY"]
    passphrase = st.secrets["BITGET_PASSPHRASE"]
except KeyError:
    st.error("⚠️ 스트림릿 설정(Secrets)에 API 키가 등록되지 않았습니다.")
    st.stop()

# 이제 화면 왼쪽 사이드바가 필요 없으므로 중앙에 버튼 하나만 만듭니다.
if st.button("🔄 최신 데이터 동기화 및 PNL 보기", use_container_width=True):
    try:
        # 거래소 연결
        exchange_spot = ccxt.bitget({'apiKey': api_key, 'secret': secret_key, 'password': passphrase, 'enableRateLimit': True})
        exchange_swap = ccxt.bitget({'apiKey': api_key, 'secret': secret_key, 'password': passphrase, 'enableRateLimit': True, 'options': {'defaultType': 'swap'}})

        # 현물 잔고 가져오기
        spot_balance = exchange_spot.fetch_balance()
        spot_usdt = spot_balance['total'].get('USDT', 0)
        
        # 선물 잔고 가져오기
        swap_balance = exchange_swap.fetch_balance()
        swap_usdt = swap_balance['total'].get('USDT', 0)

        current_total_asset = spot_usdt + swap_usdt

        # DB에 기록
        conn = init_db()
        save_today_asset(conn, current_total_asset)

        # --- 4. 화면 출력 ---
        st.success("✅ 실시간 데이터 연동 완료!")
        st.subheader("💰 내 자산 현황 (USDT)")
        
        col1, col2, col3, col4 = st.columns(4)
        asset_1d = get_past_asset(conn, 1)
        asset_1w = get_past_asset(conn, 7)
        asset_1m = get_past_asset(conn, 30)

        with col1:
            st.metric(label="현재 총 자산", value=f"${current_total_asset:,.2f}")
        with col2:
            delta_1d = (current_total_asset - asset_1d) if asset_1d else 0
            st.metric(label="1일 전 대비", value=f"${delta_1d:,.2f}" if asset_1d else "-", delta=f"${delta_1d:,.2f}" if asset_1d else None)
        with col3:
            delta_1w = (current_total_asset - asset_1w) if asset_1w else 0
            st.metric(label="1주 전 대비", value=f"${delta_1w:,.2f}" if asset_1w else "-", delta=f"${delta_1w:,.2f}" if asset_1w else None)
        with col4:
            delta_1m = (current_total_asset - asset_1m) if asset_1m else 0
            st.metric(label="1달 전 대비", value=f"${delta_1m:,.2f}" if asset_1m else "-", delta=f"${delta_1m:,.2f}" if asset_1m else None)

        st.markdown("---")

        # 차트
        df_history = pd.read_sql_query("SELECT date, total_asset FROM daily_assets ORDER BY date ASC", conn)
        df_history.set_index('date', inplace=True)
        st.line_chart(df_history, y="total_asset")

        st.markdown("---")
        st.subheader("📋 세부 보유 종목 및 포지션")
        
        spot_data = [{"종목명": coin, "보유 수량": amount} for coin, amount in spot_balance['total'].items() if amount > 0]
        if spot_data:
            st.caption("🪙 현물(Spot)")
            st.table(pd.DataFrame(spot_data))
            
        positions = exchange_swap.fetch_positions()
        swap_data = []
        for p in positions:
            if p.get('contracts', 0) > 0:
                swap_data.append({
                    "종목명": p.get('symbol', '알 수 없음'),
                    "방향": "🔴 SHORT" if p.get('side') == 'short' else "🟢 LONG",
                    "진입가": f"${float(p.get('entryPrice', 0)):,.4f}",
                    "현재가": f"${float(p.get('markPrice', 0)):,.4f}",
                    "미실현손익": f"${float(p.get('unrealizedPnl', 0)):,.2f}",
                    "수익률(%)": f"{float(p.get('percentage', 0)):,.2f}%"
                })
        
        if swap_data:
            st.caption("📈 선물(Futures)")
            st.table(pd.DataFrame(swap_data))

    except Exception as e:
        st.error(f"❌ 데이터 불러오기 실패. 에러 내용: {e}")