import streamlit as st
from datetime import datetime, timedelta, time as dt_time
import pytz
import time as py_time
from scraper import PokerfansScraper
import urllib.parse
import re
import concurrent.futures

# 日本のタイムゾーン
JST = pytz.timezone('Asia/Tokyo')

# キャッシュデータを保持する関数
@st.cache_data(ttl=86400)  # 1日（86400秒）間キャッシュを保持

# 追加する関数：並列処理でページを取得
def fetch_pages_parallel(date_str, page_start, page_end, max_details):
    """指定範囲のページを並列で取得"""
    results = {}
    pages_to_fetch = range(page_start, min(page_end, st.session_state.fetch_total_pages))
    
    # 並列数を制限（3スレッド）
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        # ページごとに処理を送信
        future_to_page = {
            executor.submit(fetch_tournament_data, date_str, page, max_details): page
            for page in pages_to_fetch
        }
        
        # 結果を受け取り
        for future in concurrent.futures.as_completed(future_to_page):
            page = future_to_page[future]
            try:
                tournaments, _, _ = future.result()
                results[f"page_{page}"] = tournaments
                # 進捗表示を更新（ここではセッション変数を直接更新できない）
            except Exception as e:
                st.error(f"ページ {page + 1} の取得に失敗: {str(e)}")
    
    return results
def fetch_tournament_data(date_str, page, max_details):
    """
    トーナメント情報を取得してキャッシュする
    Args:
        date_str: 日付文字列 (YYYY/MM/DD)
        page: ページ番号
        max_details: 詳細ページの最大取得数
    Returns:
        (tournaments, pagination_info, processing_time)
    """
    start_time = py_time.time()
    
    scraper = PokerfansScraper(target_date=date_str)
    tournaments, pagination_info = scraper.get_tournament_list(
        page=page,
        max_details_per_page=max_details
    )
    
    end_time = py_time.time()
    processing_time = end_time - start_time
    
    return tournaments, pagination_info, processing_time

def format_money(amount: int) -> str:
    """金額を読みやすい形式に変換（カンマ区切りで表示）"""
    return f"{amount:,}"

def format_odds(entry_fee: int, current_entries: int, guarantee: int) -> str:
    """
    回収率を計算して文字列で返す
    保証賞金÷エントリー総額で計算（100%超えでバリュー有り）
    """
    # エントリー総額がゼロの場合はエラー回避
    total_entry_amount = entry_fee * current_entries
    
    if guarantee <= 0:
        return "保証なし"
    elif total_entry_amount <= 0:
        return "エントリー未確認"
    
    # 保証賞金÷エントリー総額（%表示）
    odds = (guarantee / total_entry_amount) * 100
    
    # バリューの判定をアイコンで表示
    if odds >= 150:
        return f"💰💰 {odds:.1f}%"  # 非常に良いバリュー
    elif odds >= 100:
        return f"💰 {odds:.1f}%"    # 良いバリュー
    else:
        return f"{odds:.1f}%"       # 標準

def is_tournament(title: str) -> bool:
    """タイトルからリングゲームを除外"""
    exclude_keywords = ['リング', 'コインリング', 'RING', 'Ring', 'ring']
    return not any(keyword in title for keyword in exclude_keywords)

def create_page_url(base_url: str, page: int) -> str:
    """ページ番号を含むURLを生成"""
    return f"{base_url}&size=50&page={page}"

def get_pagination_info(soup) -> dict:
    """ページネーション情報を取得"""
    pagination = soup.select_one('ul.pagination')
    if not pagination:
        return {'current_page': 0, 'total_pages': 1}
    
    # アクティブなページを取得
    current_page = int(pagination.select_one('li.active a').text) - 1  # 0-based indexに変換
    
    # 総ページ数を取得（最後のページ番号）
    page_numbers = [int(a.text) for a in pagination.select('li a') if a.text.isdigit()]
    total_pages = max(page_numbers) if page_numbers else 1
    
    return {'current_page': current_page, 'total_pages': total_pages}

def parse_time(time_str):
    """時間文字列をパース"""
    if not time_str:
        return None
    
    try:
        hours, minutes = map(int, time_str.split(':'))
        return hours, minutes
    except (ValueError, AttributeError):
        return None

