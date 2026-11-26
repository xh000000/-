import {afterEach,beforeEach,describe,it,expect,vi} from 'vitest';
import {mount,flushPromises,DOMWrapper} from '@vue/test-utils';
import {nextTick} from 'vue';
import ElementPlus from 'element-plus';
import NewReportDialog from '../src/components/NewReportDialog.vue';
import {api} from '../src/api';
import * as store from '../src/store/session';

vi.mock('../src/api',()=>({api:vi.fn()}));
vi.mock('../src/store/session',async()=>{
 const {ref}=await import('vue');
 return {authors:ref([]),categories:ref([]),categoryTree:ref([]),commodities:ref([]),members:ref([]),reports:ref([]),user:ref({id:1}),refresh:vi.fn().mockResolvedValue(undefined)};
});
let wrapper;
const cfg=(kind,pattern)=>({kind,title_pattern:pattern,commodities:['铜'],sections:[{id:'one',title:'研究观点',group:'市场展望',commodity_ids:[2]}]});
async function ready(){await nextTick();await flushPromises();await new Promise(r=>setTimeout(r,30));}
const dom=()=>new DOMWrapper(document.body);
function row(label){return dom().findAll('.el-form-item').find(r=>r.find('.el-form-item__label').text()===label);}
async function input(label,value){await row(label).find('input,textarea').setValue(value);await ready();}
async function radio(value){await dom().find(`input[type="radio"][value="${value}"]`).setValue(true);await ready();}
async function click(label){const button=dom().findAll('button').find(b=>b.text()===label);expect(button,`missing button ${label}`).toBeTruthy();await button.trigger('click');await ready();}
async function select(label,choice){await row(label).find('.el-select').trigger('click');await ready();const options=[...document.querySelectorAll('.el-select-dropdown__item')];const option=options.find(o=>o.textContent.includes(choice));expect(option,`missing ${choice}`).toBeTruthy();option.click();await ready();}
beforeEach(async()=>{
 vi.clearAllMocks();api.mockResolvedValue({id:99});
 store.categories.value=[{id:1,name:'商品 / 日报',config:cfg('日报','{品种}{类型}｜{日期点分}')},{id:2,name:'商品 / 周报',config:cfg('周报','{品种}{类型}｜{日期}')}];
 store.categoryTree.value=[{id:1,folder:false,effective_enabled:true},{id:2,folder:false,effective_enabled:true}];
 store.authors.value=[{id:10,name:'日报作者',enabled:1,types:'["日报"]'},{id:11,name:'周报作者',enabled:1,types:'["周报"]'},{id:12,name:'停用作者',enabled:0,types:'["日报"]'}];
 store.commodities.value=[{id:1,name:'有色',enabled:1},{id:2,name:'铜',code:'CU',parent_id:1,enabled:1}];
 store.members.value=[{id:1,name:'本人',role:'admin',enabled:1},{id:2,name:'协作研究员',role:'researcher',enabled:1},{id:3,name:'停用研究员',role:'researcher',enabled:0},{id:4,name:'复核员',role:'reviewer',enabled:1}];
 store.reports.value=[{id:20,title:'已发布日报',category_id:1,document:'{}',status:'已发布',version:2,updated:'2026-11-18'},{id:21,title:'草稿日报',category_id:1,document:'{}',status:'草稿',version:1}];
 wrapper=mount(NewReportDialog,{attachTo:document.body,props:{modelValue:false,'onUpdate:modelValue':v=>wrapper.setProps({modelValue:v})},global:{plugins:[ElementPlus]}});
 await wrapper.setProps({modelValue:true});await ready();
});
afterEach(()=>{wrapper?.unmount();document.body.innerHTML='';});

