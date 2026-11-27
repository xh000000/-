"""数据层：SQLAlchemy 2.0 ORM 映射（20 张表）与建模配套工具。

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

import hashlib
import os
import re
import socket
import threading
import time
from pathlib import Path
from typing import Any

from sqlalchemy import (
    Float, Integer, LargeBinary, String, Text, UniqueConstraint, create_engine, event, inspect,
    select, text,
)
from sqlalchemy.dialects.mysql import LONGBLOB, LONGTEXT
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


def big_text() -> Text:
    """长文本列的类型：MySQL 用 LONGTEXT，其余方言保持 TEXT。

    MySQL 的 TEXT 只有 64KB，而研报正文加章节 JSON 一份就可能越线（实测 document
    约 20KB，正文再叠加）。SQLite 与 PostgreSQL 的 TEXT 本身无长度上限，保持原样。

    必须用 ``with_variant``：直接继承 Text 子类不行——DDL 编译按 ``__visit_name__``
    派发，子类继承到的仍是 "text"，编译出来永远是 TEXT，换个写法才真正生效。
    """
    return Text().with_variant(LONGTEXT(), 'mysql')


def big_blob() -> LargeBinary:
    """附件列的类型：MySQL 用 LONGBLOB，其余方言保持原样（BLOB 只有 64KB）。"""
    return LargeBinary().with_variant(LONGBLOB(), 'mysql')


ROOT = Path(__file__).parent
DB_PATH = Path(os.getenv('DATA_DIR', str(ROOT / 'data'))) / 'research.db'
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
DB_URL = os.getenv('DATABASE_URL') or ('sqlite:///' + DB_PATH.as_posix())


def _normalize_url(url: str) -> str:
    """把裸连接串补成本项目实际安装的驱动。

    - ``postgresql://`` → ``postgresql+psycopg://``：不补会去找 psycopg2，而依赖里装的是
      psycopg3，部署时就会变成"连不上库"这种和驱动缺包混在一起报的错。
    - ``mysql://`` → ``mysql+pymysql://``：云厂商文档给的都是裸 mysql://，SQLAlchemy 默认
      会去找 MySQLdb（需要编译 C 扩展），沙箱里装不上。
    """
    for prefix in ('postgresql://', 'postgres://'):
        if url.startswith(prefix):
            return 'postgresql+psycopg://' + url[len(prefix):]
    if url.startswith('mysql://'):
        return 'mysql+pymysql://' + url[len('mysql://'):]
    return url


DB_URL = _normalize_url(DB_URL)


def _sanitize_pg_url(url: str) -> str:
    """去掉会让 libpq 在跨境链路上卡死的参数。

    ``channel_binding=require`` 要求 SCRAM 走 tls-server-end-point 通道绑定。云厂商
    的连接池（Neon pooler 之类）在中间终止 TLS，这个协商经常谈不拢，表现不是报错
    而是**一直等到超时**。实测同一个库：带 channel_binding 必挂，去掉后能连上。

    注意不要改成往 hostaddr 里固定单个 IP：域名背后有多台机器，其中一部分 TCP 能
    握手、但会话在认证阶段被丢，写死就是干等着超时；交给 libpq 轮询全部地址反而
    能落到一台好的上面。
    """
    if not url.startswith('postgresql'):
        return url
    return re.sub(r'[?&]channel_binding=[^&]*', '', url)


DB_URL = _sanitize_pg_url(DB_URL)


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
    name: Mapped[str] = mapped_column(String(191), unique=True)
    role: Mapped[str | None] = mapped_column(big_text())
    salt: Mapped[str | None] = mapped_column(big_text())
    hash: Mapped[str | None] = mapped_column(big_text())
    dept_id: Mapped[int | None] = mapped_column(Integer)
    phone: Mapped[str | None] = mapped_column(big_text(), default='')
    title: Mapped[str | None] = mapped_column(big_text(), default='')
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)
    role_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[str | None] = mapped_column(big_text(), default='')
    last_login_at: Mapped[str | None] = mapped_column(big_text(), default='')
    # 1=正常，0=已删除（逻辑删除）。账号行保留下来，历史研报、审批记录与事件里的操作人仍能对上名字
    status: Mapped[int | None] = mapped_column(Integer, default=1)


class SessionRow(Base, MappingMixin):
    __tablename__ = 'sessions'
    token: Mapped[str] = mapped_column(big_text(), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer)
    expires: Mapped[float | None] = mapped_column(Float)
    remember: Mapped[int | None] = mapped_column(Integer, default=0)
    last_seen: Mapped[float | None] = mapped_column(Float, default=0)


class Report(Base, MappingMixin):
    __tablename__ = 'reports'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str | None] = mapped_column(big_text())
    commodity: Mapped[str | None] = mapped_column(big_text())
    kind: Mapped[str | None] = mapped_column(big_text())
    body: Mapped[str | None] = mapped_column(big_text())
    status: Mapped[str | None] = mapped_column(big_text())
    author: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int | None] = mapped_column(Integer, default=1)
    updated: Mapped[str | None] = mapped_column(big_text())
    document: Mapped[str | None] = mapped_column(big_text(), default='')
    config_snapshot: Mapped[str | None] = mapped_column(big_text(), default='')
    category_id: Mapped[int | None] = mapped_column(Integer)
    workflow_state: Mapped[str | None] = mapped_column(big_text(), default='')
    inherited_from: Mapped[int | None] = mapped_column(Integer)
    metadata_: Mapped[str | None] = mapped_column('metadata', big_text(), default='')
    updated_by: Mapped[str | None] = mapped_column(big_text(), default='')
    published_at: Mapped[str | None] = mapped_column(big_text(), default='')
    approved_at: Mapped[str | None] = mapped_column(big_text(), default='')
    views: Mapped[int | None] = mapped_column(Integer, default=0)
    issue: Mapped[int | None] = mapped_column(Integer, default=0)
    deleted: Mapped[int | None] = mapped_column(Integer, default=0)
    scheduled_at: Mapped[str | None] = mapped_column(big_text(), default='')
    ai_draft: Mapped[int | None] = mapped_column(Integer, default=0)  # 1=含 AI 生成内容，须人工复核


class Version(Base, MappingMixin):
    __tablename__ = 'versions'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int | None] = mapped_column(Integer)
    body: Mapped[str | None] = mapped_column(big_text())
    title: Mapped[str | None] = mapped_column(big_text())
    actor: Mapped[str | None] = mapped_column(big_text())
    at: Mapped[str | None] = mapped_column(big_text())
    document: Mapped[str | None] = mapped_column(big_text(), default='')
    config_snapshot: Mapped[str | None] = mapped_column(big_text(), default='')
    metadata_: Mapped[str | None] = mapped_column('metadata', big_text(), default='')


class Event(Base, MappingMixin):
    __tablename__ = 'events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int | None] = mapped_column(Integer)
    actor: Mapped[str | None] = mapped_column(big_text())
    action: Mapped[str | None] = mapped_column(big_text())
    note: Mapped[str | None] = mapped_column(big_text())
    version: Mapped[int | None] = mapped_column(Integer)
    at: Mapped[str | None] = mapped_column(big_text())


class Observation(Base, MappingMixin):
    """一个数据点：某来源、某指标、某日期的取值。

    ``indicator_id`` 指向 ``dim_indicators``，是指标身份的稳定标识；``indicator``
    文本列保留为冗余显示名，供既有查询与报表直接取用。改名时 id 不变、文本列级联更新。
    """
    __tablename__ = 'observations'
    __table_args__ = (UniqueConstraint('source', 'indicator', 'date', name='uq_observation_point'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # 这三列组成了唯一键，必须是定长字符串：MySQL 不允许对 TEXT 建索引（除非给前缀
    # 长度），而且 191×4 字节刚好压在 InnoDB 单列索引上限以内，utf8mb4 下最稳。
    source: Mapped[str | None] = mapped_column(String(64))
    indicator: Mapped[str | None] = mapped_column(String(191))
    date: Mapped[str | None] = mapped_column(String(32))
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(big_text())
    uploaded_by: Mapped[str | None] = mapped_column(big_text())
    indicator_id: Mapped[int | None] = mapped_column(Integer, index=True)  # → dim_indicators.id


class PublicationHistory(Base, MappingMixin):
    __tablename__ = 'publication_history'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    report_id: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[int | None] = mapped_column(Integer)
    document: Mapped[str | None] = mapped_column(big_text())
    config: Mapped[str | None] = mapped_column(big_text())
    metadata_: Mapped[str | None] = mapped_column('metadata', big_text())
    body: Mapped[str | None] = mapped_column(big_text())
    published_at: Mapped[str | None] = mapped_column(big_text())


class Category(Base, MappingMixin):
    __tablename__ = 'categories'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(191), unique=True)
    config: Mapped[str | None] = mapped_column(big_text())
    revision: Mapped[int | None] = mapped_column(Integer, default=1)
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)
    parent_id: Mapped[int | None] = mapped_column(Integer)
    label: Mapped[str | None] = mapped_column(big_text(), default='')
    sort_order: Mapped[int | None] = mapped_column(Integer, default=0)
    folder: Mapped[int | None] = mapped_column(Integer, default=0)


class CategoryMigration(Base, MappingMixin):
    __tablename__ = 'category_migration'
    category_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_name: Mapped[str | None] = mapped_column(big_text())
    parent_id: Mapped[int | None] = mapped_column(Integer)


class Commodity(Base, MappingMixin):
    """品种字典：板块（parent_id 为空）→ 品种（两级）。

    code 是交易所合约代码（CU、I、IF/IH/IC/IM），exchange 是交易所短码，
    aliases 存别名 JSON，用于把指标名自动拆成品种；position 决定板块内排序。
    """
    __tablename__ = 'commodities'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(191), unique=True)
    parent_id: Mapped[int | None] = mapped_column(Integer)
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)
    code: Mapped[str | None] = mapped_column(big_text(), default='')
    exchange: Mapped[str | None] = mapped_column(big_text(), default='')
    aliases: Mapped[str | None] = mapped_column(big_text(), default='')
    position: Mapped[int | None] = mapped_column(Integer, default=0)


class Author(Base, MappingMixin):
    __tablename__ = 'authors'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(191), unique=True)
    types: Mapped[str | None] = mapped_column(big_text())
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)
    license: Mapped[str | None] = mapped_column(big_text(), default='')
    # 1=正常，0=已删除（逻辑删除）；已署名研报的署名是创建时的快照，删掉作者不影响历史报告
    status: Mapped[int | None] = mapped_column(Integer, default=1)


class ApprovalFlow(Base, MappingMixin):
    __tablename__ = 'approval_flows'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(big_text())
    category_ids: Mapped[str | None] = mapped_column(big_text(), default='[]')
    nodes: Mapped[str | None] = mapped_column(big_text(), default='[]')
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)


class Role(Base, MappingMixin):
    __tablename__ = 'roles'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(191), unique=True)
    base_role: Mapped[str | None] = mapped_column(big_text())
    menus: Mapped[str | None] = mapped_column(big_text(), default='[]')
    builtin: Mapped[int | None] = mapped_column(Integer, default=0)
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)


class Department(Base, MappingMixin):
    __tablename__ = 'departments'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(big_text())
    parent_id: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int | None] = mapped_column(Integer, default=0)
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)


class ConfigEvent(Base, MappingMixin):
    __tablename__ = 'config_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int | None] = mapped_column(Integer)
    actor: Mapped[str | None] = mapped_column(big_text())
    config: Mapped[str | None] = mapped_column(big_text())
    revision: Mapped[int | None] = mapped_column(Integer)
    at: Mapped[str | None] = mapped_column(big_text())


class LibraryItem(Base, MappingMixin):
    __tablename__ = 'library_items'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    area: Mapped[str | None] = mapped_column(big_text())
    kind: Mapped[str | None] = mapped_column(big_text())
    name: Mapped[str | None] = mapped_column(big_text())
    parent_id: Mapped[int | None] = mapped_column(Integer)
    owner: Mapped[int | None] = mapped_column(Integer)
    body: Mapped[str | None] = mapped_column(big_text(), default='')
    blob: Mapped[bytes | None] = mapped_column(big_blob())
    mime: Mapped[str | None] = mapped_column(big_text(), default='')
    updated: Mapped[str | None] = mapped_column(big_text())
    deleted: Mapped[int | None] = mapped_column(Integer, default=0)


class SchemaFlag(Base, MappingMixin):
    __tablename__ = 'schema_flags'
    name: Mapped[str] = mapped_column(String(191), primary_key=True)


class AppSetting(Base, MappingMixin):
    """运行期可改的系统设置（键值对）。目前用于「外部模型」选择，键：ai_model。

    环境变量是默认值，这里存的优先；这样换模型不必改 .env、也不必重启服务。
    """
    __tablename__ = 'app_settings'
    key: Mapped[str] = mapped_column(String(191), primary_key=True)
    value: Mapped[str] = mapped_column(big_text(), default='')
    updated: Mapped[str | None] = mapped_column(big_text(), default='')


class Revision(Base, MappingMixin):
    """数据版本号，用于把「有变化」推给在线客户端（实时刷新）。

    只有一行（name='state'），任何写操作提交后原子 +1；前端收到变化只重新拉一次
    /api/state，不关心具体改了什么。刻意落库而不是放进程内存：托管平台可能起多个
    进程/实例，内存计数器各算各的，只有库里的值对所有实例一致。
    """
    __tablename__ = 'revisions'
    name: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, default=0)
    updated: Mapped[str | None] = mapped_column(big_text(), default='')


class Menu(Base, MappingMixin):
    """侧栏菜单目录：结构、排序与显示设置都以这张表为准。

    key 是稳定标识（有页面用路由路径，占位/分组用 ``group:名称`` 或
    ``item:父:子``），改名不会改变标识，便于账号权限与历史设置继续对上。
    """
    __tablename__ = 'menus'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    parent_id: Mapped[int | None] = mapped_column(Integer)
    key: Mapped[str] = mapped_column(String(191), unique=True)
    label: Mapped[str] = mapped_column(String(60))
    icon: Mapped[str | None] = mapped_column(String(60), default='')
    path: Mapped[str | None] = mapped_column(String(191), default='')
    sort_order: Mapped[int | None] = mapped_column(Integer, default=0)
    visible: Mapped[int | None] = mapped_column(Integer, default=1)
    admin_only: Mapped[int | None] = mapped_column(Integer, default=0)
    disabled: Mapped[int | None] = mapped_column(Integer, default=0)
    builtin: Mapped[int | None] = mapped_column(Integer, default=1)
    updated: Mapped[str | None] = mapped_column(big_text(), default='')


class DataSource(Base, MappingMixin):
    """一家数据来源（同花顺、Wind、卓创…）。入库标签就是这里的 name。

    接新数据源不必改代码：加一条记录，页面就多一张来源卡片与同步入口，
    真正怎么取数由 ``data_source_configs`` 里配的接口决定。
    """
    __tablename__ = 'data_sources'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)  # ifind / wind / 自定义 key
    name: Mapped[str] = mapped_column(big_text())                   # 入库标签（observations.source）
    product: Mapped[str | None] = mapped_column(big_text(), default='')     # iFinD / 金融终端
    channel: Mapped[str | None] = mapped_column(big_text(), default='')     # 取数通道说明
    scope_mode: Mapped[str | None] = mapped_column(big_text(), default='commodity')  # commodity / custom
    scope_items: Mapped[str | None] = mapped_column(big_text(), default='[]')        # custom 时的可选项
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)
    builtin: Mapped[int | None] = mapped_column(Integer, default=0)
    created_at: Mapped[str | None] = mapped_column(big_text(), default='')


class DataSourceConfig(Base, MappingMixin):
    """一条「服务端自己取数」的配置：接口地址、凭据、同步范围与计划。

    与 ``data_sync_jobs`` 的关系：作业是「一次执行」，配置是「怎么执行、多久执行一次」。
    服务端直连时凭据必须落在服务端，所以 ``secret`` 只存库、任何接口只回掩码；
    库文件本身要按机密文件保护（见 backend/README.md）。
    """
    __tablename__ = 'data_source_configs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str | None] = mapped_column(big_text())            # 配置名，如「同花顺-黑色日盘」
    source: Mapped[str | None] = mapped_column(big_text())          # ifind / wind，决定入库标签
    kind: Mapped[str | None] = mapped_column(big_text())            # ifind_http / generic_json
    base_url: Mapped[str | None] = mapped_column(big_text())
    account: Mapped[str | None] = mapped_column(big_text())         # 账号 / AppID / 用户名
    secret: Mapped[str | None] = mapped_column(big_text())          # 密码 / refresh_token / apikey
    scope: Mapped[str | None] = mapped_column(big_text())           # JSON：items、metrics、days、code_suffix
    options: Mapped[str | None] = mapped_column(big_text())         # JSON：请求模板、响应路径、字段映射
    freq: Mapped[str | None] = mapped_column(big_text(), default='manual')  # manual / daily / weekly
    run_at: Mapped[str | None] = mapped_column(big_text(), default='08:30')  # HH:MM（北京时间）
    weekday: Mapped[int | None] = mapped_column(Integer, default=1)    # 1=周一 … 7=周日
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)
    last_run: Mapped[str | None] = mapped_column(big_text(), default='')
    last_status: Mapped[str | None] = mapped_column(big_text(), default='未运行')
    last_message: Mapped[str | None] = mapped_column(big_text(), default='')
    operator: Mapped[str | None] = mapped_column(big_text())
    created_at: Mapped[str | None] = mapped_column(big_text())
    updated_at: Mapped[str | None] = mapped_column(big_text(), default='')


class DataSyncJob(Base, MappingMixin):
    """一次「从同花顺 / Wind 同步数据」的请求。

    取数本身在授权通道里完成（连接器或本地终端），服务端只负责登记范围、
    接收结果并入库，所以作业要能离开进程存活：页面点完按钮，取数可能稍后才执行。
    """
    __tablename__ = 'data_sync_jobs'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str | None] = mapped_column(big_text())          # ifind / wind
    scope: Mapped[str | None] = mapped_column(big_text())           # JSON：品种、指标、区间
    status: Mapped[str | None] = mapped_column(big_text(), default='待执行')
    rows: Mapped[int | None] = mapped_column(Integer, default=0)
    inserted: Mapped[int | None] = mapped_column(Integer, default=0)
    updated: Mapped[int | None] = mapped_column(Integer, default=0)
    operator: Mapped[str | None] = mapped_column(big_text())
    created_at: Mapped[str | None] = mapped_column(big_text())
    finished_at: Mapped[str | None] = mapped_column(big_text(), default='')
    message: Mapped[str | None] = mapped_column(big_text(), default='')


class DataScopePreset(Base, MappingMixin):
    """【历史】候选清单预置库。

    v1 时代用「分组名 + 指标名」两列裸文本描述指标，既没有分组表，也没有指标身份，
    改名就会把历史数据切成两段。现由 ``DimGroup`` / ``DimIndicator`` 接管；
    此表仅在迁移时读取一次，不再写入，保留它是为了老库回滚时仍能查到来龙去脉。
    """
    __tablename__ = 'data_scope_presets'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_name: Mapped[str] = mapped_column(Text)             # 分组：现货价 / 库存 / 开工率…
    item: Mapped[str] = mapped_column(Text, unique=True)      # 候选项，如 螺纹钢现货价
    position: Mapped[int | None] = mapped_column(Integer, default=0)  # 展示顺序


class DimGroup(Base, MappingMixin):
    """指标分组（一级目录）。有 id、有编码、有位置，允许空分组。

    ``code`` 与指标编码同规矩：创建时定下、发布后不变，改名不影响它。
    ``builtin=1`` 的是系统组（如「未分组」），用来接住那些还没归类的指标，不允许删除。
    """
    __tablename__ = 'dim_groups'
    __table_args__ = {'sqlite_autoincrement': True}          # id 永不复用，编码才不会撞
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str | None] = mapped_column(Text, default='')      # GRP00001，稳定标识
    name: Mapped[str] = mapped_column(Text, unique=True)
    position: Mapped[int | None] = mapped_column(Integer, default=0)
    builtin: Mapped[int | None] = mapped_column(Integer, default=0)
    created_at: Mapped[str | None] = mapped_column(Text, default='')


class DimIndicator(Base, MappingMixin):
    """指标主数据。``id`` 是身份，``name`` 只是显示名，可以改而不影响历史数据归属。

    字段按行业指标体系规范（编码 + 标准名称双轨）落地：
    - ``code``：稳定标识，自动生成 ``IND00001``，发布后不复用；外部引用只认它
    - ``name``：标准名，形如「品种 + 指标类型」，改名不动 id
    - ``commodity``：品种维度（螺纹钢 / 焦煤…），从名字里拆出来才能按品种筛选
    - ``aliases``：别名，同一概念的其它叫法登记在此，不另建指标（治「XX成交量 / XX成交量快照」分裂）
    - ``enabled``：停用代替删除，已入库的历史数据不会因为删字典而变成孤儿

    改名走 ``datasource.rename_indicator``：id 不变，同时把 observations 的冗余文本列
    与各数据源配置里的名字一并更新，所以数据不会断链。
    """
    __tablename__ = 'dim_indicators'
    __table_args__ = {'sqlite_autoincrement': True}          # id 永不复用
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str | None] = mapped_column(Text, unique=True)        # IND00001，稳定标识
    name: Mapped[str] = mapped_column(Text, unique=True)                # 标准显示名
    group_id: Mapped[int | None] = mapped_column(Integer, index=True)   # → dim_groups.id
    commodity: Mapped[str | None] = mapped_column(Text, default='')     # 品种维度
    aliases: Mapped[str | None] = mapped_column(Text, default='[]')     # JSON 数组，别名不另建指标
    unit: Mapped[str | None] = mapped_column(Text, default='')
    enabled: Mapped[int | None] = mapped_column(Integer, default=1)     # 1 启用 / 0 停用
    position: Mapped[int | None] = mapped_column(Integer, default=0)
    created_at: Mapped[str | None] = mapped_column(Text, default='')
    updated_at: Mapped[str | None] = mapped_column(Text, default='')




class AgentThread(Base, MappingMixin):
    """一条 Agent 对话线程。消息本体在 LangGraph 的 checkpoint 库里，
    这张表只管归属与列表：谁开的线程、叫什么、最后活跃时间。"""
    __tablename__ = 'agent_threads'
    id: Mapped[str] = mapped_column(Text, primary_key=True)   # uuid hex，同时是 checkpoint thread_id
    user_id: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(Text, default='新对话')
    created_at: Mapped[str | None] = mapped_column(Text, default='')
    updated_at: Mapped[str | None] = mapped_column(Text, default='')


class AgentTask(Base, MappingMixin):
    """一个后台 Agent 任务：排队中 / 运行中 / 已完成 / 失败。

    页面 SSE 对话走同步流；批量场景（如「把六个板块都写一版」）投递到这里，
    由单个 worker 线程顺序执行，结果落在 result 列，页面轮询取回。
    """
    __tablename__ = 'agent_tasks'
    id: Mapped[str] = mapped_column(Text, primary_key=True)   # uuid hex
    kind: Mapped[str | None] = mapped_column(String(30), default='')
    payload: Mapped[str | None] = mapped_column(big_text(), default='')
    thread_id: Mapped[str | None] = mapped_column(Text, default='')
    user_id: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text, default='')
    status: Mapped[str | None] = mapped_column(Text, default='排队中')
    result: Mapped[str | None] = mapped_column(Text, default='')
    error: Mapped[str | None] = mapped_column(Text, default='')
    created_at: Mapped[str | None] = mapped_column(Text, default='')
    started_at: Mapped[str | None] = mapped_column(Text, default='')
    finished_at: Mapped[str | None] = mapped_column(Text, default='')


class ViewpointCandidate(Base, MappingMixin):
    __tablename__ = 'viewpoint_candidates'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    report_id: Mapped[int] = mapped_column(Integer, index=True)
    publication_id: Mapped[int] = mapped_column(Integer, index=True)
    author_id: Mapped[int | None] = mapped_column(Integer)
    author_name: Mapped[str | None] = mapped_column(big_text(), default='')
    report_title: Mapped[str | None] = mapped_column(big_text(), default='')
    published_date: Mapped[str | None] = mapped_column(String(10))
    commodity: Mapped[str | None] = mapped_column(String(191))
    direction: Mapped[str | None] = mapped_column(String(20), default='')
    horizon_days: Mapped[int | None] = mapped_column(Integer)
    excerpt: Mapped[str | None] = mapped_column(big_text())
    draft_basis: Mapped[str | None] = mapped_column(big_text(), default='')
    source_method: Mapped[str | None] = mapped_column(String(20), default='rule')
    reason: Mapped[str | None] = mapped_column(big_text(), default='')
    status: Mapped[str | None] = mapped_column(String(20), default='待确认')
    conditional: Mapped[int | None] = mapped_column(Integer, default=0)
    confirmed_by: Mapped[str | None] = mapped_column(big_text(), default='')
    confirmed_at: Mapped[str | None] = mapped_column(big_text(), default='')
    created_at: Mapped[str | None] = mapped_column(big_text(), default='')

class ViewpointScan(Base, MappingMixin):
    __tablename__ = 'viewpoint_scans'
    publication_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)


class Viewpoint(Base, MappingMixin):
    """一条研究观点（观点库）：谁在什么时间、对哪个品种、看了哪个方向、依据是什么。

    结算（回溯）机制：观点带基准价与观察期，到期后取指标库价格对照涨跌，
    按 ETA《数据报表管理》观点考核的口径给出「正确 / 错误 / 持平 / 无法结算」——
    让「当初看多，后来涨没涨」可量化，支撑研究员能力画像。
    """
    __tablename__ = 'viewpoints'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(Integer)
    user_name: Mapped[str | None] = mapped_column(Text, default='')
    commodity: Mapped[str | None] = mapped_column(Text)                       # 品种名（对应 commodities）
    direction: Mapped[str | None] = mapped_column(Text)                       # 看多 / 看空 / 震荡
    basis: Mapped[str | None] = mapped_column(Text, default='')               # 观点依据（1000 字内）
    benchmark_price: Mapped[float | None] = mapped_column(Float)              # 基准价
    benchmark_date: Mapped[str | None] = mapped_column(Text, default='')      # 基准日 YYYY-MM-DD
    horizon_days: Mapped[int | None] = mapped_column(Integer, default=5)      # 观察期（自然日）
    expire_date: Mapped[str | None] = mapped_column(Text, default='')         # 结算日 = 基准日 + 观察期
    benchmark_indicator: Mapped[str | None] = mapped_column(Text, default='') # 用的哪个指标（溯源）
    candidate_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    report_id: Mapped[int | None] = mapped_column(Integer)
    publication_id: Mapped[int | None] = mapped_column(Integer)
    source_excerpt: Mapped[str | None] = mapped_column(big_text(), default='')
    report_title: Mapped[str | None] = mapped_column(big_text(), default='')
    published_date: Mapped[str | None] = mapped_column(String(10), default='')
    evaluation_threshold: Mapped[float | None] = mapped_column(Float, default=1.0)
    benchmark_source: Mapped[str | None] = mapped_column(Text, default='')
    benchmark_unit: Mapped[str | None] = mapped_column(Text, default='')
    benchmark_manual: Mapped[int | None] = mapped_column(Integer, default=0)
    result_source: Mapped[str | None] = mapped_column(Text, default='')
    result_indicator: Mapped[str | None] = mapped_column(Text, default='')

    result_price: Mapped[float | None] = mapped_column(Float)                 # 结算价
    result_date: Mapped[str | None] = mapped_column(Text, default='')         # 实际取到的价格日期
    change_pct: Mapped[float | None] = mapped_column(Float)                   # 区间涨跌幅 %
    outcome: Mapped[str | None] = mapped_column(Text, default='')             # 正确 / 错误 / 持平 / 无法结算
    status: Mapped[str | None] = mapped_column(Text, default='在途')           # 在途 / 已结算
    note: Mapped[str | None] = mapped_column(Text, default='')                # 结算说明 / 失效原因
    created_at: Mapped[str | None] = mapped_column(Text, default='')
    settled_at: Mapped[str | None] = mapped_column(Text, default='')


# --------------------------------------------------------------------------
# 引擎与会话
# --------------------------------------------------------------------------
def _connect_args(url: str) -> dict:
    """连接参数按方言给。sqlite 的 timeout / check_same_thread 语义只有它认，
    原样传给 Postgres 会直接 TypeError，所以必须分开。

    prepare_threshold=None 关掉 psycopg3 的服务端预编译语句：Neon / PgBouncer 这类
    连接池是事务级复用连接的，预编译语句跟着连接走，跨事务复用时必然撞
    "prepared statement already exists"。关掉只是少一层优化，功能不受影响。
    """
    if url.startswith('sqlite'):
        return {'timeout': 10, 'check_same_thread': False}
    if url.startswith('postgresql'):
        # 跨境/跨区访问托管库时单次建连可能就要几秒，超时给紧了一抖就启动失败
        return {'connect_timeout': 30, 'prepare_threshold': None}
    if url.startswith('mysql'):
        # 云数据库常常带「自动暂停」，闲置后第一次连接要等计算节点冷启动，
        # 实测能到十几秒，所以这里的超时不能按局域网的几秒来给。
        return {'connect_timeout': 30, 'charset': 'utf8mb4'}
    return {}


def _bounded_connect(url: str, timeout: float = 8.0):
    """带硬超时的建连，用于 psycopg 的 ``creator``。

    为什么不能只靠 ``connect_timeout``：libpq 的那个参数只约束 TCP 握手，TLS 之后
    的启动包 / 认证阶段不在它的计时范围内。跨境链路上出现过握手完成后会话被静默
    丢弃的情况，于是 connect() 永久阻塞 —— 一个请求挂死，整个 worker 线程跟着陪葬。

    所以每次尝试都丢到独立线程里跑，外面用 join 做硬截止；超时就丢弃这次尝试，
    线程留着自生自灭（daemon，不会拦住进程退出），换下一次重试。

    重试是必须的：同一条链路对同一个库的成功率实测只有一半上下，多试几次才可能
    稳定拿到连接。次数用尽仍失败就抛出最后一次的真实异常，不吞原因。
    """
    import psycopg

    attempts = int(os.getenv('DB_CONNECT_ATTEMPTS', '6'))
    last_error: BaseException | None = None

    for index in range(attempts):
        box: dict[str, Any] = {}

        def attempt() -> None:
            try:
                box['conn'] = psycopg.connect(url, connect_timeout=max(2, int(timeout)),
                                              prepare_threshold=None)
            except BaseException as exc:  # noqa: BLE001 - 原样抛给调用方
                box['error'] = exc

        worker = threading.Thread(target=attempt, daemon=True,
                                  name='db-connect-%d' % index)
        started = time.time()
        worker.start()
        worker.join(timeout + 2)

        if worker.is_alive():
            last_error = TimeoutError(
                '建连超过 %.0fs 仍未完成（第 %d 次）' % (timeout + 2, index + 1))
        elif 'conn' in box:
            return box['conn']
        else:
            last_error = box.get('error') or RuntimeError('建连失败但未拿到异常')

        # 立刻重试只会撞上同一个坏路径，退让一下让 libpq 有机会落到别的实例
        if index + 1 < attempts:
            time.sleep(min(0.5 * (index + 1), 2.0))

    raise last_error if last_error else RuntimeError('无法连接数据库')


_engine_kwargs: dict[str, Any] = {}
if DB_URL.startswith('postgresql'):
    # psycopg 只认 libpq 的 conninfo，不认 SQLAlchemy 的 "+psycopg" 方言后缀，
    # 直接拿 DB_URL 去连会报 invalid connection option。
    _libpq_url = DB_URL.replace('postgresql+psycopg://', 'postgresql://', 1)
    # Postgres 走自建 creator：只有它能给建连加上「硬超时 + 重试」
    _engine_kwargs['creator'] = lambda: _bounded_connect(
        _libpq_url, float(os.getenv('DB_CONNECT_TIMEOUT', '8')))

engine = create_engine(
    DB_URL,
    future=True,
    pool_pre_ping=True,
    pool_recycle=180,
    pool_size=5,
    max_overflow=5,
    connect_args=_connect_args(DB_URL),
    **_engine_kwargs,
)


def warmup_connections(count: int = 2, deadline: float = 90.0):
    """启动时先把连接池焐热。

    远程库第一次建连要几秒甚至要重试几轮，如果等用户第一次请求才去建，页面会一直
    转圈。这里在启动阶段就把连接摆好，失败也只是记日志 —— 之后按需建连仍然可用。
    """
    from sqlalchemy import text

    ok = 0
    started = time.time()
    for _ in range(count):
        if time.time() - started > deadline:
            break
        try:
            with engine.connect() as conn:
                conn.execute(text('select 1'))
            ok += 1
        except Exception:
            break
    return ok

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
_SCHEMA_CHECKED = False


def create_schema() -> None:
    """按模型建表（已存在则跳过）。新库一次到位，老库由各 engine 的补列迁移兜底。

    四个 engine 的 migrate 都会调这里。create_all(checkfirst=True) 对每张表各查一次
    存在性，SQLite 本地无感，但连远程库时 4 × 21 次往返能把启动拖到一分钟。所以先用
    一次 get_table_names 判断是否全都齐了——齐了就直接返回。
    """
    global _SCHEMA_CHECKED
    if _SCHEMA_CHECKED:
        return
    existing = set(inspect(engine).get_table_names())
    if not set(Base.metadata.tables) - existing:
        _SCHEMA_CHECKED = True
        return
    Base.metadata.create_all(engine, checkfirst=True)
    _SCHEMA_CHECKED = True


def schema_fingerprint() -> str:
    """由模型定义算出的结构指纹：表名 + 列名。列一变，指纹就变。

    不用手写版本号，是因为手写的那个一定会忘——加完列忘了改，线上就直接报
    "列不存在"。指纹跟着代码走，改模型必然改指纹，老库自动回到完整补列流程。
    """
    parts = []
    for name in sorted(Base.metadata.tables):
        table = Base.metadata.tables[name]
        parts.append(name + ':' + ','.join(sorted(column.name for column in table.columns)))
    return hashlib.sha1('|'.join(parts).encode('utf-8')).hexdigest()[:16]


def schema_current(session: Session) -> bool:
    """库结构是否已经和当前模型完全一致。

    为真时整段补列逻辑可以跳过：远程库上每次启动要做几十次结构查询，每个往返
    几百毫秒，累计十几秒；而 99% 的启动结构根本没变过。
    """
    try:
        existing = set(inspect(engine).get_table_names())
        if set(Base.metadata.tables) - existing:
            return False
        return has_flag(session, 'schema:' + schema_fingerprint())
    except Exception:
        # 表还没建全（甚至库还是空的）时任何反射都可能抛，一律当作"需要初始化"
        return False


def mark_schema_current(session: Session) -> None:
    """记下当前结构指纹。必须放在所有补列与一次性迁移都跑完之后。"""
    set_flag(session, 'schema:' + schema_fingerprint())


def prefetch_columns(session: Session) -> None:
    """一次性把全部表的列名装进会话缓存，供后续 add_columns 零成本命中。

    get_multi_columns 一条语句拿回所有表的结构；个别方言不支持时退回逐表查询，
    行为不变，只是慢一点。
    """
    cache = session.info.setdefault('db.table_columns', {})
    if cache:
        return
    inspector = inspect(engine)
    try:
        multi = inspector.get_multi_columns()
    except (NotImplementedError, AttributeError):
        multi = None
    if multi:
        for table, columns in multi.items():
            cache[table] = {column['name'] for column in columns}


def table_columns(table: str, session=None) -> set[str]:
    """读取表当前列名。

    传了 session 就按会话缓存：一次初始化会对同一张表检查好几轮列，远程库上每轮
    都是一次网络往返。缓存只活在单个 Session 里，不会跨进程变陈旧；刚 ALTER 出来
    的列由 add_columns 写回同一份缓存，所以同一轮里不会重复补列。
    """
    if session is None:
        return {column['name'] for column in inspect(engine).get_columns(table)}
    cache = session.info.setdefault('db.table_columns', {})
    if table not in cache:
        cache[table] = {column['name'] for column in inspect(engine).get_columns(table)}
    return cache[table]


def add_columns(session: Session, table: str, columns: dict[str, str]) -> None:
    """幂等补列。SQLite 不支持一次 ALTER 多列，只能逐条执行。

    补列定义是按 SQLite 写的（``TEXT DEFAULT ''``）。MySQL 的 TEXT 列不允许有默认值，
    原样执行会报 "BLOB/TEXT column can't have a default value"；而这里补出来的都是
    短文本（手机号、标题、时间戳），降到 VARCHAR(255) 语义不变。
    """
    existing = table_columns(table, session)
    is_mysql = engine.dialect.name == 'mysql'
    for name, definition in columns.items():
        if name in existing:
            continue
        ddl = definition.replace('TEXT', 'VARCHAR(255)') if is_mysql else definition
        session.execute(text('ALTER TABLE %s ADD COLUMN %s %s' % (table, name, ddl)))
        existing.add(name)


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
