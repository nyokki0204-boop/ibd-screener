import yfinance as yf
import pandas as pd
import numpy as np
import warnings
import datetime
import os
import json
from collections import Counter
from zoneinfo import ZoneInfo
warnings.filterwarnings('ignore')

# ===== 師匠の条件（デイトレ寄り・日足ベース）=====
CHG_MIN       = 5.0      # 前日比 +5%以上
PRICE_MIN     = 0.75     # 株価 下限
PRICE_MAX     = 300.0    # 株価 上限
AVGVOL_MIN    = 500000   # 平均出来高 50万株以上
DOLLARVOL_MIN = 1.0      # 売買代金 100万ドル以上（単位:百万ドル）
RELVOL_MIN    = 1.0      # 出来高が平均以上
RS_MIN        = 60       # 約1年騰落率の順位 60以上
LOW52_MIN     = 30.0     # 52週安値から +30%以上
PERIOD        = '1y'     # 過去1年のデータを見る
MIN_COVERAGE  = 0.80    # 取得漏れが多い日の誤った結果を公開しない

# 銘柄リストは russell-screener から借りてくる
MONEX_URL = 'https://raw.githubusercontent.com/nyokki0204-boop/russell-screener/main/Monex_US_LIST.csv'
# セクター対応表も russell-screener から借りてくる
SECTOR_URL = 'https://raw.githubusercontent.com/nyokki0204-boop/russell-screener/main/data/sector_cache.csv'

def get_tickers():
    """マネックスの銘柄リストを読み込む"""
    try:
        for enc in ['shift_jis', 'cp932', 'utf-8']:
            try:
                df = pd.read_csv(MONEX_URL, header=None, skiprows=1,
                                 encoding=enc, on_bad_lines='skip')
                tickers = df[0].dropna().astype(str).str.strip()
                tickers = tickers[tickers.str.match(r'^[A-Z]{1,5}$')]
                if len(tickers) > 100:
                    print(f'銘柄リスト読み込み成功: {len(tickers)}銘柄')
                    return tickers.drop_duplicates().tolist()
            except Exception:
                continue
        print('銘柄リスト読み込み失敗')
        return []
    except Exception as e:
        print(f'エラー: {e}')
        return []

def get_sector_map():
    """セクター対応表を読み込む（銘柄→セクター）"""
    try:
        df = pd.read_csv(SECTOR_URL)
        df = df.drop_duplicates('ticker').set_index('ticker')
        print(f'セクター対応表読み込み成功: {len(df)}銘柄')
        return df
    except Exception as e:
        print(f'セクター対応表読み込み失敗: {e}')
        return None

def calc_perf(close):
    """取得した約1年の日足の最初と最後の終値から騰落率を計算する。"""
    try:
        if len(close) < 60:
            return None
        return float(close.iloc[-1] / close.iloc[0])
    except (IndexError, TypeError, ValueError, ZeroDivisionError):
        return None

def session_date(df):
    """米国の日足の日付。取得日や日本時間の実行日とは分けて扱う。"""
    last = pd.Timestamp(df.index[-1])
    return last.tz_convert(ZoneInfo('America/New_York')).date().isoformat() if last.tzinfo else last.date().isoformat()

