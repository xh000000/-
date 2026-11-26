import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest';
import {mount,flushPromises,DOMWrapper} from '@vue/test-utils';
import {nextTick} from 'vue';
import ElementPlus from 'element-plus';
import ExternalModelsView from '../src/views/ExternalModelsView.vue';
import {api} from '../src/api';
vi.mock('../src/api',()=>({api:vi.fn()}));
vi.mock('../src/store/session',()=>({refresh:vi.fn().mockResolvedValue(undefined)}));
let wrapper,server;
const body=()=>new DOMWrapper(document.body);
const row=name=>wrapper.findAll('tr').find(r=>r.find('.cell').exists()&&r.find('.cell').text()===name);
const button=(root,name)=>root.findAll('button').find(b=>b.text()===name);
const field=name=>body().findAll('.el-form-item').find(row=>row.find('.el-form-item__label').text()===name);
async function ready(){await nextTick();await flushPromises();await new Promise(r=>setTimeout(r,30));}
async function edit(name){await button(row(name),'编辑').trigger('click');await ready();}
async function mountView(){wrapper=mount(ExternalModelsView,{attachTo:document.body,global:{plugins:[ElementPlus]}});await ready();}
beforeEach(()=>{
 vi.clearAllMocks();server={active_profile_id:'legacy',active_profile_name:'原有配置',profile_revision:2,model:'model-old',base_url:'https://old.example/v1',key_set:true,profiles:[
  {id:'legacy',name:'原有配置',model:'model-old',base_url:'https://old.example/v1',key_set:true,key_masked:'old***'},
  {id:'a',name:'日常写作',model:'model-a',base_url:'https://a.example/v1',key_set:true,key_masked:'aaa***'},
  {id:'b',name:'深度分析',model:'model-b',base_url:'https://b.example/v1',key_set:true,key_masked:'bbb***'},
 ]};
 api.mockImplementation(async(path,data)=>{
  if(path==='ai/config'&&!data)return structuredClone(server);
  if(path==='ai/profiles'){
   if(data.action==='activate'){
    const selected=server.profiles.find(p=>p.id===data.id);server={...server,...selected,active_profile_name:selected.name,active_profile_id:selected.id,profile_revision:server.profile_revision+1};
   }
   return {ok:true};
  }
  if(path==='ai/test')return {ok:true,message:'连接正常',models:['model-c'],ms:20};
  return {ok:true};
 });
});
afterEach(()=>{wrapper?.unmount();wrapper=null;document.body.innerHTML='';});
describe('多个模型配置与启用',()=>{
 it('保留原有配置，列表只标识一个当前启用项',async()=>{
  await mountView();expect(wrapper.findAll('.el-tag').filter(tag=>tag.text()==='当前启用')).toHaveLength(1);
  expect(wrapper.find('.active-model').text()).toContain('model-old');expect(row('日常写作')).toBeTruthy();
 });
 it('点击启用后切换当前模型，使用配置版本防止覆盖',async()=>{
  await mountView();await button(row('深度分析'),'启用').trigger('click');await ready();
  expect(api).toHaveBeenCalledWith('ai/profiles',{action:'activate',id:'b',revision:2});
  expect(wrapper.find('.active-model').text()).toContain('model-b');expect(wrapper.findAll('.el-tag').filter(t=>t.text()==='当前启用')).toHaveLength(1);
  expect(button(row('深度分析'),'删除').attributes('disabled')).toBeDefined();
 });
 it('添加配置读取模型选项，保存不自动启用',async()=>{
  await mountView();await button(wrapper,'添加模型配置').trigger('click');await ready();
  await field('配置名称').find('input').setValue('新模型');await field('接口地址').find('input').setValue('https://new.example/v1');await field('API Key').find('input').setValue('fake-new-key');
  await button(body(),'测试连接').trigger('click');await ready();
  expect(api).toHaveBeenCalledWith('ai/test',{profile_id:'',base_url:'https://new.example/v1',model:'',api_key:'fake-new-key'});
  await field('模型名称').find('.el-select').trigger('click');await ready();
  const option=[...document.querySelectorAll('.el-select-dropdown__item')].find(o=>o.textContent==='model-c');expect(option).toBeTruthy();option.click();await ready();
  await button(body(),'保存配置').trigger('click');await ready();
  expect(api).toHaveBeenCalledWith('ai/profiles',{action:'save',id:'',revision:2,name:'新模型',base_url:'https://new.example/v1',model:'model-c',api_key:'fake-new-key'});
  expect(wrapper.find('.active-model').text()).toContain('model-old');
 });
 it('编辑原接口留空密钥，不把掩码当密钥提交',async()=>{
  await mountView();await edit('日常写作');expect(field('API Key').find('input').element.value).toBe('');
  await field('配置名称').find('input').setValue('写作备用');await button(body(),'保存配置').trigger('click');await ready();
  expect(api).toHaveBeenCalledWith('ai/profiles',{action:'save',id:'a',revision:2,name:'写作备用',base_url:'https://a.example/v1',model:'model-a'});
 });
 it('改接口地址后必须重新填写密钥',async()=>{
  await mountView();await edit('日常写作');await field('接口地址').find('input').setValue('https://other.example/v1');await button(body(),'保存配置').trigger('click');await ready();
  expect(api.mock.calls.filter(([path])=>path==='ai/profiles')).toHaveLength(0);
 });
 it('测试另一个配置不会自动启用它或修改原有配置',async()=>{
  await mountView();await button(row('深度分析'),'测试').trigger('click');await ready();
  expect(api).toHaveBeenCalledWith('ai/test',{profile_id:'b',base_url:'https://b.example/v1',model:'model-b'});
  expect(api.mock.calls.filter(([path])=>path==='ai/profiles')).toHaveLength(0);
  expect(wrapper.find('.active-model').text()).toContain('model-old');
 });
 it('保存冲突或失败保留用户填写的草稿',async()=>{
  await mountView();await edit('日常写作');await field('配置名称').find('input').setValue('未保存草稿');
  api.mockRejectedValueOnce(new Error('配置已更新'));await button(body(),'保存配置').trigger('click');await ready();
  expect(field('配置名称').find('input').element.value).toBe('未保存草稿');
 });
});

describe('外部模型管理体验',()=>{
 it('按名称或模型搜索配置',async()=>{
  await mountView();await wrapper.find('input[aria-label="搜索模型配置"]').setValue('model-b');await ready();
  expect(row('深度分析')).toBeTruthy();expect(row('日常写作')).toBeUndefined();
 });
 it('复制配置保留接口和模型，要求重新填密钥',async()=>{
  await mountView();await button(row('日常写作'),'复制').trigger('click');await ready();
  expect(field('配置名称').find('input').element.value).toBe('日常写作 副本');
  expect(field('接口地址').find('input').element.value).toBe('https://a.example/v1');
  expect(field('API Key').find('input').element.value).toBe('');
  await button(body(),'保存配置').trigger('click');await ready();
  expect(api.mock.calls.filter(([path])=>path==='ai/profiles')).toHaveLength(0);
 });
 it('测试失败在对应行显示余额处理提示',async()=>{
  await mountView();api.mockRejectedValueOnce(new Error('429 credit_balance_exhausted'));
  await button(row('深度分析'),'测试').trigger('click');await ready();
  expect(row('深度分析').text()).toContain('API 余额或额度不足');expect(row('日常写作').text()).toContain('未测试');
 });
});
