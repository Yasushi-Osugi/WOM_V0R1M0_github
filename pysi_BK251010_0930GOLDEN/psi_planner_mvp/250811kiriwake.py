from engine_api import build_plan_from_db
root, meta = build_plan_from_db("rice_baseline", filters=None)
print(meta)
