import yfinance as yf
import pandas as pd
import numpy as np
import warnings
import datetime
import os
warnings.filterwarnings('ignore')

# ===== 師匠の条件（デイトレ寄り・日足ベース）=====
CHG_MIN       = 5.0      # 前日比 +5%以上
PRICE_MIN     = 0.75     # 株価 下限
PRICE_MAX     = 300.0    # 株価 上限
AVGVOL_MIN    = 500000   # 平均出来高 50万株以上
DOLLARVOL_MIN = 1.0      # 売買代金 100万ドル以上（単位:百万ドル）
RELVOL_MIN    = 1.0      # 出来高が平均以上
RS_MIN        = 60       # IBD式RSレーティング 60以上
LOW52_MIN     = 30.0     # 52週安値から +30%以上
PERIOD        = '1y'     # 過去1年のデータを見る

# 銘柄リストは russell-screener から借りてくる
MONEX_URL = 'https://raw.githubusercontent.com/nyokki0204-boop/russell-screener/main/Monex_US_LIST.csv'

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
                    return tickers.tolist()
            except Exception:
                continue
        print('銘柄リスト読み込み失敗')
        return []
    except Exception as e:
        print(f'エラー: {e}')
        return []

def calc_perf(close):
    """1年騰落率を計算（IBD式RSの元になる数字）"""
    try:
        if len(close) < 60:
            return None
        return float(close.iloc[-1] / close.iloc[0])
    except:
        return None

# ===== メイン処理 =====
if __name__ == '__main__':
    tickers = get_tickers()
    if len(tickers) == 0:
        print('銘柄が取得できませんでした')
        exit(1)

    print(f'{len(tickers)}銘柄をスキャンします...')

    # 1回目：全銘柄の1年騰落率を集めて、IBD式RSランキングを作る
    perfs = {}
    data_store = {}
    for idx, ticker in enumerate(tickers, 1):
        try:
            raw = yf.download(ticker, period=PERIOD, interval='1d',
                              progress=False, auto_adjust=True)
            if raw is None or len(raw) < 60:
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            df = raw[['Close','High','Low','Volume']].dropna()
            if len(df) < 60:
                continue
            perf = calc_perf(df['Close'])
            if perf is not None:
                perfs[ticker] = perf
                data_store[ticker] = df
        except Exception:
            continue
        if idx % 200 == 0:
            print(f'  {idx}/{len(tickers)} 取得中...')

    print(f'データ取得完了: {len(perfs)}銘柄')

    # IBD式RSレーティングを計算（1〜99、上位ほど高い）
    perf_series = pd.Series(perfs)
    rs_rating = perf_series.rank(pct=True) * 98 + 1  # 1〜99の範囲
    rs_rating = rs_rating.round().astype(int)

    # 2回目：各銘柄が条件を満たすかチェック
    results = []
    for ticker, df in data_store.items():
        try:
            close  = df['Close'].astype(float)
            high   = df['High'].astype(float)
            low    = df['Low'].astype(float)
            volume = df['Volume'].astype(float)

            price     = float(close.iloc[-1])
            prev      = float(close.iloc[-2])
            chg_pct   = (price - prev) / prev * 100
            avg_vol   = float(volume.iloc[-50:].mean())
            today_vol = float(volume.iloc[-1])
            rel_vol   = today_vol / avg_vol if avg_vol > 0 else 0
            dollar_vol = price * today_vol / 1_000_000   # 百万ドル単位
            low52     = float(low.iloc[-252:].min()) if len(low) >= 252 else float(low.min())
            from_low  = (price - low52) / low52 * 100
            rs        = int(rs_rating.get(ticker, 0))

            # 7条件をすべてチェック
            c1 = chg_pct   >= CHG_MIN
            c2 = PRICE_MIN <= price <= PRICE_MAX
            c3 = avg_vol   >= AVGVOL_MIN
            c4 = dollar_vol >= DOLLARVOL_MIN
            c5 = rel_vol   >= RELVOL_MIN
            c6 = rs        >= RS_MIN
            c7 = from_low  >= LOW52_MIN

            if all([c1, c2, c3, c4, c5, c6, c7]):
                results.append({
                    'ticker'     : ticker,
                    '前日比%'    : round(chg_pct, 1),
                    '株価'       : round(price, 2),
                    '平均出来高' : int(avg_vol),
                    '売買代金M$' : round(dollar_vol, 1),
                    'RelVol'     : round(rel_vol, 2),
                    'RS'         : rs,
                    '52W安値比%' : round(from_low, 1),
                })
        except Exception:
            continue

    # 結果を保存
    os.makedirs('data', exist_ok=True)
    if len(results) > 0:
        out = pd.DataFrame(results).sort_values('RS', ascending=False)
    else:
        out = pd.DataFrame(columns=['ticker','前日比%','株価','平均出来高',
                                     '売買代金M$','RelVol','RS','52W安値比%'])
    out.to_csv('data/results.csv', index=False, encoding='utf-8-sig')

    today = datetime.date.today().strftime('%Y-%m-%d')
    with open('data/last_updated.txt', 'w') as f:
        f.write(today)

    print(f'完了！条件クリア: {len(results)}銘柄')
