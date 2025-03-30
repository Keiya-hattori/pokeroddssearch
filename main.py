from scraper import PokerfansScraper

def main():
    scraper = PokerfansScraper()
    tournaments = scraper.get_tournament_list()
    
    # バリュー計算（エントリー総額 ÷ 保証賞金）
    for tournament in tournaments:
        if tournament['guarantee'] > 0:
            total_entry_amount = tournament['current_entries'] * tournament['entry_fee']
            value_ratio = total_entry_amount / tournament['guarantee']
            tournament['value_ratio'] = value_ratio
        else:
            tournament['value_ratio'] = None

    # 結果表示（例）
    for t in tournaments:
        print(f"イベント: {t['title']}")
        print(f"バリュー比率: {t['value_ratio']:.2f}" if t['value_ratio'] else "保証なし")
        print("---")

if __name__ == "__main__":
    main() 