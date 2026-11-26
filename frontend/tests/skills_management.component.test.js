import {beforeEach,afterEach,it,expect,vi} from 'vitest';
import {mount,flushPromises,DOMWrapper} from '@vue/test-utils';
import {nextTick} from 'vue';
import ElementPlus from 'element-plus';
import SkillsView from '../src/views/SkillsView.vue';
import {api,inspectSkillZip} from '../src/api';
import {user} from '../src/store/session';
vi.mock('../src/store/session',async()=>{const {ref}=await import('vue');return {user:ref({role:'admin'})};});
import {MENU,filterMenu} from '../src/utils/menu';
vi.mock('../src/api',()=>({api:vi.fn(),inspectSkillZip:vi.fn()}));
let wrapper;
const base={id:'daily-research',name:'日度研报',description:'日度研究写作',enabled:true,builtin:true,version:'v1',markdown:'---\nname: daily-research\ndescription: 数据写作\n---\n# 数据优先'};
const custom={...base,id:'custom-1',name:'铜专题',description:'铜供需专题',builtin:false};
const body=()=>new DOMWrapper(document.body);
const button=(root,name)=>root.findAll('button').find(b=>b.text()===name);
const field=name=>body().findAll('.el-form-item').find(x=>x.find('.el-form-item__label').text()===name);
async function ready(){await nextTick();await flushPromises();await new Promise(r=>setTimeout(r,35));}
async function start(){wrapper=mount(SkillsView,{attachTo:document.body,global:{plugins:[ElementPlus]}});await ready();}
beforeEach(()=>{vi.clearAllMocks();user.value={role:'admin'};api.mockImplementation(async(path,data)=>data?{ok:true}:{revision:7,skills:[base,custom]});});
afterEach(()=>{wrapper?.unmount();document.body.innerHTML='';});
it('Skill 管理在工具箱且所有登录账号可见',()=>{
 const admin=filterMenu(MENU,{role:'admin'},{});expect(admin.find(g=>g.label==='工具箱').children.some(x=>x.path==='/system/skills')).toBe(true);expect(admin.find(g=>g.label==='系统设置').children.some(x=>x.path==='/system/skills')).toBe(false);
 for(const role of ['researcher','reviewer','compliance','publisher'])expect(filterMenu(MENU,{role},{}).some(g=>g.children?.some(x=>x.path==='/system/skills'))).toBe(true);
});
it('支持搜索并从独立页面复制内置 Skill',async()=>{
 await start();await wrapper.find('input[aria-label="搜索 Skill"]').setValue('日度');await ready();expect(wrapper.text()).not.toContain('铜专题');
 await button(wrapper,'复制').trigger('click');await ready();
 expect(field('配置名称').find('input').element.value).toBe('日度研报 副本');
 expect(field('SKILL.md').find('textarea').element.value).toContain('name: daily-research');
 await button(body(),'保存 Skill').trigger('click');await ready();
 expect(api).toHaveBeenCalledWith('report-ai/skills',expect.objectContaining({id:'',name:'日度研报 副本',revision:7,enabled:true}));
});
it('自定义 Skill 可直接停用，内置 Skill 没有停用按钮',async()=>{
 await start();expect(wrapper.findAll('button').filter(b=>b.text()==='停用')).toHaveLength(1);
 await button(wrapper,'停用').trigger('click');await ready();
 expect(api).toHaveBeenCalledWith('report-ai/skills',expect.objectContaining({id:'custom-1',enabled:false,revision:7}));
});
it('保存冲突保留填写内容，避免覆盖其他管理员修改',async()=>{
 await start();await button(wrapper,'编辑').trigger('click');await ready();
 await field('配置名称').find('input').setValue('我的草稿');api.mockRejectedValueOnce(new Error('Skill 列表已更新，请刷新'));
 await button(body(),'保存 Skill').trigger('click');await ready();
 expect(field('配置名称').find('input').element.value).toBe('我的草稿');expect(body().text()).toContain('Skill 列表已更新');
});

it('普通登录账号也能新增、编辑和启停 Skill',async()=>{
 user.value={role:'reviewer'};await start();expect(wrapper.text()).toContain('铜专题');
 expect(button(wrapper,'新增 Skill')).toBeTruthy();expect(button(wrapper,'停用')).toBeTruthy();expect(button(wrapper,'编辑')).toBeTruthy();
 await button(wrapper,'停用').trigger('click');await ready();expect(api).toHaveBeenCalledWith('report-ai/skills',expect.objectContaining({id:'custom-1',enabled:false}));
});

it('ZIP 导入先预览，确认保存时保留配套资料',async()=>{
 await start();inspectSkillZip.mockResolvedValue({name:'zip-research',markdown:base.markdown,resources:{'references/method.md':'供需研究方法'},warnings:['脚本不会执行']});
 const file=new File(['mock-zip'],'report.zip',{type:'application/zip'});const input=wrapper.find('input[aria-label="导入 ZIP 技能包"]');
 Object.defineProperty(input.element,'files',{value:[file],configurable:true});await input.trigger('change');await ready();
 expect(inspectSkillZip).toHaveBeenCalledWith(file);expect(field('配置名称').find('input').element.value).toBe('zip-research');
 expect(body().text()).toContain('references/method.md');expect(api.mock.calls.some(([,d])=>d)).toBe(false);
 await button(body(),'保存 Skill').trigger('click');await ready();
 expect(api).toHaveBeenCalledWith('report-ai/skills',expect.objectContaining({resources:{'references/method.md':'供需研究方法'},revision:7}));
});
it('损坏 ZIP 显示错误，不保存配置',async()=>{
 await start();inspectSkillZip.mockRejectedValue(new Error('无法读取 ZIP'));
 const input=wrapper.find('input[aria-label="导入 ZIP 技能包"]');Object.defineProperty(input.element,'files',{value:[new File(['bad'],'bad.zip')],configurable:true});
 await input.trigger('change');await ready();expect(wrapper.text()).toContain('无法读取 ZIP');expect(api.mock.calls.some(([,d])=>d)).toBe(false);
});
