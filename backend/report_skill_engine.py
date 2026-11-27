"""Application report Skills: bounded Markdown instructions, no script or shell execution.
Inspired by Skill metadata/lazy loading; permission enforcement stays in platform code.
"""
import hashlib
import json
import re
import uuid
from pathlib import Path
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from db import AppSetting

KEY = 'report_skill_catalog'
ROOT = Path(__file__).with_name('report_skills')
BUILTINS = {'daily-research': '日度 / 周度研报', 'supply-demand': '商品供需专题'}


def parse(markdown):
    if not isinstance(markdown, str) or not 30 <= len(markdown) <= 12000:
        raise ValueError('SKILL.md 应为30至12000字的文本')
    import yaml
    match = re.match(r'\A---\s*\n(.*?)\n---\s*\n(.*)\Z', markdown.strip(), re.S)
    if not match: raise ValueError('需要 SKILL.md 格式：YAML 头部的 name、description，以及正文指令')
    class MetadataLoader(yaml.SafeLoader):
        def construct_mapping(self, node, deep=False):
            result={}
            for key_node,value_node in node.value:
                key=self.construct_object(key_node,deep=deep)
                if not isinstance(key,str) or key in result: raise ValueError('Skill 元数据字段重复或无效')
                result[key]=self.construct_object(value_node,deep=deep)
            return result
    try: headers=yaml.load(match[1],Loader=MetadataLoader)
    except yaml.YAMLError as exc: raise ValueError('SKILL.md 的 YAML 头部格式错误，请检查缩进与引号') from exc
    if not isinstance(headers,dict) or not isinstance(headers.get('name'),str) or not isinstance(headers.get('description'),str):
        raise ValueError('Skill 的 name、description 必须为文本')
    if len(headers['name'])>64 or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', headers['name']):
        raise ValueError('Skill name 请使用小写英文、数字和连字符')
    if not 1 <= len(headers.get('description','')) <= 500 or not match[2].strip():
        raise ValueError('Skill 必须包含描述和正文指令')
    return headers, match[2].strip()


def state(s):
    row = s.get(AppSetting, KEY)
    return json.loads(row.value) if row else {'revision':0,'skills':[]}


def catalog(s):
    out = []
    for sid, title in BUILTINS.items():
        raw = (ROOT/sid/'SKILL.md').read_text(encoding='utf-8')
        meta, instructions = parse(raw)
        out.append({'id':sid,'name':title,'description':meta['description'],'markdown':raw,
                    'enabled':True,'builtin':True,'version':hashlib.sha256(raw.encode()).hexdigest()[:12]})
    for row in state(s)['skills']:
        version_text = row['markdown'] + (json.dumps(row.get('resources'),ensure_ascii=False,sort_keys=True) if row.get('resources') else '')
        out.append({**row,'builtin':False,'version':hashlib.sha256(version_text.encode()).hexdigest()[:12]})
    return out


def selected(s, ids):
    if not isinstance(ids,list) or not 1 <= len(ids) <= 3 or len(set(ids)) != len(ids):
        raise ValueError('请选择1至3个不同的 Skill')
    known = {x['id']:x for x in catalog(s)}
    values = []
    for sid in ids:
        row = known.get(sid)
        if not row or not row['enabled']: raise ValueError('Skill 不存在或已停用，请重新选择')
        values.append(dict(row))
    if sum(len(x['markdown']) for x in values)>20000: raise ValueError('所选 Skill 总长度超过20000字，请减少选择')
    return values


