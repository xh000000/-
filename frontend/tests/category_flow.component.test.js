import {beforeEach,afterEach,it,expect,vi} from 'vitest';
import {mount,flushPromises} from '@vue/test-utils';
import {nextTick} from 'vue';
import ElementPlus,{ElSelect} from 'element-plus';
import CategoriesView from '../src/views/CategoriesView.vue';
import {api} from '../src/api';
import {categories,categoryTree,flows} from '../src/store/session';
vi.mock('vue-router',()=>({useRoute:()=>({query:{}})}));
vi.mock('../src/api',()=>({api:vi.fn().mockResolvedValue({ok:true})}));
vi.mock('../src/store/session',async()=>{
 const {ref}=await import('vue');return {categories:ref([]),categoryTree:ref([]),flows:ref([]),commodities:ref([]),refresh:vi.fn().mockResolvedValue(undefined)};
});
let wrapper;
afterEach(()=>{wrapper?.unmount();document.body.innerHTML='';});
beforeEach(()=>{
 vi.clearAllMocks();
 categories.value=[{id:1,name:'测试分类',revision:2,enabled:1,config:{kind:'日报',layout:'flow',commodities:['铜'],sections:[{id:'s1',title:'正文',required:true,default:''}],workflow:[{label:'旧合规',role:'compliance',mode:'any',users:[]}]}}];
 categoryTree.value=[{id:1,label:'测试分类',depth:1,folder:false,effective_enabled:true,sort_order:0}];
 flows.value=[{id:7,name:'通用审批流程',enabled:1,category_ids:[1]},{id:8,name:'新流程',enabled:1,category_ids:[]}];
});
it('分类只选择审批流，保存关联关系而不编辑审批节点',async()=>{
 wrapper=mount(CategoriesView,{attachTo:document.body,global:{plugins:[ElementPlus]}});
 await nextTick();await flushPromises();await new Promise(r=>setTimeout(r,30));
 expect(wrapper.text()).toContain('通用审批流程');
 await wrapper.findAll('button').find(b=>b.text()==='章节与审批配置').trigger('click');await flushPromises();
 expect(wrapper.text()).toContain('关联审批流');expect(wrapper.text()).not.toContain('指定审批人');
 const field=wrapper.findAll('.el-form-item').find(f=>f.find('.el-form-item__label').text()==='审批流');
 const select=field.findComponent(ElSelect);expect(select.props('modelValue')).toBe(7);
 select.vm.$emit('update:modelValue',8);await nextTick();
 await wrapper.findAll('button').find(b=>b.text()==='保存配置').trigger('click');await flushPromises();
 expect(api).toHaveBeenCalledWith('categories',expect.objectContaining({id:1,revision:2,approval_flow_id:8}));
});
