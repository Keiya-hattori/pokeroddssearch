from scraper import PokerfansScraper

# ✅ 任意の日付で指定（例: "2025/03/27"）※Noneにすれば今日
target_date = "2025/03/27"
scraper = PokerfansScraper(target_date=target_date)

print("🔍 トーナメント一覧を取得中...\n")
tournaments = scraper.get_tournament_list()

# 最初の3件だけ表示
if tournaments:
    for i, t in enumerate(tournaments[:3], 1):
        print(f"--- {i} 件目 ---")
        print(f"title: {t['title']}")
        print(f"venue: {t['venue']}")
        print(f"start_time: {t['start_time']}")
        print(f"end_time: {t['end_time']}")
        print(f"entry_fee: {t['entry_fee']}")
        print(f"current_entries: {t['current_entries']}")
        print(f"max_entries: {t['max_entries']}")
        print(f"guarantee: {t['guarantee']}")  # ✅ 今はこれだけが detail 由来
        print(f"detail_url: {t['detail_url']}")
        print()
else:
    print("❌ イベントが見つかりませんでした。")
