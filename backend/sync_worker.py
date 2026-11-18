"""同步作业执行器：把已授权通道取到的观测行写回库里。

用法（在项目根目录）::

    python backend/sync_worker.py list                 # 打印待执行作业（JSON）
    python backend/sync_worker.py push 3 rows.json     # 回填作业 3；rows.json 是观测行数组
    python backend/sync_worker.py push - rows.json     # 直接入库，不关联作业
    python backend/sync_worker.py fail 4 "本月额度已用完" # 取数通道回不来时结单
    python backend/sync_worker.py stats                # 按来源打印条数 / 指标数 / 最新日期

取数不在这里：同花顺与 Wind 走 WorkBuddy 连接器（生产环境可换 WindPy / iFinD API）。
这样「换取数通道」不影响入库逻辑，重复执行也不会写重复行。
"""
from __future__ import annotations

import json
import sys
import time

import datasource
from db import DataSyncJob, SessionFactory


def stamp() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime()) + ' UTC'


def cmd_list() -> int:
    with SessionFactory() as session:
        print(json.dumps(datasource.pending(session), ensure_ascii=False, indent=2))
    return 0


def cmd_stats() -> int:
    with SessionFactory() as session:
        print(json.dumps(datasource.stats(session), ensure_ascii=False, indent=2))
    return 0


def cmd_fail(job_id: str, message: str) -> int:
    with SessionFactory() as session:
        job = session.get(DataSyncJob, int(job_id))
        if not job:
            print('作业 %s 不存在' % job_id, file=sys.stderr)
            return 2
        datasource.fail_job(session, job, stamp(), message)
        session.commit()
    print(json.dumps({'ok': True, 'job': job_id, 'status': '失败', 'message': message},
                     ensure_ascii=False))
    return 0


def cmd_push(job_id: str, path: str) -> int:
    with open(path, encoding='utf-8') as handle:
        raw = json.load(handle)
    rows = datasource.normalize(raw.get('rows') if isinstance(raw, dict) else raw)
    with SessionFactory() as session:
        job = session.get(DataSyncJob, int(job_id)) if job_id not in ('', '-') else None
        if job_id not in ('', '-') and not job:
            print('作业 %s 不存在' % job_id, file=sys.stderr)
            return 2
        operator = (job.operator if job else '') or 'sync_worker'
        counts = datasource.apply(session, rows, operator)
        if job:
            datasource.finish_job(session, job, counts, stamp(), '由 sync_worker 回填 %s 行' % len(rows))
        session.commit()
    print(json.dumps({'ok': True, 'job': job_id, **counts}, ensure_ascii=False))
    return 0


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in ('list', 'push', 'fail', 'stats'):
        print(__doc__)
        return 1
    command = argv[1]
    if command == 'list':
        return cmd_list()
    if command == 'stats':
        return cmd_stats()
    if command == 'fail':
        if len(argv) < 4:
            print('fail 需要作业号与原因', file=sys.stderr)
            return 1
        return cmd_fail(argv[2], argv[3])
    if len(argv) < 4:
        print('push 需要作业号与文件路径', file=sys.stderr)
        return 1
    return cmd_push(argv[2], argv[3])


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
