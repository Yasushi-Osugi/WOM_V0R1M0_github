#collect_psi_data.py
def map_psi_lots2df(node, D_S_flag, psi_lots):
    if D_S_flag == "demand":
        matrix = node.psi4demand
    elif D_S_flag == "supply":
        matrix = node.psi4supply
    else:
        print("error: wrong D_S_flag is defined")
        return pd.DataFrame()
    for week, row in enumerate(matrix):
        for scoip, lots in enumerate(row):
            for step_no, lot_id in enumerate(lots):
                psi_lots.append([node.name, week, scoip, step_no, lot_id])
    for child in node.children:
        map_psi_lots2df(child, D_S_flag, psi_lots)
    columns = ["node_name", "week", "s-co-i-p", "step_no", "lot_id"]
    df = pd.DataFrame(psi_lots, columns=columns)
    return df
# **************************
# collect_psi_data
# **************************
def collect_psi_data(node, D_S_flag, week_start, week_end, psi_data):
    if D_S_flag == "demand":
        psi_lots = []
        df_demand_plan = map_psi_lots2df(node, D_S_flag, psi_lots)
        df_init = df_demand_plan
    elif D_S_flag == "supply":
        psi_lots = []
        df_supply_plan = map_psi_lots2df(node, D_S_flag, psi_lots)
        df_init = df_supply_plan
    else:
        print("error: D_S_flag should be demand or supply")
        return
    condition1 = df_init["node_name"] == node.name
    condition2 = (df_init["week"] >= week_start) & (df_init["week"] <= week_end)
    df = df_init[condition1 & condition2]
    line_data_2I = df[df["s-co-i-p"].isin([2])]
    bar_data_0S = df[df["s-co-i-p"] == 0]
    bar_data_3P = df[df["s-co-i-p"] == 3]
    line_plot_data_2I = line_data_2I.groupby("week")["lot_id"].count()
    bar_plot_data_3P = bar_data_3P.groupby("week")["lot_id"].count()
    bar_plot_data_0S = bar_data_0S.groupby("week")["lot_id"].count()
    # ノードのREVENUEとPROFITを四捨五入
    # root_out_optからroot_outboundの世界へ変換する
    #@241225 be checked
    #@ STOP
    ##@ TEST node_optとnode_originに、revenueとprofit属性を追加
    #revenue = round(node.revenue)
    #profit  = round(node.profit)
    #@241225 STOP "self.nodes_outbound"がscopeにない
    #node_origin = self.nodes_outbound[node.name]
    #
    revenue = round(node.eval_cs_price_sales_shipped)
    profit = round(node.eval_cs_profit)
    # PROFIT_RATIOを計算して四捨五入
    profit_ratio = round((profit / revenue) * 100, 1) if revenue != 0 else 0
    psi_data.append((node.name, revenue, profit, profit_ratio, line_plot_data_2I, bar_plot_data_3P, bar_plot_data_0S))
# *************************
# PSI graph
# *************************
    def show_psi(self, bound, layer):
        print("making PSI graph data...")
        week_start = 1
        week_end = self.plan_range * 53
        psi_data = []
        if bound not in ["outbound", "inbound"]:
            print("error: outbound or inbound must be defined for PSI layer")
            return
        if layer not in ["demand", "supply"]:
            print("error: demand or supply must be defined for PSI layer")
            return
        def traverse_nodes(node):
            for child in node.children:
                traverse_nodes(child)
            collect_psi_data(node, layer, week_start, week_end, psi_data)
        if bound == "outbound":
            traverse_nodes(self.root_node_outbound)
        else:
            traverse_nodes(self.root_node_inbound)
        fig, axs = plt.subplots(len(psi_data), 1, figsize=(5, len(psi_data) * 1))  # figsizeの高さをさらに短く設定
        if len(psi_data) == 1:
            axs = [axs]
        for ax, (node_name, revenue, profit, profit_ratio, line_plot_data_2I, bar_plot_data_3P, bar_plot_data_0S) in zip(axs, psi_data):
            ax2 = ax.twinx()
            ax.bar(line_plot_data_2I.index, line_plot_data_2I.values, color='r', alpha=0.6)
            ax.bar(bar_plot_data_3P.index, bar_plot_data_3P.values, color='g', alpha=0.6)
            ax2.plot(bar_plot_data_0S.index, bar_plot_data_0S.values, color='b')
            ax.set_ylabel('I&P Lots', fontsize=8)
            ax2.set_ylabel('S Lots', fontsize=8)
            ax.set_title(f'Node: {node_name} | REVENUE: {revenue:,} | PROFIT: {profit:,} | PROFIT_RATIO: {profit_ratio}%', fontsize=8)
        fig.tight_layout(pad=0.5)
        print("making PSI figure and widget...")
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        canvas_psi = FigureCanvasTkAgg(fig, master=self.scrollable_frame)
        canvas_psi.draw()
        canvas_psi.get_tk_widget().pack(fill=tk.BOTH, expand=True)