def is_available(start_time_str, end_time_str):
    """
    トーナメントがまだ参加可能かを確認
    
    ルール：
    1. 深夜開始（0-6時）のトーナメント：
       - 現在が早朝（0-6時）なら、当日のイベントとして判定
       - 現在が日中/夜（7-23時）なら、翌日のイベントなので無視
    
    2. 日中/夜開始（7-23時）のトーナメント：
       - 現在時刻が開始時刻より前なら参加可能
       - 現在時刻が開始時刻より後なら、締切時刻と比較
       - 締切が翌日深夜（0-6時）の場合は特別処理
    
    Args:
        start_time_str: 開始時間 (HH:MM)
        end_time_str: 締切時間 (HH:MM)
    Returns:
        bool: 参加可能ならTrue
    """
    if not start_time_str:
        return False  # 開始時間がない場合は除外
    
    # 現在の日本時間
    now = datetime.now(JST)
    current_hour = now.hour
    current_minute = now.minute
    
    # 開始時間と締切時間をパース
    start_time = parse_time(start_time_str)
    if not start_time:
        return False
    
    start_hour, start_minute = start_time
    
    # ケース1: 深夜開始（0-6時）のトーナメント
    if 0 <= start_hour < 7:
        # 現在も深夜（0-6時）なら、開始時間と比較
        if 0 <= current_hour < 7:
            # 現在時刻 < 開始時刻なら参加可能
            return (current_hour < start_hour) or (current_hour == start_hour and current_minute < start_minute)
        else:
            # 現在が7時以降なら、このトーナメントは今日の早朝に終了済み
            return False
    
    # ケース2: 日中/夜開始（7-23時）のトーナメント
    else:
        # 現在時刻と開始時刻を比較
        if (current_hour < start_hour) or (current_hour == start_hour and current_minute < start_minute):
            # 開始前なら参加可能
            return True
        else:
            # 開始後なら締切時間と比較
            end_time = parse_time(end_time_str)
            if not end_time:
                return False  # 締切時間がない場合は除外
            
            end_hour, end_minute = end_time
            
            # 締切が深夜（0-6時）なら翌日と解釈
            if 0 <= end_hour < 7:
                # 現在も深夜（0-6時）なら当日の締切と比較
                if 0 <= current_hour < 7:
                    return (current_hour < end_hour) or (current_hour == end_hour and current_minute < end_minute)
                else:
                    # 現在が7時以降なら、締切は翌日なので参加可能
                    return True
            else:
                # 締切も日中/夜なら単純比較
                return (current_hour < end_hour) or (current_hour == end_hour and current_minute < end_minute)

def is_jopt_tournament(title):
    """タイトルにJOPTが含まれるかチェック"""
    return bool(re.search(r'JOPT|jopt', title, re.IGNORECASE))

def display_tournaments(tournaments):
    """トーナメント一覧を表示する関数"""
    for t in tournaments:
        st.markdown("---")
        
        # 参加可否を表示
        status_text = "🟢 参加可能" if t.get('is_available', False) else "🔴 参加不可"
        
        # タイトルと参加状態
        st.markdown(f"### {t['title']}")
        st.markdown(status_text)
        
        # 回収率を計算
        odds_text = format_odds(
            t.get('entry_fee', 0), 
            t.get('current_entries', 0), 
            t.get('guarantee', 0)
        )
        
        # 開始時間と締切時間を表示
        time_display = f"{t.get('start_time', '不明')}"
        if t.get('end_time'):
            time_display += f" (締切 {t.get('end_time')})"
        
        # エントリー総額計算
        total_entry = t.get('entry_fee', 0) * t.get('current_entries', 0)
        
        st.markdown(f"""
        🏢 **会場**: {t.get('venue', '不明')}  
        🕒 **時間**: {time_display}  
        💰 **参加費**: {format_money(t.get('entry_fee', 0))}円  
        👥 **エントリー**: {t.get('current_entries', 0)} / {t.get('max_entries', 0)}人  
        🏆 **保証**: {format_money(t.get('guarantee', 0))}円  
        💵 **エントリー総額**: {format_money(total_entry)}円  
        📊 **バリュー**: {odds_text}
        """)
        
        st.markdown(f"[🔍 詳細を見る]({t.get('detail_url', '#')})")

