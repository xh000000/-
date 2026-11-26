<template>
  <div>
    <PageHead title="Skill 管理" description="集中维护研报写作方法，供研报编辑器和 AI 助手调用。修改只影响后续生成任务。">
      <el-button :loading="loading" :disabled="saving" @click="load">刷新</el-button>
      <el-button :loading="importingZip" @click="zipInput?.click()">导入 ZIP</el-button>
      <input ref="zipInput" type="file" accept=".zip,application/zip" aria-label="导入 ZIP 技能包" style="display:none" @change="importZip" />
      <el-button type="primary" @click="edit(null)">新增 Skill</el-button>
    </PageHead>
    <div class="panel">
      <div class="skill-filters"><el-input v-model="search" clearable placeholder="搜索名称、适用场景" aria-label="搜索 Skill" /><el-select v-model="kind" aria-label="Skill 类型"><el-option label="全部类型" value="" /><el-option label="内置" value="builtin" /><el-option label="自定义" value="custom" /></el-select><el-select v-model="status" aria-label="Skill 状态"><el-option label="全部状态" value="" /><el-option label="启用" value="enabled" /><el-option label="停用" value="disabled" /></el-select><span class="caption">{{ filtered.length }} / {{ skills.length }} 个 Skill</span></div>
      <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" show-icon />
      <el-table :data="filtered" v-loading="loading" empty-text="暂无符合条件的 Skill">
        <el-table-column label="名称" prop="name" min-width="160" />
        <el-table-column label="适用场景" prop="description" min-width="260" />
        <el-table-column label="类型" width="100"><template #default="{row}"><el-tag size="small" :type="row.builtin ? 'info' : 'primary'">{{ row.builtin ? '内置' : '自定义' }}</el-tag></template></el-table-column>
        <el-table-column label="状态" width="95"><template #default="{row}"><el-tag size="small" :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</el-tag></template></el-table-column>
        <el-table-column label="版本" prop="version" width="140" />
        <el-table-column label="操作" width="230" fixed="right"><template #default="{row}"><el-button link @click="inspected = row; inspectVisible = true">查看</el-button><el-button link @click="edit(row,true)">复制</el-button><template v-if="!row.builtin"><el-button link type="primary" @click="edit(row)">编辑</el-button><el-button link :type="row.enabled ? 'warning' : 'success'" :disabled="!!busyId || saving" :loading="busyId === row.id" @click="toggle(row)">{{ row.enabled ? '停用' : '启用' }}</el-button></template></template></el-table-column>
      </el-table>
      <p class="caption skill-note">内置 Skill 可查看或复制；自定义 Skill 可编辑和启停。SKILL.md 只作为写作指令加载，不执行脚本；每次生成保留当时的版本和内容快照。</p>
    </div>
    <el-dialog v-model="editorVisible" :title="form.id ? '编辑 Skill' : '新增 / 导入 Skill'" width="min(800px, 94vw)" :close-on-click-modal="false" :close-on-press-escape="!saving" :show-close="!saving">
      <el-form label-width="90px"><el-form-item label="配置名称" required><el-input v-model="form.name" maxlength="60" /></el-form-item><el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item><el-form-item label="SKILL.md" required><div class="wide"><input type="file" accept=".md,text/markdown,text/plain" aria-label="导入 SKILL.md" @change="importFile" /><p class="caption">支持含 name、description 的 YAML 头部与 Markdown 正文，最多12000字。</p><el-input v-model="form.markdown" type="textarea" :rows="16" maxlength="12000" show-word-limit /></div></el-form-item></el-form>
      <div v-if="Object.keys(form.resources).length" class="resource-note"><b>配套资料（{{ Object.keys(form.resources).length }} 个）</b><p class="caption">这些文本会随 Skill 保留版本，生成时按长度上限加载；不执行文件内容。</p><el-tag v-for="name in Object.keys(form.resources)" :key="name" size="small">{{ name }}</el-tag><el-button link @click="form.resources = {}">移除配套资料</el-button></div>
      <el-alert v-for="warning in importWarnings" :key="warning" :title="warning" type="warning" :closable="false" />
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <template #footer><el-button :disabled="saving" @click="editorVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存 Skill</el-button></template>
    </el-dialog>
    <el-dialog v-model="inspectVisible" :title="inspected?.name || 'Skill 内容'" width="min(800px, 94vw)"><p class="caption">版本 {{ inspected?.version }}</p><pre class="skill-content">{{ inspected?.markdown }}</pre><details v-for="(content,name) in inspected?.resources || {}" :key="name"><summary>{{ name }}</summary><pre class="skill-content">{{ content }}</pre></details></el-dialog>
  </div>
