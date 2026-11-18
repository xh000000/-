import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import {nextTick} from 'vue';
import ElementPlus from 'element-plus';
import {MENU,filterMenu,menuId} from '../src/utils/menu';
import MenuManagementView from '../src/views/MenuManagementView.vue';
import router from '../src/router';
import {api} from '../src/api';
import {session,refresh} from '../src/store/session';
vi.mock('../src/api',()=>({api:vi.fn()}));
vi.mock('../src/store/session',()=>({session:{ready:true,data:{menu_visibility:{}}},boot:vi.fn(),refresh:vi.fn().mockResolvedValue(undefined)}));
vi.spyOn(window,'scrollTo').mockImplementation(()=>{});
const admin={role:'admin',menus:['*']};
function paths(items){return items.flatMap(group=>[group.path,...(group.children||[]).map(child=>child.path)]).filter(Boolean);}
describe('菜单显示与权限',()=>{
 it('菜单管理仅管理员可见，即使普通用户有通配符也不能看到',()=>{
  expect(paths(filterMenu(MENU,admin))).toContain('/system/menus');
  const normal=filterMenu(MENU,{role:'researcher',menus:['*']});
  expect(normal.some(group=>group.label==='系统设置')).toBe(false);
  for(const path of ['/system/users','/system/menus','/system/models','/system/settings','/system/roles','/system/departments','/config/flows']) {
    expect(paths(normal)).not.toContain(path);
    expect(router.resolve(path).meta.admin).toBe(true);
  }
 });
 it('普通用户直接访问系统设置页面会返回工作台',async()=>{
  session.data={user:{id:2,role:'researcher',menus:['*']}};
  for(const path of ['/system/users','/system/menus','/system/models','/system/settings','/system/roles','/system/departments','/config/flows']) {
    await router.push(path);
    expect(router.currentRoute.value.name).toBe('dashboard');
  }
 });
 it('隐藏分组会隐藏所有子菜单，恢复后保留子菜单自身设置',()=>{
  const visibility={'group:数据源':false,'/data':false};
  expect(paths(filterMenu(MENU,admin,visibility))).not.toContain('/data/indicators');
  delete visibility['group:数据源'];
  expect(paths(filterMenu(MENU,admin,visibility))).toContain('/data/indicators');
  expect(paths(filterMenu(MENU,admin,visibility))).not.toContain('/data');
 });
 it('子菜单全部隐藏后不保留空分组',()=>{
  expect(filterMenu(MENU,admin,{'/data':false,'/data/indicators':false}).some(group=>group.label==='数据源')).toBe(false);
 });
 it('显示开关不会赋予账号角色中没有的菜单权限',()=>{
  expect(paths(filterMenu(MENU,{role:'researcher',menus:['研报中心']},{'/data':true}))).not.toContain('/data');
  expect(paths(filterMenu(MENU,{role:'researcher',menus:['研报中心']}))).toContain('/reports');
 });
 it('管理员的恢复入口始终保留，所有菜单标识互不重复',()=>{
  expect(paths(filterMenu(MENU,admin,{'group:系统设置':false,'/system/menus':false}))).toContain('/system/menus');
  const ids=MENU.flatMap(g=>[menuId(g),...(g.children||[]).map(c=>menuId(c,g))]);expect(new Set(ids).size).toBe(ids.length);
 });
});
let wrapper;
async function ready(){await nextTick();await flushPromises();}
function button(label){return wrapper.findAll('button').find(button=>button.text()===label);}
function row(label){return wrapper.findAll('tr').find(row=>row.find('.cell').exists()&&row.find('.cell').text().replace('仅管理员','').trim()===label);}
beforeEach(()=>{vi.clearAllMocks();session.data={menu_visibility:{}};api.mockResolvedValue({revision:0,visibility:{}});});
afterEach(()=>{wrapper?.unmount();wrapper=null;document.body.innerHTML='';});
async function mountView(){wrapper=mount(MenuManagementView,{attachTo:document.body,global:{plugins:[ElementPlus]}});await ready();}
describe('菜单管理界面',()=>{
 it('加载配置；修改显示开关后保存并更新导航',async()=>{
  await mountView();expect(button('保存设置').attributes('disabled')).toBeDefined();
  await row('数据源').find('.el-switch').trigger('click');await ready();
  expect(button('保存设置').attributes('disabled')).toBeUndefined();
  api.mockResolvedValueOnce({revision:1,visibility:{'group:数据源':false}});
  await button('保存设置').trigger('click');await ready();
  expect(api).toHaveBeenLastCalledWith('system/menus',{revision:0,visibility:{'group:数据源':false}});
  expect(session.data.menu_visibility).toEqual({'group:数据源':false});expect(refresh).toHaveBeenCalled();
 });
 it('隐藏上级时禁用子菜单开关；保留管理员入口',async()=>{
  api.mockResolvedValue({revision:2,visibility:{'group:数据源':false}});await mountView();
  expect(row('数据录入').find('.el-switch').classes()).toContain('is-disabled');
  expect(row('菜单管理').find('.el-switch').classes()).toContain('is-disabled');
  expect(row('系统设置').find('.el-switch').classes()).toContain('is-disabled');
 });
 it('恢复默认只修改草稿，点击保存后才持久化',async()=>{
  api.mockResolvedValue({revision:1,visibility:{'/data':false}});await mountView();
  await button('恢复默认').trigger('click');await ready();expect(api).toHaveBeenCalledTimes(1);
  expect(button('保存设置').attributes('disabled')).toBeUndefined();
  api.mockResolvedValueOnce({revision:2,visibility:{}});await button('保存设置').trigger('click');await ready();
  expect(api).toHaveBeenLastCalledWith('system/menus',{revision:1,visibility:{}});
 });
 it('保存冲突时保留本地修改，可重新加载',async()=>{
  await mountView();await row('指标查询').find('.el-switch').trigger('click');await ready();
  api.mockRejectedValueOnce(new Error('菜单设置已被其他管理员更新'));await button('保存设置').trigger('click');await ready();
  expect(button('保存设置').attributes('disabled')).toBeUndefined();
  api.mockResolvedValueOnce({revision:3,visibility:{'/data':false}});await button('重新加载').trigger('click');await ready();
  expect(button('保存设置').attributes('disabled')).toBeDefined();
 });
});
