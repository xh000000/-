<template>
  <el-dialog v-model="visible" title="AI / Skill 生成研报" width="min(960px, 95vw)" :close-on-click-modal="false">
    <el-tabs v-model="tab">
      <el-tab-pane label="生成研报" name="generate">
        <p class="caption">当前研报：{{ report.title }} · v{{ report.version }}。沿用分类章节、版式、编辑权限和审批流程，生成结果先作为候选保存。</p>
        <el-alert v-if="isShared" type="info" :closable="false" class="generation-note" :title="isCreator ? '多人协作：请先在章节设置中完成分工，再统一生成整篇；各章负责人分别核对、采用并提交。更改分工后需重新生成对应章节候选。' : '多人协作：共享生成进度；你可以生成和确认自己负责的章节。'" />
        <el-form label-width="100px" class="generation-form">
          <el-form-item label="写作 Skill">
            <div class="wide"><el-select v-model="form.skill_ids" filterable multiple :multiple-limit="3" :disabled="running || starting || checking" placeholder="选择1至3个写作 Skill" style="width:100%"><el-option v-for="skill in enabledSkills" :key="skill.id" :label="skill.name" :value="skill.id" /></el-select>
              <p v-for="skill in chosenSkills" :key="skill.id" class="caption">{{ skill.name }} · {{ skill.description }}</p>
            </div>
          </el-form-item>
          <el-form-item label="生成章节"><div class="wide">
            <div class="chapter-selection-head"><span class="caption">已选 {{ form.section_ids.length }} 章</span><el-button link :disabled="running || starting || checking" @click="chooseSections(false)">全部可生成</el-button><el-button link :disabled="running || starting || checking" @click="chooseSections(true)">仅空白章节</el-button></div>
            <el-table :data="sections" size="small" class="chapter-plan-table">
              <el-table-column label="生成" width="60"><template #default="{row}"><el-checkbox :aria-label="`生成章节 ${row.title || '未命名章节'}`" :model-value="form.section_ids.includes(row.id)" :disabled="running || starting || checking || !canSelect(row)" @change="toggleSection(row.id, $event)" /></template></el-table-column>
              <el-table-column label="章节" min-width="150"><template #default="{row}">{{ row.label }} {{ row.title || '未命名章节' }}</template></el-table-column>
              <el-table-column v-if="isShared" label="负责人" min-width="110"><template #default="{row}">{{ (row.editors || []).map(editorName).join('、') || '待分配' }}</template></el-table-column>
              <el-table-column label="当前状态" min-width="120"><template #default="{row}"><span>{{ sectionStatus(row) }}</span><el-button v-if="pendingJob(row.id)" link type="primary" @click="selectJob(pendingJob(row.id).id)">查看候选</el-button></template></el-table-column>
            </el-table>
            <p v-if="pendingIds.size" class="caption">已有候选的章节先由负责人采用或放弃；未处理前不会重复生成。</p>
          </div></el-form-item>
          <el-form-item label="参考资料"><div class="wide"><el-select v-model="form.library_ids" multiple filterable :multiple-limit="8" :disabled="running || starting || checking" clearable placeholder="可选：选择资料库中已解析的文档，最多8条" style="width:100%"><el-option v-for="item in materialOptions" :key="item.id" :label="item.name" :value="item.id" /></el-select><p class="caption">指标按章节关联品种和研报日期读取，资料正文只发送给当前启用的外部模型。</p></div></el-form-item>
        </el-form>
        <div class="generation-actions"><el-button :loading="checking" :disabled="running || starting || checking || !form.section_ids.length || !form.skill_ids.length" @click="checkEvidence">检查研究依据</el-button><el-button type="primary" :loading="starting" :disabled="running || checking || !preview || !form.skill_ids.length || !form.section_ids.length" @click="start">生成所选章节候选</el-button><el-button v-if="running && job.can_cancel !== false" :loading="cancelling" @click="cancelJob">取消任务</el-button></div>
        <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="generation-note" />
        <div v-if="preview" class="generation-note">
          <el-alert :title="previewSummary" :type="previewHasWarnings ? 'warning' : 'success'" :closable="false" show-icon /><p class="caption">已完成依据检查，请核对下方来源、日期和资料缺口，再点击生成；此时才会调用模型。</p>
          <p>启用模型：{{ preview.model?.model || 'CLI 默认模型' }} · {{ preview.model?.base_url }}</p>
          <el-collapse><el-collapse-item v-for="item in preview.sections" :key="item.id" :name="item.id" :title="`${item.title || '未命名章节'} · ${item.evidence.data.length} 条指标 / ${item.evidence.materials.length} 条资料`"><p v-for="warning in item.evidence.warnings" :key="warning" class="warning">{{ warning }}</p><EvidenceList :evidence="item.evidence" /></el-collapse-item></el-collapse>
        </div>
        <el-select v-if="jobs.length > 1" :model-value="job?.id" aria-label="切换生成任务" class="generation-note" style="width:100%" @change="selectJob"><el-option v-for="item in jobs" :key="item.id" :value="item.id" :label="`${(item.created_at || '').replace(/\.\d+(?= UTC$)/, '')} · ${item.initiator || '本人'} · ${item.status}`" /></el-select>
        <div v-if="job" class="generation-job">
          <p v-if="job.shared" class="caption">共享任务 · 发起人：{{ job.initiator }} · 已处理 {{ Object.keys(job.result?.reviews || {}).length }} / {{ job.result?.total || 0 }} 章</p>
          <div class="generation-job-head"><b>{{ job.status }} · {{ job.status === '已取消' ? '候选未保存到研报' : job.result?.stage || '' }}</b><el-button link :loading="polling" @click="fetchJob">刷新进度</el-button></div>
          <el-progress :percentage="progress" :status="job.status === '失败' ? 'exception' : ['已完成','部分采用','已采用','已放弃'].includes(job.status) ? 'success' : undefined" />
          <p class="caption">已生成 {{ job.result?.completed || 0 }} / {{ job.result?.total || 0 }} 章。{{ running ? '可关闭弹窗继续工作；同一章被修改后，旧候选不会覆盖新内容。' : '生成不等于保存或送审。' }}</p>
          <p class="caption">加载的 Skill：{{ (job.result?.skills || []).map(x => `${x.name}@${x.version}`).join('、') }}</p>
          <div v-if="job.can_retry" class="generation-actions generation-note"><el-button type="primary" :loading="retrying" @click="retryJob">重试未完成章节</el-button><span class="caption">已成功的 {{ job.result?.completed || 0 }} 章会保留</span></div>
          <p v-for="failure in job.result?.errors || []" :key="failure.id" class="warning">{{ failure.title || failure.id }}：{{ failure.error }}</p>
          <el-alert v-if="job.error" :title="errorHelp(job.error)" :description="job.error" type="error" :closable="false" show-icon />
          <el-radio-group v-if="job.shared && ['已完成','部分采用'].includes(job.status)" v-model="mode" class="generation-note"><el-radio value="append">追加文字，保留原文</el-radio><el-radio value="replace">替换本章文字，保留图表</el-radio></el-radio-group>
          <el-collapse><el-collapse-item v-for="section in job.result?.sections || []" :key="section.id" :name="section.id" :title="`${section.title || '未命名章节'}${job.shared ? ' · ' + reviewLabel(section) : ''}`">
            <p v-if="job.shared" class="caption">负责人：{{ (section.editors || []).join('、') || '待分配' }}<span v-if="section.review"> · {{ section.review.name }}于{{ section.review.at }}{{ section.review.decision === 'apply' ? '采用' : '放弃' }}</span></p>
            <el-input :model-value="section.body" type="textarea" :autosize="{minRows:5,maxRows:16}" readonly /><p v-for="warning in section.warnings" :key="warning" class="warning">{{ warning }}</p><details><summary>查看本章数据和资料出处</summary><EvidenceList :evidence="section.evidence" /></details>
            <div v-if="job.shared && ['已完成','部分采用'].includes(job.status) && section.can_apply" class="generation-adopt">
              <el-checkbox v-model="chapterReviewed[section.id]">已核对本章内容、数字与引用来源</el-checkbox>
              <div><el-button type="primary" :disabled="!chapterReviewed[section.id]" :loading="applying" @click="applySection(section.id)">采用本章候选</el-button><el-button :disabled="applying" @click="applySection(section.id, 'skip')">放弃本章候选</el-button></div>
            </div>
            <el-button v-if="job.shared && job.status === '失败' && section.can_apply" class="generation-note" :disabled="applying" @click="applySection(section.id, 'skip')">放弃本章候选</el-button>
          </el-collapse-item></el-collapse>
          <div v-if="job.status === '已完成' && !job.shared" class="generation-adopt">
            <el-radio-group v-model="mode"><el-radio value="append">追加为章节文字块</el-radio><el-radio value="replace">替换所选章节文字，保留图表</el-radio></el-radio-group>
            <el-checkbox v-model="reviewed">已逐章核对内容、数字与引用来源</el-checkbox>
            <el-button type="primary" :disabled="!reviewed" :loading="applying" @click="apply">确认保存到当前研报</el-button>
          </div>
        </div>
      </el-tab-pane>
      <el-tab-pane label="Skill 库" name="skills">
        <div class="generation-job-head"><p class="caption">查看写作方法；集中维护请到工具箱中的 Skill 管理。</p><el-link href="/system/skills" target="_blank" type="primary">打开 Skill 管理</el-link></div>
        <el-table :data="skillList"><el-table-column label="名称" prop="name" min-width="150" /><el-table-column label="适用场景" prop="description" min-width="240" /><el-table-column label="状态" width="80"><template #default="{row}">{{ row.enabled ? '启用' : '停用' }}</template></el-table-column><el-table-column label="操作" width="90"><template #default="{row}"><el-button link @click="inspect = row">查看</el-button></template></el-table-column></el-table>
        <div v-if="inspect" class="skill-inspect"><b>{{ inspect.name }} · {{ inspect.version }}</b><pre>{{ inspect.markdown }}</pre></div>
      </el-tab-pane>
    </el-tabs>
    <template #footer><el-button @click="visible = false">关闭</el-button></template>
  </el-dialog>