</template>
<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import PageHead from '../components/PageHead.vue';
import { api, inspectSkillZip } from '../api';
const skills=ref([]), revision=ref(0), loading=ref(false), saving=ref(false), busyId=ref(''), loadError=ref(''), error=ref('');
const search=ref(''), kind=ref(''), status=ref(''), editorVisible=ref(false), inspectVisible=ref(false), inspected=ref(null);
const form=reactive({id:'',name:'',enabled:true,markdown:'',resources:{}});
const zipInput=ref(null), importingZip=ref(false), importWarnings=ref([]);
let importEpoch=0;
let editRevision=0;
const filtered=computed(()=>skills.value.filter(x=>(!kind.value || (kind.value==='builtin')===x.builtin) && (!status.value || (status.value==='enabled')===x.enabled) && `${x.name} ${x.description}`.toLowerCase().includes(search.value.trim().toLowerCase())));
async function load(){loading.value=true;loadError.value='';try{const result=await api('report-ai/skills');skills.value=result.skills;revision.value=result.revision;}catch(e){loadError.value=e.message;}finally{loading.value=false;}}
function edit(row,copy=false){importEpoch++;importWarnings.value=[];editRevision=revision.value;Object.assign(form,{id:row&&!copy&&!row.builtin?row.id:'',name:row?row.name+(copy||row.builtin?' 副本':''):'',enabled:row?.enabled??true,resources:JSON.parse(JSON.stringify(row?.resources || {})),markdown:row?.markdown || '---\nname: custom-research\ndescription: 说明适用报告和写作方法\n---\n# 研究写作方法\n\n1. 核对证据的来源和日期。\n2. 仅依据证据包撰写当前章节。\n'});error.value='';editorVisible.value=true;}
async function importFile(event){const file=event.target.files?.[0];if(!file)return;try{if(file.size>60000)throw new Error('Skill 文件过大');const text=await file.text();if(text.length>12000)throw new Error('SKILL.md 最多12000字');form.markdown=text;error.value='';}catch(e){error.value=e.message;}finally{event.target.value='';}}
async function importZip(event){
 const file=event.target.files?.[0];if(!file)return;
 const request=++importEpoch;importingZip.value=true;loadError.value='';
 try{
  if(file.size>2*1024*1024)throw new Error('ZIP 文件不能超过2 MB');
  const bundle=await inspectSkillZip(file);if(request!==importEpoch)return;
  edit(null);form.name=bundle.name;form.markdown=bundle.markdown;form.resources=bundle.resources || {};importWarnings.value=bundle.warnings || [];
 }catch(e){if(request===importEpoch)loadError.value=e.message;}
 finally{importingZip.value=false;event.target.value='';}
}
async function save(){if(saving.value)return;if(!form.name.trim()||!form.markdown.trim()){error.value='请填写名称和 SKILL.md 内容';return;}saving.value=true;error.value='';try{await api('report-ai/skills',{...form,revision:editRevision});editorVisible.value=false;await load();ElMessage.success('Skill 已保存，后续生成使用新版本');}catch(e){error.value=e.message;}finally{saving.value=false;}}
async function toggle(row){if(busyId.value)return;busyId.value=row.id;try{await api('report-ai/skills',{id:row.id,name:row.name,markdown:row.markdown,enabled:!row.enabled,revision:revision.value});await load();ElMessage.success(row.enabled?'已停用':'已启用');}catch(e){ElMessage.error(e.message);}finally{busyId.value='';}}
onMounted(load);
</script>
<style scoped>
.skill-filters{display:flex;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:20px}.skill-filters>.el-input{width:300px;max-width:100%}.skill-filters>.el-select{width:140px}.skill-note{margin-top:16px;line-height:1.8}.wide{width:100%}.wide .caption{margin:10px 0;line-height:1.7}.resource-note{margin:16px 0}.resource-note .el-tag{margin:4px 8px 4px 0}details{margin:12px 0}summary{cursor:pointer}.skill-content{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;line-height:1.8}
</style>