def save(s, data, user, stamp):
    import app
    before = state(s)
    if data.get('revision')!=before['revision']: raise app.ApiError(409,'Skill 列表已更新，请刷新')
    sid = str(data.get('id') or '')
    if sid in BUILTINS: raise ValueError('内置 Skill 不可修改，可复制其内容新增自定义 Skill')
    old = next((x for x in before['skills'] if x['id']==sid),None)
    if sid and old is None: raise ValueError('Skill 不存在')
    markdown = data.get('markdown')
    meta,_ = parse(markdown)
    title = str(data.get('name') or meta['name']).strip()
    if not 1 <= len(title)<=60: raise ValueError('配置名称应为1至60字')
    if old is None and len(before['skills'])>=30: raise ValueError('最多保存30个自定义 Skill')
    resources=clean_resources(data.get('resources', (old or {}).get('resources',{})))
    value = {'id':sid or 'custom-'+uuid.uuid4().hex,'name':title,'description':meta['description'],
             'markdown':markdown,'resources':resources,'enabled':bool(data.get('enabled',True)),'updated':stamp}
    updated = {'revision':before['revision']+1,'skills':[value if x['id']==sid else x for x in before['skills']]}
    if old is None: updated['skills'].append(value)
    row = s.get(AppSetting,KEY)
    if row:
        old_value = row.value
        changed = s.execute(update(AppSetting).where(AppSetting.key==KEY,AppSetting.value==old_value)
                            .values(value=json.dumps(updated,ensure_ascii=False),updated=stamp)).rowcount
        if changed!=1: raise app.ApiError(409,'Skill 列表已更新，请刷新')
    else: s.add(AppSetting(key=KEY,value=json.dumps(updated,ensure_ascii=False),updated=stamp))
    try: s.commit()
    except IntegrityError:
        s.rollback(); raise app.ApiError(409,'Skill 列表已更新，请刷新')
    return {'id':value['id']}


def delete(s, data, user, stamp):
    """删除自定义 Skill；内置只读、不可删。CAS 更新避免覆盖别人的修改。"""
    import app
    before = state(s)
    if data.get('revision')!=before['revision']: raise app.ApiError(409,'Skill 列表已更新，请刷新')
    sid = str(data.get('id') or '')
    if sid in BUILTINS: raise ValueError('内置 Skill 不可删除')
    if not any(x['id']==sid for x in before['skills']): raise ValueError('Skill 不存在或已删除')
    updated = {'revision':before['revision']+1,'skills':[x for x in before['skills'] if x['id']!=sid]}
    row = s.get(AppSetting,KEY)
    if not row: raise ValueError('Skill 不存在或已删除')
    old_value = row.value
    changed = s.execute(update(AppSetting).where(AppSetting.key==KEY,AppSetting.value==old_value)
                        .values(value=json.dumps(updated,ensure_ascii=False),updated=stamp)).rowcount
    if changed!=1: raise app.ApiError(409,'Skill 列表已更新，请刷新')
    try: s.commit()
    except IntegrityError:
        s.rollback(); raise app.ApiError(409,'Skill 列表已更新，请刷新')
    return {'id':sid,'deleted':True}


TEXT_EXTENSIONS = {'.md', '.txt', '.json', '.csv'}
MAX_ZIP_BYTES = 2 * 1024 * 1024


def clean_resources(resources):
    from pathlib import PurePosixPath
    if not isinstance(resources, dict) or len(resources)>80: raise ValueError('配套文本资料最多80个')
    total=0; result={}
    for name, content in resources.items():
        if not isinstance(name,str) or not name or len(name)>240 or '\\' in name or ':' in name or any(ord(char)<32 for char in name):
            raise ValueError('配套资料路径无效')
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or path.suffix.lower() not in TEXT_EXTENSIONS:
            raise ValueError('配套资料仅支持包内 Markdown、TXT、JSON、CSV 文件')
        if not isinstance(content,str) or len(content)>60000: raise ValueError('单个文本资料最多60000字')
        total+=len(content)
        if total>200000: raise ValueError('配套文本资料总量最多200000字')
        result[str(path)]=content
    return result


