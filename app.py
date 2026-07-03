import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os

try:
    import japanize_matplotlib
except:
    pass

st.set_page_config(page_title="IBD Screener", page_icon="🚀", layout="wide")
st.title("🚀 IBD式スクリーナー")
st.caption("師匠の条件 — デイトレ寄り（日足ベース）")

DATA_PATH     = 'data/results.csv'
UPDATED_PATH  = 'data/last_updated.txt'
HISTORY_PATH  = 'data/sector_history.csv'
TICKER_HIST   = 'data/ticker_history.csv'

if not os.path.exists(DATA_PATH):
    st.warning('まだスキャン結果がありません。')
    st.stop()

df = pd.read_csv(DATA_PATH)

if os.path.exists(UPDATED_PATH):
    with open(UPDATED_PATH) as f:
        last_updated = f.read().strip()
else:
    last_updated = '不明'

st.info(f'📅 最終スキャン日: {last_updated}')

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

c1, c2 = st.columns(2)
c1.metric('条件クリア銘柄', f'{len(df)}銘柄')
if 'sector' in df.columns:
    c2.metric('セクター数', f'{df["sector"].nunique()}')

if len(df) == 0:
    st.warning('今回は条件を満たす銘柄がありませんでした。')
    st.stop()

def color_rs(val):
    try:
        v = int(val)
        if v >= 90: return 'background-color:#1a6e1a;color:white'
        if v >= 80: return 'background-color:#2e7d32;color:white'
        if v >= 70: return 'background-color:#4a7a1a;color:white'
        return ''
    except:
        return ''

def color_chg(val):
    try:
        v = float(val)
        if v >= 10: return 'background-color:#1a6e1a;color:white'
        if v >= 5:  return 'background-color:#2e7d32;color:white'
        return ''
    except:
        return ''

if 'sector' in df.columns:
    show_cols = ['ticker','sector','industry','前日比%','株価',
                 '平均出来高','売買代金M$','RelVol','RS','52W安値比%']
else:
    show_cols = ['ticker','前日比%','株価',
                 '平均出来高','売買代金M$','RelVol','RS','52W安値比%']
show_cols = [c for c in show_cols if c in df.columns]

# タブを5つにする（履歴を追加）
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ['🚀 全銘柄', '📂 セクター別', '📊 セクターサマリー', '📈 変遷グラフ', '🗓️ 銘柄履歴']
)

with tab1:
    st.subheader(f'🚀 条件クリア: {len(df)}銘柄')
    df_show = df.reset_index(drop=True)
    df_show.index += 1
    st.dataframe(
        df_show[show_cols].style
        .map(color_rs, subset=['RS'])
        .map(color_chg, subset=['前日比%']),
        use_container_width=True,
        height=500
    )
    st.subheader('📋 TradingView用リスト')
    st.code(','.join(df['ticker'].tolist()))

with tab2:
    st.subheader('📂 セクター別に見る')
    if 'sector' not in df.columns:
        st.info('セクター情報がありません。次回スキャンから表示されます。')
    else:
        sectors = sorted(df['sector'].dropna().unique().tolist())
        selected = st.selectbox('セクターを選択', ['すべて'] + sectors)
        if selected == 'すべて':
            df_sec = df
        else:
            df_sec = df[df['sector'] == selected]
        df_sec = df_sec.reset_index(drop=True)
        df_sec.index += 1
        st.write(f'{len(df_sec)}銘柄')
        st.dataframe(
            df_sec[show_cols].style
            .map(color_rs, subset=['RS'])
            .map(color_chg, subset=['前日比%']),
            use_container_width=True,
            height=500
        )
        if len(df_sec) > 0:
            st.code(','.join(df_sec['ticker'].tolist()))

with tab3:
    st.subheader('📊 セクターサマリー')
    if 'sector' not in df.columns:
        st.info('セクター情報がありません。次回スキャンから表示されます。')
    else:
        summary = (
            df.groupby('sector')
            .agg(
                銘柄数=('ticker', 'count'),
                平均RS=('RS', 'mean'),
                平均前日比=('前日比%', 'mean'),
            )
            .sort_values('銘柄数', ascending=False)
            .round(1)
        )
        st.dataframe(summary, use_container_width=True)
        st.caption('今日どのセクターに勢いが集まっているかが分かります')