def save_scan_status(**kwargs):
    os.makedirs('data', exist_ok=True)
    status = {'checked_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), **kwargs}
    with open('data/scan_status.json', 'w', encoding='utf-8') as f:
        json.dump(status, f, ensure_ascii=False, indent=2)

def save_sector_metrics(df, data_store, sector_map, today):
    """同じ日に取得できた銘柄を分母にしてセクター通過率を残す。"""
    eligible = Counter()
    for ticker in data_store:
        sector = 'その他'
        if sector_map is not None and ticker in sector_map.index:
            sector = sector_map.loc[ticker, 'sector']
        eligible[str(sector) if pd.notna(sector) else 'その他'] += 1
    passed = df.groupby('sector')['ticker'].count().to_dict() if len(df) else {}
    rows = [{'date': today, 'sector': sector, 'eligible': count,
             'passed': int(passed.get(sector, 0)),
             'pass_rate': round(100 * passed.get(sector, 0) / count, 2)}
            for sector, count in sorted(eligible.items())]
    path = 'data/sector_metrics.csv'
    new = pd.DataFrame(rows, columns=['date', 'sector', 'eligible', 'passed', 'pass_rate'])
    if os.path.exists(path):
        old = pd.read_csv(path)
        new = pd.concat([old[old['date'] != today], new], ignore_index=True)
    new.sort_values(['date', 'sector']).to_csv(path, index=False, encoding='utf-8-sig')

def save_sector_history(df, today):
    """セクター別の銘柄数を日付つきで記録する（変遷用のノート）"""
    history_path = 'data/sector_history.csv'
    if 'sector' in df.columns and len(df) > 0:
        sector_counts = df.groupby('sector')['ticker'].count().to_dict()
    else:
        sector_counts = {}
    row = {'date': today, 'total': len(df)}
    for sec, cnt in sector_counts.items():
        row[sec] = cnt
    new_row = pd.DataFrame([row])
    if os.path.exists(history_path):
        history = pd.read_csv(history_path)
        history = history[history['date'] != today]
        history = pd.concat([history, new_row], ignore_index=True)
    else:
        history = new_row
    history = history.sort_values('date')
    history = history.fillna(0)
    history.to_csv(history_path, index=False, encoding='utf-8-sig')
    print(f'セクター履歴を保存: {len(history)}日分')

def save_ticker_history(df, today):
    """抽出された銘柄そのものを日付つきで記録する（日々のリスト）"""
    history_path = 'data/ticker_history.csv'

    # 今日抽出された銘柄に、日付をつけて記録用の表を作る
    if len(df) > 0:
        today_df = df.copy()
        today_df.insert(0, 'date', today)   # 先頭に日付の列を足す
    else:
        # 今日は0件でも「0件だった」と分かるように空の記録を残す
        today_df = pd.DataFrame([{'date': today, 'ticker': '(該当なし)'}])

    # 既にノートがあれば、そこに書き足す（同じ日付は上書き）
    if os.path.exists(history_path):
        old = pd.read_csv(history_path)
        old = old[old['date'] != today]
        history = pd.concat([old, today_df], ignore_index=True)
    else:
        history = today_df

    history.to_csv(history_path, index=False, encoding='utf-8-sig')
    print(f'銘柄履歴を保存: のべ{len(history)}行')

# ===== メイン処理 =====
def run_scan():
    tickers = get_tickers()
    if len(tickers) == 0:
        save_scan_status(ok=False, reason='銘柄リストを取得できませんでした')
        print('銘柄が取得できませんでした')
        exit(1)

    sector_map = get_sector_map()

    print(f'{len(tickers)}銘柄をスキャンします...')

    # 1回目：全銘柄の約1年騰落率を集めて、取得可能銘柄内の順位を作る
    perfs = {}
    data_store = {}
    failures = Counter()
    dates = Counter()
    for idx, ticker in enumerate(tickers, 1):
        try:
            raw = yf.download(ticker, period=PERIOD, interval='1d',
                              progress=False, auto_adjust=True)
            if raw is None or len(raw) < 60:
                failures['履歴不足'] += 1
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            df = raw[['Close','High','Low','Volume']].dropna()
            if len(df) < 60:
                failures['履歴不足'] += 1
                continue
            perf = calc_perf(df['Close'])
            if perf is not None:
                perfs[ticker] = perf
                data_store[ticker] = df
                dates[session_date(df)] += 1
            else:
                failures['計算不可'] += 1
        except Exception as e:
            failures[type(e).__name__] += 1
            continue
        if idx % 200 == 0:
            print(f'  {idx}/{len(tickers)} 取得中...')

    print(f'データ取得完了: {len(perfs)}銘柄')

    # 最新取引日が一致しない銘柄を混ぜない。失敗日は前回の正常な結果を保持する。
    market_date = dates.most_common(1)[0][0] if dates else None
    stale = [ticker for ticker, df in data_store.items() if session_date(df) != market_date]
    for ticker in stale:
        del data_store[ticker]
        del perfs[ticker]
    coverage = len(data_store) / len(tickers)
    if market_date is None or coverage < MIN_COVERAGE:
        save_scan_status(ok=False, reason='データ取得率が基準未満です',
                         market_date=market_date, universe=len(tickers),
                         fetched=len(data_store), stale=len(stale),
                         coverage=round(coverage, 4), errors=dict(failures))
        raise RuntimeError(f'スキャン未完了: {len(data_store)}/{len(tickers)}銘柄 ({coverage:.1%})')

    # 米国の引けから1時間以内の足は未確定の可能性があるため公開しない。
    now_et = datetime.datetime.now(ZoneInfo('America/New_York'))
    if market_date == now_et.date().isoformat() and now_et.time() < datetime.time(17, 0):
        save_scan_status(ok=False, reason='米国市場の日足が未確定です', market_date=market_date,
                         universe=len(tickers), fetched=len(data_store), coverage=round(coverage, 4))
        raise RuntimeError('米国市場の日足が未確定です')

    previous_path = 'data/last_updated.txt'
    previous_date = ''
    if os.path.exists(previous_path):
        with open(previous_path, encoding='utf-8') as f:
            previous_date = f.read().strip()
    if previous_date and market_date < previous_date:
        save_scan_status(ok=False, reason='取得データが保存済みの取引日より古いです',
                         market_date=market_date, previous_date=previous_date,
                         universe=len(tickers), fetched=len(data_store), coverage=round(coverage, 4))
        raise RuntimeError('取得データが保存済みの取引日より古いです')
    unchanged = market_date == previous_date

    # 約1年騰落率の順位（1〜99）。IBD社のRS Ratingとは異なる。
    perf_series = pd.Series(perfs)
    rs_rating = perf_series.rank(pct=True) * 98 + 1
    rs_rating = rs_rating.round().astype(int)

    # 2回目：各銘柄が条件を満たすかチェック
    results = []
    evaluated = 0
    for ticker, df in data_store.items():
        try:
            close  = df['Close'].astype(float)
            high   = df['High'].astype(float)
            low    = df['Low'].astype(float)
            volume = df['Volume'].astype(float)

            price     = float(close.iloc[-1])
            prev      = float(close.iloc[-2])
            chg_pct   = (price - prev) / prev * 100
            avg_vol   = float(volume.iloc[-51:-1].mean())
            today_vol = float(volume.iloc[-1])
            rel_vol   = today_vol / avg_vol if avg_vol > 0 else 0
            dollar_vol = price * today_vol / 1_000_000
            low52     = float(low.iloc[-252:].min()) if len(low) >= 252 else float(low.min())
            from_low  = (price - low52) / low52 * 100
            rs        = int(rs_rating.get(ticker, 0))

            c1 = chg_pct   >= CHG_MIN
            c2 = PRICE_MIN <= price <= PRICE_MAX
            c3 = avg_vol   >= AVGVOL_MIN
            c4 = dollar_vol >= DOLLARVOL_MIN
            c5 = rel_vol   >= RELVOL_MIN
            c6 = rs        >= RS_MIN
            c7 = from_low  >= LOW52_MIN
            evaluated += 1

            if all([c1, c2, c3, c4, c5, c6, c7]):
                sector = 'その他'
                industry = ''
                if sector_map is not None and ticker in sector_map.index:
                    sector = sector_map.loc[ticker, 'sector']
                    if 'industry' in sector_map.columns:
                        industry = sector_map.loc[ticker, 'industry']
                if pd.isna(sector):
                    sector = 'その他'
                if pd.isna(industry):
                    industry = ''

                results.append({
                    'ticker'     : ticker,
                    'sector'     : sector,
                    'industry'   : industry,
                    '前日比%'    : round(chg_pct, 1),
                    '株価'       : round(price, 2),
                    '平均出来高' : int(avg_vol),
                    '売買代金M$' : round(dollar_vol, 1),
                    'RelVol'     : round(rel_vol, 2),
                    'RS'         : rs,
                    '52W安値比%' : round(from_low, 1),
                })
        except Exception as e:
            failures[f'判定:{type(e).__name__}'] += 1
            continue

    if evaluated / len(tickers) < MIN_COVERAGE:
        save_scan_status(ok=False, reason='判定できた銘柄が基準未満です',
                         market_date=market_date, universe=len(tickers),
                         fetched=len(data_store), evaluated=evaluated,
                         coverage=round(evaluated / len(tickers), 4), errors=dict(failures))
        raise RuntimeError(f'判定未完了: {evaluated}/{len(tickers)}銘柄')

    # 結果を保存
    os.makedirs('data', exist_ok=True)
    if len(results) > 0:
        out = pd.DataFrame(results).sort_values('RS', ascending=False)
    else:
        out = pd.DataFrame(columns=['ticker','sector','industry','前日比%','株価',
                                     '平均出来高','売買代金M$','RelVol','RS','52W安値比%'])
    out.to_csv('data/results.csv', index=False, encoding='utf-8-sig')

    today = market_date
    with open('data/last_updated.txt', 'w') as f:
        f.write(today)

    # セクター別の変遷を記録する
    save_sector_history(out, today)
    save_sector_metrics(out, data_store, sector_map, today)
    # 抽出された銘柄そのものを記録する
    save_ticker_history(out, today)

    save_scan_status(ok=True, market_date=today, universe=len(tickers),
                     fetched=len(data_store), evaluated=evaluated, stale=len(stale),
                     coverage=round(evaluated / len(tickers), 4), matched=len(out), unchanged=unchanged,
                     errors=dict(failures), rs_method='約1年騰落率の取得可能銘柄内順位')

    print(f'完了！条件クリア: {len(results)}銘柄')


if __name__ == '__main__':
    run_scan()
