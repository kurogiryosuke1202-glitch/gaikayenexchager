import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta
import pandas as pd
import re

st.set_page_config(page_title="外貨→円 変換", page_icon="💱")
st.title("💱 外貨 → 円 変換アプリ")
st.caption("三菱UFJ銀行 公表対顧客外国為替相場 (MURC掲載) を使用")

CURRENCIES = {
    "USD": "米ドル", "EUR": "ユーロ", "GBP": "イギリスポンド",
    "AUD": "オーストラリア・ドル", "NZD": "ニュージーランド・ドル",
    "CAD": "カナダドル", "CHF": "スイスフラン", "CNY": "中国元",
    "HKD": "香港ドル", "SGD": "シンガポール・ドル",
    "KRW": "韓国ウォン (100単位)", "THB": "タイ・バーツ",
    "ZAR": "南アフリカ・ランド",
}
PER_100 = ["KRW", "IDR"]


def parse_number(text):
    if not text:
        return None
    t = str(text).strip().replace(",", "").replace("\xa0", "").replace(" ", "")
    try:
        return float(t)
    except ValueError:
        return None


def parse_html_for_rates(html: str):
    """HTMLからTTS/TTB表を抽出"""
    soup = BeautifulSoup(html, "html.parser")
    
    # ページ日付検出
    page_date = None
    m = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", soup.get_text())
    if m:
        page_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    
    rates = {}
    tables_info = []  # デバッグ用
    
    for ti, table in enumerate(soup.find_all("table")):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        
        # 全行スキャンしてヘッダー行を探す
        header_idx = None
        header_cells = None
        for ri, tr in enumerate(rows):
            cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
            if any("TTS" in c.upper() for c in cells) and any("TTB" in c.upper() for c in cells):
                header_idx = ri
                header_cells = cells
                break
        
        if header_idx is None:
            continue
        
        tables_info.append({
            "table_index": ti,
            "header_row": header_idx,
            "headers": header_cells,
        })
        
        tts_idx = next((i for i, h in enumerate(header_cells) if "TTS" in h.upper()), None)
        ttb_idx = next((i for i, h in enumerate(header_cells) if "TTB" in h.upper()), None)
        code_idx = next((i for i, h in enumerate(header_cells) if "Code" in h or "略称" in h), None)
        
        # データ行解析
        for tr in rows[header_idx + 1:]:
            cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) <= max(tts_idx or 0, ttb_idx or 0):
                continue
            
            # 通貨コード特定
            code = None
            if code_idx is not None and code_idx < len(cells):
                v = cells[code_idx].strip()
                if len(v) == 3 and v.isalpha():
                    code = v.upper()
            if not code:
                for c in cells:
                    cs = c.strip()
                    if len(cs) == 3 and cs.isalpha() and cs.isupper():
                        code = cs
                        break
            if not code:
                continue
            
            tts = parse_number(cells[tts_idx])
            ttb = parse_number(cells[ttb_idx])
            if tts is None or ttb is None:
                continue
            
            ttm = round((tts + ttb) / 2, 4)
            rates[code] = {"TTS": tts, "TTB": ttb, "TTM": ttm}
        
        if rates:
            break
    
    return rates, page_date, tables_info


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_mufg(target_date: date):
    """複数URLを試行してMUFGレート取得"""
    id_str = target_date.strftime("%Y%m%d")
    
    urls = [
        f"https://www.murc-kawasesouba.jp/fx/past/index.php?id={id_str}",
        f"https://www.murc-kawasesouba.jp/fx/historical/k_{id_str}.php",
        f"https://www.murc-kawasesouba.jp/fx/past_3month_result.php?id={id_str}",
        f"https://www.murc-kawasesouba.jp/fx/index.php",  # 本日ページ(最終フォールバック)
    ]
    
    debug_log = []
    
    for url in urls:
        try:
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            res.encoding = res.apparent_encoding or "shift_jis"
            debug_log.append({
                "url": url,
                "status": res.status_code,
                "size": len(res.text),
            })
            
            if res.status_code != 200 or len(res.text) < 1000:
                continue
            
            rates, page_date, tables_info = parse_html_for_rates(res.text)
            debug_log[-1]["page_date"] = page_date
            debug_log[-1]["tables_found"] = len(tables_info)
            debug_log[-1]["currencies_found"] = len(rates)
            
            if rates:
                return rates, page_date, url, debug_log, res.text
        except Exception as e:
            debug_log.append({"url": url, "error": str(e)})
            continue
    
    return None, None, None, debug_log, None


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
        rates, page_date, used_url, debug_log, raw_html = fetch_mufg(target_date)
        
        if not rates:
            st.error("❌ どのURLからもレート取得できませんでした")
            with st.expander("🔧 デバッグ情報(必読)"):
                st.json(debug_log)
                if raw_html:
                    st.subheader("取得HTML(冒頭2000文字)")
                    st.code(raw_html[:2000])
        else:
            req_str = target_date.strftime("%Y-%m-%d")
            if page_date and page_date != req_str:
                st.warning(f"⚠ 指定日 {req_str} のデータが無く、ページ表示日は {page_date} です。"
                           f"土日祝・休業日・未来日付の可能性があります。")
            
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
                st.caption("↑ 右上のコピーアイコンでコピー")

                with st.expander("📊 当日の全レート"):
                    df_show = pd.DataFrame(rates).T
                    df_show.index.name = "通貨"
                    st.dataframe(df_show, use_container_width=True)
            
            with st.expander("🔧 デバッグ情報"):
                st.write("使用URL:", used_url)
                st.json(debug_log)

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
