import {afterEach,beforeEach,it,expect,vi} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import AgentChatView from '../src/views/AgentChatView.vue';
import {api} from '../src/api';
import {user} from '../src/store/session';
const {push}=vi.hoisted(()=>({push:vi.fn()}));
vi.mock('vue-router',()=>({useRouter:()=>({push})}));
vi.mock('../src/store/session',async()=>{const {ref}=await import('vue');return {user:ref({name:'研究员',role:'researcher'})};});
vi.mock('../src/api',()=>({api:vi.fn(),del:vi.fn()}));
let w;
const mountPage=async()=>{w=mount(AgentChatView,{global:{stubs:{PageHead:{template:'<header><slot/></header>'},NewReportDialog:{props:['modelValue','aiMode'],emits:['created'],template:'<div class="create-dialog" :data-open="modelValue" />'},'el-button':{template:'<button @click="$emit(\'click\')"><slot/></button>'},'el-tag':{template:'<span><slot/></span>'},'el-alert':true,'el-input':true,'el-icon':true,'el-drawer':{template:'<aside><slot/></aside>'}}}});await flushPromises();};
beforeEach(()=>{vi.clearAllMocks();user.value={name:'研究员',role:'researcher'};api.mockImplementation(async path=>path==='report-ai/recent-jobs'?{jobs:[{id:'j1',report_id:7,title:'铜日报',status:'已完成',editable:true,result:{completed:2,total:2}}]}:path==='agent/status'?{configured:true}:{threads:[]});});
afterEach(()=>w?.unmount());
it('复用分类创建和编辑器 Skill 生成，不调用旧流水线',async()=>{
 await mountPage();expect(w.text()).toContain('候选待确认');expect(w.find('header').text()).not.toContain('AI 生成研报');expect(w.find('.agent-report-entry').text()).toContain('AI 生成研报');
 await w.findAll('button').find(b=>b.text().includes('AI 生成研报')).trigger('click');
 expect(w.find('.create-dialog').attributes('data-open')).toBe('true');
 w.findComponent('.create-dialog').vm.$emit('created',9,{writingMode:'ai',collaboration:'personal'});await flushPromises();
 expect(push).toHaveBeenCalledWith({name:'editor',params:{id:9},query:{ai:'1'}});
 await w.findAll('button').find(b=>b.text()==='查看候选').trigger('click');
 expect(push).toHaveBeenCalledWith({name:'editor',params:{id:7},query:{ai:'1'}});
 expect(api.mock.calls.some(([p])=>p==='agent/pipeline/run')).toBe(false);
});
it('审批角色不显示生成入口或请求生成任务',async()=>{
 user.value.role='reviewer';await mountPage();expect(w.text()).not.toContain('AI 生成研报');expect(api).not.toHaveBeenCalledWith('report-ai/recent-jobs');
});

it('新建跳转统一遵守手工、AI 和多人分工选项',async()=>{
 const {createdReportRoute}=await import('../src/utils/reportCreation');
 expect(createdReportRoute(3,{writingMode:'manual',collaboration:'shared'}).query).toEqual({});
 expect(createdReportRoute(3,{writingMode:'ai',collaboration:'shared'}).query).toEqual({ai:'setup'});
 expect(createdReportRoute(3,{writingMode:'ai',collaboration:'shared',assignmentsReady:true}).query).toEqual({ai:'1'});
 expect(createdReportRoute(3,{writingMode:'ai',collaboration:'personal'}).query).toEqual({ai:'1'});
});