# **** an image of sample data ****
#s = self.psi4demand[w][0] 89 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 90 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 91 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 92 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 93 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 94 [] &[w][3] ['CS_JPN2026010001', 'CS_JPN2026010002'] &[w][2] ['CS_JPN2026010001', 'CS_JPN2026010002']
#s = self.psi4demand[w][0] 95 ['CS_JPN2026010001', 'CS_JPN2026010002'] &[w][3] ['CS_JPN2026020001', 'CS_JPN2026020002', 'CS_JPN2026020003'] &[w][2] ['CS_JPN2026020001', 'CS_JPN2026020002', 'CS_JPN2026020003']
#s = self.psi4demand[w][0] 96 ['CS_JPN2026020001', 'CS_JPN2026020002', 'CS_JPN2026020003'] &[w][3] ['CS_JPN2026030001', 'CS_JPN2026030002', 'CS_JPN2026030003'] &[w][2] ['CS_JPN2026030001', 'CS_JPN2026030002', 'CS_JPN2026030003']
#s = self.psi4demand[w][0] 97 ['CS_JPN2026030001', 'CS_JPN2026030002', 'CS_JPN2026030003'] &[w][3] ['CS_JPN2026040001', 'CS_JPN2026040002', 'CS_JPN2026040003'] &[w][2] ['CS_JPN2026040001', 'CS_JPN2026040002', 'CS_JPN2026040003']
#s = self.psi4demand[w][0] 98 ['CS_JPN2026040001', 'CS_JPN2026040002', 'CS_JPN2026040003'] &[w][3] ['CS_JPN2026050001', 'CS_JPN2026050002', 'CS_JPN2026050003'] &[w][2] ['CS_JPN2026050001', 'CS_JPN2026050002', 'CS_JPN2026050003']
#s = self.psi4demand[w][0] 99 ['CS_JPN2026050001', 'CS_JPN2026050002', 'CS_JPN2026050003'] &[w][3] ['CS_JPN2026060001', 'CS_JPN2026060002', 'CS_JPN2026060003'] &[w][2] ['CS_JPN2026060001', 'CS_JPN2026060002', 'CS_JPN2026060003']
#s = self.psi4demand[w][0] 100 ['CS_JPN2026060001', 'CS_JPN2026060002', 'CS_JPN2026060003'] &[w][3] ['CS_JPN2026070001', 'CS_JPN2026070002', 'CS_JPN2026070003'] &[w][2] ['CS_JPN2026070001', 'CS_JPN2026070002', 'CS_JPN2026070003']
#s = self.psi4demand[w][0] 101 ['CS_JPN2026070001', 'CS_JPN2026070002', 'CS_JPN2026070003'] &[w][3] ['CS_JPN2026080001', 'CS_JPN2026080002', 'CS_JPN2026080003'] &[w][2] ['CS_JPN2026080001', 'CS_JPN2026080002', 'CS_JPN2026080003']
#s = self.psi4demand[w][0] 102 ['CS_JPN2026080001', 'CS_JPN2026080002', 'CS_JPN2026080003'] &[w][3] ['CS_JPN2026090001', 'CS_JPN2026090002', 'CS_JPN2026090003'] &[w][2] ['CS_JPN2026090001', 'CS_JPN2026090002', 'CS_JPN2026090003']
#s = self.psi4demand[w][0] 103 ['CS_JPN2026090001', 'CS_JPN2026090002', 'CS_JPN2026090003'] &[w][3] ['CS_JPN2026100001', 'CS_JPN2026100002', 'CS_JPN2026100003'] &[w][2] ['CS_JPN2026100001', 'CS_JPN2026100002', 'CS_JPN2026100003']
#s = self.psi4demand[w][0] 104 ['CS_JPN2026100001', 'CS_JPN2026100002', 'CS_JPN2026100003'] &[w][3] ['CS_JPN2026110001', 'CS_JPN2026110002', 'CS_JPN2026110003'] &[w][2] ['CS_JPN2026110001', 'CS_JPN2026110002', 'CS_JPN2026110003']
#s = self.psi4demand[w][0] 105 ['CS_JPN2026110001', 'CS_JPN2026110002', 'CS_JPN2026110003'] &[w][3] ['CS_JPN2026120001', 'CS_JPN2026120002', 'CS_JPN2026120003'] &[w][2] ['CS_JPN2026120001', 'CS_JPN2026120002', 'CS_JPN2026120003']
#s = self.psi4demand[w][0] 106 ['CS_JPN2026120001', 'CS_JPN2026120002', 'CS_JPN2026120003'] &[w][3] ['CS_JPN2026130001', 'CS_JPN2026130002', 'CS_JPN2026130003'] &[w][2] ['CS_JPN2026130001', 'CS_JPN2026130002', 'CS_JPN2026130003']
#s = self.psi4demand[w][0] 107 ['CS_JPN2026130001', 'CS_JPN2026130002', 'CS_JPN2026130003'] &[w][3] ['CS_JPN2026140001', 'CS_JPN2026140002', 'CS_JPN2026140003'] &[w][2] ['CS_JPN2026140001', 'CS_JPN2026140002', 'CS_JPN2026140003']
#s = self.psi4demand[w][0] 108 ['CS_JPN2026140001', 'CS_JPN2026140002', 'CS_JPN2026140003'] &[w][3] ['CS_JPN2026150001', 'CS_JPN2026150002', 'CS_JPN2026150003'] &[w][2] ['CS_JPN2026150001', 'CS_JPN2026150002', 'CS_JPN2026150003']
#s = self.psi4demand[w][0] 109 ['CS_JPN2026150001', 'CS_JPN2026150002', 'CS_JPN2026150003'] &[w][3] ['CS_JPN2026160001', 'CS_JPN2026160002', 'CS_JPN2026160003'] &[w][2] ['CS_JPN2026160001', 'CS_JPN2026160002', 'CS_JPN2026160003']
#s = self.psi4demand[w][0] 110 ['CS_JPN2026160001', 'CS_JPN2026160002', 'CS_JPN2026160003'] &[w][3] ['CS_JPN2026170001', 'CS_JPN2026170002', 'CS_JPN2026170003'] &[w][2] ['CS_JPN2026170001', 'CS_JPN2026170002', 'CS_JPN2026170003']
#s = self.psi4demand[w][0] 111 ['CS_JPN2026170001', 'CS_JPN2026170002', 'CS_JPN2026170003'] &[w][3] ['CS_JPN2026180001', 'CS_JPN2026180002', 'CS_JPN2026180003'] &[w][2] ['CS_JPN2026180001', 'CS_JPN2026180002', 'CS_JPN2026180003']
#s = self.psi4demand[w][0] 112 ['CS_JPN2026180001', 'CS_JPN2026180002', 'CS_JPN2026180003'] &[w][3] ['CS_JPN2026190001', 'CS_JPN2026190002', 'CS_JPN2026190003'] &[w][2] ['CS_JPN2026190001', 'CS_JPN2026190002', 'CS_JPN2026190003']
#s = self.psi4demand[w][0] 113 ['CS_JPN2026190001', 'CS_JPN2026190002', 'CS_JPN2026190003'] &[w][3] ['CS_JPN2026200001', 'CS_JPN2026200002', 'CS_JPN2026200003'] &[w][2] ['CS_JPN2026200001', 'CS_JPN2026200002', 'CS_JPN2026200003']
#s = self.psi4demand[w][0] 114 ['CS_JPN2026200001', 'CS_JPN2026200002', 'CS_JPN2026200003'] &[w][3] ['CS_JPN2026210001', 'CS_JPN2026210002', 'CS_JPN2026210003'] &[w][2] ['CS_JPN2026210001', 'CS_JPN2026210002', 'CS_JPN2026210003']
#s = self.psi4demand[w][0] 115 ['CS_JPN2026210001', 'CS_JPN2026210002', 'CS_JPN2026210003'] &[w][3] ['CS_JPN2026220001', 'CS_JPN2026220002', 'CS_JPN2026220003'] &[w][2] ['CS_JPN2026220001', 'CS_JPN2026220002', 'CS_JPN2026220003']
#s = self.psi4demand[w][0] 116 ['CS_JPN2026220001', 'CS_JPN2026220002', 'CS_JPN2026220003'] &[w][3] ['CS_JPN2026230001', 'CS_JPN2026230002', 'CS_JPN2026230003'] &[w][2] ['CS_JPN2026230001', 'CS_JPN2026230002', 'CS_JPN2026230003']
#s = self.psi4demand[w][0] 117 ['CS_JPN2026230001', 'CS_JPN2026230002', 'CS_JPN2026230003'] &[w][3] ['CS_JPN2026240001', 'CS_JPN2026240002', 'CS_JPN2026240003'] &[w][2] ['CS_JPN2026240001', 'CS_JPN2026240002', 'CS_JPN2026240003']
#s = self.psi4demand[w][0] 118 ['CS_JPN2026240001', 'CS_JPN2026240002', 'CS_JPN2026240003'] &[w][3] ['CS_JPN2026250001', 'CS_JPN2026250002', 'CS_JPN2026250003'] &[w][2] ['CS_JPN2026250001', 'CS_JPN2026250002', 'CS_JPN2026250003']
#s = self.psi4demand[w][0] 119 ['CS_JPN2026250001', 'CS_JPN2026250002', 'CS_JPN2026250003'] &[w][3] ['CS_JPN2026260001', 'CS_JPN2026260002', 'CS_JPN2026260003'] &[w][2] ['CS_JPN2026260001', 'CS_JPN2026260002', 'CS_JPN2026260003']
#s = self.psi4demand[w][0] 120 ['CS_JPN2026260001', 'CS_JPN2026260002', 'CS_JPN2026260003'] &[w][3] ['CS_JPN2026270001', 'CS_JPN2026270002', 'CS_JPN2026270003'] &[w][2] ['CS_JPN2026270001', 'CS_JPN2026270002', 'CS_JPN2026270003']
#s = self.psi4demand[w][0] 121 ['CS_JPN2026270001', 'CS_JPN2026270002', 'CS_JPN2026270003'] &[w][3] ['CS_JPN2026280001', 'CS_JPN2026280002', 'CS_JPN2026280003'] &[w][2] ['CS_JPN2026280001', 'CS_JPN2026280002', 'CS_JPN2026280003']
#s = self.psi4demand[w][0] 122 ['CS_JPN2026280001', 'CS_JPN2026280002', 'CS_JPN2026280003'] &[w][3] ['CS_JPN2026290001', 'CS_JPN2026290002', 'CS_JPN2026290003'] &[w][2] ['CS_JPN2026290001', 'CS_JPN2026290002', 'CS_JPN2026290003']
#s = self.psi4demand[w][0] 123 ['CS_JPN2026290001', 'CS_JPN2026290002', 'CS_JPN2026290003'] &[w][3] ['CS_JPN2026300001', 'CS_JPN2026300002', 'CS_JPN2026300003'] &[w][2] ['CS_JPN2026300001', 'CS_JPN2026300002', 'CS_JPN2026300003']
#s = self.psi4demand[w][0] 124 ['CS_JPN2026300001', 'CS_JPN2026300002', 'CS_JPN2026300003'] &[w][3] ['CS_JPN2026310001', 'CS_JPN2026310002', 'CS_JPN2026310003'] &[w][2] ['CS_JPN2026310001', 'CS_JPN2026310002', 'CS_JPN2026310003']
#s = self.psi4demand[w][0] 125 ['CS_JPN2026310001', 'CS_JPN2026310002', 'CS_JPN2026310003'] &[w][3] ['CS_JPN2026320001', 'CS_JPN2026320002', 'CS_JPN2026320003'] &[w][2] ['CS_JPN2026320001', 'CS_JPN2026320002', 'CS_JPN2026320003']
#s = self.psi4demand[w][0] 126 ['CS_JPN2026320001', 'CS_JPN2026320002', 'CS_JPN2026320003'] &[w][3] ['CS_JPN2026330001', 'CS_JPN2026330002', 'CS_JPN2026330003'] &[w][2] ['CS_JPN2026330001', 'CS_JPN2026330002', 'CS_JPN2026330003']
#s = self.psi4demand[w][0] 127 ['CS_JPN2026330001', 'CS_JPN2026330002', 'CS_JPN2026330003'] &[w][3] ['CS_JPN2026340001', 'CS_JPN2026340002', 'CS_JPN2026340003'] &[w][2] ['CS_JPN2026340001', 'CS_JPN2026340002', 'CS_JPN2026340003']
#s = self.psi4demand[w][0] 128 ['CS_JPN2026340001', 'CS_JPN2026340002', 'CS_JPN2026340003'] &[w][3] ['CS_JPN2026350001', 'CS_JPN2026350002', 'CS_JPN2026350003'] &[w][2] ['CS_JPN2026350001', 'CS_JPN2026350002', 'CS_JPN2026350003']
#s = self.psi4demand[w][0] 129 ['CS_JPN2026350001', 'CS_JPN2026350002', 'CS_JPN2026350003'] &[w][3] ['CS_JPN2026360001', 'CS_JPN2026360002', 'CS_JPN2026360003'] &[w][2] ['CS_JPN2026360001', 'CS_JPN2026360002', 'CS_JPN2026360003']
#s = self.psi4demand[w][0] 130 ['CS_JPN2026360001', 'CS_JPN2026360002', 'CS_JPN2026360003'] &[w][3] ['CS_JPN2026370001', 'CS_JPN2026370002', 'CS_JPN2026370003'] &[w][2] ['CS_JPN2026370001', 'CS_JPN2026370002', 'CS_JPN2026370003']
#s = self.psi4demand[w][0] 131 ['CS_JPN2026370001', 'CS_JPN2026370002', 'CS_JPN2026370003'] &[w][3] ['CS_JPN2026380001', 'CS_JPN2026380002', 'CS_JPN2026380003'] &[w][2] ['CS_JPN2026380001', 'CS_JPN2026380002', 'CS_JPN2026380003']
#s = self.psi4demand[w][0] 132 ['CS_JPN2026380001', 'CS_JPN2026380002', 'CS_JPN2026380003'] &[w][3] ['CS_JPN2026390001', 'CS_JPN2026390002', 'CS_JPN2026390003'] &[w][2] ['CS_JPN2026390001', 'CS_JPN2026390002', 'CS_JPN2026390003']
#s = self.psi4demand[w][0] 133 ['CS_JPN2026390001', 'CS_JPN2026390002', 'CS_JPN2026390003'] &[w][3] ['CS_JPN2026400001', 'CS_JPN2026400002', 'CS_JPN2026400003'] &[w][2] ['CS_JPN2026400001', 'CS_JPN2026400002', 'CS_JPN2026400003']
#s = self.psi4demand[w][0] 134 ['CS_JPN2026400001', 'CS_JPN2026400002', 'CS_JPN2026400003'] &[w][3] ['CS_JPN2026410001', 'CS_JPN2026410002', 'CS_JPN2026410003'] &[w][2] ['CS_JPN2026410001', 'CS_JPN2026410002', 'CS_JPN2026410003']
#s = self.psi4demand[w][0] 135 ['CS_JPN2026410001', 'CS_JPN2026410002', 'CS_JPN2026410003'] &[w][3] ['CS_JPN2026420001', 'CS_JPN2026420002', 'CS_JPN2026420003'] &[w][2] ['CS_JPN2026420001', 'CS_JPN2026420002', 'CS_JPN2026420003']
#s = self.psi4demand[w][0] 136 ['CS_JPN2026420001', 'CS_JPN2026420002', 'CS_JPN2026420003'] &[w][3] ['CS_JPN2026430001', 'CS_JPN2026430002', 'CS_JPN2026430003'] &[w][2] ['CS_JPN2026430001', 'CS_JPN2026430002', 'CS_JPN2026430003']
#s = self.psi4demand[w][0] 137 ['CS_JPN2026430001', 'CS_JPN2026430002', 'CS_JPN2026430003'] &[w][3] ['CS_JPN2026440001', 'CS_JPN2026440002', 'CS_JPN2026440003'] &[w][2] ['CS_JPN2026440001', 'CS_JPN2026440002', 'CS_JPN2026440003']
#s = self.psi4demand[w][0] 138 ['CS_JPN2026440001', 'CS_JPN2026440002', 'CS_JPN2026440003'] &[w][3] ['CS_JPN2026450001', 'CS_JPN2026450002', 'CS_JPN2026450003'] &[w][2] ['CS_JPN2026450001', 'CS_JPN2026450002', 'CS_JPN2026450003']
#s = self.psi4demand[w][0] 139 ['CS_JPN2026450001', 'CS_JPN2026450002', 'CS_JPN2026450003'] &[w][3] ['CS_JPN2026460001', 'CS_JPN2026460002', 'CS_JPN2026460003'] &[w][2] ['CS_JPN2026460001', 'CS_JPN2026460002', 'CS_JPN2026460003']
#s = self.psi4demand[w][0] 140 ['CS_JPN2026460001', 'CS_JPN2026460002', 'CS_JPN2026460003'] &[w][3] ['CS_JPN2026470001', 'CS_JPN2026470002', 'CS_JPN2026470003'] &[w][2] ['CS_JPN2026470001', 'CS_JPN2026470002', 'CS_JPN2026470003']
#s = self.psi4demand[w][0] 141 ['CS_JPN2026470001', 'CS_JPN2026470002', 'CS_JPN2026470003'] &[w][3] ['CS_JPN2026480001', 'CS_JPN2026480002', 'CS_JPN2026480003'] &[w][2] ['CS_JPN2026480001', 'CS_JPN2026480002', 'CS_JPN2026480003']
#s = self.psi4demand[w][0] 142 ['CS_JPN2026480001', 'CS_JPN2026480002', 'CS_JPN2026480003'] &[w][3] ['CS_JPN2026490001', 'CS_JPN2026490002', 'CS_JPN2026490003'] &[w][2] ['CS_JPN2026490001', 'CS_JPN2026490002', 'CS_JPN2026490003']
#s = self.psi4demand[w][0] 143 ['CS_JPN2026490001', 'CS_JPN2026490002', 'CS_JPN2026490003'] &[w][3] ['CS_JPN2026500001', 'CS_JPN2026500002', 'CS_JPN2026500003'] &[w][2] ['CS_JPN2026500001', 'CS_JPN2026500002', 'CS_JPN2026500003']
#s = self.psi4demand[w][0] 144 ['CS_JPN2026500001', 'CS_JPN2026500002', 'CS_JPN2026500003'] &[w][3] ['CS_JPN2026510001', 'CS_JPN2026510002', 'CS_JPN2026510003'] &[w][2] ['CS_JPN2026510001', 'CS_JPN2026510002', 'CS_JPN2026510003']
#s = self.psi4demand[w][0] 145 ['CS_JPN2026510001', 'CS_JPN2026510002', 'CS_JPN2026510003'] &[w][3] ['CS_JPN2026520001', 'CS_JPN2026520002', 'CS_JPN2026520003'] &[w][2] ['CS_JPN2026520001', 'CS_JPN2026520002', 'CS_JPN2026520003']
#s = self.psi4demand[w][0] 146 ['CS_JPN2026520001', 'CS_JPN2026520002', 'CS_JPN2026520003'] &[w][3] ['CS_JPN2026530001', 'CS_JPN2026530002'] &[w][2] ['CS_JPN2026530001', 'CS_JPN2026530002']
#s = self.psi4demand[w][0] 147 ['CS_JPN2026530001', 'CS_JPN2026530002'] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 148 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 149 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 150 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 151 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 152 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 153 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 154 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 155 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 156 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 157 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 158 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 159 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 160 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 161 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 162 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 163 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 164 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 165 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 166 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 167 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 168 [] &[w][3] [] &[w][2] []
#s = self.psi4demand[w][0] 169 [] &[w][3] [] &[w][2] []
