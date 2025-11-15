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
  long_vacation_weeks TEXT NOT NULL DEFAULT '[]',  -- JSON string (e.g. "[31,32]")
  -- 最適化・ネットワーク用（グローバル）
  nx_weight   INTEGER NOT NULL DEFAULT 0,         -- エッジ重みのソース
  nx_capacity INTEGER NOT NULL DEFAULT 0          -- ノード/葉のキャパシティ
);

-- node × product のコスト比率（0..1）と lot_size
CREATE TABLE IF NOT EXISTS node_product (
  node_name    TEXT NOT NULL REFERENCES node(node_name)    ON DELETE CASCADE,
  product_name TEXT NOT NULL REFERENCES product(product_name) ON DELETE CASCADE,
  lot_size     INTEGER NOT NULL DEFAULT 1,

  -- すべて“比率”。合計≈1 はアプリ側でバリデーション
  cs_logistics_costs        REAL NOT NULL DEFAULT 0.0,
  cs_warehouse_cost         REAL NOT NULL DEFAULT 0.0,
  cs_fixed_cost             REAL NOT NULL DEFAULT 0.0,
  cs_profit                 REAL NOT NULL DEFAULT 0.0,
  cs_direct_materials_costs REAL NOT NULL DEFAULT 0.0,
  cs_tax_portion            REAL NOT NULL DEFAULT 0.0,

  PRIMARY KEY (node_name, product_name)
);

-- 金額（/ロット）。材料・関税の“金額”はここに保持
CREATE TABLE IF NOT EXISTS price_money_per_lot (
  node_name    TEXT NOT NULL REFERENCES node(node_name)    ON DELETE CASCADE,
  product_name TEXT NOT NULL REFERENCES product(product_name) ON DELETE CASCADE,
  direct_materials_costs REAL NOT NULL DEFAULT 0.0,  -- 仕入れ金額/lot（関税含むならここに）
  tariff_cost            REAL NOT NULL DEFAULT 0.0,  -- 関税金額/lot（分離管理したい場合）
  PRIMARY KEY (node_name, product_name)
);

-- 関税率マスタ（0..1）
CREATE TABLE IF NOT EXISTS tariff (
  product_name TEXT NOT NULL REFERENCES product(product_name) ON DELETE CASCADE,
  from_node    TEXT NOT NULL REFERENCES node(node_name)       ON DELETE CASCADE,
  to_node      TEXT NOT NULL REFERENCES node(node_name)       ON DELETE CASCADE,
  tariff_rate  REAL NOT NULL,
  PRIMARY KEY (product_name, from_node, to_node)
);

-- 445/ISO週の軸
CREATE TABLE IF NOT EXISTS calendar445 (
  iso_index  INTEGER PRIMARY KEY,    -- 0..N-1
  iso_year   INTEGER NOT NULL,
  iso_week   INTEGER NOT NULL,       -- 1..53
  week_label TEXT                    -- 445表示用ラベル
);

-- 週次需要（lot生成元）
CREATE TABLE IF NOT EXISTS weekly_demand (
  node_name    TEXT NOT NULL REFERENCES node(node_name)       ON DELETE CASCADE,
  product_name TEXT NOT NULL REFERENCES product(product_name) ON DELETE CASCADE,
  iso_year     INTEGER NOT NULL,
  iso_week     INTEGER NOT NULL,
  s_lot        INTEGER NOT NULL,
  lot_id_list  TEXT NOT NULL,     -- JSON 配列文字列（ロットID群）

  PRIMARY KEY (node_name, product_name, iso_year, iso_week)
);

-- PSI（lot 粒度で保存）
CREATE TABLE IF NOT EXISTS psi (
  node_name    TEXT NOT NULL REFERENCES node(node_name)       ON DELETE CASCADE,
  product_name TEXT NOT NULL REFERENCES product(product_name) ON DELETE CASCADE,
  iso_index    INTEGER NOT NULL REFERENCES calendar445(iso_index) ON DELETE CASCADE,
  bucket       TEXT NOT NULL CHECK (bucket IN ('S','CO','I','P')),
  lot_id       TEXT NOT NULL,
  PRIMARY KEY (node_name, product_name, iso_index, bucket, lot_id)
);

-- 価格タグ（ASIS/TOBE）
CREATE TABLE IF NOT EXISTS price_tag (
  node_name    TEXT NOT NULL REFERENCES node(node_name)       ON DELETE CASCADE,
  product_name TEXT NOT NULL REFERENCES product(product_name) ON DELETE CASCADE,
  tag   TEXT NOT NULL CHECK (tag IN ('ASIS','TOBE')),
  price REAL NOT NULL,
  PRIMARY KEY (node_name, product_name, tag)
);

-- 製品ごとのエッジ（IN/OUTを明示）
CREATE TABLE IF NOT EXISTS product_edge (
  product_name TEXT NOT NULL REFERENCES product(product_name) ON DELETE CASCADE,
  parent_name  TEXT NOT NULL REFERENCES node(node_name)       ON DELETE CASCADE,
  child_name   TEXT NOT NULL REFERENCES node(node_name)       ON DELETE CASCADE,
  bound        TEXT NOT NULL CHECK(bound IN ('OUT','IN')),
  UNIQUE(product_name, bound, parent_name, child_name)
);

-- ノードの緯度経度
CREATE TABLE IF NOT EXISTS node_geo (
  node_name TEXT PRIMARY KEY
            REFERENCES node(node_name) ON DELETE CASCADE,
  lat REAL NOT NULL,
  lon REAL NOT NULL
);

-- ==============================
-- Indexes（パフォーマンス強化）
-- ==============================
CREATE INDEX IF NOT EXISTS ix_weekly_demand_lookup
  ON weekly_demand (node_name, product_name, iso_year, iso_week);

CREATE INDEX IF NOT EXISTS ix_psi_lookup
  ON psi (node_name, product_name, iso_index, bucket);

CREATE INDEX IF NOT EXISTS ix_tariff_lookup
  ON tariff (product_name, from_node, to_node);

CREATE INDEX IF NOT EXISTS idx_node_geo_latlon
  ON node_geo(lat, lon);

CREATE INDEX IF NOT EXISTS ix_node_product
  ON node_product(node_name, product_name);

CREATE INDEX IF NOT EXISTS ix_price_money_per_lot
  ON price_money_per_lot(node_name, product_name);

CREATE INDEX IF NOT EXISTS ix_price_tag
  ON price_tag(node_name, product_name, tag);

CREATE INDEX IF NOT EXISTS idx_edge_prod_bound
  ON product_edge(product_name, bound);

CREATE INDEX IF NOT EXISTS idx_edge_prod_parent
  ON product_edge(product_name, bound, parent_name);

CREATE INDEX IF NOT EXISTS idx_edge_prod_child
  ON product_edge(product_name, bound, child_name);

-- ==============================
-- View（便利ビュー）
-- ==============================
CREATE VIEW IF NOT EXISTS v_node_cost AS
SELECT
  np.node_name,
  np.product_name,
  np.lot_size,
  np.cs_logistics_costs,
  np.cs_warehouse_cost,
  np.cs_fixed_cost,
  np.cs_profit,
  np.cs_direct_materials_costs,
  np.cs_tax_portion,
  pm.direct_materials_costs AS dm_cost_per_lot,
  pm.tariff_cost            AS tariff_cost_per_lot
FROM node_product np
LEFT JOIN price_money_per_lot pm
  ON pm.node_name = np.node_name
 AND pm.product_name = np.product_name;
