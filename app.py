import streamlit as st
import pandas as pd
import os

st.set_page_config(page_title="IBD Screener", page_icon="🚀", layout="wide")
st.title("🚀 IBD式スクリーナー")
st.caption("師匠の条件 — デイトレ寄り（日足ベース）")

DATA_PATH    = 'data/results.csv'
UPDATED_PATH = 'data/last_updated.txt'

# 結果がまだ無い場合
if not os.path.exists(DATA_PATH):
    st.warning('まだスキャン結果がありません。')
    st.stop()

df = pd.read_csv(DATA_PATH)

# 最終更新日を表示
if os.path.exists(UPDATED_PATH):
    with open(UPDATED_PATH) as f:
        last_updated = f.read().strip()
else:
    last_updated = '不明'

st.info(f'📅 最終スキャン日: {last_updated}')

# 条件の説明
with st.expander('📋 スクリーニング条件'):
    st.markdown('''
    - 前日比 ≥ +5%
    - 株価 $0.75〜$300
    - 平均出来高 ≥ 50万株
    - 売買代金 ≥ $1M
    - RelVol ≥ 1（出来高が平均以上）
    - IBD式RS ≥ 60
    - 52週安値から ≥ +30%
    ''')

# 件数を大きく表示
st.metric('条件クリア銘柄', f'{len(df)}銘柄')

if len(df) == 0:
    st.warning('今回は条件を満たす銘柄がありませんでした。')
    st.stop()

# 色付けの関数（RSが高いほど緑を濃く）
def color_rs(val):
    try:
        v = int(val)
        if v >= 90: return 'background-color:#1a6e1a;color:white'
        if v >= 80: return 'background-color:#2e7d32;color:white'
        if v >= 70: return 'background-color:#4a7a1a;color:white'
        return ''
    except:
        return ''

# 前日比の色付け（プラスは緑）
def color_chg(val):
    try:
        v = float(val)
        if v >= 10: return 'background-color:#1a6e1a;color:white'
        if v >= 5:  return 'background-color:#2e7d32;color:white'
        return ''
    except:
        return ''

# 表を表示
df_show = df.reset_index(drop=True)
df_show.index += 1

st.dataframe(
    df_show.style
    .map(color_rs, subset=['RS'])
    .map(color_chg, subset=['前日比%']),
    use_container_width=True,
    height=600
)

# TradingView用に銘柄をまとめてコピーできるように
st.subheader('📋 TradingView用リスト')
st.caption('下のリストをコピーしてTradingViewのウォッチリストに貼り付けられます')
st.code(','.join(df['ticker'].tolist()))

st.caption(f'データ: yfinance  |  対象: マネックス証券取扱銘柄')