describe('添加研报组件交互',()=>{
 it('默认分类、作者、品种、标题和章节预览正确',()=>{
  expect(row('报告标题').find('input').element.value).toContain('铜日报');
  expect(dom().find('.template-preview').text()).toContain('CU');
  expect(dom().find('.template-preview').text()).toContain('研究观点');
  expect(row('署名作者').text()).not.toContain('停用作者');
 });
 it('取消不提交，重开重置表单',async()=>{
  await input('报告标题','不应提交');await click('取消');expect(api).not.toHaveBeenCalled();
  await wrapper.setProps({modelValue:true});await ready();expect(row('报告标题').find('input').element.value).toContain('铜日报');
 });
 it.each(['flow','grid','free'])('布局 %s 正确提交并跳转',async(layout)=>{
  await radio(layout);await input('报告标题','自定义研报标题');await input('报告摘要','摘要内容');await click('确定并进入编辑器');
  expect(api).toHaveBeenCalledWith('reports',expect.objectContaining({manual:true,title:'自定义研报标题',summary:'摘要内容',byline_id:10,commodity:'铜',layout,collaboration:'personal',public:true,inherit_id:null}));
  expect(wrapper.emitted('created')?.[0]).toEqual([99,{writingMode:'manual',collaboration:'personal'}]);expect(store.refresh).toHaveBeenCalled();
 });
 it('空标题和日期均阻止提交',async()=>{
  await input('报告标题','');await click('确定并进入编辑器');expect(api).not.toHaveBeenCalled();
  await input('报告标题','日期校验');await input('创建日期','');await row('创建日期').find('input').trigger('blur');await ready();await click('确定并进入编辑器');expect(api).not.toHaveBeenCalled();
 });
 it('多人协作必须选人，且只提供有效账号',async()=>{
  await radio('shared');await click('确定并进入编辑器');expect(api).not.toHaveBeenCalled();
  await row('协作人').find('.el-select').trigger('click');await ready();
  const text=[...document.querySelectorAll('.el-select-dropdown__item')].map(e=>e.textContent).join('|');
  expect(text).toContain('协作研究员');expect(text).not.toContain('停用研究员');expect(text).not.toContain('复核员');
  await select('协作人','协作研究员');await click('确定并进入编辑器');
  expect(api).toHaveBeenCalledWith('reports',expect.objectContaining({collaboration:'shared',collaborators:[2]}));
 });
 it('切换分类会同步作者、标题与继承选项',async()=>{
  await select('报告分类','周报');expect(row('报告标题').find('input').element.value).toContain('铜周报');
  await click('确定并进入编辑器');expect(api).toHaveBeenCalledWith('reports',expect.objectContaining({category_id:2,byline_id:11}));
 });
 it('继承只选择同分类的已发布报告；不存在时阻止提交',async()=>{
  await radio('inherit');await click('确定并进入编辑器');expect(api).toHaveBeenCalledWith('reports',expect.objectContaining({inherit_id:20}));
 });
 it('没有可继承报告时不能提交',async()=>{
  store.reports.value=[];await radio('inherit');await click('确定并进入编辑器');expect(api).not.toHaveBeenCalled();
 });
 it.each(['author','commodity','category'])('缺少 %s 时不能创建',async(kind)=>{
  await wrapper.setProps({modelValue:false});await ready();
  if(kind==='author')store.authors.value=[];
  if(kind==='commodity')store.commodities.value[0].enabled=0;
  if(kind==='category')store.categoryTree.value=[];
  await wrapper.setProps({modelValue:true});await ready();await click('确定并进入编辑器');expect(api).not.toHaveBeenCalled();
 });
 it('私有报告选项正确提交',async()=>{
  await radio('false');await click('确定并进入编辑器');expect(api).toHaveBeenCalledWith('reports',expect.objectContaining({public:false}));
 });
 it('改日期会更新标题并正确提交',async()=>{
  const dateInput=row('创建日期').find('input');dateInput.element.focus();await dateInput.trigger('click');await ready();
  const day=[...document.querySelectorAll('.el-date-table td.available')].find(cell=>cell.textContent.trim()==='20');
  expect(day).toBeTruthy();day.click();await ready();
  expect(row('报告标题').find('input').element.value).toContain('2026.11.20');
  await click('确定并进入编辑器');expect(api).toHaveBeenCalledWith('reports',expect.objectContaining({report_date:'2026-11-20'}));
 });
 it('保存中重复点击只创建一次',async()=>{
  let finish;api.mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
  await click('确定并进入编辑器');await click('确定并进入编辑器');expect(api).toHaveBeenCalledTimes(1);
  finish({id:99});await ready();expect(wrapper.emitted('created')).toHaveLength(1);
 });
 it('继承章节预览使用原报告快照',async()=>{
  store.reports.value[0].config_snapshot=JSON.stringify({sections:[{id:'historic',title:'历史模板章节'}]});
  await radio('inherit');expect(dom().find('.template-preview').text()).toContain('历史模板章节');
 });
 it('后台失败保留窗口与草稿，允许重试',async()=>{
  api.mockRejectedValueOnce(new Error('测试网络错误'));await input('报告标题','保留草稿');await click('确定并进入编辑器');
  expect(wrapper.emitted('created')).toBeUndefined();expect(row('报告标题').find('input').element.value).toBe('保留草稿');
  await click('确定并进入编辑器');expect(api).toHaveBeenCalledTimes(2);expect(wrapper.emitted('created')?.[0]).toEqual([99,{writingMode:'manual',collaboration:'personal'}]);
 });
});

it('AI 辅助多人模式说明先分工，并将所选写作方式交给入口跳转',async()=>{
 await radio('ai');await radio('shared');await select('协作人','协作研究员');
 expect(row('写作方式').text()).toContain('分配章节负责人');
 await click('确定并进入编辑器');
 expect(wrapper.emitted('created')[0]).toEqual([99,{writingMode:'ai',collaboration:'shared',assignmentsReady:true}]);
});
it('AI 快捷入口默认 AI 辅助，仍可切回手工编写',async()=>{
 await wrapper.setProps({modelValue:false,aiMode:true});await ready();await wrapper.setProps({modelValue:true});await ready();
 expect(row('写作方式').find('input[value="ai"]').element.checked).toBe(true);
 await radio('manual');await click('确定并进入编辑器');expect(wrapper.emitted('created')[0][1].writingMode).toBe('manual');
});
it('新建弹窗按组展示章节，并将统一分工与研报一起提交',async()=>{
 await radio('shared');await select('协作人','协作研究员');
 expect(dom().find('.creation-outline').text()).toContain('市场展望');
 await dom().find('.creation-batch .el-select').trigger('click');await ready();
 [...document.querySelectorAll('.el-select-dropdown__item')].find(x=>x.textContent==='协作研究员').click();await ready();
 await click('应用全部章节');await click('确定并进入编辑器');
 expect(api).toHaveBeenCalledWith('reports',expect.objectContaining({section_assignments:[{section_id:'one',editors:[2]}]}));
});
it('切换分类会重置章节分工，避免复用另一个模板的分配',async()=>{
 await radio('shared');await select('协作人','协作研究员');await dom().find('.creation-batch .el-select').trigger('click');await ready();
 [...document.querySelectorAll('.el-select-dropdown__item')].find(x=>x.textContent==='协作研究员').click();await ready();await click('应用全部章节');
 await select('报告分类','周报');await click('确定并进入编辑器');
 expect(api).toHaveBeenCalledWith('reports',expect.objectContaining({section_assignments:[{section_id:'one',editors:[1]}]}));
});
