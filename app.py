import json
import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd
import streamlit as st

st.set_page_config(page_title='急伸・相対強度スクリーナー', page_icon='📈', layout='wide')

DATA_PATH = 'data/results.csv'
HISTORY_PATH = 'data/ticker_history.csv'
SECTOR_PATH = 'data/sector_metrics.csv'
LEGACY_SECTOR_PATH = 'data/sector_history.csv'
STATUS_PATH = 'data/scan_status.json'
UPDATED_PATH = 'data/last_updated.txt'
DISPLAY_COLUMNS = ['ticker', 'sector', 'industry', '前日比%', '株価', '平均出来高',
                   '売買代金M$', 'RelVol', 'RS', '52W安値比%']


def read_csv(path):
    return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()


def chart_link(base_url, ticker):
    if not base_url or not ticker:
        return ''
    parts = urlsplit(base_url.strip())
    if parts.scheme not in ('https', 'http') or not parts.netloc:
        return ''
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query['ticker'] = str(ticker)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def appearances(frame, history):
    """直近5取引日の登場回数と、前回までの履歴の有無を付ける。"""
    if frame.empty:
        return frame
    frame = frame.copy()
    if history.empty or not {'date', 'ticker'}.issubset(history.columns):
        frame['直近5日'] = 1
        frame['初登場'] = '—'
        return frame
    valid = history[history['ticker'].notna() & (history['ticker'] != '(該当なし)')].copy()
    dates = sorted(valid['date'].dropna().astype(str).unique(), reverse=True)
    current = str(last_updated)
    recent = [current] + [d for d in dates if d != current and d < current][:4]
    subset = valid[valid['date'].astype(str).isin(recent)]
    counts = subset.groupby('ticker')['date'].nunique()
    prior = valid[valid['date'].astype(str) < current]['ticker'].unique()
    frame['直近5日'] = frame['ticker'].map(counts).fillna(1).astype(int)
    frame['初登場'] = frame['ticker'].apply(lambda t: 'NEW' if t not in prior else '')
    return frame


st.title('📈 急伸・相対強度スクリーナー')
st.caption('前日比・出来高・約1年の相対強度から、米国株の日足を確認')

if not os.path.exists(DATA_PATH):
    st.warning('スキャン結果がまだありません。定期スキャンの状態を確認してください。')
    st.stop()

results = read_csv(DATA_PATH)
history = read_csv(HISTORY_PATH)
sectors = read_csv(SECTOR_PATH)
legacy_sectors = read_csv(LEGACY_SECTOR_PATH)
status = {}
if os.path.exists(STATUS_PATH):
    try:
        with open(STATUS_PATH, encoding='utf-8') as f:
            status = json.load(f)
    except (ValueError, OSError):
        st.warning('スキャン状態ファイルを読み込めませんでした。')
last_updated = '不明'
if os.path.exists(UPDATED_PATH):
    with open(UPDATED_PATH, encoding='utf-8') as f:
        last_updated = f.read().strip() or '不明'

if status and not status.get('ok', False):
    st.error(f"最新のスキャンは未完了です：{status.get('reason', '原因不明')}。下は前回の正常な結果です。")
elif status.get('unchanged'):
    st.info('米国市場の新しい取引日はありません。前回の結果を表示しています。')
st.caption(f'米国市場の取引日：{last_updated}　｜　データ：yfinance / マネックス取扱銘柄')
if status.get('ok') and status.get('market_date') == last_updated:
    st.caption(f"取得 {status.get('fetched', 0):,}・判定 {status.get('evaluated', 0):,} "
               f"/ 対象 {status.get('universe', 0):,}銘柄 "
               f"(判定率 {status.get('coverage', 0):.1%})　｜　日付不一致 {status.get('stale', 0)}銘柄")

with st.sidebar:
    st.header('表示設定')
    chart_base = st.text_input('マイチャートの公開URL（任意）',
                               value=os.environ.get('MYCHART_URL', ''),
                               placeholder='https://…/mychart.html',
                               help='銘柄を開くときに ?ticker=銘柄 を付けます。マイチャート側にもURL読込が必要です。')
    if chart_base and not chart_link(chart_base, 'AAPL'):
        st.warning('http または https で始まるURLを入力してください。')
    st.caption('RSは取得できた銘柄の約1年騰落率の順位です。IBD社のRS Ratingではありません。')
    with st.expander('抽出条件'):
        st.markdown('前日比 +5%以上／株価 $0.75〜$300／過去50日平均出来高50万株以上／'
                    '当日売買代金 $1M以上／RelVol 1以上／RS 60以上／52週安値比 +30%以上。'
                    'RelVolの平均出来高は当日を含みません。')

results = appearances(results, history)
if not results.empty:
    results = results.sort_values(['直近5日', 'RS'], ascending=False)

st.subheader('今日の変化')
current_metrics = pd.DataFrame()
if not sectors.empty and {'date', 'sector', 'eligible', 'passed', 'pass_rate'}.issubset(sectors.columns):
    current_metrics = sectors[sectors['date'].astype(str) == last_updated].copy()
    if not current_metrics.empty:
        older = sectors[sectors['date'].astype(str) < last_updated].copy()
        prev_dates = sorted(older['date'].astype(str).unique(), reverse=True)[:5]
        prev = older[older['date'].astype(str).isin(prev_dates)]
        baseline = prev.groupby('sector').agg(passed_prev=('passed', 'sum'),
                                               eligible_prev=('eligible', 'sum'))
        current_metrics = current_metrics.join(baseline, on='sector')
        current_metrics['前5日比pt'] = (
            current_metrics['pass_rate'] -
            100 * current_metrics['passed_prev'] / current_metrics['eligible_prev']
        ).round(2)

