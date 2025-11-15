# csv_to_sqlite.py
import pandas as pd
from models import Session, Scenario, Parameter
# 想定CSV: parameters.csv (key,value,dtype,unit,min,max,help)
# シナリオ名を引数化してもOK
SCENARIO = "rice_baseline"
with Session() as db:
    sc = db.query(Scenario).filter_by(name=SCENARIO).first()
    if not sc:
        sc = Scenario(name=SCENARIO, description="imported from CSV")
        db.add(sc); db.commit()
    df = pd.read_csv("parameters.csv")
    for _,row in df.iterrows():
        p = db.query(Parameter).filter_by(scenario_id=sc.id, key=row['key']).first()
        if not p:
            p = Parameter(scenario_id=sc.id, key=row['key'])
            db.add(p)
        p.value = str(row['value'])
        p.dtype = str(row.get('dtype', 'float'))
        p.unit  = str(row.get('unit', ''))
        p.min   = float(row['min']) if 'min' in row and pd.notna(row['min']) else None
        p.max   = float(row['max']) if 'max' in row and pd.notna(row['max']) else None
        p.help  = str(row.get('help', ''))
    db.commit()
    print("Imported parameters for", SCENARIO)