import {beforeEach,afterEach,it,expect,vi} from 'vitest';
import {mount,flushPromises,DOMWrapper} from '@vue/test-utils';
import {nextTick} from 'vue';
import ElementPlus from 'element-plus';
import AiReportGenerator from '../src/components/AiReportGenerator.vue';
import {api} from '../src/api';
import {user} from '../src/store/session';
vi.mock('../src/api',()=>({api:vi.fn()}));
vi.mock('../src/store/session',async()=>{const {ref}=await import('vue');return {user:ref({id:1,role:'researcher'}),library:ref([]),members:ref([{id:1,name:'发起人'},{id:2,name:'协作者'}])};});
let wrapper, latest, current;
const body=()=>new DOMWrapper(document.body);
const button=(root,name)=>root.findAll('button').find(x=>x.text()===name);
const field=name=>body().findAll('.el-form-item').find(x=>x.find('.el-form-item__label').text()===name);
const skill={id:'daily-research',name:'日度研报',description:'使用真实数据写作',enabled:true,builtin:true,version:'v1',markdown:'---\nname: daily-research\ndescription: 数据写作\n---\n# 数据优先'};
const evidence={words:['铜'],data:[{id:'D1',source:'测试源',indicator:'铜现货价',date:'2026-11-18',value:100,unit:'元/吨'}],materials:[],warnings:[],as_of:'2026-11-18'};
const done={id:'j1',status:'已完成',result:{completed:1,total:1,stage:'候选已生成',skills:[skill],sections:[{id:'s1',title:'市场',body:'模拟候选正文[D1]',evidence,warnings:[]}]}};
const report={id:2,title:'铜日报',author:1,version:3,metadata:JSON.stringify({collaboration:'personal'}),document:JSON.stringify({sections:[{id:'s1',title:'市场',state:'未提交',editors:[1]},{id:'s2',title:'风险',state:'已提交',editors:[1]}]})};
async function ready(){await nextTick();await flushPromises();await new Promise(r=>setTimeout(r,35));}
async function start(props={}){wrapper=mount(AiReportGenerator,{attachTo:document.body,props:{modelValue:true,report,...props},global:{plugins:[ElementPlus]}});await ready();}
beforeEach(()=>{
 vi.clearAllMocks();user.value={id:1,role:'researcher'};latest=null;current=structuredClone(done);
 api.mockImplementation(async(path,data)=>{
  if(path==='report-ai/skills'&&!data)return {revision:7,skills:[skill]};
  if(path==='report-ai/reports/2/latest')return {job:latest};
  if(path==='report-ai/preview')return {model:{model:'模拟模型',base_url:'https://example.invalid/v1'},sections:[{id:'s1',title:'市场',evidence}],skills:[skill]};
  if(path==='report-ai/jobs')return {id:'j1'};
  if(path==='report-ai/jobs/j1')return current;
  if(path==='report-ai/jobs/j1/cancel'){current={...done,status:'已取消'};return {ok:true};}
  return {ok:true,version:4};
 });
});
afterEach(()=>{wrapper?.unmount();document.body.innerHTML='';});
it('检查依据和 Skill 不会发起生成，也不保存研报',async()=>{
 await start();await button(body(),'检查研究依据').trigger('click');await ready();
 expect(api).toHaveBeenCalledWith('report-ai/preview',expect.objectContaining({report_id:2,version:3,skill_ids:['daily-research'],section_ids:['s1']}));
 expect(api.mock.calls.some(([p])=>p==='report-ai/jobs')).toBe(false);
});
it('生成候选后必须核对才能保存，默认追加不覆盖文字',async()=>{
 await start();expect(button(body(),'生成所选章节候选').attributes('disabled')).toBeDefined();await button(body(),'检查研究依据').trigger('click');await ready();await button(body(),'生成所选章节候选').trigger('click');await ready();
 expect(body().text()).toContain('候选已生成');expect(api.mock.calls.some(([p])=>p.endsWith('/apply'))).toBe(false);
 const save=button(body(),'确认保存到当前研报');expect(save.attributes('disabled')).toBeDefined();
 const review=body().findAll('.el-checkbox').find(x=>x.text()==='已逐章核对内容、数字与引用来源');await review.find('input').setValue(true);await ready();
 await save.trigger('click');await ready();
 expect(api).toHaveBeenCalledWith('report-ai/jobs/j1/apply',{version:3,reviewed:true,mode:'append'});
 expect(wrapper.emitted('saved')).toHaveLength(1);
});
it('保存版本冲突时保留生成的候选',async()=>{
 latest=structuredClone(done);await start();
 const review=body().findAll('.el-checkbox').find(x=>x.text()==='已逐章核对内容、数字与引用来源');await review.find('input').setValue(true);await ready();
 api.mockRejectedValueOnce(new Error('报告在生成后已被修改'));await button(body(),'确认保存到当前研报').trigger('click');await ready();
 expect(body().text()).toContain('报告在生成后已被修改');expect(wrapper.emitted('saved')).toBeUndefined();
 expect(body().find('textarea').element.value).toContain('模拟候选正文');
});
it('重新打开可看到未完成任务，并可以取消',async()=>{
 latest={...done,status:'运行中',result:{...done.result,completed:0,sections:[]}};current=structuredClone(latest);await start();
 expect(button(body(),'生成所选章节候选').attributes('disabled')).toBeDefined();
 await button(body(),'取消任务').trigger('click');await ready();expect(body().text()).toContain('已取消');
 expect(api).toHaveBeenCalledWith('report-ai/jobs/j1/cancel',{});
});
it('余额不足解释 API 计费，不伪装为生成成功',async()=>{
 latest={...done,status:'失败',error:'429 credit_balance_exhausted'};await start();
 expect(body().text()).toContain('模型 API 余额或额度不足');expect(button(body(),'确认保存到当前研报')).toBeUndefined();
});
it('编辑器只查看和选择 Skill，管理员可打开独立管理页',async()=>{
 user.value={id:1,role:'admin'};await start();
 await body().findAll('[role=tab]').find(x=>x.text()==='Skill 库').trigger('click');await ready();
 expect(body().find('a[href="/system/skills"]').exists()).toBe(true);
 expect(button(body(),'新增 Skill')).toBeUndefined();
 expect(button(body(),'复制')).toBeUndefined();
});

