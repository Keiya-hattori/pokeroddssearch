import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import time
from typing import List, Dict
import random
import streamlit as st

class PokerfansScraper:
    def __init__(self, target_date: str = None):
        """
        Args:
            target_date (str, optional): 'YYYY/MM/DD'形式の日付文字列。
                                       Noneの場合は現在の日付を使用。
        """
        # target_dateが指定されていない場合は現在の日付を使用
        date_str = target_date or datetime.now().strftime('%Y/%m/%d')
        
        # ベースURLとクエリパラメータを分離
        self.base_url = "https://pokerfans.jp/"
        self.params = {
            "startDate": date_str,
            "weekly": "false",
            "prize": "",
            "location": "東京都",
            "clubId": "",
            "withEndTime": "false",
            "applyEndTime": "",
            "size": "50"
        }
        
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        # キャッシュ: 詳細ページの内容を保存
        self._detail_cache = {}

    def _random_delay(self, min_seconds=3, max_seconds=7):
        """ランダムな時間待機してリクエスト制限を回避"""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)

    def _extract_number(self, text: str) -> int:
        """文字列から数値のみを抽出"""
        if not text:
            return 0
        numbers = re.findall(r'\d+', text.replace(',', ''))
        return int(numbers[0]) if numbers else 0

    def _extract_guarantee(self, text: str) -> int:
        """
        文字列から保証額を抽出して円単位で返す（タイトル用）
        Args:
            text: 保証額を含む可能性のある文字列
        Returns:
            int: 保証額（円単位）。見つからない場合は0
        """
        if not text:
            return 0
        
        # 全角数字を半角に変換
        text = text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
        
        # 保証額のパターン
        patterns = [
            # "万"を含むパターン（例：84万相当、40万コイン、7万円保証）
            (r'(?:総額)?(\d+)万(?:円|coin|コイン)?(?:相当|保証)?', lambda x: int(x) * 10000),
            
            # 数値+通貨単位のパターン（例：50,000coin、100,000コイン）
            (r'(?:Web|ウェブ)?(?:最低保証)?[^\d]*(\d+[,\d]*)(?:円|coin|コイン)(?:保証)?',
             lambda x: int(x.replace(',', ''))),
        ]
        
        # 各パターンで検索
        for pattern, converter in patterns:
            match = re.search(pattern, text, re.IGNORECASE)  # 大文字小文字を区別しない
            if match:
                try:
                    return converter(match.group(1))
                except (ValueError, IndexError):
                    continue
        
        return 0

    def _extract_guarantee_from_detail(self, text: str) -> int:
        """
        詳細ページのテキストから保証額を抽出（より厳密な条件で）
        Args:
            text: 詳細ページのテキスト
        Returns:
            int: 保証額（円単位）。見つからない場合は0
        """
        if not text:
            return 0
        
        # 全角数字を半角に変換
        text = text.translate(str.maketrans('０１２３４５６７８９', '0123456789'))
        
        # 詳細ページ用の厳密なパターン
        patterns = [
            # "保証"という単語が必ず含まれるパターンのみ
            
            # ●●万円保証
            (r'(\d+)万円保証', lambda x: int(x) * 10000),
            
            # ●●万保証
            (r'(\d+)万保証', lambda x: int(x) * 10000),
            
            # ●●,●●●円保証
            (r'(\d+[,\d]*)円保証', lambda x: int(x.replace(',', ''))),
            
            # ●●万コイン保証
            (r'(\d+)万(?:coin|コイン)保証', lambda x: int(x) * 10000),
            
            # ●●,●●●コイン保証
            (r'(\d+[,\d]*)(?:coin|コイン)保証', lambda x: int(x.replace(',', ''))),
            
            # 総額●●万保証
            (r'総額(\d+)万保証', lambda x: int(x) * 10000),
            
            # 最低保証●●万
            (r'最低保証[^\d]*(\d+)万', lambda x: int(x) * 10000),
            
            # 最低保証●●,●●●コイン
            (r'最低保証[^\d]*(\d+[,\d]*)(?:coin|コイン)', lambda x: int(x.replace(',', ''))),
        ]
        
        # 各パターンで検索（改行を含む可能性があるため、re.MULTILINE | re.IGNORECASE を使用）
        for pattern, converter in patterns:
            match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
            if match:
                try:
                    return converter(match.group(1))
                except (ValueError, IndexError):
                    continue
        
        return 0

    def get_tournament_list(self, page: int = 0, max_details_per_page: int = 5) -> tuple[List[Dict], Dict]:
        """
        トーナメント一覧を取得（詳細ページの取得数を制限）
        Args:
            page: ページ番号（0-based）
            max_details_per_page: 1ページあたり取得する詳細ページの最大数（0=すべて取得しない）
        """
        tournaments = []
        
        # ページ番号をパラメータに設定
        params = self.params.copy()
        params["page"] = str(page)
        
        # リクエスト実行（より長い待機時間）
        try:
            response = requests.get(
                self.base_url,
                params=params,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()  # エラーチェック
        except requests.RequestException as e:
            print(f"一覧ページの取得に失敗: {e}")
            return [], {"current_page": page, "total_pages": 1}
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # ページネーション情報を取得
        pagination_info = self._get_pagination_info(soup)
        
        # トーナメント情報の取得
        details_count = 0
        
        for event in soup.select('.profile-event'):
            try:
                # タイトルと詳細ページURL
                title_link = event.select_one('h5 > a.color-green.tooltips')
                if not title_link:
                    continue
                    
                title = title_link.text.strip()
                detail_url = self.base_url.rstrip('/') + title_link['href']
                
                # リングゲームは除外
                if any(keyword in title for keyword in ['リング', 'コインリング', 'RING', 'Ring', 'ring']):
                    continue
                
                # 施設名
                venue_spans = event.select('div.oneline span')
                venue = venue_spans[1].text.strip() if len(venue_spans) > 1 else ''            
                # 開始・締切時刻の抽出
                time_text = event.select_one('strong.text-danger').text.strip()
                print(f"🕒 time_text raw: '{time_text}'")  # デバッグ用

                # 開始時間の抽出（最初に出てくる時間）
                start_time_match = re.search(r'(\d{2}:\d{2})', time_text)

                # 締切時間の抽出 - 〆またはEndの後ろの時間
                end_time_match = re.search(r'(?:〆|End)(\d{2}:\d{2})', time_text)

                start_time = start_time_match.group(1) if start_time_match else None
                end_time = end_time_match.group(1) if end_time_match else None
                
                # エントリー費
                entry_fee_text = ''
                for span in event.select('div.col-xs-6 span'):
                    text = span.text.strip()
                    if re.search(r'\(?E\)?|エントリー|参加費|¥|円|￥', text):
                        entry_fee_text = text
                        break
                entry_fee = self._extract_number(entry_fee_text)
                
                # エントリー人数／定員の処理を修正
                try:
                    entry_count_text = event.select_one('i.icon-users + span').text.strip()
                    # "0 /" や "0 / " のようなケースに対応
                    parts = [p.strip() for p in entry_count_text.split('/')]
                    current_entries = int(parts[0]) if parts[0].strip() else 0
                    max_entries = int(parts[1]) if len(parts) > 1 and parts[1].strip() else 0
                except (ValueError, AttributeError, IndexError):
                    current_entries = 0
                    max_entries = 0
                    print(f"Warning: Could not parse entry count from text: {entry_count_text}")
                # venue 抽出
                venue_spans = event.select('div.oneline span')
                venue = venue_spans[1].text.strip() if len(venue_spans) > 1 else ''

                # ✅ フィルタ：東京都以外はスキップ
                if "東京都" not in venue:
                    continue
                
                tournament_info = {
                    'title': title,
                    'venue': venue,
                    'start_time': start_time,
                    'end_time': end_time,
                    'entry_fee': entry_fee,
                    'current_entries': current_entries,
                    'max_entries': max_entries,
                    'detail_url': detail_url
                }
                
                # タイトルから保証額を取得
                guarantee = self._extract_guarantee(title)
                tournament_info['guarantee'] = guarantee
                
                # タイトルから取得できず、詳細取得数が上限未満の場合のみ詳細ページをチェック
                # if guarantee == 0 and (max_details_per_page == 0 or details_count < max_details_per_page):
                #     detail_info = self.get_tournament_detail(detail_url)
                #     tournament_info['guarantee'] = detail_info['guarantee']
                #     details_count += 1
                #     self._random_delay()  # 詳細ページアクセス後に待機
                
                tournaments.append(tournament_info)
                
            except Exception as e:
                print(f"トーナメント情報の取得中にエラー: {e}")
                continue
        
        # 次のリクエストまでより長く待機
        self._random_delay(5, 10)
        
        return tournaments, pagination_info

    def _get_pagination_info(self, soup) -> Dict:
        """ページネーション情報を取得"""
        pagination = soup.select_one('ul.pagination')
        if not pagination:
            return {'current_page': 0, 'total_pages': 1}
        
        current_page = int(pagination.select_one('li.active a').text) - 1
        page_numbers = [int(a.text) for a in pagination.select('li a') if a.text.isdigit()]
        total_pages = max(page_numbers) if page_numbers else 1
        
        return {'current_page': current_page, 'total_pages': total_pages}

    def get_tournament_detail(self, url: str) -> Dict:
        """詳細ページから情報取得（キャッシュ対応）"""
        # キャッシュにあればそれを返す
        if url in self._detail_cache:
            return self._detail_cache[url]
            
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            detail_text = soup.select_one('pre.pre-white').text if soup.select_one('pre.pre-white') else ''
            
            # 保証賞金の抽出
            guarantee = self._extract_guarantee_from_detail(detail_text)
            
            result = {'guarantee': guarantee}
            
            # キャッシュに保存
            self._detail_cache[url] = result
            return result
            
        except Exception as e:
            print(f"詳細ページの取得に失敗: {url} - {e}")
            return {'guarantee': 0}


