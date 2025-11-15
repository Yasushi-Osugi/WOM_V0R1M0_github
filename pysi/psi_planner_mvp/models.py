# models.py
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Text, ForeignKey,
    DateTime, JSON, create_engine, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
Base = declarative_base()
class Scenario(Base):
    __tablename__ = "scenarios"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(Text, default="")
    tags = Column(String, default="")          # "rice,baseline,JP"
    base_date = Column(String, default="2025W32")
    parameters = relationship("Parameter", back_populates="scenario", cascade="all, delete-orphan")
class Parameter(Base):
    __tablename__ = "parameters"
    id = Column(Integer, primary_key=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))
    key = Column(String, nullable=False)
    value = Column(String, nullable=False)
    dtype = Column(String, default="float")    # int|float|string|bool|json
    unit = Column(String, default="")          # days|JPY|ratio
    min = Column(Float, nullable=True)
    max = Column(Float, nullable=True)
    help = Column(Text, default="")
    scenario = relationship("Scenario", back_populates="parameters")
    __table_args__ = (UniqueConstraint('scenario_id','key', name='uq_scenario_key'),)
class CostItem(Base):
    __tablename__ = "cost_items"
    id = Column(Integer, primary_key=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))
    name = Column(String)                      # 加工費/ロジ費/保管費 等
    scope = Column(String)                     # SKU|DC|lane|global
    fixed = Column(Boolean, default=False)
    amount = Column(Float)                     # JPY
    unit = Column(String, default="JPY")
    note = Column(Text, default="")
class Elasticity(Base):
    __tablename__ = "elasticities"
    id = Column(Integer, primary_key=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))
    sku = Column(String)
    region = Column(String)
    elastic_price = Column(Float)              # 価格弾力性（マイナスが通常）
    elastic_promo = Column(Float)              # 施策弾力性
class Run(Base):
    __tablename__ = "runs"
    id = Column(Integer, primary_key=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"))
    label = Column(String)                     # "baseline" / "price+5%" 等
    sweep = Column(JSON, default={})           # 変動させたパラメータ
    created_at = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="queued") # queued|done|failed
    summary = Column(JSON, default={})         # KPIサマリ（在庫回転/粗利 等）
engine = create_engine("sqlite:///psi.db")
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)