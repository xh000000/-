import {beforeEach,afterEach,describe,it,expect,vi} from 'vitest';
import {mount,flushPromises,DOMWrapper} from '@vue/test-utils';
import {nextTick} from 'vue';
import ElementPlus from 'element-plus';
import ReportEditorView from '../src/views/ReportEditorView.vue';
import ReportBlock from '../src/components/ReportBlock.vue';
import {api} from '../src/api';
import {reports,indicators} from '../src/store/session';
vi.mock('vue-router',()=>({useRoute:()=>({params:{id:'1'}}),useRouter:()=>({push:vi.fn()}),onBeforeRouteLeave:vi.fn()}));
vi.mock('../src/api',()=>({api:vi.fn(),fileUrl:id=>'/file/'+id,printUrl:id=>'/print/'+id}));
vi.mock('../src/store/session',async()=>{
 const {ref}=await import('vue');const reports=ref([]);
 return {reports,reportById:id=>reports.value.find(r=>r.id===Number(id)),user:ref({id:1,role:'researcher'}),
  authors:ref([]),commodities:ref([]),library:ref([]),indicators:ref([]),memberName:()=> '研究员',refresh:vi.fn().mockResolvedValue(undefined)};
});
let wrapper;
const points=[{date:'2026-11-17',value:10,unit:'元/吨'},{date:'2026-11-18',value:12,unit:'元/吨'}];
async function ready(){await nextTick();await flushPromises();await new Promise(r=>setTimeout(r,30));}
const body=()=>new DOMWrapper(document.body);
const button=(root,name)=>root.findAll('button').find(b=>b.text()===name);
function report(layout){return {id:1,author:1,title:'图表插入测试',version:1,status:'草稿',kind:'日报',allowed_actions:[],
 metadata:JSON.stringify({collaboration:'personal',byline_id:1,collaborators:[]}),config_snapshot:JSON.stringify({sections:[]}),
 document:JSON.stringify({layout,sections:[{id:'s1',title:'测试章节',required:true,revision:1,state:'未提交',editors:[1],blocks:[]}]})};}
async function mountEditor(layout='flow'){
 reports.value=[report(layout)];wrapper=mount(ReportEditorView,{attachTo:document.body,global:{plugins:[ElementPlus]}});await ready();
}
async function insert(kind){
 await button(wrapper,kind==='chart'?'＋ 指标图表':'＋ 数据表格').trigger('click');await ready();
 await button(body(),'插入当前章节').trigger('click');await ready();
}
beforeEach(()=>{
 vi.clearAllMocks();indicators.value=[{source:'测试源',indicator:'铜收盘价',unit:'元/吨',latest:'2026-11-18'}];
 api.mockImplementation(async(path,data)=>{
  if(path.startsWith('data/series?'))return {points,unit:'元/吨'};
  if(path==='personal-save'){
   const doc=JSON.parse(JSON.stringify(data.document));
   for(const s of doc.sections)for(const b of s.blocks){delete b.preview;b.refreshed_at='2026-11-18T13:00:00Z';}
   reports.value=[{...reports.value[0],version:2,document:JSON.stringify(doc)}];
  }
  return {ok:true};
 });
});
afterEach(()=>{wrapper?.unmount();wrapper=null;document.body.innerHTML='';});
describe('研报画板指标图表与表格',()=>{
 for(const layout of ['flow','grid','free'])for(const kind of ['chart','table']){
  it(`${layout} 布局插入 ${kind} 后保存前即可看到数据`,async()=>{
   await mountEditor(layout);await insert(kind);
   expect(api).toHaveBeenCalledWith(expect.stringContaining('data/series?'));
   expect(wrapper.findAllComponents(ReportBlock)).toHaveLength(1);
   if(kind==='chart')expect(wrapper.find('.canvas-paper svg[role="img"]').exists()).toBe(true);
   else {expect(wrapper.find('.canvas-paper .el-table').exists()).toBe(true);expect(wrapper.find('.canvas-paper').text()).toContain('2026-11-18');expect(wrapper.find('.canvas-paper').text()).toContain('12');}
   expect(wrapper.find('.data-caption').text()).toContain('尚未保存');
   expect(api.mock.calls.some(([path])=>path==='personal-save')).toBe(false);
  });
 }
 it('保存后图表仍显示，预览标记转为正式快照信息',async()=>{
  await mountEditor();await insert('chart');await button(wrapper,'保存本章').trigger('click');await ready();
  expect(wrapper.find('.canvas-paper svg[role="img"]').exists()).toBe(true);
  expect(wrapper.find('.data-caption').text()).not.toContain('尚未保存');
 });
 it('单个数据点也会显示可见标记，零值不会被误当成空数据',()=>{
  wrapper=mount(ReportBlock,{props:{block:{id:'b',type:'chart',source:'测试源',indicator:'库存',data:[{date:'2026-11-18',value:0,unit:'吨'}]}},global:{plugins:[ElementPlus]}});
  expect(wrapper.find('svg circle').exists()).toBe(true);expect(wrapper.find('svg circle').attributes('cx')).toBe('290');
  expect(wrapper.find('svg').html()).not.toContain('NaN');
 });
 it('没有数据时不插入空组件，允许重新选择',async()=>{
  api.mockResolvedValue({points:[]});await mountEditor();await insert('table');
  expect(wrapper.findAllComponents(ReportBlock)).toHaveLength(0);expect(button(body(),'插入当前章节').exists()).toBe(true);
 });
 it('取数失败时不插入空组件',async()=>{
  api.mockRejectedValue(new Error('取数失败'));await mountEditor();await insert('chart');expect(wrapper.findAllComponents(ReportBlock)).toHaveLength(0);
 });
 it('取消取数弹窗后，迟到的请求不会插入画板',async()=>{
  let resolve;api.mockImplementation(()=>new Promise(r=>{resolve=r;}));await mountEditor();
  await button(wrapper,'＋ 数据表格').trigger('click');await ready();
  await button(body(),'插入当前章节').trigger('click');await ready();
  const dialog=body().findAll('.el-dialog').find(d=>d.text().includes('插入数据表格'));
  await button(dialog,'取消').trigger('click');await ready();resolve({points});await ready();
  expect(wrapper.findAllComponents(ReportBlock)).toHaveLength(0);
 });
 it('自由布局连续插入时按实际高度排列，避免重叠遮挡',async()=>{
  await mountEditor('free');await insert('table');await insert('chart');
  const blocks=wrapper.findAllComponents(ReportBlock).map(b=>b.props('block'));
  expect(blocks[1].y).toBeGreaterThan(blocks[0].y+blocks[0].height);
 });
});


describe('章节设置编号',()=>{
 it('允许独立修改编号并随章节设置提交',async()=>{
  await mountEditor();
  await wrapper.find('button[title="章节设置"]').trigger('click');await ready();
  const dialog=body().findAll('.el-dialog').find(d=>d.text().includes('字段与分类模板对应'));
  const numberField=dialog.findAll('.el-form-item').find(f=>f.find('.el-form-item__label').text()==='章节编号');
  await numberField.find('input').setValue('附录A');
  await button(dialog,'保存设置').trigger('click');await ready();
  expect(api).toHaveBeenCalledWith('chapters',expect.objectContaining({action:'edit',label:'附录A',title:'测试章节'}));
 });
});
