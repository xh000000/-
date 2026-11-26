<template>
  <el-dialog v-model="visible" title="章节分工" width="min(960px, 95vw)" :close-on-click-modal="false">
    <p class="caption">集中分配本研报的章节编辑人，每章可由多人共同编辑。已提交章节需先撤销提交；更改分工后，旧 AI 候选需由新负责人放弃后重新生成。</p>
    <div class="assignment-toolbar">
      <span>已选 {{ selected.length }} 章</span>
      <el-select v-model="batchEditors" multiple collapse-tags collapse-tags-tooltip placeholder="选择编辑人" aria-label="批量编辑人" style="width:260px" :disabled="saving">
        <el-option v-for="person in people" :key="person.id" :label="person.name" :value="person.id" />
      </el-select>
      <el-button :disabled="saving || !selected.length || !batchEditors.length" @click="applyBatch">应用到选中章节</el-button>
    </div>
    <el-table :data="rows" max-height="460" @selection-change="selected = $event">
      <el-table-column type="selection" width="45" :selectable="row => row.state !== '已提交' && !saving" />
      <el-table-column label="章节" min-width="200"><template #default="{row}"><span class="caption">{{ row.group }}</span><div>{{ row.label }} {{ row.title || '未命名章节' }}</div></template></el-table-column>
      <el-table-column label="状态" width="90" prop="state" />
      <el-table-column label="编辑人" min-width="260"><template #default="{row}">
        <el-select v-model="row.editors" multiple collapse-tags collapse-tags-tooltip :disabled="saving || row.state === '已提交'" :aria-label="`编辑人 ${row.title || row.id}`" style="width:100%">
          <el-option v-for="person in people" :key="person.id" :label="person.name" :value="person.id" />
        </el-select>
      </template></el-table-column>
    </el-table>
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon style="margin-top:14px" />
    <template #footer><span class="caption" style="margin-right:16px">{{ changed.length }} 章分工待保存</span><el-button :disabled="saving" @click="visible = false">取消</el-button><el-button type="primary" :disabled="!changed.length" :loading="saving" @click="save">保存分工</el-button></template>
  </el-dialog>
</template>
<script setup>
import {computed,ref,watch} from 'vue';
import {api} from '../api';
import {memberName} from '../store/session';
import {ElMessage} from 'element-plus';
const props=defineProps({modelValue:Boolean,report:{type:Object,required:true}});
const emit=defineEmits(['update:modelValue','saved']);
const visible=computed({get:()=>props.modelValue,set:v=>emit('update:modelValue',v)});
const rows=ref([]),selected=ref([]),batchEditors=ref([]),original=ref({}),version=ref(0),saving=ref(false),error=ref('');
const people=computed(()=>{let md={};try{md=JSON.parse(props.report.metadata || '{}');}catch{}return [...new Set([props.report.author,...(md.collaborators || [])])].filter(Boolean).map(id=>({id,name:memberName(id)}));});
const signature=ids=>[...ids].sort((a,b)=>a-b).join(',');
const changed=computed(()=>rows.value.filter(row=>signature(row.editors)!==original.value[row.id]));
watch(visible,value=>{if(!value)return;try{rows.value=JSON.parse(props.report.document || '{}').sections || [];}catch{rows.value=[];}original.value=Object.fromEntries(rows.value.map(row=>[row.id,signature(row.editors || [])]));version.value=props.report.version;selected.value=[];batchEditors.value=[];error.value='';},{immediate:true});
function applyBatch(){for(const row of selected.value)if(row.state!=='已提交')row.editors=[...batchEditors.value];}
async function save(){
 if(saving.value || !changed.value.length)return;
 if(changed.value.some(row=>!row.editors.length)){error.value='每章至少需要一位编辑人';return;}
 saving.value=true;error.value='';
 try{await api('chapters',{id:props.report.id,version:version.value,action:'assign',assignments:changed.value.map(row=>({section_id:row.id,editors:row.editors}))});visible.value=false;emit('saved');ElMessage.success('章节分工已保存');}
 catch(e){error.value=e.message;}finally{saving.value=false;}
}
</script>
<style scoped>.assignment-toolbar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:18px 0}</style>
