import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta

st.set_page_config(page_title="外貨→円 変換", page_icon="💱")

st.title("💱 外貨 → 円 変換アプリ")
st.caption("三菱UFJリサーチ&コンサルティング (MURC) の過去TTMレートを使用")

# 通貨マッピング
CURRENCY_MAP = {
    "米ドル (USD)": "米ドル",
    "ユーロ (EUR)": "ユーロ",
    "英ポンド (GBP)": "英ポンド",
    "豪ドル (AUD)": "豪ドル",
    "カナダドル (CAD)": "カナダドル",
    "スイスフラン (CHF)": "スイスフラン",
    "中国元 (CNY)": "中国元",
    "韓国ウォン (KRW) ※100単位": "韓国ウォン",
    "香港ドル (HKD)": "香港ドル",
    "シンガポールドル (SGD)": "シンガポールドル",
}
PER_100 = ["韓国ウォン"]


@st.cache_data(ttl=3600)
def fetch_mufg_rates(target_date: date) -> dict:
    """指定日のMUFGレートを取得して辞書で返す"""
    id_str = target_date.strftime("%Y%m%d")
    url = f"https://www.murc-kawasesouba.jp/fx/past/index.php?id={id_str}"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers, timeout=10)
    res.encoding = res.apparent_encoding
    soup = BeautifulSoup(res.text, "html.parser")

    rates = {}
    for tr in soup.select("table tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) < 2:
            continue
        label = cells[0].get_text(strip=True)
        for name in CURRENCY_MAP.values():
            if name in label:
                for c in cells[1:]:
                    txt = c.get_text(strip=True).replace(",", "")
                    try:
                        val = float(txt)
                        if val > 0:
                            rates[name] = val
                            break
                    except ValueError:
                        continue
    return rates


# --- 入力フォーム ---
col1, col2 = st.columns(2)
with col1:
    default_date = date.today() - timedelta(days=1)
    target_date = st.date_input("📅 日付(平日)", value=default_date)
with col2:
    currency_label = st.selectbox("💴 通貨", list(CURRENCY_MAP.keys()))

amount = st.number_input("💰 金額(外貨)", min_value=0.0, value=100.0, step=1.0)

if st.button("🔄 レート取得して変換", type="primary"):
    with st.spinner("MUFGからレート取得中..."):
        try:
            rates = fetch_mufg_rates(target_date)
            if not rates:
                st.error("❌ レートが取得できません。土日祝の可能性があります。")
            else:
                cur_name = CURRENCY_MAP[currency_label]
                rate = rates.get(cur_name)
                if not rate:
                    st.error(f"❌ {cur_name} のレートが見つかりません。")
                else:
                    divisor = 100 if cur_name in PER_100 else 1
                    jpy = amount * rate / divisor
                    jpy_rounded = round(jpy, 2)

                    st.success("✅ 変換完了")
                    st.metric(
                        label=f"1 {cur_name}{'(100単位)' if divisor==100 else ''} = {rate} 円",
                        value=f"{jpy_rounded:,.2f} 円"
                    )

                    # コピー用テキストエリア + ボタン
                    st.code(f"{jpy_rounded}", language="text")
                    st.caption("↑ 右上のコピーアイコンで円金額をコピーできます")

                    with st.expander("📊 当日の全レート一覧"):
                        st.dataframe(
                            {"通貨": list(rates.keys()), "TTM(円)": list(rates.values())},
                            use_container_width=True
                        )
        except Exception as e:
            st.error(f"❌ 取得エラー: {e}")

# --- 手動レート入力 ---
with st.expander("🛠 手動レート入力(取得失敗時)"):
    manual_rate = st.number_input("1通貨あたりの円レート", min_value=0.0, step=0.0001, format="%.4f")
    if st.button("手動レートで変換"):
        if manual_rate > 0 and amount > 0:
            cur_name = CURRENCY_MAP[currency_label]
            divisor = 100 if cur_name in PER_100 else 1
            jpy = amount * manual_rate / divisor
            jpy_rounded = round(jpy, 2)
            st.success(f"💴 {jpy_rounded:,.2f} 円")
            st.code(f"{jpy_rounded}", language="text")

st.markdown("---")
st.caption("データ元: https://www.murc-kawasesouba.jp/")
