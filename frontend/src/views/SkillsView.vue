<template>
  <div>
    <PageContainer title="Skill 管理">
      <template #actions>
        <el-tooltip content="刷新列表" placement="bottom">
          <el-button class="skill-refresh" :loading="loading" :disabled="saving" circle aria-label="刷新列表" @click="load"><el-icon><Refresh /></el-icon></el-button>
        </el-tooltip>
        <el-input v-model="search" class="skill-search" clearable placeholder="搜索技能" aria-label="搜索技能">
          <template #prefix><el-icon><Search /></el-icon></template>
        </el-input>
        <el-button type="primary" class="skill-upload" :disabled="saving || importingZip" @click="openImport">
          <el-icon class="skill-upload__icon"><Upload /></el-icon>上传技能
        </el-button>
        <input ref="zipInput" type="file" accept=".zip,application/zip" aria-label="导入 ZIP 技能包" style="display:none" @change="importZip" />
      </template>
    <div class="panel">
      <div class="skill-filters"><el-select v-model="kind" placeholder="全部类型" aria-label="Skill 类型"><el-option label="全部类型" value="" /><el-option label="内置" value="builtin" /><el-option label="自定义" value="custom" /></el-select><el-select v-model="status" placeholder="全部状态" aria-label="Skill 状态"><el-option label="全部状态" value="" /><el-option label="启用" value="enabled" /><el-option label="停用" value="disabled" /></el-select><span class="caption">{{ filtered.length }} / {{ skills.length }} 个 Skill</span></div>
      <el-alert v-if="loadError" :title="loadError" type="error" :closable="false" show-icon />
      <el-table :data="filtered" v-loading="loading" empty-text="暂无符合条件的 Skill">
        <el-table-column label="名称" prop="name" min-width="160" />
        <el-table-column label="适用场景" prop="description" min-width="260" />
        <el-table-column label="类型" width="100"><template #default="{row}"><el-tag size="small" :type="row.builtin ? 'info' : 'primary'">{{ row.builtin ? '内置' : '自定义' }}</el-tag></template></el-table-column>
        <el-table-column label="状态" width="95"><template #default="{row}"><el-tag size="small" :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</el-tag></template></el-table-column>
        <el-table-column label="版本" width="140">
          <template #default="{ row }"><span class="mono tiny">{{ row.version }}</span></template>
        </el-table-column>
        <el-table-column label="操作" width="210" fixed="right"><template #default="{row}"><el-button link @click="inspected = row; inspectVisible = true">查看</el-button><template v-if="!row.builtin"><el-button link type="danger" :disabled="!!busyId || saving" :loading="busyId === row.id" @click="remove(row)">删除</el-button><el-button link type="primary" :disabled="!!busyId || saving" @click="edit(row)">编辑</el-button><el-button link :type="row.enabled ? 'warning' : 'success'" :disabled="!!busyId || saving" :loading="busyId === row.id" @click="toggle(row)">{{ row.enabled ? '停用' : '启用' }}</el-button></template></template></el-table-column>
      </el-table>
    </div>
    <el-dialog v-model="importVisible" title="导入技能" width="min(520px, 94vw)" :close-on-click-modal="!importingZip" :close-on-press-escape="!importingZip" :show-close="!importingZip" @closed="dragging = false">
      <div class="dropzone" :class="{ 'is-drag': dragging, 'is-busy': importingZip }" role="button" tabindex="0" aria-label="拖拽或点击上传技能包"
        @click="pickZip" @keydown.enter.prevent="pickZip" @keydown.space.prevent="pickZip"
        @dragover.prevent="dragging = true" @dragleave.prevent="onDragLeave" @drop.prevent="onDrop">
        <el-icon class="dropzone__icon"><UploadFilled /></el-icon>
        <p class="dropzone__text">{{ importingZip ? '正在解析技能包…' : '拖拽 ZIP 文件或点击上传' }}</p>
      </div>
      <el-alert v-if="importError" :title="importError" type="error" :closable="false" show-icon class="import-error" />
      <div class="import-tips">
        <b>文件要求</b>
        <ul>
          <li>ZIP 内需要包含 SKILL.md 文件（放在根目录或一个技能目录里都可以）</li>
          <li>SKILL.md 需包含 YAML 格式的技能名称（name）和描述（description）</li>
        </ul>
        <p class="caption">UTF-8 文本；单个 ZIP 不超过 2 MB，解压后不超过 8 MB（最多 150 个文件，单文件不超过 512 KB）。只读取文本，脚本与二进制文件不会执行。</p>
        <el-button link type="primary" :disabled="importingZip" @click="pickZip">选择 ZIP 文件</el-button>
      </div>
    </el-dialog>
    <el-dialog v-model="editorVisible" :title="form.id ? '编辑 Skill' : '新建 Skill'" width="min(800px, 94vw)" :close-on-click-modal="false" :close-on-press-escape="!saving" :show-close="!saving">
      <el-form label-width="90px"><el-form-item label="配置名称" required><el-input v-model="form.name" maxlength="60" /></el-form-item><el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item><el-form-item label="SKILL.md" required><div class="wide"><input type="file" accept=".md,text/markdown,text/plain" aria-label="导入 SKILL.md" @change="importFile" /><el-input v-model="form.markdown" type="textarea" :rows="16" maxlength="12000" show-word-limit /></div></el-form-item></el-form>
      <div v-if="Object.keys(form.resources).length" class="resource-note"><b>配套资料（{{ Object.keys(form.resources).length }} 个）</b><el-tag v-for="name in Object.keys(form.resources)" :key="name" size="small">{{ name }}</el-tag><el-button link @click="form.resources = {}">移除配套资料</el-button></div>
      <el-alert v-for="warning in importWarnings" :key="warning" :title="warning" type="warning" :closable="false" />
      <el-alert v-if="error" :title="error" type="error" :closable="false" />
      <template #footer><el-button :disabled="saving" @click="editorVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存 Skill</el-button></template>
    </el-dialog>
    <el-dialog v-model="inspectVisible" :title="inspected?.name || 'Skill 内容'" width="min(800px, 94vw)"><p class="caption">版本 {{ inspected?.version }}</p><pre class="skill-content">{{ inspected?.markdown }}</pre><details v-for="(content,name) in inspected?.resources || {}" :key="name"><summary>{{ name }}</summary><pre class="skill-content">{{ content }}</pre></details></el-dialog>
    </PageContainer>
  </div>
