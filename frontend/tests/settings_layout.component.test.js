import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest';
import {mount,flushPromises,DOMWrapper} from '@vue/test-utils';
import {nextTick} from 'vue';
import ElementPlus from 'element-plus';
import AccountMenu from '../src/components/AccountMenu.vue';
import ExternalModelsView from '../src/views/ExternalModelsView.vue';
import FlowsView from '../src/views/FlowsView.vue';
import DepartmentsView from '../src/views/DepartmentsView.vue';
import UsersView from '../src/views/UsersView.vue';
import {MENU} from '../src/utils/menu';
import {api} from '../src/api';
import {user,users,departments,roles} from '../src/store/session';
vi.mock('../src/api',()=>({api:vi.fn()}));
vi.mock('vue-router',()=>({useRouter:()=>({push:vi.fn()})}));
vi.mock('../src/store/session',async()=>{
 const {ref,computed}=await import('vue');const user=ref({role:'admin'});
 return {user,isAdmin:computed(()=>user.value.role==='admin'),refresh:vi.fn().mockResolvedValue(undefined),session:{data:{}},categoryTree:ref([]),flows:ref([]),users:ref([]),departments:ref([]),roles:ref([])};
});
let wrapper;
async function ready(){await nextTick();await flushPromises();await new Promise(r=>setTimeout(r,35));}
function buttons(root,label){return root.findAll('button').find(button=>button.text()===label);}
beforeEach(()=>{
 vi.clearAllMocks();users.value=[];departments.value=[{id:5,name:'研究部',depth:1,parent_id:null,effective_enabled:true,users:0}];roles.value=[{id:10,name:'研究员',base_role:'researcher'}];user.value={name:'张研究',role:'admin',dept_name:'研究部',phone:'13800000000',title:'研究员'};
 api.mockResolvedValue({model:'research-model',base_url:'https://example.invalid/v1',key_set:true,key_masked:'key***',models:['research-model'],max_tokens:8000});
});
afterEach(()=>{wrapper?.unmount();wrapper=null;document.body.innerHTML='';});
describe('设置入口重组',()=>{
 it('系统菜单使用外部模型和审批流设置，不再显示基本配置',()=>{
  const settings=MENU.find(group=>group.label==='系统设置');
  expect(settings.children.some(item=>item.label==='外部模型'&&item.path==='/system/models'&&item.admin)).toBe(true);
  expect(settings.children.some(item=>item.label==='审批流设置'&&item.path==='/config/flows')).toBe(true);
  expect(settings.children.some(item=>item.label==='基本配置')).toBe(false);
 });
 it('右上角账号模块对普通用户也可用，显示本人信息并可修改密码',async()=>{
  user.value.role='researcher';wrapper=mount(AccountMenu,{attachTo:document.body,global:{plugins:[ElementPlus]}});
  await wrapper.find('button[aria-label="我的账号"]').trigger('click');await ready();
  const body=new DOMWrapper(document.body);expect(body.find('.account-panel').text()).toContain('研究部');
  expect(body.find('.account-panel').text()).toContain('13800000000');
  await buttons(body,'修改密码').trigger('click');await ready();expect(wrapper.emitted('password')).toHaveLength(1);
 });
 it('退出登录由账号模块发出，交由既有退出确认流程处理',async()=>{
  wrapper=mount(AccountMenu,{attachTo:document.body,global:{plugins:[ElementPlus]}});
  await wrapper.find('button[aria-label="我的账号"]').trigger('click');await ready();
  await buttons(new DOMWrapper(document.body),'退出登录').trigger('click');await ready();expect(wrapper.emitted('logout')).toHaveLength(1);
 });
 it('外部模型页独立展示模型配置，不包含账号及审批模块',async()=>{
  wrapper=mount(ExternalModelsView,{attachTo:document.body,global:{plugins:[ElementPlus]}});await ready();
  expect(api).toHaveBeenCalledWith('ai/config');expect(wrapper.text()).toContain('外部模型');
  expect(wrapper.text()).not.toContain('我的账号');expect(wrapper.text()).not.toContain('研报审批');
  await buttons(wrapper,'编辑').trigger('click');await ready();
  const keyRow=new DOMWrapper(document.body).findAll('.el-form-item').find(row=>row.find('.el-form-item__label').text()==='API Key');
  expect(keyRow.find('input').element.value).toBe('');
 });
 it('编辑原有配置后可以保存，换地址时重新填写密钥',async()=>{
  wrapper=mount(ExternalModelsView,{attachTo:document.body,global:{plugins:[ElementPlus]}});await ready();
  await buttons(wrapper,'编辑').trigger('click');await ready();
  const body=new DOMWrapper(document.body);
  const baseRow=body.findAll('.el-form-item').find(row=>row.find('.el-form-item__label').text()==='接口地址');
  await baseRow.find('input').setValue('https://example.invalid/v2');
  const keyRow=body.findAll('.el-form-item').find(row=>row.find('.el-form-item__label').text()==='API Key');
  await keyRow.find('input').setValue('test-reentered-key');await buttons(body,'保存并更新启用配置').trigger('click');await ready();
  expect(api).toHaveBeenCalledWith('ai/config',{model:'research-model',base_url:'https://example.invalid/v2',api_key:'test-reentered-key'});
 });
 it('审批说明归入审批流设置页面，保留配置操作',()=>{
  wrapper=mount(FlowsView,{global:{plugins:[ElementPlus]}});
  expect(wrapper.text()).toContain('审批流设置');expect(wrapper.text()).toContain('研报审批规则');
  expect(wrapper.text()).toContain('作者不能审核或发布自己的报告');expect(buttons(wrapper,'添加审批流')).toBeTruthy();
 });
 it('审批流选择器只显示同角色的启用账号',async()=>{
  users.value=[{id:20,name:'启用复核员',role:'reviewer',enabled:1},{id:21,name:'停用复核员',role:'reviewer',enabled:0},{id:22,name:'合规人员',role:'compliance',enabled:1}];
  wrapper=mount(FlowsView,{attachTo:document.body,global:{plugins:[ElementPlus]}});
  await buttons(wrapper,'添加审批流').trigger('click');await ready();
  const body=new DOMWrapper(document.body);
  const row=body.findAll('.el-form-item').find(row=>row.find('.el-form-item__label').text()==='指定审批人');
  await row.find('.el-select').trigger('click');await ready();
  const options=[...document.querySelectorAll('.el-select-dropdown__item')].map(option=>option.textContent).join('|');
  expect(options).toContain('启用复核员');expect(options).not.toContain('停用复核员');expect(options).not.toContain('合规人员');
 });

 it('部门管理与账号列表分开，分别提供自己的入口',()=>{
  wrapper=mount(DepartmentsView,{global:{plugins:[ElementPlus]}});
  expect(wrapper.text()).toContain('部门与分组');expect(wrapper.text()).not.toContain('账号列表');expect(buttons(wrapper,'添加账号')).toBeUndefined();
  wrapper.unmount();wrapper=mount(UsersView,{global:{plugins:[ElementPlus]}});
  expect(wrapper.text()).toContain('账号管理');expect(wrapper.text()).toContain('账号列表');expect(buttons(wrapper,'添加账号')).toBeTruthy();
  const settings=MENU.find(item=>item.label==='系统设置');expect(settings.children.some(item=>item.path==='/system/users'&&item.admin)).toBe(true);
 });
 it('独立账号页可以新增账号，保留角色和部门字段',async()=>{
  wrapper=mount(UsersView,{attachTo:document.body,global:{plugins:[ElementPlus]}});
  await buttons(wrapper,'添加账号').trigger('click');await ready();
  const body=new DOMWrapper(document.body);const field=label=>body.findAll('.el-form-item').find(row=>row.find('.el-form-item__label').text()===label);
  await field('姓名').find('input').setValue('新测试账号');await field('初始密码').find('input').setValue('test-user-123');
  await buttons(body,'保存').trigger('click');await ready();
  expect(api).toHaveBeenCalledWith('users',expect.objectContaining({action:'create',name:'新测试账号',password:'test-user-123',role_id:10,dept_id:null}));
 });
 it('独立账号页编辑既有账号时保留部门归属',async()=>{
  users.value=[{id:20,name:'账号用户',role:'researcher',role_id:10,dept_id:5,dept_name:'研究部',enabled:1}];
  wrapper=mount(UsersView,{attachTo:document.body,global:{plugins:[ElementPlus]}});
  await ready();await buttons(wrapper,'编辑').trigger('click');await ready();
  const body=new DOMWrapper(document.body);await buttons(body,'保存').trigger('click');await ready();
  expect(api).toHaveBeenCalledWith('users',expect.objectContaining({action:'update',id:20,name:'账号用户',role_id:10,dept_id:5}));
 });

});
