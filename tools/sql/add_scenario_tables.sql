PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS scenario (
  scenario_id   TEXT PRIMARY KEY,
  label         TEXT NOT NULL,
  base_scenario TEXT,
  created_at    TEXT NOT NULL DEFAULT (datetime('now')),
  notes         TEXT
);

CREATE TABLE IF NOT EXISTS scenario_param (
  scenario_id TEXT NOT NULL REFERENCES scenario(scenario_id) ON DELETE CASCADE,
  key         TEXT NOT NULL,
  value_json  TEXT NOT NULL,
  PRIMARY KEY (scenario_id, key)
);

CREATE TABLE IF NOT EXISTS scenario_price_tag (
  scenario_id  TEXT NOT NULL REFERENCES scenario(scenario_id) ON DELETE CASCADE,
  product_name TEXT NOT NULL,
  node_name    TEXT NOT NULL,
  tag          TEXT NOT NULL CHECK(tag IN ('ASIS','TOBE')),
  price        REAL NOT NULL,
  PRIMARY KEY (scenario_id, product_name, node_name, tag)
);

-- 将来拡張（今日はいじらない）
CREATE TABLE IF NOT EXISTS scenario_node_product (
  scenario_id  TEXT NOT NULL REFERENCES scenario(scenario_id) ON DELETE CASCADE,
  product_name TEXT NOT NULL,
  node_name    TEXT NOT NULL,
  cs_logistics_costs        REAL,
  cs_warehouse_cost         REAL,
  cs_fixed_cost             REAL,
  cs_profit                 REAL,
  cs_direct_materials_costs REAL,
  cs_tax_portion            REAL,
  cs_prod_indirect_labor    REAL,
  cs_prod_indirect_others   REAL,
  cs_direct_labor_costs     REAL,
  cs_depreciation_others    REAL,
  cs_mfg_overhead           REAL,
  PRIMARY KEY (scenario_id, product_name, node_name)
);

CREATE TABLE IF NOT EXISTS scenario_tariff (
  scenario_id  TEXT NOT NULL REFERENCES scenario(scenario_id) ON DELETE CASCADE,
  product_name TEXT NOT NULL,
  from_node    TEXT NOT NULL,
  to_node      TEXT NOT NULL,
  tariff_rate  REAL NOT NULL,
  PRIMARY KEY (scenario_id, product_name, from_node, to_node)
);

-- 実行ログ/結果（後段で利用）
CREATE TABLE IF NOT EXISTS scenario_run (
  run_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  scenario_id TEXT NOT NULL REFERENCES scenario(scenario_id) ON DELETE CASCADE,
  started_at  TEXT NOT NULL DEFAULT (datetime('now')),
  finished_at TEXT,
  notes       TEXT
);

CREATE TABLE IF NOT EXISTS scenario_result_summary (
  run_id        INTEGER PRIMARY KEY REFERENCES scenario_run(run_id) ON DELETE CASCADE,
  total_revenue REAL NOT NULL,
  total_profit  REAL NOT NULL,
  profit_ratio  REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS scenario_result_node (
  run_id       INTEGER NOT NULL REFERENCES scenario_run(run_id) ON DELETE CASCADE,
  product_name TEXT NOT NULL,
  node_name    TEXT NOT NULL,
  revenue      REAL NOT NULL,
  profit       REAL NOT NULL,
  price        REAL NOT NULL,
  logistics_costs REAL NOT NULL,
  warehouse_cost  REAL NOT NULL,
  manufacturing_overhead REAL NOT NULL,
  direct_materials_costs REAL NOT NULL,
  tax_portion   REAL NOT NULL,
  PRIMARY KEY (run_id, product_name, node_name)
);
