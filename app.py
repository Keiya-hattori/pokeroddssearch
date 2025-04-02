import streamlit as st
from datetime import datetime, timedelta, time as dt_time
import pytz
import time as py_time
from scraper import PokerfansScraper
import urllib.parse
import re

# 日本のタイムゾーン
JST = pytz.timezone('Asia/Tokyo')

# キャッシュデータを保持する関数
@st.cache_data(ttl=86400)  # 1日（86400秒）間キャッシュを保持
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
    
    # 「すべてのページを取得（キャッシュを更新）」ボタン
    if st.button("すべてのページを取得（キャッシュを更新）"):
        # キャッシュをクリア
        st.cache_data.clear()
        with st.spinner("全ページのデータを取得中..."):
            # 最初の1ページを取得して総ページ数を確認
            first_page_tournaments, first_page_info, _ = fetch_tournament_data(date_str, 0, max_details)
            total_pages = first_page_info.get('total_pages', 1)
            
            # 最初のページを保存
            st.session_state.all_tournaments = {
                "page_0": first_page_tournaments
            }
            pagination_info = first_page_info
            tournaments = first_page_tournaments
            
            # 進捗バーの表示
            progress_bar = st.progress(0)
            for i, page in enumerate(range(1, total_pages)):  # 1から開始（0ページは既に取得済み）
                page_tournaments, _, _ = fetch_tournament_data(date_str, page, max_details)
                st.session_state.all_tournaments[f"page_{page}"] = page_tournaments
                # 進捗表示
                st.info(f"ページ {page + 1}/{total_pages} 取得完了（{len(page_tournaments)} 件）")
                progress_bar.progress((i + 1) / (total_pages - 1))
                py_time.sleep(3)  # サーバー負荷軽減
            
            # セッションに保存されているデータから全体を集計
            for page_data in st.session_state.all_tournaments.values():
                all_collected.extend(page_data)
            
            st.success(f"すべてのページの取得完了！合計 {len(all_collected)} 件のトーナメントデータを収集しました。")
    else:
        # ボタンが押されていない場合は、セッションに保存されているデータを使用
        for page_data in st.session_state.all_tournaments.values():
            all_collected.extend(page_data)
    
    # ソートオプション
    sort_option = st.radio(
        "並び順",
        ["時間順", "回収率順"],
        horizontal=True
    )
    
    # 「全体ソート＆表示」ボタン
    if st.button("全体ソート＆表示") and all_collected:
        # 参加可否判定とJOPT分類
        for t in all_collected:
            t['is_available'] = is_available(t.get('start_time'), t.get('end_time'))
            t['is_jopt'] = is_jopt_tournament(t.get('title', ''))
        
        # 選択されたソート順でソート
        if sort_option == "時間順":
            sorted_tournaments = sorted(all_collected, key=lambda x: x.get('start_time', '99:99'))
        else:  # 回収率順
            # バリュー計算（保証賞金 ÷ エントリー総額）で100%超えるとバリュー有り
            for tournament in sorted_tournaments:
                if tournament['guarantee'] > 0:
                    total_entry_amount = tournament['current_entries'] * tournament['entry_fee']
                    if total_entry_amount > 0:  # ゼロ除算を防ぐ
                        value_ratio = tournament['guarantee'] / total_entry_amount  # 計算式を反転
                        tournament['value_ratio'] = value_ratio * 100  # パーセント表示にするため100倍
                    else:
                        tournament['value_ratio'] = None  # エントリーがない場合
                else:
                    tournament['value_ratio'] = None  # 保証がない場合
            
            # 回収率の高い順にソート
            sorted_tournaments = sorted(sorted_tournaments, key=lambda x: x.get('value_ratio', 0), reverse=True)
        
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
    
    # 通常の表示（現在のページのみ）
    elif tournaments:
        current_time = datetime.now(JST).strftime('%H:%M')
        st.caption(f"現在時刻: {current_time}")
        
        # トーナメントをJOPTと通常に分類
        jopt_tournaments = []
        normal_tournaments = []
        
        for t in tournaments:
            # 参加可否を判定
            t['is_available'] = is_available(t.get('start_time'), t.get('end_time'))
            
            # JOPTかどうかチェック
            if is_jopt_tournament(t.get('title', '')):
                jopt_tournaments.append(t)
            else:
                normal_tournaments.append(t)
        
        # タブ作成
        tab1, tab2 = st.tabs(["通常トーナメント", "JOPTトーナメント"])
        
        # タブ1: 通常トーナメント
        with tab1:
            # 参加可能なもののみフィルタ
            available_normal = [t for t in normal_tournaments if t['is_available']]
            
            if available_normal:
                st.success(f"🎯 参加可能な通常トーナメント: {len(available_normal)}件")
                
                # トーナメント表示
                display_tournaments(available_normal)
                
            else:
                st.info("現在参加可能な通常トーナメントはありません。")
                
                # オプションで参加不可も表示
                if st.checkbox("参加不可の通常トーナメントも表示する", key="show_unavailable_normal"):
                    st.warning("⚠️ 以下には参加不可のトーナメントも含まれています")
                    display_tournaments(normal_tournaments)
        
        # タブ2: JOPTトーナメント
        with tab2:
            # 参加可能なもののみフィルタ
            available_jopt = [t for t in jopt_tournaments if t['is_available']]
            
            if available_jopt:
                st.success(f"🏆 参加可能なJOPTトーナメント: {len(available_jopt)}件")
                
                # トーナメント表示
                display_tournaments(available_jopt)
                
            else:
                st.info("現在参加可能なJOPTトーナメントはありません。")
                
                # オプションで参加不可も表示
                if st.checkbox("参加不可のJOPTトーナメントも表示する", key="show_unavailable_jopt"):
                    st.warning("⚠️ 以下には参加不可のトーナメントも含まれています")
                    display_tournaments(jopt_tournaments)
        
        # ページネーションUI
        st.markdown("---")
        cols = st.columns([1, 3, 1])
        
        # 前のページボタン
        with cols[0]:
            if st.session_state.current_page > 0:
                if st.button("◀ 前のページ"):
                    st.session_state.current_page -= 1
                    st.rerun()
        
        # ページ番号選択
        with cols[1]:
            total_pages = pagination_info.get('total_pages', 1)
            
            page_options = list(range(total_pages))
            selected_page = st.selectbox(
                "ページ選択",
                options=page_options,
                format_func=lambda x: f"ページ {x + 1}",
                index=st.session_state.current_page
            )
            
            if selected_page != st.session_state.current_page:
                st.session_state.current_page = selected_page
                st.rerun()
        
        # 次のページボタン
        with cols[2]:
            if st.session_state.current_page < total_pages - 1:
                if st.button("次のページ ▶"):
                    st.session_state.current_page += 1
                    st.rerun()
    else:
        st.info("取得ボタンを押してトーナメント情報を取得してください。")

if __name__ == "__main__":
    st.set_page_config(
        page_title="Pokerfans トーナメント一覧",
        page_icon="🎲",
        layout="wide"
    )
    main() 