</template>
<script setup>
import { computed, defineComponent, h, onBeforeUnmount, reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import { api } from '../api';
import { library, members, user } from '../store/session';
const props = defineProps({ modelValue:Boolean, report:{type:Object,required:true}, focusSectionId:{type:String,default:''} });
const emit = defineEmits(['update:modelValue','saved']);
const visible = computed({get:()=>props.modelValue,set:v=>emit('update:modelValue',v)});
const tab=ref('generate'), skillList=ref([]), inspect=ref(null);
const form=reactive({skill_ids:[],section_ids:[],library_ids:[]});
const retrying=ref(false);
const jobs=ref([]), chapterReviewed=reactive({});
const preview=ref(null), job=ref(null), error=ref(''), checking=ref(false), starting=ref(false), polling=ref(false), cancelling=ref(false), applying=ref(false), reviewed=ref(false), mode=ref('append');
const sections=computed(()=>{try{return JSON.parse(props.report.document || '{}').sections || [];}catch{return [];}});
const meta=computed(()=>{try{return JSON.parse(props.report.metadata || '{}');}catch{return {};}});
const isShared=computed(()=>meta.value.collaboration==='shared');
const isCreator=computed(()=>props.report.author===user.value.id);
const enabledSkills=computed(()=>skillList.value.filter(x=>x.enabled));
const chosenSkills=computed(()=>skillList.value.filter(x=>form.skill_ids.includes(x.id)));
const editorName=id=>id===user.value.id ? '我' : members.value.find(x=>x.id===id)?.name || `成员 ${id}`;
const pendingJob=id=>jobs.value.find(j=>j.shared && ['排队中','运行中','已完成','部分采用','失败'].includes(j.status) && !j.result?.reviews?.[id] && (
 ['排队中','运行中'].includes(j.status) ? j.planned_section_ids?.includes(id) : j.result?.sections?.some(x=>x.id===id)));
const pendingIds=computed(()=>new Set(sections.value.filter(x=>pendingJob(x.id)).map(x=>x.id)));
const previewHasWarnings=computed(()=>preview.value?.sections?.some(x=>x.evidence.warnings?.length));
const previewSummary=computed(()=>{const list=preview.value?.sections || [];const empty=list.filter(x=>!x.evidence.data.length && !x.evidence.materials.length).length;return `已检查 ${list.length} 章${empty ? `，其中 ${empty} 章资料不足，仅生成待补充说明` : ''}${previewHasWarnings.value ? '；请先核对数据时效与提示' : '，研究依据可用'}`;});
const materialOptions=computed(()=>library.value.filter(x=>!x.deleted && x.body && x.kind!=='folder' && (isShared.value ? x.area!=='cloud' : (x.area!=='cloud' || x.owner===user.value.id || user.value.role==='admin'))));
const running=computed(()=>['排队中','运行中'].includes(job.value?.status));
const watchShared=computed(()=>job.value?.shared && ['已完成','部分采用'].includes(job.value?.status));
const progress=computed(()=>Math.min(100,Math.round((job.value?.result?.completed || 0)/Math.max(1,job.value?.result?.total || 1)*100)));
function canWrite(section){return section.state!=='已提交' && (meta.value.collaboration!=='shared' || section.editors?.includes(user.value.id));}
function canGenerate(section){return canWrite(section) || (isShared.value && isCreator.value && section.state!=='已提交');}
function canSelect(section){return canGenerate(section) && !pendingIds.value.has(section.id);}
function sectionStatus(section){return section.state==='已提交' ? '已提交' : pendingIds.value.has(section.id) ? '候选待处理' : !canGenerate(section) ? '他人负责' : section.blocks?.some(x=>x.text?.trim() || x.data?.length) ? '已有正文' : '空白章节';}
function toggleSection(id, checked){form.section_ids=checked ? [...new Set([...form.section_ids,id])] : form.section_ids.filter(x=>x!==id);}
function chooseSections(emptyOnly){form.section_ids=sections.value.filter(x=>canSelect(x) && (!emptyOnly || !x.blocks?.length)).map(x=>x.id);}
function reviewLabel(section){return section.review ? (section.review.decision==='apply' ? '已采用' : '已放弃') : section.can_apply ? '待我确认' : '待负责人确认';}
async function selectJob(id){stop();epoch++;reviewed.value=false;Object.keys(chapterReviewed).forEach(k=>delete chapterReviewed[k]);job.value=jobs.value.find(x=>x.id===id);await fetchJob();}
function input(){return {report_id:props.report.id,version:props.report.version,...JSON.parse(JSON.stringify(form))};}
function errorHelp(message=''){return /quota|credit_balance|余额|额度/i.test(message)?'模型 API 余额或额度不足，请检查外部模型的 API 计费；聊天会员不包含本次 API 用量。':message;}
let timer, epoch=0;
function stop(){clearTimeout(timer);timer=undefined;}
async function fetchJob(){
 if(!job.value || polling.value)return;
 const request=epoch; const id=job.value.id;polling.value=true;
 try{const value=await api(`report-ai/jobs/${id}`);if(request===epoch && job.value?.id===id){job.value=value;const i=jobs.value.findIndex(x=>x.id===id);if(i>=0)jobs.value[i]=value;else jobs.value.unshift(value);}}
 catch(e){if(request===epoch)error.value=e.message;}
 finally{polling.value=false;if(visible.value && (running.value || watchShared.value)){stop();timer=setTimeout(fetchJob,running.value ? 2000 : 5000);}}
}
async function load(){
 const request=++epoch;stop();error.value='';preview.value=null;reviewed.value=false;
 try{
  const [catalog,latest]=await Promise.all([api('report-ai/skills'),api(`report-ai/reports/${props.report.id}/latest`)]);
  if(request!==epoch)return;
  skillList.value=catalog.skills;
  form.skill_ids=form.skill_ids.filter(id=>catalog.skills.some(x=>x.id===id&&x.enabled));if(!form.skill_ids.length&&enabledSkills.value.length){const preferred=/专题/.test(props.report.kind || '') ? 'supply-demand' : 'daily-research';form.skill_ids=[enabledSkills.value.find(x=>x.id===preferred)?.id || enabledSkills.value[0].id];}
  jobs.value=latest.jobs || (latest.job ? [latest.job] : []);job.value=latest.job;
  form.section_ids=sections.value.filter(x=>canSelect(x) && (!props.focusSectionId || x.id===props.focusSectionId)).map(x=>x.id);
  if(running.value || watchShared.value)timer=setTimeout(fetchJob,1000);
 }catch(e){if(request===epoch)error.value=e.message;}
}
watch(pendingIds,ids=>{const next=form.section_ids.filter(id=>!ids.has(id));if(next.length!==form.section_ids.length)form.section_ids=next;});
watch(()=>[...form.skill_ids,...form.section_ids,...form.library_ids],()=>{preview.value=null;});
watch(visible,value=>{if(value)load();else{stop();epoch++;}},{immediate:true});
onBeforeUnmount(()=>{stop();epoch++;});
async function checkEvidence(){checking.value=true;error.value='';try{preview.value=await api('report-ai/preview',input());}catch(e){error.value=errorHelp(e.message);}finally{checking.value=false;}}
async function start(){
 if(starting.value||running.value)return;
 if(!preview.value){error.value='请先检查研究依据，核对生成范围和数据缺口后再生成';return;}
 starting.value=true;error.value='';
 try{preview.value=await api('report-ai/preview',input());const result=await api('report-ai/jobs',input());job.value={id:result.id,status:'排队中',result:{sections:[],completed:0,total:form.section_ids.length}};reviewed.value=false;await fetchJob();}
 catch(e){error.value=errorHelp(e.message);}finally{starting.value=false;}
}
async function retryJob(){
 if(retrying.value || running.value)return;
 retrying.value=true;error.value='';
 try{await api(`report-ai/jobs/${job.value.id}/retry`,{});await fetchJob();}
 catch(e){error.value=e.message;}finally{retrying.value=false;}
}
async function cancelJob(){cancelling.value=true;try{await api(`report-ai/jobs/${job.value.id}/cancel`,{});await fetchJob();}catch(e){error.value=e.message;}finally{cancelling.value=false;}}
async function applySection(id, decision='apply'){
 if(applying.value || (decision==='apply' && !chapterReviewed[id]))return;
 applying.value=true;error.value='';
 try{await api(`report-ai/jobs/${job.value.id}/apply`,{version:props.report.version,reviewed:true,mode:mode.value,section_ids:[id],decision});
  chapterReviewed[id]=false;await fetchJob();emit('saved');ElMessage.success(decision==='skip' ? '已放弃本章候选，可重新生成或手工编写' : '本章候选已采用，请核对正文后提交本章');
 }catch(e){error.value=e.message;}finally{applying.value=false;}
}
async function apply(){
 if(applying.value||!reviewed.value)return;
 applying.value=true;error.value='';
 try{await api(`report-ai/jobs/${job.value.id}/apply`,{version:props.report.version,reviewed:true,mode:mode.value});job.value.status='已采用';emit('saved');ElMessage.success('候选已保存为 AI 初稿，请继续核对后按原审批流程提交');}
 catch(e){error.value=e.message;}finally{applying.value=false;}
}
const EvidenceList=defineComponent({props:['evidence'],setup(p){return()=>h('div',{class:'evidence-list'},[
 h('ul',{},(p.evidence?.data || []).map(x=>h('li',{},`[${x.id}] ${x.source} / ${x.indicator} · ${x.date} · ${x.value} ${x.unit}`))),
 h('ul',{},(p.evidence?.materials || []).map(x=>h('li',{},[`[${x.id}] ${x.name} · ${x.updated || ''}`,h('p',{},x.excerpt)])))
]);}});
</script>
<style scoped>
.wide{width:100%}.chapter-selection-head{display:flex;align-items:center;gap:14px;margin-bottom:8px}.chapter-plan-table{border:1px solid var(--el-border-color-lighter);border-radius:6px}.generation-form{margin-top:20px}.generation-form .caption{margin:6px 0 0;line-height:1.6}.generation-actions{display:flex;flex-wrap:wrap;gap:8px}.generation-note,.generation-job{margin-top:20px}.generation-job{padding:18px;border:1px solid var(--el-border-color-light);border-radius:10px}.generation-job-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}.generation-adopt{display:flex;flex-direction:column;align-items:flex-start;gap:12px;margin-top:20px}.warning{color:var(--el-color-warning);line-height:1.7}.skill-inspect{padding:16px;background:var(--el-fill-color-light);margin-top:16px;border-radius:8px}.skill-inspect pre{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.8;font:inherit}details{margin-top:12px}summary{cursor:pointer;color:var(--el-color-primary)}.evidence-list{font-size:12px;line-height:1.8;overflow-wrap:anywhere}.evidence-list ul{padding-left:20px}.el-checkbox-group{display:flex;flex-wrap:wrap}
</style>
