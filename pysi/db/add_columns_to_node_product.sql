-- Add columns to node_product table for detailed production cost components
ALTER TABLE node_product ADD COLUMN cs_prod_indirect_labor     REAL NOT NULL DEFAULT 0.0;
ALTER TABLE node_product ADD COLUMN cs_prod_indirect_others    REAL NOT NULL DEFAULT 0.0;
ALTER TABLE node_product ADD COLUMN cs_direct_labor_costs      REAL NOT NULL DEFAULT 0.0;
ALTER TABLE node_product ADD COLUMN cs_depreciation_others     REAL NOT NULL DEFAULT 0.0;
ALTER TABLE node_product ADD COLUMN cs_mfg_overhead            REAL NOT NULL DEFAULT 0.0;