m1, m2, m3 = st.columns(3)
m1.metric('条件通過', f'{len(results)}銘柄')
m2.metric('初登場', f"{(results['初登場'] == 'NEW').sum() if '初登場' in results else 0}銘柄")
m3.metric('セクター', f'{results["sector"].nunique() if "sector" in results else 0}分野')

if not current_metrics.empty:
    focus = current_metrics[(current_metrics['eligible'] >= 10) &
                            (current_metrics['sector'] != 'その他')].copy()
    focus = focus.sort_values('前5日比pt', ascending=False)
    if not focus.empty:
        st.markdown('**通過率の変化（前5取引日との比較）**')
        show = focus[['sector', 'passed', 'eligible', 'pass_rate', '前5日比pt']].rename(columns={
            'sector': 'セクター', 'passed': '通過', 'eligible': '取得',
            'pass_rate': '通過率%', '前5日比pt': '前5日比pt'})
        st.dataframe(show, width='stretch', hide_index=True,
                     column_config={'通過率%': st.column_config.ProgressColumn('通過率%',
                                    min_value=0, max_value=100, format='%.1f%%')})
        st.caption('通過率の分母は、その日に価格データを取得できた同セクターの銘柄数。'
                   '前5日比は過去5取引日の合計から計算。少数セクターは除外。')

if not results.empty:
    st.markdown('**連続して目に入る銘柄**')
    leaders = results[results['直近5日'] >= 2].head(12)
    if leaders.empty:
        st.caption('直近5取引日で複数回抽出された銘柄はありません。')
    else:
        st.dataframe(leaders[[c for c in ['ticker', 'sector', '直近5日', 'RS', 'RelVol', '前日比%']
                                  if c in leaders]], width='stretch', hide_index=True)

all_tab, sector_tab, trend_tab, history_tab = st.tabs(['銘柄一覧', 'セクター', '推移', '履歴'])
with all_tab:
    if results.empty:
        st.info('今回は条件を満たす銘柄がありませんでした。履歴と推移は引き続き確認できます。')
    else:
        selected_sector = st.selectbox('セクター', ['すべて'] + sorted(results['sector'].dropna().unique()))
        shown = results if selected_sector == 'すべて' else results[results['sector'] == selected_sector]
        shown = shown.copy()
        if chart_base:
            shown['マイチャート'] = shown['ticker'].map(lambda t: chart_link(chart_base, t))
        cols = ['ticker', '初登場', '直近5日'] + DISPLAY_COLUMNS[1:]
        if chart_base:
            cols += ['マイチャート']
        st.dataframe(shown[[c for c in cols if c in shown]], width='stretch',
                     hide_index=True, height=510,
                     column_config={'マイチャート': st.column_config.LinkColumn('マイチャート',
                                                                  display_text='開く')})
        st.code(','.join(shown['ticker'].astype(str)))
        st.download_button('CSVをダウンロード', shown.to_csv(index=False).encode('utf-8-sig'),
                           file_name=f'ibd-screener-{last_updated}.csv', mime='text/csv')

with sector_tab:
    if current_metrics.empty:
        st.info('通過率は次回の正常なスキャンから表示されます。')
    else:
        st.dataframe(current_metrics[['sector', 'passed', 'eligible', 'pass_rate', '前5日比pt']]
                     .sort_values('pass_rate', ascending=False), width='stretch',
                     hide_index=True)
        st.caption('これは「+5%などの抽出条件を満たす銘柄の広がり」です。'
                   'セクターETFの値動きや長期RSとは別の指標です。')

with trend_tab:
    if not current_metrics.empty:
        pivot = sectors.pivot_table(index='date', columns='sector', values='pass_rate')
        selected = st.multiselect('比較するセクター', pivot.columns.tolist(),
                                  default=focus.head(4)['sector'].tolist() if not focus.empty else [])
        if selected:
            st.line_chart(pivot[selected].tail(60), height=340)
            st.caption('日々の通過率。取得銘柄数が少ない日は変動が大きくなります。')
    if not legacy_sectors.empty and 'total' in legacy_sectors:
        st.markdown('**条件通過銘柄数の履歴**')
        st.line_chart(legacy_sectors.set_index('date')['total'].tail(60), height=260)

with history_tab:
    if history.empty or 'date' not in history:
        st.info('銘柄履歴はまだありません。')
    else:
        dates = sorted(history['date'].dropna().astype(str).unique(), reverse=True)
        picked = st.selectbox('米国市場の取引日', dates)
        past = history[history['date'].astype(str) == picked].copy()
        past = past[past['ticker'].notna() & (past['ticker'] != '(該当なし)')]
        st.write(f'{picked}：{len(past)}銘柄')
        if past.empty:
            st.info('この日は該当銘柄がありませんでした。')
        else:
            st.dataframe(past[[c for c in DISPLAY_COLUMNS if c in past]],
                         width='stretch', hide_index=True)
            st.code(','.join(past['ticker'].astype(str)))
