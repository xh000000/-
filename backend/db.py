"""数据层：SQLAlchemy 2.0 ORM 映射（18 张表）与建模配套工具。

分工
----
- 模型：一张表一个类，列名与库内保持一致；业务代码只跟模型打交道。
- ``MappingMixin``：让模型实例兼容 ``row['col']`` / ``dict(row)`` 这种字典式取值，
  业务函数里大量存在这类写法，保留它可以避免为了「像 ORM」而把可读代码改差。
- 迁移工具：``create_schema`` 建表、``add_columns`` 补列、``has_flag`` / ``set_flag``
  记录一次性迁移。DDL 无法用 ORM 表达，是这里唯一保留的 SQL 文本。

注意：``reports.metadata`` 与 Declarative 的 ``Base.metadata`` 同名，
模型属性必须改名为 ``metadata_`` 并通过 ``mapped_column('metadata')`` 指定真实列名。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Float, Integer, LargeBinary, Text, create_engine, event, inspect, select, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

ROOT = Path(__file__).parent
DB_PATH = Path(os.getenv('DATA_DIR', str(ROOT / 'data'))) / 'research.db'
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DB_URL = os.getenv('DATABASE_URL') or ('sqlite:///' + DB_PATH.as_posix())


class Base(DeclarativeBase):
    """所有模型的基类。"""


_COLMAPS: dict[type, dict[str, str]] = {}


def colmap(model: type) -> dict[str, str]:
    """数据库列名 → ORM 属性名。结果按类缓存，避免每次下标访问都重建。

    注意不能用 ``table.columns[i].key``：``mapped_column('metadata')`` 会把
    Column.key 也设成 'metadata'，取不到真实属性名 metadata_。必须走 mapper。
    """
    cached = _COLMAPS.get(model)
    if cached is None:
        cached = {prop.columns[0].name: prop.key for prop in inspect(model).column_attrs}
        _COLMAPS[model] = cached
    return cached


class MappingMixin:
    """让 ORM 实例支持 ``row['col']`` / ``dict(row)`` / ``row.keys()``。

    业务函数里大量使用 sqlite3.Row 的下标访问。实现 keys() + __getitem__ 即可满足
    dict() 的 mapping 协议，模型可以直接当行用，不必到处包 dict()。
    """

    def keys(self):
        return [c.name for c in self.__table__.columns]

    def __getitem__(self, key: str) -> Any:
        # 真实列名 → 属性名。reports.metadata 因与 Base.metadata 冲突而改名 metadata_，
        # 这类列必须走映射表，否则 getattr(self, 'metadata') 会拿到 MetaData 对象。
        attr = colmap(type(self)).get(key, key)
        try:
            return getattr(self, attr)
        except AttributeError:
            raise KeyError(key) from None

    def to_dict(self) -> dict:
        mapping = colmap(type(self))
        return {name: getattr(self, mapping.get(name, name)) for name in self.keys()}


class User(Base, MappingMixin):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    role: Mapped[str | None] = mapped_column(Text)
    salt: Mapped[str | None] = mapped_column(Text)
    hash: Mapped[str | None] = mapped_column(Text)
    dept_id: Mapped[int | None] = mapped_column(Integer)
    phone: Mapped[str | None] = mapped_column(Text, default='')
    title: Mapped[str | None] = mapped_column(Text, default='')
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)
    role_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str | None] = mapped_column(Text, default='')
    last_login_at: Mapped[str | None] = mapped_column(Text, default='')


class SessionRow(Base, MappingMixin):
    __tablename__ = 'sessions'
    token: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer)
    expires: Mapped[float | None] = mapped_column(Float)
    remember: Mapped[int | None] = mapped_column(Integer, default=0)
    last_seen: Mapped[float | None] = mapped_column(Float, default=0)


class Report(Base, MappingMixin):
    __tablename__ = 'reports'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str | None] = mapped_column(Text)
    commodity: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(Text)
    author: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int | None] = mapped_column(Integer, default=1)
    updated: Mapped[str | None] = mapped_column(Text)
    document: Mapped[str | None] = mapped_column(Text, default='')
    config_snapshot: Mapped[str | None] = mapped_column(Text, default='')
    category_id: Mapped[int | None] = mapped_column(Integer)
    workflow_state: Mapped[str | None] = mapped_column(Text, default='')
    inherited_from: Mapped[int | None] = mapped_column(Integer)
    metadata_: Mapped[str | None] = mapped_column('metadata', Text, default='')
    updated_by: Mapped[str | None] = mapped_column(Text, default='')
    published_at: Mapped[str | None] = mapped_column(Text, default='')
    approved_at: Mapped[str | None] = mapped_column(Text, default='')
    views: Mapped[int | None] = mapped_column(Integer, default=0)
    issue: Mapped[int | None] = mapped_column(Integer, default=0)
    deleted: Mapped[int | None] = mapped_column(Integer, default=0)
    scheduled_at: Mapped[str | None] = mapped_column(Text, default='')


class Version(Base, MappingMixin):
    __tablename__ = 'versions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int | None] = mapped_column(Integer)
    body: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str | None] = mapped_column(Text)
    at: Mapped[str | None] = mapped_column(Text)
    document: Mapped[str | None] = mapped_column(Text, default='')
    config_snapshot: Mapped[str | None] = mapped_column(Text, default='')
    metadata_: Mapped[str | None] = mapped_column('metadata', Text, default='')


class Event(Base, MappingMixin):
    __tablename__ = 'events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int | None] = mapped_column(Integer)
    actor: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int | None] = mapped_column(Integer)
    at: Mapped[str | None] = mapped_column(Text)


class Observation(Base, MappingMixin):
    __tablename__ = 'observations'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str | None] = mapped_column(Text)
    indicator: Mapped[str | None] = mapped_column(Text)
    date: Mapped[str | None] = mapped_column(Text)
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[str | None] = mapped_column(Text)


class PublicationHistory(Base, MappingMixin):
    __tablename__ = 'publication_history'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int | None] = mapped_column(Integer)
    document: Mapped[str | None] = mapped_column(Text)
    config: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[str | None] = mapped_column('metadata', Text)
    body: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[str | None] = mapped_column(Text)


class Category(Base, MappingMixin):
    __tablename__ = 'categories'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    config: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int | None] = mapped_column(Integer, default=1)
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)
    parent_id: Mapped[int | None] = mapped_column(Integer)
    label: Mapped[str | None] = mapped_column(Text, default='')
    sort_order: Mapped[int | None] = mapped_column(Integer, default=0)
    folder: Mapped[int | None] = mapped_column(Integer, default=0)


class CategoryMigration(Base, MappingMixin):
    __tablename__ = 'category_migration'
    category_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_name: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(Integer)


class Commodity(Base, MappingMixin):
    __tablename__ = 'commodities'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    parent_id: Mapped[int | None] = mapped_column(Integer)
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)
    code: Mapped[str | None] = mapped_column(Text, default='')


class Author(Base, MappingMixin):
    __tablename__ = 'authors'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    types: Mapped[str | None] = mapped_column(Text)
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)
    license: Mapped[str | None] = mapped_column(Text, default='')


class ApprovalFlow(Base, MappingMixin):
    __tablename__ = 'approval_flows'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)
    category_ids: Mapped[str | None] = mapped_column(Text, default='[]')
    nodes: Mapped[str | None] = mapped_column(Text, default='[]')
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)


class Role(Base, MappingMixin):
    __tablename__ = 'roles'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    base_role: Mapped[str | None] = mapped_column(Text)
    menus: Mapped[str | None] = mapped_column(Text, default='[]')
    builtin: Mapped[int | None] = mapped_column(Integer, default=0)
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)


class Department(Base, MappingMixin):
    __tablename__ = 'departments'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int | None] = mapped_column(Integer, default=0)
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)


class ConfigEvent(Base, MappingMixin):
    __tablename__ = 'config_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int | None] = mapped_column(Integer)
    actor: Mapped[str | None] = mapped_column(Text)
    config: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int | None] = mapped_column(Integer)
    at: Mapped[str | None] = mapped_column(Text)


class LibraryItem(Base, MappingMixin):
    __tablename__ = 'library_items'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    area: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str | None] = mapped_column(Text)
    name: Mapped[str | None] = mapped_column(Text)
    parent_id: Mapped[int | None] = mapped_column(Integer)
    owner: Mapped[int | None] = mapped_column(Integer)
    body: Mapped[str | None] = mapped_column(Text, default='')
    blob: Mapped[bytes | None] = mapped_column(LargeBinary)
    mime: Mapped[str | None] = mapped_column(Text, default='')
    updated: Mapped[str | None] = mapped_column(Text)
    deleted: Mapped[int | None] = mapped_column(Integer, default=0)


class SchemaFlag(Base, MappingMixin):
    __tablename__ = 'schema_flags'
    name: Mapped[str] = mapped_column(Text, primary_key=True)


class AppSetting(Base, MappingMixin):
    """运行期可改的系统设置（键值对）。目前用于「外部模型」选择，键：ai_model。

    环境变量是默认值，这里存的优先；这样换模型不必改 .env、也不必重启服务。
    """
    __tablename__ = 'app_settings'
    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, default='')
    updated: Mapped[str | None] = mapped_column(Text, default='')


class DataSource(Base, MappingMixin):
    """一家数据来源（同花顺、Wind、卓创…）。入库标签就是这里的 name。

    接新数据源不必改代码：加一条记录，页面就多一张来源卡片与同步入口，
    真正怎么取数由 ``data_source_configs`` 里配的接口决定。
    """
    __tablename__ = 'data_sources'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(Text, unique=True)       # ifind / wind / 自定义 key
    name: Mapped[str] = mapped_column(Text)                   # 入库标签（observations.source）
    product: Mapped[str | None] = mapped_column(Text, default='')     # iFinD / 金融终端
    channel: Mapped[str | None] = mapped_column(Text, default='')     # 取数通道说明
    scope_mode: Mapped[str | None] = mapped_column(Text, default='commodity')  # commodity / custom
    scope_items: Mapped[str | None] = mapped_column(Text, default='[]')        # custom 时的可选项
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)
    builtin: Mapped[int | None] = mapped_column(Integer, default=0)
    created_at: Mapped[str | None] = mapped_column(Text, default='')


class DataSourceConfig(Base, MappingMixin):
    """一条「服务端自己取数」的配置：接口地址、凭据、同步范围与计划。

    与 ``data_sync_jobs`` 的关系：作业是「一次执行」，配置是「怎么执行、多久执行一次」。
    服务端直连时凭据必须落在服务端，所以 ``secret`` 只存库、任何接口只回掩码；
    库文件本身要按机密文件保护（见 backend/README.md）。
    """
    __tablename__ = 'data_source_configs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(Text)            # 配置名，如「同花顺-黑色日盘」
    source: Mapped[str | None] = mapped_column(Text)          # ifind / wind，决定入库标签
    kind: Mapped[str | None] = mapped_column(Text)            # ifind_http / generic_json
    base_url: Mapped[str | None] = mapped_column(Text)
    account: Mapped[str | None] = mapped_column(Text)         # 账号 / AppID / 用户名
    secret: Mapped[str | None] = mapped_column(Text)          # 密码 / refresh_token / apikey
    scope: Mapped[str | None] = mapped_column(Text)           # JSON：items、metrics、days、code_suffix
    options: Mapped[str | None] = mapped_column(Text)         # JSON：请求模板、响应路径、字段映射
    freq: Mapped[str | None] = mapped_column(Text, default='manual')  # manual / daily / weekly
    run_at: Mapped[str | None] = mapped_column(Text, default='08:30')  # HH:MM（北京时间）
    weekday: Mapped[int | None] = mapped_column(Integer, default=1)    # 1=周一 … 7=周日
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)
    last_run: Mapped[str | None] = mapped_column(Text, default='')
    last_status: Mapped[str | None] = mapped_column(Text, default='未运行')
    last_message: Mapped[str | None] = mapped_column(Text, default='')
    operator: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[str | None] = mapped_column(Text, default='')


class DataSyncJob(Base, MappingMixin):
    """一次「从同花顺 / Wind 同步数据」的请求。

    取数本身在授权通道里完成（连接器或本地终端），服务端只负责登记范围、
    接收结果并入库，所以作业要能离开进程存活：页面点完按钮，取数可能稍后才执行。
    """
    __tablename__ = 'data_sync_jobs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str | None] = mapped_column(Text)          # ifind / wind
    scope: Mapped[str | None] = mapped_column(Text)           # JSON：品种、指标、区间
    status: Mapped[str | None] = mapped_column(Text, default='待执行')
    rows: Mapped[int | None] = mapped_column(Integer, default=0)
    inserted: Mapped[int | None] = mapped_column(Integer, default=0)
    updated: Mapped[int | None] = mapped_column(Integer, default=0)
    operator: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[str | None] = mapped_column(Text)
    finished_at: Mapped[str | None] = mapped_column(Text, default='')
    message: Mapped[str | None] = mapped_column(Text, default='')



# --------------------------------------------------------------------------
# 引擎与会话
# --------------------------------------------------------------------------
engine = create_engine(
    DB_URL,
    future=True,
    pool_pre_ping=True,
    connect_args={'timeout': 10, 'check_same_thread': False},
)

if DB_URL.startswith('sqlite'):

    @event.listens_for(engine, 'connect')
    def _sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute('PRAGMA journal_mode=WAL')
        cur.execute('PRAGMA foreign_keys=ON')
        cur.execute('PRAGMA busy_timeout=10000')
        cur.close()


SessionFactory = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def get_session():
    """FastAPI 依赖：每个请求一个 Session，出栈时关闭（未提交的改动自动回滚）。"""
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


# --------------------------------------------------------------------------
# 建模配套：建表、补列、迁移标记
#
# 这三件事都是 DDL，SQLAlchemy 没有对应的 ORM 表达，只能落到 text() 上；
# 除此之外整个后端不再出现手写 SQL。
# --------------------------------------------------------------------------
def create_schema() -> None:
    """按模型建表（已存在则跳过）。新库一次到位，老库由各 engine 的补列迁移兜底。"""
    Base.metadata.create_all(engine, checkfirst=True)


def table_columns(table: str) -> set[str]:
    """读取表当前列名。每次新建 Inspector，避免反射结果被缓存而看不到刚补的列。"""
    return {column['name'] for column in inspect(engine).get_columns(table)}


def add_columns(session: Session, table: str, columns: dict[str, str]) -> None:
    """幂等补列。SQLite 不支持一次 ALTER 多列，只能逐条执行。"""
    existing = table_columns(table)
    for name, definition in columns.items():
        if name not in existing:
            session.execute(text('ALTER TABLE %s ADD COLUMN %s %s' % (table, name, definition)))


def has_flag(session: Session, name: str) -> bool:
    return session.get(SchemaFlag, name) is not None


def set_flag(session: Session, name: str) -> None:
    if not has_flag(session, name):
        session.add(SchemaFlag(name=name))
        session.flush()


def next_issue(session: Session, category_id: int | None, exclude_id: int) -> int:
    """同一分类下的期号：取当前最大值 +1（空分类从 1 开始）。"""
    same_category = (Report.category_id.is_(None) if category_id is None
                     else Report.category_id == category_id)
    highest = session.execute(
        select(Report.issue).where(same_category, Report.id != exclude_id)
        .order_by(Report.issue.desc()).limit(1)
    ).scalar()
    return (highest or 0) + 1
