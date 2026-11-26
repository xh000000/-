import {afterEach,beforeEach,it,expect,vi} from 'vitest';
import {mount,flushPromises,DOMWrapper} from '@vue/test-utils';
import {nextTick} from 'vue';
import ElementPlus from 'element-plus';
import ChapterAssignments from '../src/components/ChapterAssignments.vue';
import {api} from '../src/api';
vi.mock('../src/api',()=>({api:vi.fn()}));
vi.mock('../src/store/session',()=>({memberName:id=>({1:'发起人',2:'研究员甲'})[id]}));
let w;
const report={id:9,author:1,version:4,metadata:JSON.stringify({collaboration:'shared',collaborators:[2]}),document:JSON.stringify({sections:[{id:'s1',title:'铜',state:'未提交',editors:[1]},{id:'s2',title:'铝',state:'未提交',editors:[1]},{id:'s3',title:'风险',state:'已提交',editors:[1]}]})};
const body=()=>new DOMWrapper(document.body);
const button=name=>body().findAll('button').find(b=>b.text()===name);
async function ready(){await nextTick();await flushPromises();await new Promise(r=>setTimeout(r,35));}
async function setup(){w=mount(ChapterAssignments,{attachTo:document.body,props:{modelValue:true,report},global:{plugins:[ElementPlus]}});await ready();}
async function batch(){await body().find('.el-table__header-wrapper input[type=checkbox]').setValue(true);await body().find('.assignment-toolbar .el-select').trigger('click');await ready();const option=[...document.querySelectorAll('.el-select-dropdown__item')].find(x=>x.textContent==='研究员甲');option.click();await ready();await button('应用到选中章节').trigger('click');await ready();}
beforeEach(()=>{vi.clearAllMocks();api.mockResolvedValue({ok:true,version:5});});
afterEach(()=>{w?.unmount();document.body.innerHTML='';});
it('批量分配仅影响未提交章节，一次保存且不修改父组件数据',async()=>{
 await setup();expect(button('保存分工').attributes('disabled')).toBeDefined();await batch();expect(body().text()).toContain('2 章分工待保存');
 await button('保存分工').trigger('click');await ready();expect(api).toHaveBeenCalledWith('chapters',{id:9,version:4,action:'assign',assignments:[{section_id:'s1',editors:[2]},{section_id:'s2',editors:[2]}]});
 expect(w.emitted('saved')).toHaveLength(1);expect(JSON.parse(report.document).sections[0].editors).toEqual([1]);
});
it('版本冲突保留本次分工，取消不发送任何请求',async()=>{
 await setup();await batch();api.mockRejectedValueOnce(new Error('结构版本已更新，请刷新'));
 await button('保存分工').trigger('click');await ready();expect(body().text()).toContain('结构版本已更新');expect(body().text()).toContain('2 章分工待保存');expect(w.emitted('saved')).toBeUndefined();
 vi.clearAllMocks();await button('取消').trigger('click');expect(api).not.toHaveBeenCalled();
});
