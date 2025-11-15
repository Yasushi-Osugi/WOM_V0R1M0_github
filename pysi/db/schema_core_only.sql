-- schema_core_only.sql : orchestrator/ETL/PSIに必要な最小スキーマ
-- python -c "from pysi.db.apply_schema import apply_schema; apply_schema('var/psi.sqlite','pysi/db/schema_core_only.sql')"
-- 


PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA foreign_keys=ON;

-- 正本カレンダ（Step1）
CREATE TABLE IF NOT EXISTS calendar_iso (
  week_index INTEGER PRIMARY KEY,
  iso_year   INTEGER NOT NULL,
  iso_week   INTEGER NOT NULL,
  week_start TEXT    NOT NULL,
  week_end   TEXT    NOT NULL,
  UNIQUE (iso_year, iso_week)
);
CREATE INDEX IF NOT EXISTS idx_calendar_year_week
  ON calendar_iso(iso_year, iso_week);

-- シナリオ
CREATE TABLE IF NOT EXISTS scenario (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT NOT NULL UNIQUE,
  plan_year_st  INTEGER NOT NULL,
  plan_range    INTEGER NOT NULL,
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- マスタ
CREATE TABLE IF NOT EXISTS node (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  longitude REAL, latitude REAL
);
CREATE TABLE IF NOT EXISTS product (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE
);

-- ノード×製品のパラメータ
CREATE TABLE IF NOT EXISTS node_product (
  node_id INTEGER NOT NULL,
  product_id INTEGER NOT NULL,
  lot_size INTEGER NOT NULL DEFAULT 1,
  leadtime INTEGER NOT NULL DEFAULT 0,
  ss_days INTEGER NOT NULL DEFAULT 0,
  long_vacation_weeks TEXT,
  PRIMARY KEY (node_id, product_id),
  FOREIGN KEY (node_id) REFERENCES node(id) ON DELETE CASCADE,
  FOREIGN KEY (product_id) REFERENCES product(id) ON DELETE CASCADE
);

-- 月次ステージング
CREATE TABLE IF NOT EXISTS monthly_demand_stg (
  scenario_id INTEGER NOT NULL,
  node_id     INTEGER NOT NULL,
  product_id  INTEGER NOT NULL,
  year        INTEGER NOT NULL,
  m1 REAL DEFAULT 0,  m2 REAL DEFAULT 0,  m3 REAL DEFAULT 0,
  m4 REAL DEFAULT 0,  m5 REAL DEFAULT 0,  m6 REAL DEFAULT 0,
  m7 REAL DEFAULT 0,  m8 REAL DEFAULT 0,  m9 REAL DEFAULT 0,
  m10 REAL DEFAULT 0, m11 REAL DEFAULT 0, m12 REAL DEFAULT 0,
  UNIQUE (scenario_id, node_id, product_id, year),
  FOREIGN KEY (scenario_id) REFERENCES scenario(id) ON DELETE CASCADE,
  FOREIGN KEY (node_id) REFERENCES node(id) ON DELETE CASCADE,
  FOREIGN KEY (product_id) REFERENCES product(id) ON DELETE CASCADE
);

-- 週次需要
CREATE TABLE IF NOT EXISTS weekly_demand (
  scenario_id INTEGER NOT NULL,
  node_id     INTEGER NOT NULL,
  product_id  INTEGER NOT NULL,
  iso_year    INTEGER NOT NULL,
  iso_week    INTEGER NOT NULL,
  value       REAL NOT NULL DEFAULT 0,
  UNIQUE (scenario_id, node_id, product_id, iso_year, iso_week),
  FOREIGN KEY (scenario_id) REFERENCES scenario(id) ON DELETE CASCADE,
  FOREIGN KEY (node_id) REFERENCES node(id) ON DELETE CASCADE,
  FOREIGN KEY (product_id) REFERENCES product(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_weekly_qry
  ON weekly_demand (scenario_id, node_id, product_id, iso_year, iso_week);

-- 生成ロット
CREATE TABLE IF NOT EXISTS lot (
  scenario_id INTEGER NOT NULL,
  node_id     INTEGER NOT NULL,
  product_id  INTEGER NOT NULL,
  iso_year    INTEGER NOT NULL,
  iso_week    INTEGER NOT NULL,
  lot_id      TEXT NOT NULL,
  UNIQUE (lot_id),
  FOREIGN KEY (scenario_id) REFERENCES scenario(id) ON DELETE CASCADE,
  FOREIGN KEY (node_id) REFERENCES node(id) ON DELETE CASCADE,
  FOREIGN KEY (product_id) REFERENCES product(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_lot_lookup
  ON lot (scenario_id, node_id, product_id, iso_year, iso_week);

-- エンジン出力（S/CO/I/P）
CREATE TABLE IF NOT EXISTS lot_bucket (
  scenario_id INTEGER NOT NULL,
  layer  TEXT NOT NULL CHECK(layer IN ('demand','supply')),
  node_id     INTEGER NOT NULL,
  product_id  INTEGER NOT NULL,
  week_index  INTEGER NOT NULL,
  bucket TEXT NOT NULL CHECK(bucket IN ('S','CO','I','P')),
  lot_id  TEXT  NOT NULL,
  UNIQUE (scenario_id, layer, node_id, product_id, week_index, bucket, lot_id),
  FOREIGN KEY (scenario_id) REFERENCES scenario(id) ON DELETE CASCADE,
  FOREIGN KEY (node_id) REFERENCES node(id) ON DELETE CASCADE,
  FOREIGN KEY (product_id) REFERENCES product(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_lot_bucket_qry
  ON lot_bucket (scenario_id, layer, node_id, product_id, week_index, bucket);
