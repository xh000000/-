import {afterEach,it,expect,vi} from 'vitest';
import {mount,flushPromises,DOMWrapper} from '@vue/test-utils';
import ElementPlus from 'element-plus';
import ViewpointsView from '../src/views/ViewpointsView.vue';
import {api} from '../src/api';
vi.mock('vue-router',()=>({useRouter:()=>({push:vi.fn()})}));
vi.mock('../src/api',()=>({api:vi.fn()}));
vi.mock('../src/store/session',async()=>{const {ref}=await import('vue');return {user:ref({id:1,role:'researcher'}),commodities:ref([{name:'铜',code:'CU',enabled:1}])};});
let wrapper;
afterEach(()=>{wrapper?.unmount();document.body.innerHTML='';vi.clearAllMocks();});
async function start(){
 api.mockImplementation(async p=>p.startsWith('viewpoints/candidates')?{items:[{id:99,report_id:8,report_title:'铜研报',published_date:'2026-11-25',author_name:'本人',commodity:'铜',direction:'看多',horizon_days:5,excerpt:'铜未来5天看多',reason:'核对原文',status:'待确认',can_confirm:true}]}:p==='viewpoints/rules'?{revision:1,items:[{commodity:'铜',horizon_days:5,threshold:2}]}:p==='viewpoints'?{items:Array.from({length:12},(_,i)=>({id:i+1,user_id:i===0?1:2,user_name:i===0?'本人':'同事',commodity:'铜',direction:'看多',status:i===1?'已结算':'在途',outcome:i===1?'无法结算':'',expire_date:'2020-01-01',horizon_days:5,basis:'完整观点依据'+i,benchmark_price:0,note:'缺少价格数据'}))}:{overall:{pending:11,settled:1}});
 wrapper=mount(ViewpointsView,{attachTo:document.body,global:{plugins:[ElementPlus]}});await flushPromises();await new Promise(r=>setTimeout(r,40));
}
it('列表分页并支持只看本人观点',async()=>{
 await start();await wrapper.findAll('[role=tab]').find(x=>x.text()==='跟踪中').trigger('click');await flushPromises();expect(wrapper.findAll('.el-table__body-wrapper tbody tr').length).toBeGreaterThanOrEqual(10);
 const mine=wrapper.findAll('.el-radio-button').find(x=>x.text()==='我的观点');await mine.find('input').setValue(true);await flushPromises();
 expect(wrapper.findAll('.vp-list-heading')[1].text()).toContain('1 条');
});
it('详情展示完整依据和取价说明，零值正常展示',async()=>{
 await start();await wrapper.findAll('button').find(x=>x.text()==='详情').trigger('click');await flushPromises();
 const body=new DOMWrapper(document.body);const drawer=body.find('.el-drawer');
 expect(drawer.text()).toContain('完整观点依据0');expect(drawer.text()).toContain('缺少价格数据');expect(drawer.text()).toContain('旧记录未锁定');
});
it('无法结算记录不会显示待结算，搜索包含品种',async()=>{
 await start();await wrapper.findAll('[role=tab]').find(x=>x.text()==='复盘结果').trigger('click');await flushPromises();expect(wrapper.findAll('.vp-records')[1].text()).toContain('无可用价格');
 await wrapper.find('input[aria-label="搜索观点"]').setValue('不存在');await flushPromises();
 expect(wrapper.findAll('.vp-records')[1].text()).toContain('没有符合筛选条件');
});

