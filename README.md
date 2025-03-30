# Pokerodds - ポーカートーナメント情報アプリ

Pokerfansのトーナメント情報をスクレイピングして、バリュートーナメントを簡単に見つけるためのアプリケーションです。

## 機能

- 東京のポーカートーナメント情報をリアルタイムで取得
- 参加可能/不可のトーナメントを自動判別
- バリュー率の計算（保証賞金÷エントリー総額）
- 通常トーナメントとJOPTサテライトの分類表示
- 全ページのデータをまとめて表示・ソート

## 使用技術

- Python 3.9
- Streamlit
- BeautifulSoup4
- Requests

## ローカルでの実行方法

```bash
# 依存関係のインストール
pip install -r requirements.txt

# アプリの実行
streamlit run app.py
```

## Renderへのデプロイ方法

1. Renderアカウントを作成
2. 「New Web Service」を選択
3. GitHubリポジトリを接続
4. 設定:
   - Name: pokerodds
   - Runtime: Python 3.9
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`

## 注意事項

- Pokerfansの規約に従ってご利用ください
- リクエスト制限に引っかからないよう、取得間隔を空けています 