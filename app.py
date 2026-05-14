import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta
import pandas as pd
import re

st.set_page_config(page_title="外貨→円 変換", page_icon="💱")
st.title("💱 外貨 → 円 変換アプリ")
st.caption("三菱UFJ銀行 公表対顧客外国為替相場 (MURC 過去3ヶ月データ)")

CURRENCIES = {
    "USD": "米ドル", "EUR": "ユーロ", "GBP": "イギリスポンド",
    "AUD": "オーストラリア・ドル", "NZD": "ニュージーランド・ドル",
    "CAD": "カナダドル", "CHF": "スイスフラン", "CNY": "中国元",
    "HKD": "香港ドル", "SGD": "シンガポール・ドル",
    "KRW": "韓国ウォン (100単位)", "THB": "タイ・バーツ",
    "ZAR": "南アフリカ・ランド", "DKK": "デンマーククローネ",
    "NOK": "ノルウェークローネ", "SEK": "スウェーデンクローナ",
    "INR": "インドルピー", "IDR": "インドネシアルピア",
    "MXN": "メキシコペソ", "PHP": "フィリピンペソ",
    "TRY": "トルコリラ", "RUB": "ロシアルーブル",
}
PER_100 = ["KRW", "IDR"]
KNOWN_CODES = list(CURRENCIES.keys())


def _to_float(text):
    if text is None:
        return None
    t = re.sub(r"[,\s\xa0]", "", str(text))
    try:
        return float(t)
    except ValueError:
        return None


def parse_past_3month(html: str):
    """過去3ヶ月ページ用パーサー(TTS/TTB/TTM/ACC.RATE形式)"""
    soup = BeautifulSoup(html, "html.parser")
    text_all = soup.get_text("\n")
    
    # ページ日付検出
    page_date = None
    m = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", text_all)
    if m:
        page_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    
    rates = {}
    
    # tr単位で解析
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if len(cells) < 4:
            continue
        cell_texts = [c.get_text(" ", strip=True) for c in cells]
        
        # 通貨コード位置検出
        code = None
        code_pos = None
        for i, t in enumerate(cell_texts):
            ts = t.strip()
            if ts in KNOWN_CODES:
                code = ts
                code_pos = i
                break
        
        if not code:
            continue
        
        # 後続セルから数値を取得
        numbers = []
        for t in cell_texts[code_pos + 1:]:
            n = _to_float(t)
            if n is not None and n > 0:
                numbers.append(n)
        
        if len(numbers) >= 3:
            # 過去3ヶ月ページの典型構造: TTS, TTB, TTM (またはTTS, TTB, TTM, ACC)
            tts, ttb, ttm = numbers[0], numbers[1], numbers[2]
            if tts < ttb:
                tts, ttb = ttb, tts
            rates[code] = {"TTS": tts, "TTB": ttb, "TTM": ttm}
        elif len(numbers) == 2:
            # TTS, TTBのみの場合は計算
            tts, ttb = numbers[0], numbers[1]
            if tts < ttb:
                tts, ttb = ttb, tts
            rates[code] = {
                "TTS": tts, "TTB": ttb,
                "TTM": round((tts + ttb) / 2, 4)
            }
    
    # フォールバック: 正規表現
    if not rates:
        for code in KNOWN_CODES:
            pat = re.compile(
                rf"\b{code}\b[\s\S]{{0,300}}?([\d]+\.[\d]+)[\s\S]{{0,80}}?([\d]+\.[\d]+)(?:[\s\S]{{0,80}}?([\d]+\.[\d]+))?"
            )
            m = pat.search(text_all)
            if m:
                try:
                    nums = [float(g) for g in m.groups() if g]
                    if len(nums) >= 3:
                        tts, ttb, ttm = nums[0], nums[1], nums[2]
                        if tts < ttb:
                            tts, ttb = ttb, tts
                        rates[code] = {"TTS": tts, "TTB": ttb, "TTM": ttm}
                    elif len(nums) == 2:
                        tts, ttb = nums[0], nums[1]
                        if tts < ttb:
                            tts, ttb = ttb, tts
                        rates[code] = {
                            "TTS": tts, "TTB": ttb,
                            "TTM": round((tts + ttb) / 2, 4)
                        }
                except ValueError:
                    pass
    
    return rates, page_date


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_mufg_3month(target_date: date):
    """過去3ヶ月ページからレート取得"""
    id_str = target_date.strftime("%Y%m%d")
    
    # 過去3ヶ月ページのURLパターン(複数試行)
    urls = [
        f"https://www.murc-kawasesouba.jp/fx/past_3month_result.php?id={id_str}",
        f"https://www.murc-kawasesouba.jp/fx/past/index.php?id={id_str}",  # 念のため
    ]
    
    debug_log = []
    raw_sample = None
    
    for url in urls:
        try:
            res = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15
            )
            res.encoding = "shift_jis"
            entry = {"url": url, "status": res.status_code, "size": len(res.text)}
            
            if res.status_code == 200 and len(res.text) > 1000:
                rates, page_date = parse_past_3month(res.text)
                entry["page_date"] = page_date
                entry["currencies_found"] = len(rates)
                debug_log.append(entry)
                raw_sample = res.text
                
                if rates:
                    return rates, page_date, url, debug_log, raw_sample
            else:
                debug_log.append(entry)
        except Exception as e:
            debug_log.append({"url": url, "error": str(e)})
    
    return None, None, None, debug_log, raw_sample


