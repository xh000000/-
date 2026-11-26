#!/usr/bin/env python3
"""把现有 SQLite 库整库搬到外部数据库（PostgreSQL / MySQL / 自建都适用）。

为什么单独写一个脚本，而不是塞进 app.py 的启动流程
------------------------------------------------
搬运是一次性动作：跑完就该删掉，留在启动路径里每次开机都要判断一遍，还会让
「库是空的」和「库刚迁完」两种状态混在一起。所以做成独立命令，人工触发。

用法
----
    # 先看源库有什么，不写目标库
    python backend/migrate_database.py --from var/research.db --dry-run

    # 真正搬（DATABASE_URL 指向目标库）
    DATABASE_URL='postgresql://user:pass@host/db?sslmode=require' \
        python backend/migrate_database.py --from var/research.db
    DATABASE_URL='mysql://user:pass@host:3306/db?charset=utf8mb4' \
        python backend/migrate_database.py --from var/research.db

    # 目标库已有数据时默认拒绝覆盖，确认要清空重搬再加 --force
    ... --force

搬运规则
--------
- 表结构由 ORM 模型生成（create_all），不依赖 SQLite 里的旧 DDL；
- 数据按外键依赖顺序（metadata.sorted_tables）整表插入，附件 BLOB 原样进二进制列；
- PostgreSQL 的自增序列不会跟着 INSERT 的显式 id 前进，搬完必须 setval，
  否则下一次插入就撞主键；MySQL 的 AUTO_INCREMENT 会自己跳到 max(id)+1，无需处理。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parent))
import db  # noqa: E402  （导入即建好 Base.metadata 与目标 engine）


def open_target(url: str):
    """目标库一律走 DATABASE_URL，避免和源库搞混。连接参数复用 db 模块的方言规则。"""
    if not url:
        raise SystemExit('缺少目标库：设置 DATABASE_URL，或用 --to 指定')
    normalized = db._normalize_url(url)
    return create_engine(normalized, future=True, pool_pre_ping=True,
                         connect_args=db._connect_args(normalized))


def table_counts(conn, tables) -> dict[str, int]:
    return {t.name: conn.execute(select(func.count()).select_from(t)).scalar() or 0 for t in tables}


def main() -> int:
    parser = argparse.ArgumentParser(description='SQLite → 外部数据库（PostgreSQL / MySQL）整库迁移')
    parser.add_argument('--from', dest='source', default=str(db.DB_PATH),
                        help='源 SQLite 文件路径（默认取当前 DATA_DIR/research.db）')
    parser.add_argument('--to', dest='target', default=os.getenv('DATABASE_URL', ''),
                        help='目标库连接串（默认取环境变量 DATABASE_URL）')
    parser.add_argument('--dry-run', action='store_true', help='只统计源库行数，不写目标库')
    parser.add_argument('--force', action='store_true', help='目标库非空时仍然清空重搬')
    args = parser.parse_args()

    source_path = Path(args.source)
    if not source_path.is_file():
        raise SystemExit('源库不存在：%s' % source_path)

    source_url = 'sqlite:///' + source_path.resolve().as_posix()
    source_engine = create_engine(source_url, future=True)
    tables = list(db.Base.metadata.sorted_tables)

    with source_engine.connect() as src:
        counts = table_counts(src, tables)
        total = sum(counts.values())
        print('源库 %s：%d 张表，%d 行' % (source_path, len(tables), total))
        for name, count in counts.items():
            if count:
                print('  %-22s %d' % (name, count))
        if args.dry_run:
            print('\n--dry-run：未写入任何目标库')
            return 0

        target_url = args.target
        if target_url.startswith('sqlite'):
            # 允许用另一个 sqlite 文件做演练，但不能就地覆盖源库
            if Path(make_url(target_url).database or '').resolve() == source_path.resolve():
                raise SystemExit('目标库和源库是同一个文件，拒绝执行')
        if not target_url:
            raise SystemExit('缺少目标库连接串')

        target_engine = open_target(target_url)
        db.Base.metadata.create_all(target_engine, checkfirst=True)

        with target_engine.begin() as dst:
            existing = table_counts(dst, tables)
            if sum(existing.values()) and not args.force:
                raise SystemExit('目标库已有数据（共 %d 行）。确认要清空重搬请加 --force' % sum(existing.values()))
            if args.force:
                # 逆序删除，避开外键约束
                for table in reversed(tables):
                    dst.execute(table.delete())
                print('已清空目标库')

            for table in tables:
                rows = [dict(row._mapping) for row in src.execute(select(table))]
                if rows:
                    dst.execute(table.insert(), rows)
                print('  %-22s 写入 %d 行' % (table.name, len(rows)))

            if target_engine.dialect.name == 'postgresql':
                # 显式 id 插入不会推进序列，不修的话下一次插入必然主键冲突
                for table in tables:
                    if 'id' not in table.c:
                        continue
                    dst.execute(text(
                        "SELECT setval(pg_get_serial_sequence('%(t)s', 'id'), "
                        "GREATEST(COALESCE((SELECT MAX(id) FROM %(t)s), 0), 1))" % {'t': table.name}))
                print('已校正 PostgreSQL 自增序列')

    print('\n迁移完成。目标库：%s' % (make_url(args.target).render_as_string(hide_password=True)
                                     if args.target else '(未指定)'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