def main():
    st.title("🎲 Pokerfans トーナメント一覧")
    
    # 日付選択
    today = datetime.now()
    selected_date = st.date_input(
        "日付を選択",
        value=today,
        min_value=today,
        max_value=today.replace(year=today.year + 1)
    )
    date_str = selected_date.strftime("%Y/%m/%d")
    
    # セッションステートの初期化
    if 'current_page' not in st.session_state:
        st.session_state.current_page = 0
    
    if 'all_tournaments' not in st.session_state:
        st.session_state.all_tournaments = {}
    
    # ページ変更検出のためのフラグ
    if 'prev_page' not in st.session_state:
        st.session_state.prev_page = st.session_state.current_page
    
    # 詳細ページの取得数を制限するオプション
    max_details = st.slider(
        "1ページあたりの詳細取得数 (0=すべて取得しない)",
        min_value=0,
        max_value=10,
        value=0,
        help="詳細ページへのアクセス数を制限してリクエスト制限を回避"
    )
    
    # キャッシュ情報の表示
    last_updated = st.session_state.get('last_updated')
    if last_updated:
        elapsed = datetime.now() - last_updated
        st.info(f"最終更新: {last_updated.strftime('%H:%M:%S')} ({int(elapsed.total_seconds())}秒前)")
    
    # 初回データ取得を行わない
    if 'initialized' not in st.session_state:
        st.session_state.initialized = True
        # 初回メッセージを表示
        st.info("「すべてのページを取得」ボタンを押してデータを取得してください")
    
    # ページが変更された場合も処理が必要
    page_changed = st.session_state.prev_page != st.session_state.current_page
    if page_changed:
        st.session_state.prev_page = st.session_state.current_page
    
    # データ取得（キャッシュ対応）
    tournaments = None
    pagination_info = None
    
    # 全ページデータの集計を初期化
    all_collected = []
    
    # セッションステートにデータが存在するか確認
    if 'sorted_tournaments' not in st.session_state:
        st.session_state.sorted_tournaments = None
    
    # 「すべてのページを取得（キャッシュを更新）」ボタン
    if st.button("すべてのページを取得（キャッシュを更新）"):
        # キャッシュをクリア
        st.cache_data.clear()
        
        # 取得状態を保存するためのセッション変数を設定
        st.session_state.is_fetching = True
        st.session_state.fetch_progress = 0
        st.session_state.fetch_total_pages = 0
        st.session_state.fetch_current_page = 0
        st.session_state.fetch_date = date_str
        st.session_state.fetch_max_details = max_details
        
        # リダイレクトして取得処理を開始
        st.rerun()

    # 取得処理の継続（スマホでのセッション切れに対応）
    if 'is_fetching' in st.session_state and st.session_state.is_fetching:
        with st.spinner(f"データを取得中... 進捗: {st.session_state.fetch_progress}%"):
            # 進捗バーの表示（常に表示）
            progress_bar = st.progress(st.session_state.fetch_progress / 100)
            
            # 初回の場合、最初のページを取得
            if st.session_state.fetch_total_pages == 0:
                st.info("最初のページを取得中...")
                
                # 最初の1ページを取得して総ページ数を確認
                first_page_tournaments, first_page_info, _ = fetch_tournament_data(
                    st.session_state.fetch_date, 
                    0, 
                    st.session_state.fetch_max_details
                )
                total_pages = first_page_info.get('total_pages', 1)
                
                # 最初のページを保存
                st.session_state.all_tournaments = {
                    "page_0": first_page_tournaments
                }
                
                # 状態を更新
                st.session_state.fetch_total_pages = total_pages
                st.session_state.fetch_current_page = 0  # バッチ処理用に0に初期化
                st.session_state.fetch_progress = (1 / total_pages) * 100 if total_pages > 0 else 100
                st.session_state.batch_progress = 0
                st.session_state.batch_size = 3  # 一度に処理するページ数
                
                # 進捗情報を表示
                st.info(f"ページ 1/{total_pages} 取得完了（{len(first_page_tournaments)} 件）")
                progress_bar.progress(st.session_state.fetch_progress / 100)
                
                # 次のバッチへ進む前に一時停止
                py_time.sleep(1)
                st.rerun()
            
            # バッチ処理（複数ページを並列取得）
            elif st.session_state.fetch_current_page < st.session_state.fetch_total_pages - 1:
                total_pages = st.session_state.fetch_total_pages
                current_batch_start = st.session_state.fetch_current_page + 1  # 次のページから
                batch_size = st.session_state.batch_size
                current_batch_end = min(current_batch_start + batch_size, total_pages)
                
                # バッチ処理の進捗表示
                batch_progress_bar = st.progress(st.session_state.batch_progress)
                st.info(f"ページ {current_batch_start + 1}～{current_batch_end}/{total_pages} を並列取得中...")
                
                # 並列取得
                batch_results = fetch_pages_parallel(
                    st.session_state.fetch_date,
                    current_batch_start,
                    current_batch_end,
                    st.session_state.fetch_max_details
                )
                
                # 結果を保存
                st.session_state.all_tournaments.update(batch_results)
                
                # 状態を更新
                st.session_state.fetch_current_page = current_batch_end - 1
                st.session_state.fetch_progress = (current_batch_end / total_pages) * 100
                
                # 進捗情報を表示
                batch_tournaments_count = sum(len(tournaments) for tournaments in batch_results.values())
                st.info(f"ページ {current_batch_start + 1}～{current_batch_end}/{total_pages} 取得完了（{batch_tournaments_count} 件）")
                progress_bar.progress(st.session_state.fetch_progress / 100)
                
                # バッチの進捗をリセット
                st.session_state.batch_progress = 0
                batch_progress_bar.progress(0)
                
                # 次のバッチに進む前に一時停止（サーバー負荷軽減）
                py_time.sleep(2)
                st.rerun()
            
            # すべてのページの取得が完了
            else:
                # 全データを集計
                all_collected = []
                for page_data in st.session_state.all_tournaments.values():
                    all_collected.extend(page_data)
                
                # 取得完了メッセージ
                st.success(f"すべてのページの取得完了！合計 {len(all_collected)} 件のトーナメントデータを収集しました。")
                
                # 取得状態をリセット
                st.session_state.is_fetching = False
                st.session_state.fetch_progress = 100
                progress_bar.progress(1.0)
                
                # データを処理してセッションに保存
                process_and_display_tournaments(all_collected)
    
    # 保存されたデータがある場合は表示
    elif st.session_state.sorted_tournaments is not None:
        display_sorted_tournaments(st.session_state.sorted_tournaments)
    
    else:
        st.info("「すべてのページを取得」ボタンを押してデータを取得してください。")

