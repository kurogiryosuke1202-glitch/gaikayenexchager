import streamlit as st
import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta
import pandas as pd

st.set_page_config(page_title="外貨→円 変換", page_icon="💱")
st.title("💱 外貨 → 円 変換アプリ")
st.caption("三菱UFJ銀行 公表対顧客外国為替相場 (MURC掲載) を使用")

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
    "DKK": "デンマーク・クローネ",
    "NOK": "ノルウェー・クローネ",
    "SEK": "スウェーデン・クローナ",
}
PER_100 = ["KRW", "IDR"]


def parse_number(text: str):
    """文字列から数値を抽出。unquoted等はNone"""
    if not text:
        return None
    t = str(text).strip().replace(",", "").replace("\xa0", "")
    try:
        return float(t)
    except ValueError:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_mufg(target_date: date):
    """MUFGページからレート辞書を取得"""
    id_str = target_date.strftime("%Y%m%d")
    
    # 過去ページ → 本日ページの順で試行
    urls = [
        f"https://www.murc-kawasesouba.jp/fx/past/index.php?id={id_str}",
        f"https://www.murc-kawasesouba.jp/fx/lastmonth.php?id={id_str}",
    ]
    
    html = None
    used_url = None
    for url in urls:
        try:
            res = requests.get(
                url,
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15,
            )
            res.encoding = res.apparent_encoding or "shift_jis"
            if res.status_code == 200 and len(res.text) > 1000:
                html = res.text
                used_url = url
                break
        except Exception:
            continue
    
    if not html:
        raise RuntimeError("MUFGサイトに接続できませんでした")
    
    soup = BeautifulSoup(html, "html.parser")
    
    # 全テーブルを走査して、USD行を含むものを取得
    rates = {}
    page_date = None
    
    # 日付検出(ページ内テキストから)
    text_all = soup.get_text()
    import re
    m = re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日", text_all)
    if m:
        page_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 3:
            continue
        
        # ヘッダー行を解析(TTS/TTBの列位置を取得)
        header_cells = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]
        if not any("TTS" in h.upper() for h in header_cells):
            continue
        
        tts_idx = next((i for i, h in enumerate(header_cells) if "TTS" in h.upper()), None)
        ttb_idx = next((i for i, h in enumerate(header_cells) if "TTB" in h.upper()), None)
        code_idx = next((i for i, h in enumerate(header_cells) if "Code" in h or "略称" in h), None)
        
        if tts_idx is None or ttb_idx is None:
            continue
        
        # データ行を解析
        for tr in rows[1:]:
            cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) <= max(tts_idx, ttb_idx):
                continue
            
            # 通貨コード取得(code_idxが無ければ全セルから3文字大文字を探す)
            code = None
            if code_idx is not None and code_idx < len(cells):
                code = cells[code_idx].strip()
            if not code or len(code) != 3:
                for c in cells:
                    cs = c.strip()
                    if len(cs) == 3 and cs.isupper() and cs.isalpha():
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
            break  # 1つの表で見つかれば終了
    
    if not rates:
        raise ValueError(f"レート表が解析できません(取得URL: {used_url})")
    
    return rates, page_date, used_url


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
            rates, page_date, used_url = fetch_mufg(target_date)
            
            # ページ日付と指定日が違う場合の警告
            req_str = target_date.strftime("%Y-%m-%d")
            if page_date and page_date != req_str:
                st.warning(f"⚠ 指定日 {req_str} のデータが無く、ページには {page_date} のレートが表示されています。"
                           f"土日祝・休業日の可能性があります。")
            
            if code not in rates:
                st.error(f"❌ {code} のレートが見つかりません(unquotedの可能性)")
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
                st.caption("↑ 右上のコピーアイコンでコピーできます")

                with st.expander("📊 当日の全レート(TTM=(TTS+TTB)/2)"):
                    df_show = pd.DataFrame(rates).T
                    df_show.index.name = "通貨コード"
                    st.dataframe(df_show, use_container_width=True)
                
                with st.expander("🔧 デバッグ情報"):
                    st.write(f"取得URL: {used_url}")
                    st.write(f"検出通貨数: {len(rates)}")
        
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