it('候选原文确认后才调用跟踪接口，不提交价格',async()=>{
 await start();expect(wrapper.text()).not.toContain('could not be cloned');expect(wrapper.text()).toContain('铜未来5天看多');
 await wrapper.findAll('button').find(b=>b.text()==='编辑确认').trigger('click');await flushPromises();
 const body=new DOMWrapper(document.body);const dialog=body.findAll('.el-dialog').find(x=>x.text().includes('确认研报观点'));
 const submit=dialog.findAll('button').find(b=>b.text()==='确认并开始跟踪');expect(submit.attributes('disabled')).toBeDefined();
 await dialog.find('.el-checkbox input').setValue(true);await flushPromises();
 await submit.trigger('click');await flushPromises();
 expect(api).toHaveBeenCalledWith('viewpoints/confirm',{items:[{id:99,basis:'铜未来5天看多',direction:'看多',horizon_days:5,reviewed:true,condition_confirmed:false}]});
});
it('确认失败保留候选和原文，便于补齐价格后重试',async()=>{
 await start();await wrapper.findAll('button').find(b=>b.text()==='编辑确认').trigger('click');await flushPromises();
 const dialog=new DOMWrapper(document.body).findAll('.el-dialog').find(x=>x.text().includes('确认研报观点'));
 await dialog.find('.el-checkbox input').setValue(true);await flushPromises();api.mockRejectedValueOnce(new Error('发布日前无价格'));
 await dialog.findAll('button').find(b=>b.text()==='确认并开始跟踪').trigger('click');await flushPromises();
 expect(dialog.text()).toContain('铜未来5天看多');expect(wrapper.text()).toContain('候选观点');
});

it('提取明确提交日期范围，普通读取只筛选候选列表',async()=>{
 await start();expect(api.mock.calls.some(([p])=>p==='viewpoints/extract')).toBe(false);
 const query=api.mock.calls.find(([p])=>p.startsWith('viewpoints/candidates'))[0];const params=new URLSearchParams(query.split('?')[1]);
 api.mockResolvedValueOnce({added:2});await wrapper.findAll('button').find(b=>b.text()==='提取研报观点').trigger('click');await flushPromises();
 expect(api).toHaveBeenCalledWith('viewpoints/extract',{start_date:params.get('start_date'),end_date:params.get('end_date')});
});

it('观点说明可手工编辑，提交时保留原文并只发送编辑字段',async()=>{
 await start();await wrapper.findAll('button').find(b=>b.text()==='编辑确认').trigger('click');await flushPromises();
 const dialog=new DOMWrapper(document.body).findAll('.el-dialog').find(x=>x.text().includes('确认研报观点'));
 await dialog.find('textarea').setValue('人工修订：需求风险需要继续核实');await dialog.find('.el-checkbox input').setValue(true);
 await dialog.findAll('button').find(b=>b.text()==='确认并开始跟踪').trigger('click');await flushPromises();
 expect(api).toHaveBeenCalledWith('viewpoints/confirm',expect.objectContaining({items:[expect.objectContaining({basis:'人工修订：需求风险需要继续核实'})]}));
});
it('AI 提取使用后台任务并沿用日期范围',async()=>{
 await start();await wrapper.find('.vp-extract-actions .el-select').trigger('click');await flushPromises();[...document.querySelectorAll('.el-select-dropdown__item')].find(x=>x.textContent==='AI 提取').click();await flushPromises();
 api.mockResolvedValueOnce({task_id:'ai-task'});await wrapper.findAll('button').find(b=>b.text()==='提取研报观点').trigger('click');await flushPromises();
 expect(api).toHaveBeenCalledWith('viewpoints/extract',expect.objectContaining({method:'ai',start_date:expect.any(String),end_date:expect.any(String)}));
});

it('状态由标签页区分，品种不再重复打开详情，批量操作按需显示',async()=>{
 await start();expect(wrapper.findAll('button').some(x=>x.text()==='批量确认')).toBe(false);
 expect(wrapper.findAll('.el-select').some(x=>x.text().includes('全部状态'))).toBe(false);
 await wrapper.findAll('[role=tab]').find(x=>x.text()==='复盘结果').trigger('click');await flushPromises();
 expect(wrapper.findAll('.el-radio-button').some(x=>x.text()==='到期待结算')).toBe(false);
 expect(wrapper.findAll('button').some(x=>x.text()==='铜')).toBe(false);
});
