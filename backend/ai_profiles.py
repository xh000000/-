"""Saved model configurations. Only the active profile is used for generation."""
import json
import uuid
from urllib.parse import urlsplit
from sqlalchemy import update
from db import AppSetting

KEY = 'ai_model_profiles'


def read(session):
    if KEY not in session.info:
        row = session.get(AppSetting, KEY)
        session.info[KEY] = json.loads(row.value) if row else {'revision': 0, 'active_id': 'legacy', 'profiles': []}
    return session.info[KEY]


def active(session):
    state = read(session)
    if state['active_id'] == 'legacy':
        return None
    profile = next((p for p in state['profiles'] if p['id'] == state['active_id']), None)
    if profile is None:
        raise ValueError('当前启用的模型配置不存在，请由管理员重新选择')
    return profile


def public(profile, mask):
    return {k: v for k, v in profile.items() if k != 'api_key'} | {
        'key_set': bool(profile.get('api_key')), 'key_masked': mask(profile.get('api_key', '')),
    }


def valid_base(value):
    value = str(value or '').strip().rstrip('/')
    parts = urlsplit(value)
    if (len(value) > 500 or parts.scheme not in ('http', 'https') or not parts.hostname
            or parts.username or parts.password or parts.query or parts.fragment
            or any(ch.isspace() for ch in value)):
        raise ValueError('请填写有效的 HTTP / HTTPS 接口根地址，不含账号、查询参数或片段')
    return value


def mutate(session, data, legacy, at):
    revision = data.get('revision')
    if type(revision) is not int or revision < 0:
        raise ValueError('模型配置版本无效，请重新加载')
    session.execute(update(AppSetting).where(AppSetting.key == KEY)
                    .values(value=AppSetting.value).execution_options(synchronize_session=False))
    session.expire_all()
    session.info.pop(KEY, None)
    state = read(session)
    if state['revision'] != revision:
        return {'error': '模型配置已被其他管理员修改，请重新加载后再操作'}, 409
    action, pid = data.get('action'), str(data.get('id') or '')
    profile = next((p for p in state['profiles'] if p['id'] == pid), None)
    if action == 'save':
        if pid and not profile:
            raise ValueError('模型配置不存在')
        if not profile and len(state['profiles']) >= 30:
            raise ValueError('最多保存 30 个模型配置')
        name, model = str(data.get('name') or '').strip(), str(data.get('model') or '').strip()
        if not name or len(name) > 60 or not model or len(model) > 120:
            raise ValueError('配置名称和模型名称必填（分别最多 60、120 字符）')
        base = valid_base(data.get('base_url'))
        key = str(data.get('api_key') or '').strip()
        if not key and profile:
            if base != profile['base_url']:
                raise ValueError('修改接口地址时请重新填写密钥')
            key = profile['api_key']
        if not key or len(key) > 512 or any(ch.isspace() for ch in key):
            raise ValueError('请填写有效密钥（最多 512 字符，不含空格或换行）')
        saved = {'id': pid or uuid.uuid4().hex, 'name': name, 'provider': 'openai',
                 'model': model, 'base_url': base, 'api_key': key, 'updated': at}
        if profile:
            state['profiles'][state['profiles'].index(profile)] = saved
        else:
            state['profiles'].append(saved)
    elif action == 'activate':
        if pid == 'legacy':
            session.info.pop('legacy_ai_profile', None)
        selected = legacy() if pid == 'legacy' else profile
        if not selected:
            raise ValueError('模型配置不存在')
        if not selected.get('api_key') or (selected.get('provider') != 'codebuddy-cli' and not selected.get('model')):
            raise ValueError('请先补齐此配置的模型名称和密钥，再启用')
        state['active_id'] = pid
    elif action == 'delete':
        if pid == 'legacy':
            raise ValueError('原有配置不能删除')
        if not profile:
            raise ValueError('模型配置不存在')
        if state['active_id'] == pid:
            raise ValueError('当前启用的配置不能删除，请先启用其他配置')
        state['profiles'].remove(profile)
    else:
        raise ValueError('不支持的模型配置操作')
    state['revision'] += 1
    row = session.get(AppSetting, KEY)
    if row:
        row.value, row.updated = json.dumps(state, ensure_ascii=False), at
    else:
        session.add(AppSetting(key=KEY, value=json.dumps(state, ensure_ascii=False), updated=at))
    session.flush()
    return {'ok': True, 'revision': state['revision'], 'active_id': state['active_id']}, 200