def process_and_display_tournaments(tournaments):
    """トーナメントデータを処理して表示・保存する"""
    # 参加可否判定とJOPT分類
    for t in tournaments:
        t['is_available'] = is_available(t.get('start_time'), t.get('end_time'))
        t['is_jopt'] = is_jopt_tournament(t.get('title', ''))
    
    # ソートオプション
    sort_option = st.radio(
        "並び順",
        ["時間順", "回収率順"],
        horizontal=True
    )
    
    # ソート処理
    if sort_option == "時間順":
        sorted_tournaments = sorted(tournaments, key=lambda x: x.get('start_time', '99:99'))
    else:  # 回収率順
        # バリュー計算
        for t in tournaments:
            if t['guarantee'] > 0:
                total_entry_amount = t['current_entries'] * t['entry_fee']
                if total_entry_amount > 0:
                    value_ratio = t['guarantee'] / total_entry_amount
                    t['value_ratio'] = value_ratio * 100
                else:
                    t['value_ratio'] = None
            else:
                t['value_ratio'] = None
        
        sorted_tournaments = sorted(
            tournaments,
            key=lambda x: x.get('value_ratio', 0) if x.get('value_ratio') is not None else 0,
            reverse=True
        )
    
    # セッションに保存
    st.session_state.sorted_tournaments = sorted_tournaments
    
    # 表示
    display_sorted_tournaments(sorted_tournaments)

def display_sorted_tournaments(sorted_tournaments):
    """ソート済みトーナメントを表示する"""
    # タブ作成
    tab1, tab2 = st.tabs(["通常トーナメント", "JOPTトーナメント"])
    
    # 通常トーナメント
    with tab1:
        normal_tournaments = [t for t in sorted_tournaments if not t.get('is_jopt', False)]
        st.success(f"通常トーナメント: 合計{len(normal_tournaments)}件")
        display_tournaments(normal_tournaments)
    
    # JOPTトーナメント
    with tab2:
        jopt_tournaments = [t for t in sorted_tournaments if t.get('is_jopt', False)]
        st.success(f"JOPTトーナメント: 合計{len(jopt_tournaments)}件")
        display_tournaments(jopt_tournaments)

if __name__ == "__main__":
    st.set_page_config(
        page_title="Pokerfans トーナメント一覧",
        page_icon="🎲",
        layout="wide"
    )
    main() 