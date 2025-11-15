# pysi/network/factory.py
from __future__ import annotations
from pathlib import Path
from typing import Optional
import os
# “コア”を別名で読み込むだけ（_core_factory = network_factory.factory）
from pysi.network.network_factory import factory as _core_factory, available_products
def factory(data_dir: str | Path = "data",
            product_name: Optional[str] = None,
            direction: str = "outbound"):
    """
    orchestrator から呼ばれるアダプタ。
    優先度: 明示引数 > 環境変数(PYSI_PRODUCT) > CSV先頭の製品
    """
    data_dir = str(data_dir)
    if product_name is None:
        product_name = os.getenv("PYSI_PRODUCT")
    if product_name is None:
        prods = available_products(data_dir, direction=direction)
        if not prods:
            raise ValueError(f"No Product_name found in CSV under: {data_dir}")
        product_name = prods[0]
    return _core_factory(data_dir=data_dir, product_name=product_name, direction=direction)
