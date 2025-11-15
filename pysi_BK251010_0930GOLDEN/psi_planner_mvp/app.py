# app.py
import streamlit as st
import pandas as pd
import altair as alt
import json
import os
from sqlalchemy.orm import Session
from models import Session as DBSession, Scenario, Parameter, Run
from psi_runner import run_simulation
from psi_adapter import run_real_engine, EngineNotAvailable
from engine_api import build_plan_from_db, collect_facets, count_nodes  # 追加
st.set_page_config(page_title="Global Weekly PSI Planner", layout="wide")
st.title("PSI Planner – シナリオ/パラメータ設定・実行")
# --- ヘルパー ---
def get_or_create_scenario(s: Session, name: str) -> Scenario:
    sc = s.query(Scenario).filter_by(name=name).first()
    if not sc:
        sc = Scenario(name=name, description="Rice SC baseline")
        s.add(sc); s.commit()
    return sc
PARAM_DEFS = [
    ("lead_time_days","float","days",0.0,180.0,"補充LT（日）"),  # 型をfloatに統一
    ("price_markup","float","ratio",0.8,1.5,"原価→販売価格倍率"),
    ("service_level","float","ratio",0.8,0.999,"在庫サービス水準")
]
with DBSession() as db:
    # シナリオ選択/作成
    st.sidebar.header("Scenario")
    names = [x.name for x in db.query(Scenario).all()]
    sel = st.sidebar.selectbox("シナリオを選択", names + ["(新規)"])
    if sel == "(新規)":
        new = st.sidebar.text_input("新規シナリオ名", "rice_baseline")
        if st.sidebar.button("作成"):
            get_or_create_scenario(db, new)
            st.rerun()
        st.stop()
    sc = db.query(Scenario).filter_by(name=sel).first()
    # 実エンジン切替
    USE_REAL = st.sidebar.toggle("Use real PSI engine", value=bool(os.getenv("USE_REAL_ENGINE")))
    # --- プルダウン：PlanGraph から候補を自動抽出 ---
    # 既存の root, facet = build_plan_from_db(...), collect_facets(root) の代わりに：
    root_all, _m = build_plan_from_db(sc.name, filters=None)
    facet_all = collect_facets(root_all)
    st.sidebar.caption(
        "facets: " +
        ", ".join([f"{k}={len(v)}" for k,v in (facet_all if 'facet_all' in locals() else facet).items()])
    )
    # --- Debug: ノード一覧と件数を表示（確認用） ---
    def flatten(root):
        rows=[]
        def walk(n,depth=0):
            rows.append({
                "id": n.id,
                "name": n.name,
                "sku": n.sku,
                "node_type": n.node_type,
                "region": n.region,
                "origin": n.origin,
                "dest": n.dest,
                "direction": n.attrs.get("direction", "OUT" if not str(n.id).startswith("IN::") else "IN")
            })
            for c in n.children: walk(c, depth+1)
        walk(root); return pd.DataFrame(rows)
    with st.expander("Debug: Graph stats / nodes"):
        st.write(f"Graph source: {_m.get('built_from')}  nodes={count_nodes(root_all)}")
        st.dataframe(flatten(root_all), use_container_width=True, height=240)
        #st.write(f"Graph source: {_meta.get('built_from')}  nodes={count_nodes(root)}")
        #st.dataframe(flatten(root), use_container_width=True, height=240)
    # 既存の facet = collect_facets(root) の直後にラベル辞書を作成
    def make_labels(root):
        m={}
        def walk(n):
            tag = "[IN]" if str(n.id).startswith("IN::") else "[OUT]"
            base = str(n.id).replace("IN::","")
            m[n.id] = f"{tag} {base} ｜ {n.name}"
            for c in n.children: walk(c)
        walk(root); return m
    labels = make_labels(root_all)
    st.sidebar.header("Scope Filters (optional)")
    # --- フィルタUI（Origin/Dest/Channel をラベル表示に） ---
    with st.sidebar.expander("Filters", expanded=False):
        sku_sel     = st.multiselect("SKU",     options=facet_all["sku"],
                                    default=facet_all["sku"][:1] if facet_all["sku"] else [])
        region_sel  = st.multiselect("Region",  options=facet_all["region"],
                                    default=facet_all["region"][:1] if facet_all["region"] else [])
        # Filters の expander 内、Origin/Dest を出す直前に
        direction = st.radio("Direction", ["OUT+IN", "OUT only", "IN only"], horizontal=True)
        def keep_by_dir(x: str) -> bool:
            is_in = str(x).startswith("IN::")
            return (direction == "OUT+IN") or (direction == "OUT only" and not is_in) or (direction == "IN only" and is_in)
        origin_opts = sorted([x for x in facet_all["origin"] if keep_by_dir(x)], key=lambda v: str(v).replace("IN::",""))
        origin_sel  = st.multiselect("Origin", origin_opts,
                                    default=origin_opts[:1] if origin_opts else [],
                                    format_func=lambda v: labels.get(v, v))
        dest_opts   = sorted([x for x in facet_all["dest"] if keep_by_dir(x)], key=lambda v: str(v).replace("IN::",""))
        dest_sel    = st.multiselect("Dest", dest_opts,
                                    default=dest_opts[:1] if dest_opts else [],
                                    format_func=lambda v: labels.get(v, v))
        #origin_opts = sorted(facet_all["origin"], key=lambda x: str(x).replace("IN::",""))
        #origin_sel  = st.multiselect("Origin",  options=origin_opts,
        #                            default=origin_opts[:1] if origin_opts else [],
        #                            format_func=lambda v: labels.get(v, v))
        #dest_opts   = sorted(facet_all["dest"], key=lambda x: str(x).replace("IN::",""))
        #dest_sel    = st.multiselect("Dest",    options=dest_opts,
        #                            default=dest_opts[:1] if dest_opts else [],
        #                            format_func=lambda v: labels.get(v, v))
        channel_sel = st.multiselect("Channel", options=facet_all["channel"],
                                    default=facet_all["channel"][:1] if facet_all["channel"] else [])
    # 段階連動版（SKU→Region→Origin→Dest）にしたい場合
    #root, _meta = build_plan_from_db(sc.name, filters=None)
    #facet = collect_facets(root)
    #with st.sidebar.expander("Filters", expanded=False):
    #    sku_sel = st.multiselect("SKU", facet["sku"],
    #                            default=facet["sku"][:1] if facet["sku"] else [])
    #    # SKUで剪定→候補更新
    #    filt = {"sku": sku_sel} if sku_sel else None
    #    root_sku, _ = build_plan_from_db(sc.name, filters=filt)
    #    facet_sku = collect_facets(root_sku)
    #    region_sel = st.multiselect("Region", facet_sku["region"],
    #                                default=facet_sku["region"][:1] if facet_sku["region"] else [])
    #    filt = {"sku": sku_sel, "region": region_sel} if (sku_sel or region_sel) else None
    #    root_sr, _ = build_plan_from_db(sc.name, filters=filt)
    #    facet_sr = collect_facets(root_sr)
    #    origin_opts = sorted(facet_sr["origin"], key=lambda x: str(x).replace("IN::",""))
    #    origin_sel  = st.multiselect("Origin", origin_opts,
    #                                default=origin_opts[:1] if origin_opts else [],
    #                                format_func=lambda v: labels.get(v, v))
    #    filt = {"sku": sku_sel, "region": region_sel, "origin": origin_sel} \
    #        if any([sku_sel, region_sel, origin_sel]) else None
    #    root_sro, _ = build_plan_from_db(sc.name, filters=filt)
    #    facet_sro = collect_facets(root_sro)
    #    dest_opts = sorted(facet_sro["dest"], key=lambda x: str(x).replace("IN::",""))
    #    dest_sel  = st.multiselect("Dest", dest_opts,
    #                            default=dest_opts[:1] if dest_opts else [],
    #                            format_func=lambda v: labels.get(v, v))
    #    filt = {"sku": sku_sel, "region": region_sel, "origin": origin_sel, "dest": dest_sel} \
    #        if any([sku_sel, region_sel, origin_sel, dest_sel]) else None
    #    root_srod, _ = build_plan_from_db(sc.name, filters=filt)
    #    facet_srod = collect_facets(root_srod)
    #    channel_sel = st.multiselect("Channel", facet_srod["channel"],
    #                                default=facet_srod["channel"][:1] if facet_srod["channel"] else [])
    # 最終フィルタを辞書化
    filters = {}
    if sku_sel:     filters["sku"]     = sku_sel if len(sku_sel)>1 else sku_sel[0]
    if region_sel:  filters["region"]  = region_sel if len(region_sel)>1 else region_sel[0]
    if origin_sel:  filters["origin"]  = origin_sel if len(origin_sel)>1 else origin_sel[0]
    if dest_sel:    filters["dest"]    = dest_sel if len(dest_sel)>1 else dest_sel[0]
    if channel_sel: filters["channel"] = channel_sel if len(channel_sel)>1 else channel_sel[0]
    if filters:
        st.sidebar.caption("適用フィルタ")
        st.sidebar.code(json.dumps(filters, ensure_ascii=False, indent=2))
    root_all, _m = build_plan_from_db(sc.name, filters=filters or None)
    with st.expander("Debug: Graph after filters"):
        st.write(f"nodes={count_nodes(root_all)}  filters={filters}")
        st.dataframe(flatten(root_all), use_container_width=True, height=240)
    st.subheader(f"Parameters: {sc.name}")
    # パラメータ編集（3列）
    cols = st.columns(3)
    updates = {}
    for i,(k,dt,unit,vmin,vmax,help_) in enumerate(PARAM_DEFS):
        p = next((x for x in sc.parameters if x.key==k), None)
        cur = float(p.value) if p else (vmin+vmax)/2
        with cols[i]:
            val = st.number_input(
                f"{k} ({unit})",
                min_value=float(vmin), max_value=float(vmax),
                value=float(cur), step=0.01, help=help_
            )
            updates[k]=val
    # バリデーション
    errors = []
    for (k,dt,unit,vmin,vmax,help_) in PARAM_DEFS:
        val = updates[k]
        if dt == "float" and not (float(vmin) <= float(val) <= float(vmax)):
            errors.append(f"{k} は {vmin}〜{vmax} の範囲で入力してください")
    if errors:
        st.warning("\n".join(errors))
    if st.button("保存", type="primary"):
        if errors:
            st.error("入力エラーを修正してください")
        else:
            for k,val in updates.items():
                p = next((x for x in sc.parameters if x.key==k), None)
                if not p:
                    p = Parameter(scenario_id=sc.id, key=k, dtype="float",
                                  unit=next(x[2] for x in PARAM_DEFS if x[0]==k))
                    db.add(p)
                p.value = str(val)
            db.commit()
            st.success("保存しました。")
    st.caption("パラメータ辞書（型/単位/範囲/説明）")
    st.table(pd.DataFrame([
        {"key": k, "type": dt, "unit": unit, "range": f"{vmin}–{vmax}", "help": help_}
        for (k,dt,unit,vmin,vmax,help_) in PARAM_DEFS
    ]))
    st.divider()
    # 感度分析（スイープ）
    st.subheader("価格感度の例：price_markup ±% をスイープ")
    sweep = st.slider("変動幅(%)", -20, 20, 5, 1)
    if st.button("PSIを実行"):
        if errors:
            st.error("入力エラーを修正してください")
            st.stop()
        base = {p.key: p.value for p in sc.parameters}
        variants = [
            ("baseline", 0),
            ("price_minus", -sweep),
            ("price_plus", sweep),
        ]
        rows = []
        for label, pct in variants:
            params = base.copy()
            params["price_markup"] = str(float(base.get("price_markup", 1.2)) * (1+pct/100))
            r = Run(scenario_id=sc.id, label=label, sweep={"price_markup_pct": pct})
            db.add(r); db.commit()
            try:
                if USE_REAL:
                    kpi = run_real_engine(sc.name, params, filters=filters if filters else None)
                else:
                    kpi = run_simulation(sc.name, params)  # ダミーはfilters未対応
            except EngineNotAvailable:
                st.info("実エンジンが未接続のためスタブで実行します")
                kpi = run_simulation(sc.name, params)
            r.status = "done"; r.summary = kpi; db.commit()
            rows.append({"variant": label, **kpi})
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True)
        # チャート
        chart1 = alt.Chart(df).mark_bar().encode(
            x=alt.X('variant:N', title=''),
            y=alt.Y('gross_profit:Q', title='Gross Profit'),
            color='variant'
        )
        chart2 = alt.Chart(df).mark_bar().encode(
            x=alt.X('variant:N', title=''),
            y=alt.Y('inventory_turns:Q', title='Inventory Turns'),
            color='variant'
        )
        chart3 = alt.Chart(df).mark_bar().encode(
            x=alt.X('variant:N', title=''),
            y=alt.Y('stockout_rate:Q', title='Stockout Rate'),
            color='variant'
        )
        st.altair_chart((chart1 | chart2 | chart3).resolve_scale(y='independent'), use_container_width=True)
