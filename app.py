import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta
import pandas as pd
from io import StringIO

st.set_page_config(page_title="外貨→円 変換", page_icon="💱")
st.title("💱 外貨 → 円 変換アプリ")
st.caption("三菱UFJ銀行 公表対顧客外国為替相場 (MURC掲載) を使用")

# 通貨コード → 表示名
CURRENCIES = {
    "USD": "米ドル",
    "EUR": "ユーロ",
    "GBP": "イギリスポンド",
    "AUD": "オーストラリア・ドル",
    "NZD": "ニュージーランド・ドル",
    "CAD": "カナダドル",
    "CHF": "スイスフラン",
    "CNY": "中国元",
    "HKD": "香港ドル",
    "SGD": "シンガポール・ドル",
    "KRW": "韓国ウォン (100単位)",
    "THB": "タイ・バーツ",
    "ZAR": "南アフリカ・ランド",
}
PER_100 = ["KRW", "IDR"]  # 100通貨単位の通貨


@st.cache_data(ttl=3600)
def fetch_mufg(target_date: date):
    """MUFGページからレート表を取得"""
    id_str = target_date.strftime("%Y%m%d")
    url = f"https://www.murc-kawasesouba.jp/fx/past/index.php?id={id_str}"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers, timeout=10)
    res.encoding = "shift_jis"  # MUFGはShift_JIS
    html = res.text

    # 表示日付を確認(指定日と異なる場合は休日リダイレクトの可能性)
    soup = BeautifulSoup(html, "html.parser")
    
    # pandasで表抽出(StringIOで包む)
    tables = pd.read_html(StringIO(html))
    
    # USD/米ドルを含む表を選定
    rate_df = None
    for t in tables:
        s = t.astype(str).to_string()
        if "USD" in s and "TTS" in s:
            rate_df = t
            break
    
    if rate_df is None:
        raise ValueError("レート表が見つかりません")

    # 列名を整理
    rate_df.columns = [str(c).strip() for c in rate_df.columns]
    
    # TTS, TTB列を特定
    tts_col = next((c for c in rate_df.columns if "TTS" in c.upper()), None)
    ttb_col = next((c for c in rate_df.columns if "TTB" in c.upper()), None)
    code_col = next((c for c in rate_df.columns if "Code" in c or "略称" in c), None)
    
    if not (tts_col and ttb_col and code_col):
        raise ValueError(f"必要な列が見つかりません: {rate_df.columns.tolist()}")
    
    # 通貨コード→レート辞書
    rates = {}
    for _, row in rate_df.iterrows():
        code = str(row[code_col]).strip()
        try:
            tts = float(str(row[tts_col]).replace(",", "").strip())
            ttb = float(str(row[ttb_col]).replace(",", "").strip())
            ttm = round((tts + ttb) / 2, 4)
            rates[code] = {"TTS": tts, "TTB": ttb, "TTM": ttm}
        except (ValueError, TypeError):
            continue  # "unquoted" などはスキップ
    
    return rates, rate_df


# --- UI ---
col1, col2 = st.columns(2)
with col1:
    target_date = st.date_input("📅 日付(平日)", value=date.today() - timedelta(days=1))
with col2:
    code = st.selectbox("💴 通貨", list(CURRENCIES.keys()),
                        format_func=lambda c: f"{c} - {CURRENCIES[c]}")

amount = st.number_input("💰 金額(外貨)", min_value=0.0, value=100.0, step=1.0)
rate_type = st.radio("レート種別", ["TTM(仲値)", "TTS(売値)", "TTB(買値)"], horizontal=True)
rate_key = rate_type.split("(")[0].strip()

if st.button("🔄 レート取得して変換", type="primary"):
    with st.spinner("MUFGからレート取得中..."):
        try:
            rates, raw_df = fetch_mufg(target_date)
            
            if code not in rates:
                st.error(f"❌ {code} のレートが見つかりません(unquotedの可能性)")
                st.dataframe(raw_df)
            else:
                r = rates[code][rate_key]
                divisor = 100 if code in PER_100 else 1
                jpy = round(amount * r / divisor, 2)

                st.success("✅ 変換完了")
                st.metric(
                    label=f"1 {code}{'(100単位)' if divisor==100 else ''} = {r} 円 ({rate_key})",
                    value=f"{jpy:,.2f} 円"
                )
                st.code(f"{jpy}", language="text")
                st.caption("↑ コードボックス右上のコピーアイコンでコピー")

                with st.expander("📊 当日の全レート(TTM=自動計算)"):
                    df_show = pd.DataFrame(rates).T
                    df_show.index.name = "通貨"
                    st.dataframe(df_show, use_container_width=True)
        
        except Exception as e:
            st.error(f"❌ 取得エラー: {e}")
            st.info("土日祝日・未来日付は取得できません。平日を選んでください。")

# 手動レート
with st.expander("🛠 手動レート入力"):
    manual_rate = st.number_input("1通貨あたりの円レート", min_value=0.0, step=0.0001, format="%.4f")
    if st.button("手動レートで変換"):
        if manual_rate > 0 and amount > 0:
            divisor = 100 if code in PER_100 else 1
            jpy = round(amount * manual_rate / divisor, 2)
            st.success(f"💴 {jpy:,.2f} 円")
            st.code(f"{jpy}", language="text")

st.markdown("---")
st.caption("データ元: https://www.murc-kawasesouba.jp/")
