"""启动入口。

原实现是 ThreadingHTTPServer + 手写分发（见 _backup_pre_fastapi/server.py），
现已迁移到 FastAPI；本文件只负责把应用交给 uvicorn，保持
``python backend/server.py`` 这个启动方式不变。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> None:
    """把项目根目录的 .env 读进环境变量，方便本地与 Docker 用同一份配置。

    已存在的环境变量优先（命令行临时覆盖不会被文件盖掉）；只做 KEY=VALUE，
    不引入 python-dotenv，保持后端零额外依赖。.env 已在 .gitignore 内。
    """
    for candidate in (ROOT / '.env', Path(__file__).resolve().parent / '.env'):
        if not candidate.is_file():
            continue
        for raw in candidate.read_text(encoding='utf-8', errors='replace').splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")


load_env()
sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

from app import app as application  # noqa: E402

if __name__ == '__main__':
    uvicorn.run(
        application,
        host=os.getenv('HOST', '127.0.0.1'),
        port=int(os.getenv('PORT', '8080')),
        log_level=os.getenv('LOG_LEVEL', 'info'),
        access_log=os.getenv('ACCESS_LOG', '1') == '1',
    )