</template>
<script setup>
import { computed, nextTick, onMounted, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Refresh, Search, Upload, UploadFilled } from '@element-plus/icons-vue';
import PageContainer from '../components/PageContainer.vue';
import { api, inspectSkillZip } from '../api';
/* 后端校验文案本身就是完整句子，去掉框架统一加的「输入无效：」前缀更好读 */
const plain=(message)=>String(message??'').replace(/^输入无效：/,'');
const skills=ref([]), revision=ref(0), loading=ref(false), saving=ref(false), busyId=ref(''), loadError=ref(''), error=ref('');
const search=ref(''), kind=ref(''), status=ref(''), editorVisible=ref(false), inspectVisible=ref(false), inspected=ref(null);
const form=reactive({id:'',name:'',enabled:true,markdown:'',resources:{}});
const zipInput=ref(null), importingZip=ref(false), importWarnings=ref([]);
const importVisible=ref(false), importError=ref(''), dragging=ref(false);
let importEpoch=0;
let editRevision=0;
const filtered=computed(()=>skills.value.filter(x=>(!kind.value || (kind.value==='builtin')===x.builtin) && (!status.value || (status.value==='enabled')===x.enabled) && `${x.name} ${x.description}`.toLowerCase().includes(search.value.trim().toLowerCase())));
async function load(){loading.value=true;loadError.value='';try{const result=await api('report-ai/skills');skills.value=result.skills;revision.value=result.revision;}catch(e){loadError.value=plain(e.message);}finally{loading.value=false;}}
function edit(row){importEpoch++;importWarnings.value=[];editRevision=revision.value;Object.assign(form,{id:row&&!row.builtin?row.id:'',name:row?row.name:'',enabled:row?.enabled??true,resources:JSON.parse(JSON.stringify(row?.resources || {})),markdown:row?.markdown || '---\nname: custom-research\ndescription: 说明适用报告和写作方法\n---\n# 研究写作方法\n\n1. 核对证据的来源和日期。\n2. 仅依据证据包撰写当前章节。\n'});error.value='';editorVisible.value=true;}
async function importFile(event){const file=event.target.files?.[0];if(!file)return;try{if(file.size>60000)throw new Error('Skill 文件过大');const text=await file.text();if(text.length>12000)throw new Error('SKILL.md 最多12000字');form.markdown=text;error.value='';}catch(e){error.value=plain(e.message);}finally{event.target.value='';}}
/* 导入技能：拖拽或点选 ZIP，解析成功后在同一次操作里打开预览弹窗确认保存 */
function openImport(){importError.value='';importVisible.value=true;}
function pickZip(){if(!importingZip.value)zipInput.value?.click();}
function onDragLeave(event){if(!event.currentTarget.contains(event.relatedTarget))dragging.value=false;}
function onDrop(event){dragging.value=false;const file=[...(event.dataTransfer?.files||[])][0];if(!file)return;
  if(!/\.zip$/i.test(file.name)){importError.value='只支持 .zip 技能包，文件夹请先压缩成 ZIP 再导入';return;}
  handleZip(file);}
