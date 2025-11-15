PRAGMA foreign_keys = ON;

-- ==============================
-- Master
-- ==============================
CREATE TABLE IF NOT EXISTS product (
  product_name TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS node (
  node_name   TEXT PRIMARY KEY,
  parent_name TEXT REFERENCES node(node_name) ON DELETE SET NULL,
  leadtime    INTEGER NOT NULL DEFAULT 1,
  ss_days     INTEGER NOT NULL DEFAULT 7,
  long_vacation_weeks TEXT NOT NULL DEFAULT '[]'  -- JSON 文字列
);

-- node × product のコスト比率（0..1）と lot_size
CREATE TABLE IF NOT EXISTS node_product (
  node_name    TEXT NOT NULL REFERENCES node(node_name) ON DELETE CASCADE,
  product_name TEXT NOT NULL REFERENCES product(product_name) ON DELETE CASCADE,
  lot_size     INTEGER NOT NULL DEFAULT 1,

  -- すべて“比率”。cs_* の合計≈1 をアプリ側でバリデーション
  cs_logistics_costs        REAL NOT NULL DEFAULT 0.0,
  cs_warehouse_cost         REAL NOT NULL DEFAULT 0.0,
  cs_fixed_cost             REAL NOT NULL DEFAULT 0.0,
  cs_profit                 REAL NOT NULL DEFAULT 0.0,
  cs_direct_materials_costs REAL NOT NULL DEFAULT 0.0,  -- 材料“比率”
  cs_tax_portion            REAL NOT NULL DEFAULT 0.0,  -- 関税“比率”

  PRIMARY KEY (node_name, product_name)
);

-- 金額（/ロット）。材料・関税の“金額”はここに保持
CREATE TABLE IF NOT EXISTS price_money_per_lot (
  node_name    TEXT NOT NULL REFERENCES node(node_name) ON DELETE CASCADE,
  product_name TEXT NOT NULL REFERENCES product(product_name) ON DELETE CASCADE,
  direct_materials_costs REAL NOT NULL DEFAULT 0.0,  -- 仕入れ金額/lot（親販売×関税込み）
  tariff_cost            REAL NOT NULL DEFAULT 0.0,  -- 関税金額/lot
  PRIMARY KEY (node_name, product_name)
);

-- 関税率マスタ（0..1）
CREATE TABLE IF NOT EXISTS tariff (
  product_name TEXT NOT NULL REFERENCES product(product_name) ON DELETE CASCADE,
  from_node    TEXT NOT NULL REFERENCES node(node_name)    ON DELETE CASCADE,
  to_node      TEXT NOT NULL REFERENCES node(node_name)    ON DELETE CASCADE,
  tariff_rate  REAL NOT NULL,
  PRIMARY KEY (product_name, from_node, to_node)
);

-- 445/ISO週の軸
CREATE TABLE IF NOT EXISTS calendar445 (
  iso_index INTEGER PRIMARY KEY,    -- 0..N-1
  iso_year  INTEGER NOT NULL,
  iso_week  INTEGER NOT NULL,       -- 1..53
  week_label TEXT                   -- 445表示用ラベル
);

-- 週次需要（lot生成元）
CREATE TABLE IF NOT EXISTS weekly_demand (
  node_name TEXT NOT NULL REFERENCES node(node_name)    ON DELETE CASCADE,
  product_name TEXT NOT NULL REFERENCES product(product_name) ON DELETE CASCADE,
  iso_year INTEGER NOT NULL,
  iso_week INTEGER NOT NULL,
  s_lot    INTEGER NOT NULL,
  lot_id_list TEXT NOT NULL,     -- JSON 配列文字列

  PRIMARY KEY (node_name, product_name, iso_year, iso_week)
);

-- PSI（lot 粒度で保存）
CREATE TABLE IF NOT EXISTS psi (
  node_name    TEXT NOT NULL REFERENCES node(node_name)    ON DELETE CASCADE,
  product_name TEXT NOT NULL REFERENCES product(product_name) ON DELETE CASCADE,
  iso_index    INTEGER NOT NULL REFERENCES calendar445(iso_index) ON DELETE CASCADE,
  bucket       TEXT NOT NULL CHECK (bucket IN ('S','CO','I','P')),
  lot_id       TEXT NOT NULL,
  PRIMARY KEY (node_name, product_name, iso_index, bucket, lot_id)
);

-- 価格タグ（ASIS/TOBE）
CREATE TABLE IF NOT EXISTS price_tag (
  node_name    TEXT NOT NULL REFERENCES node(node_name)    ON DELETE CASCADE,
  product_name TEXT NOT NULL REFERENCES product(product_name) ON DELETE CASCADE,
  tag   TEXT NOT NULL CHECK (tag IN ('ASIS','TOBE')),
  price REAL NOT NULL,
  PRIMARY KEY (node_name, product_name, tag)
);

-- ==============================
-- Indexes
-- ==============================
CREATE INDEX IF NOT EXISTS ix_weekly_demand_lookup
  ON weekly_demand (node_name, product_name, iso_year, iso_week);

CREATE INDEX IF NOT EXISTS ix_psi_lookup
  ON psi (node_name, product_name, iso_index, bucket);

CREATE INDEX IF NOT EXISTS ix_tariff_lookup
  ON tariff (product_name, from_node, to_node);

-- ==============================
-- add table "product_edge"
-- ==============================
-- 製品ごとのエッジを、IN/OUTを明示して保持
CREATE TABLE IF NOT EXISTS product_edge (
  product_name TEXT NOT NULL,
  parent_name  TEXT NOT NULL,
  child_name   TEXT NOT NULL,
  bound        TEXT NOT NULL CHECK(bound IN ('OUT','IN')),
  UNIQUE(product_name, bound, parent_name, child_name)
);

-- あると嬉しい索引
CREATE INDEX IF NOT EXISTS idx_edge_prod_bound
  ON product_edge(product_name, bound);


-- ==============================
-- add_node_geo.sql
-- ==============================
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS node_geo (
  node_name TEXT PRIMARY KEY
            REFERENCES node(node_name) ON DELETE CASCADE,
  lat REAL NOT NULL,
  lon REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_node_geo_latlon ON node_geo(lat, lon);

