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

    # トーナメント情報表示部分
    odds_text = format_odds(
        t.get('entry_fee', 0), 
        t.get('current_entries', 0), 
        t.get('guarantee', 0)
    )

    # 想定エントリー数の計算（保証額があり、エントリー費がある場合）
    if t.get('guarantee', 0) > 0 and t.get('entry_fee', 0) > 0:
        estimated_entries = t.get('guarantee', 0) // t.get('entry_fee', 0)
        estimated_text = f"（{estimated_entries}エントリーで元取れる）"
    else:
        estimated_text = ""

    # エントリー総額計算
    total_entry = t.get('entry_fee', 0) * t.get('current_entries', 0)

    st.markdown(f"""
    🏢 **会場**: {t.get('venue', '不明')}  
    🕒 **時間**: {time_display}  
    💰 **参加費**: {format_money(t.get('entry_fee', 0))}円  
    👥 **エントリー**: {t.get('current_entries', 0)} / {t.get('max_entries', 0)}人  
    🏆 **保証**: {format_money(t.get('guarantee', 0))}円  
    💵 **エントリー総額**: {format_money(total_entry)}円  
    📊 **バリュー**: {odds_text} {estimated_text}
    """)

if __name__ == "__main__":
    main() 