async function handleZip(file){
 const request=++importEpoch;importingZip.value=true;importError.value='';
 try{
  if(file.size>2*1024*1024)throw new Error('ZIP 文件不能超过2 MB');
  const bundle=await inspectSkillZip(file);if(request!==importEpoch)return;
  importVisible.value=false;
  await nextTick();
  edit(null);form.name=bundle.name;form.markdown=bundle.markdown;form.resources=bundle.resources || {};importWarnings.value=bundle.warnings || [];
 }catch(e){if(request===importEpoch)importError.value=plain(e.message);}
 finally{importingZip.value=false;}
}
async function importZip(event){
 const file=event.target.files?.[0];event.target.value='';
 if(file)await handleZip(file);
}
async function save(){if(saving.value)return;if(!form.name.trim()||!form.markdown.trim()){error.value='请填写名称和 SKILL.md 内容';return;}saving.value=true;error.value='';try{await api('report-ai/skills',{...form,revision:editRevision});editorVisible.value=false;await load();ElMessage.success('Skill 已保存，后续生成使用新版本');}catch(e){error.value=plain(e.message);}finally{saving.value=false;}}
async function remove(row){
  try{
    await ElMessageBox.confirm(`删除后不可恢复，已经生成过的研报正文不受影响。确定删除「${row.name}」？`, '删除 Skill',
      {type:'warning', confirmButtonText:'删除', cancelButtonText:'取消', confirmButtonClass:'el-button--danger'});
  }catch{return;}
  busyId.value=row.id;
  try{
    await api('report-ai/skills',{action:'delete',id:row.id,revision:revision.value});
    await load();ElMessage.success('Skill 已删除');
  }catch(e){ElMessage.error(plain(e.message));load();}
  finally{busyId.value='';}
}
async function toggle(row){if(busyId.value)return;busyId.value=row.id;try{await api('report-ai/skills',{id:row.id,name:row.name,markdown:row.markdown,enabled:!row.enabled,revision:revision.value});await load();ElMessage.success(row.enabled?'已停用':'已启用');}catch(e){ElMessage.error(plain(e.message));}finally{busyId.value='';}}
onMounted(load);
</script>
<style scoped>
.skill-search{width:220px;max-width:100%}.skill-search :deep(.el-input__prefix){color:var(--ink-3)}
.skill-upload__icon{margin-right:5px;font-size:14px}
.skill-refresh{color:var(--ink-2)}
.dropzone{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;padding:40px 16px;margin:2px 0 14px;border:1px dashed var(--line);border-radius:6px;background:var(--paper);cursor:pointer;transition:border-color .15s,background .15s}
.dropzone:hover,.dropzone:focus-visible,.dropzone.is-drag{border-color:var(--accent);background:var(--accent-soft);outline:none}
.dropzone.is-busy{cursor:progress;opacity:.7}
.dropzone__icon{font-size:26px;color:var(--ink-3)}
.dropzone__text{font-size:13px;color:var(--ink-2)}
.import-error{margin-bottom:14px}
.import-tips b{display:block;font-size:13px;color:var(--ink-1);margin-bottom:8px}
.import-tips ul{margin:0 0 10px;padding-left:18px;display:flex;flex-direction:column;gap:5px}
.import-tips li{font-size:13px;line-height:1.7;color:var(--ink-2)}
.import-tips .caption{display:block;margin-bottom:12px;line-height:1.7;font-size:12px;color:var(--ink-3)}
.skill-filters{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:12px}.skill-filters>.el-select{width:140px}.skill-note{margin-top:16px;line-height:1.8}.wide{width:100%}.wide .caption{margin:10px 0;line-height:1.7}.resource-note{margin:16px 0}.resource-note .el-tag{margin:4px 8px 4px 0}details{margin:12px 0}summary{cursor:pointer}.skill-content{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit;line-height:1.8}
</style>
