#export_node_geo.py
from pysi.io.sql_bridge import export_node_geo_csv
DB  = r"C:\Users\ohsug\PySI_V0R8_SQL_010\data\pysi.sqlite3"
CSV = r"C:\Users\ohsug\PySI_V0R8_SQL_010\data\node_geo4export.csv"  # 出力先は任意
export_node_geo_csv(DB, CSV, include_current=False)  # 空欄テンプレで出力
print("[GEO] exported:", CSV)
