import unittest
from test_workflow import Workflow

class MenuSettings(Workflow):
    def test_admin_visibility_settings(self):
        admin=self.client();self.assertEqual(self.call(admin,'setup',{'name':'admin','password':'123456'})[0],200)
        status,department=self.call(admin,'departments',{'name':'菜单测试研究部'})
        self.assertEqual(status,200)
        self.assertEqual(self.call(admin,'users',{'name':'menu-user','role':'researcher','password':'123456','dept_id':department['id']})[0],200)
        member=self.client();self.assertEqual(self.call(member,'login',{'name':'menu-user','password':'123456'})[0],200)
        self.assertEqual(self.call(self.client(),'system/menus')[0],401)
        self.assertEqual(self.call(member,'system/menus')[0],403)
        self.assertEqual(self.call(member,'system/menus',{'revision':0,'visibility':{}})[0],403)
        status,current=self.call(admin,'system/menus');self.assertEqual(status,200)
        self.assertEqual(current,{'revision':0,'visibility':{}})
        config={'group:数据源':False,'/library/cloud':False,'item:工具箱:AI问答':False}
        status,saved=self.call(admin,'system/menus',{'revision':0,'visibility':config})
        self.assertEqual(status,200,saved);self.assertEqual(saved['revision'],1)
        # Both accounts receive the same global visibility; no role grants are changed.
        for account in [admin,member]:
            state=self.call(account,'state')[1]
            self.assertEqual(state['menu_visibility'],config)
        member_state=self.call(member,'state')[1]
        self.assertNotIn('系统管理',member_state['user']['menus'])
        self.assertEqual(member_state['user']['dept_name'],'菜单测试研究部')
        self.assertEqual(member_state['departments'],[])
        self.assertEqual(member_state['users'],[])
        # A fresh admin session sees persisted configuration.
        other=self.client();self.call(other,'login',{'name':'admin','password':'123456'})
        self.assertEqual(self.call(other,'system/menus')[1],saved)
        self.assertEqual(self.call(other,'system/menus',{'revision':0,'visibility':{}})[0],409)
        self.assertEqual(self.call(admin,'system/menus')[1],saved)
        for bad in [{'group:系统设置':False},{'/system/menus':False},{'/data':'false'}]:
            self.assertEqual(self.call(admin,'system/menus',{'revision':1,'visibility':bad})[0],400)
            self.assertEqual(self.call(admin,'system/menus')[1],saved)
        status,restored=self.call(admin,'system/menus',{'revision':1,'visibility':{}})
        self.assertEqual(status,200);self.assertEqual(restored,{'revision':2,'visibility':{}})
        self.assertEqual(self.call(member,'state')[1]['menu_visibility'],{})
        # Legacy basic-settings visibility continues to hide the new model page.
        self.assertEqual(self.call(admin,'system/menus',{'revision':2,'visibility':{'/system/settings':False}})[0],200)
        self.assertEqual(self.call(admin,'system/menus')[1]['visibility'],{'/system/models':False})
        self.assertEqual(self.call(member,'state')[1]['menu_visibility'],{'/system/models':False})


def load_tests(loader,tests,pattern):
    return unittest.TestSuite([MenuSettings('test_admin_visibility_settings')])

if __name__=='__main__':unittest.main(verbosity=2)
