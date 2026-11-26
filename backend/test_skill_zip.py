"""Archive validation and resource snapshots; no filesystem extraction or external APIs."""
from test_environment import prepare
prepare()
import io
import json
import stat
import unittest
import zipfile
from unittest.mock import patch
import report_skill_engine as skills

RAW='---\nname: zip-research\ndescription: >\n  使用资料进行\n  供需研究\n---\n# 研究方法\n\n先阅读 references/method.md，再根据证据写作。'

def archive(files):
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,text in files:
            z.writestr(name,text)
    return out.getvalue()

class SkillZip(unittest.TestCase):
    def test_root_and_wrapped_package(self):
        for prefix in ('','my-research/'):
            package=skills.inspect_zip(archive([(prefix+'SKILL.md',RAW),(prefix+'references/method.md','库存与供需方法'),(prefix+'scripts/run.py','raise RuntimeError("must not execute")')]))
            self.assertEqual(package['name'],'zip-research');self.assertEqual(package['resources'],{'references/method.md':'库存与供需方法'})
            self.assertIn('scripts/run.py',package['warnings'][0]);self.assertIn('库存与供需方法',skills.context(package))

    def test_bad_missing_and_multiple(self):
        for data in (b'bad zip',archive([('README.md','none')]),archive([('a/SKILL.md',RAW),('b/SKILL.md',RAW)])):
            with self.assertRaises(ValueError):skills.inspect_zip(data)

    def test_paths_links_duplicates(self):
        link=zipfile.ZipInfo('references/link.md');link.create_system=3;link.external_attr=(stat.S_IFLNK|0o777)<<16
        for files in ([('SKILL.md',RAW),('../escaped.md','bad')],[('SKILL.md',RAW),('/tmp/bad.md','bad')],
                      [('SKILL.md',RAW),('a\\b.md','bad')],[('SKILL.md',RAW),('skill.md',RAW)], [('SKILL.md',RAW),(link,'/etc/passwd')]):
            with self.assertRaises(ValueError):skills.inspect_zip(archive(files))

    def test_size_count_encoding(self):
        for data in (b'x'*(skills.MAX_ZIP_BYTES+1),archive([('SKILL.md',RAW),('huge.txt','x'*(512*1024+1))]),
                     archive([('SKILL.md',RAW)]+[(f'{i}.txt','a') for i in range(150)]),archive([('SKILL.md',b'\xff\xfe')])):
            with self.assertRaises(ValueError):skills.inspect_zip(data)

    def test_safe_yaml_and_nested_skill(self):
        for raw in ('---\nname: a\nname: b\ndescription: test\n---\n# content', '---\nname: !!python/object/apply:os.system ["false"]\ndescription: test\n---\n# content'):
            with self.assertRaises(ValueError):skills.parse(raw)
        bundle=skills.inspect_zip(archive([('SKILL.md',RAW),('tests/SKILL.md',RAW)]))
        self.assertEqual(bundle['name'],'zip-research')

    def test_resources_affect_version_and_context_is_bounded(self):
        one={'id':'a','name':'test','description':'test','markdown':RAW,'enabled':True,'resources':{'a.md':'a'*60000}}
        with patch.object(skills,'state',return_value={'skills':[one]}):first=skills.catalog(None)[-1]['version']
        other={**one,'resources':{'a.md':'b'*60000}}
        with patch.object(skills,'state',return_value={'skills':[other]}):self.assertNotEqual(first,skills.catalog(None)[-1]['version'])
        self.assertLess(len(skills.context(one)),18000)
        with self.assertRaises(ValueError):skills.clean_resources({'../bad.md':'bad'})

if __name__=='__main__':unittest.main(verbosity=2)