with tab4:
    st.subheader('📈 セクター別 変遷グラフ')
    if not os.path.exists(HISTORY_PATH):
        st.info('まだ変遷データがありません。スキャンを重ねると表示されます。')
    else:
        hist = pd.read_csv(HISTORY_PATH)
        if len(hist) < 2:
            st.info('変遷グラフは2日分以上の記録が必要です。次回スキャンから育っていきます。')
        else:
            hist['date'] = pd.to_datetime(hist['date'])
            hist = hist.sort_values('date')
            sector_cols = [c for c in hist.columns if c not in ['date', 'total']]

            fig, ax = plt.subplots(figsize=(12, 6), facecolor='#0d1117')
            ax.set_facecolor('#0d1117')
            ax.tick_params(colors='#aaaaaa', labelsize=9)
            ax.grid(True, alpha=0.12, color='#444444')
            for spine in ax.spines.values():
                spine.set_color('#2a2a2a')
            palette = ['#00ff88','#ff6b6b','#4ecdc4','#ffd93d','#a29bfe',
                       '#fd79a8','#74b9ff','#e17055','#55efc4','#fdcb6e','#b2bec3']
            for i, col in enumerate(sector_cols):
                if hist[col].sum() > 0:
                    ax.plot(hist['date'], hist[col],
                            color=palette[i % len(palette)],
                            linewidth=2.0, marker='o', markersize=4, label=col)
            ax.set_title('セクター別 銘柄数の変遷', color='white',
                         fontsize=12, fontweight='bold')
            ax.set_ylabel('銘柄数', color='#aaaaaa')
            ax.legend(facecolor='#1a1a1a', labelcolor='white',
                      fontsize=8, loc='upper left', ncol=2)
            plt.xticks(rotation=30)
            plt.tight_layout()
            st.pyplot(fig)

            st.subheader('📊 合計銘柄数の変遷')
            fig2, ax2 = plt.subplots(figsize=(12, 3), facecolor='#0d1117')
            ax2.set_facecolor('#0d1117')
            ax2.tick_params(colors='#aaaaaa', labelsize=9)
            ax2.grid(True, alpha=0.12, color='#444444')
            for spine in ax2.spines.values():
                spine.set_color('#2a2a2a')
            ax2.plot(hist['date'], hist['total'], color='#00ff88',
                     linewidth=2.5, marker='o', markersize=5)
            ax2.set_ylabel('合計銘柄数', color='#aaaaaa')
            plt.xticks(rotation=30)
            plt.tight_layout()
            st.pyplot(fig2)

with tab5:
    st.subheader('🗓️ 銘柄履歴（日ごとに抽出された銘柄）')
    if not os.path.exists(TICKER_HIST):
        st.info('まだ履歴がありません。スキャンを重ねると、日ごとの銘柄がたまっていきます。')
    else:
        thist = pd.read_csv(TICKER_HIST)
        # 日付の一覧を新しい順に並べる
        dates = sorted(thist['date'].dropna().unique().tolist(), reverse=True)

        if len(dates) == 0:
            st.info('まだ履歴がありません。')
        else:
            pick = st.selectbox('日付を選ぶ', dates)
            day_df = thist[thist['date'] == pick].reset_index(drop=True)
            day_df.index += 1

            st.write(f'{pick} の抽出銘柄：{len(day_df)}件')

            # その日の表を見せる（存在する列だけ）
            day_cols = [c for c in ['ticker','sector','industry','前日比%','株価',
                                    '売買代金M$','RelVol','RS','52W安値比%']
                        if c in day_df.columns]
            st.dataframe(day_df[day_cols], use_container_width=True, height=400)

            # TradingView用のコピー
            if 'ticker' in day_df.columns:
                st.code(','.join(day_df['ticker'].astype(str).tolist()))

st.caption('データ: yfinance  |  対象: マネックス証券取扱銘柄')
