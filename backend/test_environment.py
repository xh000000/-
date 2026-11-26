"""Shared test-process database isolation, before the first import of db.
Discovery imports modules before running setUpModule: changing DATA_DIR later is too late.
"""
import atexit
import os
import shutil
import sys
import tempfile

_root = None


def prepare():
    global _root
    if _root is None:
        _root = tempfile.mkdtemp(prefix='research-unittest-')
        atexit.register(shutil.rmtree, _root, ignore_errors=True)
    existing = sys.modules.get('db')
    if existing is not None and str(existing.DB_PATH.parent) != _root:
        raise RuntimeError('数据库已在测试隔离前加载，拒绝运行可能写入业务库的测试')
    os.environ['DATA_DIR'] = _root
    os.environ.pop('DATABASE_URL', None)
    os.environ['SKIP_DOTENV'] = '1'
    return _root
