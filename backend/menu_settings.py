"""Global navigation visibility. Visibility never grants business permissions."""
import json
from sqlalchemy import update
from db import AppSetting

KEY = 'menu_visibility'
PROTECTED = {'group:系统设置', '/system/menus'}


def read(session):
    row = session.get(AppSetting, KEY)
    try:
        stored = json.loads(row.value) if row else {}
    except (ValueError, TypeError):
        stored = {}
    visibility = stored.get('visibility', {}) if isinstance(stored, dict) else {}
    if not isinstance(visibility, dict):
        visibility = {}
    visibility = {('/system/models' if key == '/system/settings' else key): value
                  for key, value in visibility.items() if key != '/system/settings' or '/system/models' not in visibility}
    return {'revision': stored.get('revision', 0) if isinstance(stored, dict) else 0,
            'visibility': {key: value for key, value in visibility.items()
                           if isinstance(key, str) and type(value) is bool and key not in PROTECTED}}


def save(session, data, at):
    visibility = data.get('visibility')
    revision = data.get('revision')
    if not isinstance(visibility, dict) or len(visibility) > 200:
        raise ValueError('菜单显示设置需为对象，最多 200 项')
    if type(revision) is not int or revision < 0:
        raise ValueError('菜单设置版本无效，请刷新后重试')
    for key, value in visibility.items():
        if not isinstance(key, str) or not key or len(key) > 200 or type(value) is not bool:
            raise ValueError('菜单显示设置需使用菜单标识及布尔值')
        if key in PROTECTED and not value:
            raise ValueError('系统设置与菜单管理需保留管理员入口')
    # Reserve the SQLite writer before reading the revision. Independent admin
    # sessions cannot silently replace a newer saved configuration.
    session.execute(update(AppSetting).where(AppSetting.key == KEY)
                    .values(value=AppSetting.value).execution_options(synchronize_session=False))
    session.expire_all()
    current = read(session)
    if current['revision'] != revision:
        return {'error': '菜单设置已被其他管理员更新，请重新加载后再修改'}, 409
    result = {'revision': revision + 1,
              'visibility': {key: value for key, value in visibility.items() if not value and key not in PROTECTED}}
    row = session.get(AppSetting, KEY)
    if row:
        row.value = json.dumps(result, ensure_ascii=False)
        row.updated = at
    else:
        session.add(AppSetting(key=KEY, value=json.dumps(result, ensure_ascii=False), updated=at))
    session.flush()
    return result, 200