# --- UI ---
st.info("📅 過去3ヶ月以内の平日のレートを取得できます")

col1, col2 = st.columns(2)
with col1:
    default = date.today() - timedelta(days=1)
    # 土日なら金曜に
    while default.weekday() >= 5:
        default -= timedelta(days=1)
    target_date = st.date_input(
        "📅 日付(平日)",
        value=default,
        min_value=date.today() - timedelta(days=90),
        max_value=date.today()
    )
with col2:
    code = st.selectbox("💴 通貨", list(CURRENCIES.keys()),
                        format_func=lambda c: f"{c} - {CURRENCIES[c]}")

amount = st.number_input("💰 金額(外貨)", min_value=0.0, value=100.0, step=1.0)
rate_type = st.radio("レート種別", ["TTM(仲値)", "TTS(売値)", "TTB(買値)"], horizontal=True)
rate_key = rate_type.split("(")[0].strip()

if st.button("🔄 レート取得して変換", type="primary"):
    with st.spinner("MUFG過去3ヶ月データを取得中..."):
        rates, page_date, used_url, debug_log, raw_html = fetch_mufg_3month(target_date)
        
        if not rates:
            st.error("❌ レート取得できませんでした")
            with st.expander("🔧 デバッグ情報"):
                st.json(debug_log)
                if raw_html:
                    idx = raw_html.find("USD")
                    if idx >= 0:
                        st.subheader("USD周辺HTML(500文字)")
                        st.code(raw_html[max(0,idx-100):idx+500])
                    else:
                        st.code(raw_html[:2000])
        else:
            req_str = target_date.strftime("%Y-%m-%d")
            if page_date and page_date != req_str:
                st.warning(f"⚠ 指定日 {req_str} のデータが無く、ページ表示日は {page_date} です。"
                           f"(土日祝・休業日の可能性)")
            
            if code not in rates:
                st.error(f"❌ {code} のレートが見つかりません")
                st.write("検出された通貨:", list(rates.keys()))
            else:
                r = rates[code][rate_key]
                divisor = 100 if code in PER_100 else 1
                jpy = round(amount * r / divisor, 2)

                st.success(f"✅ 変換完了(ページ表示日: {page_date or '不明'})")
                st.metric(
                    label=f"1 {code}{'(100単位)' if divisor==100 else ''} = {r} 円 ({rate_key})",
                    value=f"{jpy:,.2f} 円"
                )
                st.code(f"{jpy}", language="text")
                st.caption("↑ コードボックス右上のアイコンでコピー")

                with st.expander("📊 当日の全レート"):
                    df_show = pd.DataFrame(rates).T
                    df_show.index.name = "通貨"
                    st.dataframe(df_show, use_container_width=True)
            
            with st.expander("🔧 デバッグ情報"):
                st.write("使用URL:", used_url)
                st.json(debug_log)

with st.expander("🛠 手動レート入力"):
    manual_rate = st.number_input("1通貨あたりの円レート", min_value=0.0, step=0.0001, format="%.4f")
    if st.button("手動レートで変換"):
        if manual_rate > 0 and amount > 0:
            divisor = 100 if code in PER_100 else 1
            jpy = round(amount * manual_rate / divisor, 2)
            st.success(f"💴 {jpy:,.2f} 円")
            st.code(f"{jpy}", language="text")

st.markdown("---")
st.caption("データ元: https://www.murc-kawasesouba.jp/fx/past_3month.php")
