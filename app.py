import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta
import pandas as pd

st.set_page_config(page_title="外貨→円 変換", page_icon="💱")
st.title("💱 外貨 → 円 変換アプリ")
st.caption("三菱UFJリサーチ&コンサルティング (MURC) の過去TTMレート使用")

CURRENCY_MAP = {
    "米ドル (USD)": "USD",
    "ユーロ (EUR)": "EUR",
    "英ポンド (GBP)": "GBP",
    "豪ドル (AUD)": "AUD",
    "カナダドル (CAD)": "CAD",
    "スイスフラン (CHF)": "CHF",
    "中国元 (CNY)": "CNY",
    "韓国ウォン (KRW) ※100単位": "KRW",
    "香港ドル (HKD)": "HKD",
    "シンガポールドル (SGD)": "SGD",
}
PER_100 = ["KRW"]


@st.cache_data(ttl=3600)
def fetch_mufg_table(target_date: date) -> pd.DataFrame:
    """MUFGページから当日の全レート表をDataFrameで取得"""
    id_str = target_date.strftime("%Y%m%d")
    url = f"https://www.murc-kawasesouba.jp/fx/past/index.php?id={id_str}"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers, timeout=10)
    res.encoding = res.apparent_encoding

    # pandasで表を直接読み込む(最も確実)
    tables = pd.read_html(res.text)
    if not tables:
        raise ValueError("ページに表が見つかりません")

    # 通貨コードを含む表を探す
    for t in tables:
        text_all = t.astype(str).to_string()
        if "USD" in text_all or "米ドル" in text_all:
            return t
    return tables[0]


def extract_rate(df: pd.DataFrame, currency_code: str, rate_type: str = "TTM"):
    """指定通貨・指定レート種別の値を返す"""
    # 列名を文字列化
    df.columns = [str(c).strip() for c in df.columns]
    
    # TTM列を探す(列名にTTM/仲値が含まれる)
    target_col = None
    for col in df.columns:
        col_up = col.upper()
        if rate_type == "TTM" and ("TTM" in col_up or "仲値" in col or "中値" in col):
            target_col = col
            break
        elif rate_type == "TTS" and ("TTS" in col_up or "売" in col):
            target_col = col
            break
        elif rate_type == "TTB" and ("TTB" in col_up or "買" in col):
            target_col = col
            break

    # 通貨行を探す
    first_col = df.columns[0]
    for idx, row in df.iterrows():
        cell = str(row[first_col])
        if currency_code in cell:
            if target_col:
                val = row[target_col]
            else:
                # 列名で見つからない場合、数値列の最初をTTMとして扱う
                for c in df.columns[1:]:
                    try:
                        val = float(str(row[c]).replace(",", ""))
                        break
                    except (ValueError, TypeError):
                        continue
            try:
                return float(str(val).replace(",", ""))
            except (ValueError, TypeError):
                return None
    return None


# --- UI ---
col1, col2 = st.columns(2)
with col1:
    target_date = st.date_input("📅 日付(平日)", value=date.today() - timedelta(days=1))
with col2:
    currency_label = st.selectbox("💴 通貨", list(CURRENCY_MAP.keys()))

amount = st.number_input("💰 金額(外貨)", min_value=0.0, value=100.0, step=1.0)
rate_type = st.radio("レート種別", ["TTM(仲値)", "TTS(売値)", "TTB(買値)"], horizontal=True)
rate_type_key = rate_type.split("(")[0].strip()

if st.button("🔄 レート取得して変換", type="primary"):
    with st.spinner("MUFGからレート取得中..."):
        try:
            df = fetch_mufg_table(target_date)
            
            # デバッグ表示
            with st.expander("🔍 取得した生データ(確認用)"):
                st.dataframe(df, use_container_width=True)
                st.write("列名:", list(df.columns))

            code = CURRENCY_MAP[currency_label]
            rate = extract_rate(df, code, rate_type_key)
            
            if rate is None:
                st.error(f"❌ {code} の {rate_type_key} レートが見つかりません")
            else:
                divisor = 100 if code in PER_100 else 1
                jpy = amount * rate / divisor
                jpy_rounded = round(jpy, 2)

                st.success("✅ 変換完了")
                st.metric(
                    label=f"1 {code}{'(100単位)' if divisor==100 else ''} = {rate} 円 ({rate_type_key})",
                    value=f"{jpy_rounded:,.2f} 円"
                )
                st.code(f"{jpy_rounded}", language="text")
                st.caption("↑ 右上アイコンでコピーできます")

        except Exception as e:
            st.error(f"❌ エラー: {e}")
            st.info("土日祝日はデータがありません。平日を選んでください。")

# 手動入力
with st.expander("🛠 手動レート入力"):
    manual_rate = st.number_input("1通貨あたりの円レート", min_value=0.0, step=0.0001, format="%.4f")
    if st.button("手動レートで変換"):
        if manual_rate > 0 and amount > 0:
            code = CURRENCY_MAP[currency_label]
            divisor = 100 if code in PER_100 else 1
            jpy = round(amount * manual_rate / divisor, 2)
            st.success(f"💴 {jpy:,.2f} 円")
            st.code(f"{jpy}", language="text")

st.markdown("---")
st.caption("データ元: https://www.murc-kawasesouba.jp/")