const sharedReport={...report,metadata:JSON.stringify({collaboration:'shared',collaborators:[2]}),document:JSON.stringify({sections:[{id:'s1',title:'市场',state:'未提交',editors:[2]},{id:'s2',title:'风险',state:'未提交',editors:[1]}]})};
it('多人发起人可选择他人章节生成，候选由对应负责人确认',async()=>{
 latest={...structuredClone(done),shared:true,initiator:'负责人',result:{...structuredClone(done.result),sections:[{...structuredClone(done.result.sections[0]),editors:['协作者'],can_apply:false}]}};
 const candidate=latest;latest=null;await start({report:sharedReport});
 await button(body(),'检查研究依据').trigger('click');await ready();
 expect(api).toHaveBeenCalledWith('report-ai/preview',expect.objectContaining({section_ids:['s1','s2']}));
 latest=candidate;await wrapper.setProps({modelValue:false});await ready();await wrapper.setProps({modelValue:true});await ready();
 expect(body().text()).toContain('待负责人确认');expect(button(body(),'采用本章候选')).toBeUndefined();expect(button(body(),'确认保存到当前研报')).toBeUndefined();
});
it('协作者只生成本人章节并逐章采用，共享任务保留其他章节状态',async()=>{
 user.value={id:2,role:'researcher'};
 latest={...structuredClone(done),shared:true,initiator:'发起人',result:{...structuredClone(done.result),sections:[{...structuredClone(done.result.sections[0]),editors:['我'],can_apply:true}]}};
 current={...structuredClone(latest),status:'部分采用',result:{...structuredClone(latest.result),reviews:{s1:{decision:'apply',name:'我',at:'2026-11-26'}},sections:[{...structuredClone(latest.result.sections[0]),can_apply:false,review:{decision:'apply',name:'我',at:'2026-11-26'}}]}};
 await start({report:sharedReport});expect(button(body(),'检查研究依据').attributes('disabled')).toBeDefined();
 await body().find('.el-collapse-item__header').trigger('click');await ready();
 const save=button(body(),'采用本章候选');expect(save.attributes('disabled')).toBeDefined();
 const checkbox=body().findAll('.el-checkbox').find(x=>x.text()==='已核对本章内容、数字与引用来源');await checkbox.find('input').setValue(true);await ready();
 await save.trigger('click');await ready();expect(api).toHaveBeenCalledWith('report-ai/jobs/j1/apply',{version:3,reviewed:true,mode:'append',section_ids:['s1'],decision:'apply'});
 expect(body().text()).toContain('部分采用');expect(wrapper.emitted('saved')).toHaveLength(1);
});
it('协作者不能取消他人的任务',async()=>{
 latest={...structuredClone(done),status:'运行中',shared:true,can_cancel:false};await start({report:sharedReport});expect(button(body(),'取消任务')).toBeUndefined();
});

it('已有待确认候选不再默认重复生成，并显示负责人',async()=>{
 latest={...structuredClone(done),shared:true,initiator:'发起人',result:{...structuredClone(done.result),sections:[{...structuredClone(done.result.sections[0]),editors:['协作者'],can_apply:false}]}};
 await start({report:sharedReport});
 expect(body().find('.chapter-plan-table').text()).toContain('协作者');expect(body().text()).toContain('候选待处理');
 await button(body(),'检查研究依据').trigger('click');await ready();expect(api).toHaveBeenCalledWith('report-ai/preview',expect.objectContaining({section_ids:['s2']}));
});
it('失败任务只重试未完成章节，保留已成功的候选',async()=>{
 latest={...structuredClone(done),status:'失败',can_retry:true,error:'另一章生成失败',result:{...structuredClone(done.result),total:2,errors:[{id:'s2',title:'风险',error:'接口暂时异常'}]}};
 current=structuredClone(done);await start();expect(body().find('textarea').element.value).toContain('模拟候选正文');
 await button(body(),'重试未完成章节').trigger('click');await ready();expect(api).toHaveBeenCalledWith('report-ai/jobs/j1/retry',{});expect(body().text()).toContain('候选已生成');
});
