#tools/run_rice_v0.py

from pysi.tutorial.rice_v0_adapter import load_rice_v0
from pysi.tutorial.plot_rice_v0 import plot_psi_with_capacity


if __name__ == "__main__":
    m = load_rice_v0("data/rice_v0")

    print("months:", m.months[:3], "...", m.months[-3:])
    print("total demand:", float(m.demand.sum()))
    print("total production:", float(m.production.sum()))
    print("ending inventory:", float(m.inv.iloc[-1]))
    print("total shortage:", float(m.shortage.sum()))

    plot_psi_with_capacity(m)