def inspect_zip(raw):
    """Inspect in memory. No archive entry is extracted to disk or executed."""
    import io
    import stat
    import unicodedata
    import zipfile
    import zlib
    from pathlib import PurePosixPath
    if not raw or len(raw)>MAX_ZIP_BYTES: raise ValueError('ZIP 文件不能为空且不能超过2 MB')
    try:
        archive=zipfile.ZipFile(io.BytesIO(raw))
        with archive:
            entries=archive.infolist()
            if len(entries)>150 or sum(x.file_size for x in entries)>8*1024*1024:
                raise ValueError('ZIP 文件数量或解压后大小超限（最多150项、8 MB）')
            files={}; seen=set()
            for item in entries:
                name=unicodedata.normalize('NFC',item.orig_filename)
                path=PurePosixPath(name)
                if '\\' in name or ':' in name or any(ord(char)<32 for char in name) or path.is_absolute() or '..' in path.parts or len(name)>300:
                    raise ValueError('ZIP 中含不安全的文件路径')
                mode=stat.S_IFMT(item.external_attr>>16)
                if mode not in (0,stat.S_IFREG,stat.S_IFDIR): raise ValueError('ZIP 不允许符号链接或特殊文件')
                if item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED): raise ValueError('请使用普通 ZIP 压缩（存储或 Deflate）')
                if item.flag_bits & 1: raise ValueError('不支持加密 ZIP，请先解除密码')
                key=str(path).casefold()
                if key in seen: raise ValueError('ZIP 中存在重复或大小写冲突的路径')
                seen.add(key)
                if item.is_dir() or '__MACOSX' in path.parts or path.name.startswith('._'): continue
                if item.file_size>512*1024: raise ValueError('ZIP 中单个文件不得超过512 KB')
                files[str(path)]=item
            candidates=sorted((x for x in files if PurePosixPath(x).name.casefold()=='skill.md'),key=lambda x:len(PurePosixPath(x).parts))
            roots=[]
            for candidate in candidates:
                if not any(PurePosixPath(root).parent in PurePosixPath(candidate).parents for root in roots): roots.append(candidate)
            if len(roots)!=1: raise ValueError('ZIP 中需包含一个 Skill 包及其 SKILL.md；多个独立 Skill 请分别导入')
            main=roots[0]; prefix=str(PurePosixPath(main).parent)
            prefix='' if prefix=='.' else prefix+'/'
            def read(item):
                with archive.open(item) as stream:
                    data=stream.read(512*1024+1)
                if len(data)>512*1024: raise ValueError('ZIP 文件实际大小超限')
                return data.decode('utf-8-sig')
            try: markdown=read(files[main])
            except UnicodeDecodeError: raise ValueError('SKILL.md 需要 UTF-8 编码')
            meta,_=parse(markdown)
            resources={}; ignored=[]
            for name,item in files.items():
                if name==main or not name.startswith(prefix): continue
                local=name[len(prefix):]
                if PurePosixPath(local).name.casefold()=='skill.md' or PurePosixPath(local).suffix.lower() not in TEXT_EXTENSIONS:
                    ignored.append(local); continue
                try: resources[local]=read(item)
                except UnicodeDecodeError: ignored.append(local+'（非 UTF-8 文本）')
            resources=clean_resources(resources)
            return {'name':meta['name'],'markdown':markdown,'resources':resources,
                    'warnings':(['以下文件不参与导入，也不会执行：'+ '、'.join(ignored)] if ignored else [])}
    except (zipfile.BadZipFile,NotImplementedError,RuntimeError,zlib.error) as exc:
        raise ValueError('无法读取 ZIP，请确认文件完整且使用标准 ZIP 压缩') from exc


def context(skill, limit=18000):
    """Bounded, attributable reference loading; snapshots retain the full imported texts."""
    text=skill['markdown']; remaining=max(0,limit-len(text))
    resources=skill.get('resources') or {}
    names=sorted(resources,key=lambda name:(name not in skill['markdown'],name))
    for name in names:
        if remaining<100: break
        content=resources[name]
        piece='\n\n【Skill 配套资料：'+name+'】\n'+content[:min(6000,remaining-80)]
        if len(content)>min(6000,remaining-80):piece+='\n（本资料仅加载前段，使用前请核对完整内容）'
        text+=piece;remaining-=len(piece)
    return text
