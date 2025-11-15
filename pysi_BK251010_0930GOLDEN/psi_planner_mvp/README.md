# セットアップ
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt

# 初回起動（DB生成）
streamlit run app.py

# 既存CSVからの取り込み（任意）
python csv_to_sqlite.py