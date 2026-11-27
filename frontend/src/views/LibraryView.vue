<template>
  <div>
    <PageContainer :title="title">
      <template #actions>
        <el-button @click="openFolderDialog">新建文件夹</el-button>
        <el-button type="primary" @click="openUploadDialog">
          {{ area === 'docs' ? '新建文档' : isMaterials ? '上传素材' : '上传文件' }}
        </el-button>
      </template>

    <div class="panel" style="padding: 0">
      <div class="lib-toolbar">
        <el-button v-if="parentId" size="small" @click="goUp">← 返回上级</el-button>
        <span class="lib-path">当前位置：{{ trail.map(item => item.name).join(' / ') || '全部资料' }}</span>
        <span class="grow"></span>
        <el-button size="small" :disabled="!selected.length" @click="openMoveDialog">批量移动</el-button>
        <el-button size="small" :disabled="!selected.length" @click="batchDelete">批量删除</el-button>
        <el-button size="small" :disabled="!selected.length" @click="batchDownload">批量下载</el-button>
        <span class="caption">已选 {{ selected.length }} 项</span>
      </div>

      <div class="lib-items">
        <div v-if="isMaterials" class="lib-grid">
          <div v-for="item in items" :key="item.id" class="lib-card">
            <div v-if="item.kind === 'folder'" class="thumb" @click="openFolder(item.id)">
              <el-icon><Folder /></el-icon>
            </div>
            <div v-else class="thumb" @click="lightbox = item">
              <img :src="fileUrl(item.id)" :alt="item.name" />
            </div>
            <div class="meta">
              <p :title="item.name">{{ item.name }}</p>
              <p class="caption">{{ ownerName(item.owner) }} · {{ localTime(item.updated) }}</p>
            </div>
            <div class="ops">
              <el-checkbox
                :model-value="selected.includes(item.id)"
                size="small"
                @change="toggle(item.id)"
              >选择</el-checkbox>
              <span class="row" style="gap: 6px">
                <el-button v-if="item.kind === 'folder'" link size="small" @click="openFolder(item.id)">打开</el-button>
                <el-button link size="small" @click="openEditDialog(item)">编辑</el-button>
                <el-button v-if="item.kind !== 'folder'" link size="small" @click="download(item.id)">下载</el-button>
              </span>
            </div>
          </div>
          <p v-if="!items.length" class="empty-hint" style="grid-column: 1 / -1">暂无素材</p>
        </div>

        <el-table v-else :data="items" row-key="id" :empty-text="'暂无内容'">
          <el-table-column width="46" align="center">
            <template #header>
              <el-checkbox :model-value="allChecked" :indeterminate="partChecked" @change="toggleAll" />
            </template>
            <template #default="{ row }">
              <el-checkbox :model-value="selected.includes(row.id)" @change="toggle(row.id)" />
            </template>
          </el-table-column>
          <el-table-column label="名称" min-width="240">
            <template #default="{ row }">
              <el-button v-if="row.kind === 'folder'" link type="primary" @click="openFolder(row.id)">
                {{ row.name }}
              </el-button>
              <span v-else>{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="类型" width="150">
            <template #default="{ row }">{{ kindLabel(row) }}</template>
          </el-table-column>
          <el-table-column label="创建人" width="110">
            <template #default="{ row }">{{ ownerName(row.owner) }}</template>
          </el-table-column>
          <el-table-column label="更新时间" width="160">
            <template #default="{ row }">{{ localTime(row.updated) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="170">
            <template #default="{ row }">
              <el-button v-if="row.kind === 'folder'" link size="small" @click="openFolder(row.id)">打开</el-button>
              <el-button v-if="row.kind === 'document'" link size="small" @click="openEditDialog(row)">查看 / 编辑</el-button>
              <el-button v-if="['file', 'image'].includes(row.kind)" link size="small" @click="download(row.id)">下载</el-button>
              <el-button link size="small" @click="openEditDialog(row)">{{ row.kind === 'folder' ? '重命名' : '编辑' }}</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 新建文件夹 -->
    <el-dialog v-model="folderVisible" title="新建文件夹" width="420px">
      <el-form label-width="84px">
        <el-form-item label="名称">
          <el-input v-model="folderName" maxlength="120" placeholder="请输入文件夹名称" />
        </el-form-item>
      </el-form>
      <p class="caption">{{ isMaterials ? '素材库最多三级分类。' : '目录层级不限。' }}</p>
      <template #footer>
        <el-button @click="folderVisible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="createFolder">创建</el-button>
      </template>
    </el-dialog>

    <!-- 上传 / 新建文档 -->
    <el-dialog v-model="uploadVisible" :title="uploadTitle" width="520px">
      <el-form label-width="84px">
        <el-form-item label="名称">
          <el-input v-model="uploadName" maxlength="120" placeholder="留空则使用文件名" />
        </el-form-item>
        <el-form-item v-if="uploadKind === 'document'" label="文档正文">
          <el-input v-model="uploadBody" type="textarea" :rows="8" />
        </el-form-item>
        <el-form-item v-else label="选择文件">
          <input
            ref="fileInput"
            type="file"
            :accept="uploadKind === 'image' ? 'image/png,image/jpeg,image/webp' : ''"
            @change="onFileChange"
          />
        </el-form-item>
      </el-form>
      <p class="caption">
        单个文件不超过 5MB。{{ uploadKind === 'image' ? '素材可直接插入研报。' : '' }}
      </p>
      <template #footer>
        <el-button @click="uploadVisible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="submitUpload">上传</el-button>
      </template>
    </el-dialog>

    <!-- 资料详情 -->
    <el-dialog v-model="editVisible" title="资料详情" :width="editItem?.kind === 'document' ? 720 : 520">
      <el-form v-if="editItem" label-width="84px">
        <el-form-item label="名称">
          <el-input v-model="editName" :readonly="!editEditable" maxlength="120" />
        </el-form-item>
        <el-form-item label="所在目录">
          <el-select v-model="editParent" :disabled="!editEditable" clearable placeholder="根目录" style="width: 100%">
            <el-option v-for="item in folderOptions" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="editItem.kind === 'document'" label="文档正文">
          <el-input v-model="editBody" type="textarea" :rows="10" :readonly="!editEditable" />
        </el-form-item>
        <el-form-item v-if="['file', 'image'].includes(editItem.kind)" label="文件">
          <el-button link type="primary" @click="download(editItem.id)">下载该文件</el-button>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button v-if="editEditable" type="danger" plain @click="removeItem">移除</el-button>
        <el-button v-if="editEditable" type="primary" :loading="busy" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>

    <!-- 批量移动 -->
    <el-dialog v-model="moveVisible" :title="`批量移动（${selected.length} 项）`" width="440px">
      <el-select v-model="moveTarget" clearable placeholder="根目录" style="width: 100%">
        <el-option v-for="item in folderOptions" :key="item.id" :label="item.name" :value="item.id" />
      </el-select>
      <template #footer>
        <el-button @click="moveVisible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="submitMove">移动</el-button>
      </template>
    </el-dialog>

    <!-- 大图预览 -->
    <el-dialog v-model="lightboxVisible" title="素材预览" width="760px" top="6vh">
      <div v-if="lightbox" class="lightbox">
        <img :src="fileUrl(lightbox.id)" :alt="lightbox.name" />
      </div>
      <div v-if="lightbox" class="row spread" style="margin-top: 12px">
        <b>{{ lightbox.name }}</b>
        <el-button link type="primary" @click="download(lightbox.id)">下载原图</el-button>
      </div>
    </el-dialog>
    </PageContainer>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Folder } from '@element-plus/icons-vue';
import PageContainer from '../components/PageContainer.vue';
import { api, downloadUrl, fileUrl } from '../api';
import { library, memberName, refresh, user } from '../store/session';
import { fileSize, localTime } from '../utils/format';

const route = useRoute();
const area = computed(() => route.params.area || 'cloud');
const isMaterials = computed(() => area.value === 'materials');

const TITLE = { cloud: '云盘', docs: '文档管理库', materials: '素材库' };
const title = computed(() => TITLE[area.value] || '云盘');
const description = computed(() =>
  isMaterials.value
    ? '素材库支持三级分类，可直接插入研报、预览与批量下载。'
    : area.value === 'docs'
      ? '文档在组织内共享，仅创建人与管理员可修改。'
      : '云盘用于存放文件，支持文件夹与批量下载。'
);

const parentId = ref(null);
const selected = ref([]);
const busy = ref(false);

watch(area, () => {
  parentId.value = null;
  selected.value = [];
});

const items = computed(() => library.value.filter(item => item.area === area.value && item.parent_id === parentId.value));

const trail = computed(() => {
  const path = [];
  let cursor = library.value.find(item => item.id === parentId.value);
  while (cursor) {
    path.unshift(cursor);
    cursor = library.value.find(item => item.id === cursor.parent_id);
  }
  return path;
});

const allChecked = computed(() => items.value.length > 0 && items.value.every(item => selected.value.includes(item.id)));
const partChecked = computed(() => !allChecked.value && items.value.some(item => selected.value.includes(item.id)));

const ownerName = id => memberName(id);
const kindLabel = row => (row.kind === 'folder' ? '文件夹' : row.kind === 'document' ? '文档' : row.kind === 'image' ? '图片' : row.mime || '文件');

function toggle(id) {
  selected.value = selected.value.includes(id) ? selected.value.filter(item => item !== id) : [...selected.value, id];
}

function toggleAll(checked) {
  selected.value = checked ? items.value.map(item => item.id) : [];
}

function openFolder(id) {
  parentId.value = id;
  selected.value = [];
}

function goUp() {
  const parent = library.value.find(item => item.id === parentId.value);
  parentId.value = parent?.parent_id ?? null;
  selected.value = [];
}

function download(id) {
  window.open(downloadUrl(id), '_blank');
}

function batchDownload() {
  if (!selected.value.length) return;
  window.open('/api/library/zip?ids=' + selected.value.join(','), '_blank');
}

/* ---------- 新建文件夹 ---------- */
const folderVisible = ref(false);
const folderName = ref('');

function openFolderDialog() {
  folderName.value = '';
  folderVisible.value = true;
}

async function createFolder() {
  if (!folderName.value.trim()) return ElMessage.warning('请输入文件夹名称');
  busy.value = true;
  try {
    await api('library', {
      action: 'create',
      area: area.value,
      kind: 'folder',
      name: folderName.value.trim(),
      parent_id: parentId.value,
    });
    await refresh();
    folderVisible.value = false;
    ElMessage.success('文件夹已创建');
  } catch (error) {
    ElMessage.error(error.message || '创建失败');
  } finally {
    busy.value = false;
  }
}

/* ---------- 上传 ---------- */
const uploadVisible = ref(false);
const uploadKind = ref('file');
const uploadName = ref('');
const uploadBody = ref('');
const uploadFile = ref(null);
const fileInput = ref(null);

const uploadTitle = computed(() =>
  uploadKind.value === 'document' ? '新建文档' : uploadKind.value === 'image' ? '上传素材' : '上传文件'
);

function openUploadDialog() {
  uploadKind.value = isMaterials.value ? 'image' : area.value === 'docs' ? 'document' : 'file';
  uploadName.value = '';
  uploadBody.value = '';
  uploadFile.value = null;
  uploadVisible.value = true;
}

function onFileChange(event) {
  const file = event.target.files?.[0] || null;
  uploadFile.value = file;
  if (file && !uploadName.value) uploadName.value = file.name;
}

function readBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

async function submitUpload() {
  busy.value = true;
  try {
    const payload = {
      action: 'create',
      area: area.value,
      kind: uploadKind.value,
      name: uploadName.value.trim(),
      parent_id: parentId.value,
      body: uploadBody.value,
    };
    if (uploadKind.value !== 'document') {
      if (!uploadFile.value) throw new Error('请选择文件');
      if (uploadFile.value.size > 5_000_000) throw new Error('文件超过 5MB');
      payload.base64 = await readBase64(uploadFile.value);
      if (!payload.name) payload.name = uploadFile.value.name;
    }
    if (!payload.name) throw new Error('请填写名称');
    await api('library', payload);
    await refresh();
    uploadVisible.value = false;
    ElMessage.success('已保存');
  } catch (error) {
    ElMessage.error(error.message || '上传失败');
  } finally {
    busy.value = false;
  }
}

/* ---------- 编辑 ---------- */
const editVisible = ref(false);
const editItem = ref(null);
const editName = ref('');
const editParent = ref(null);
const editBody = ref('');

const editEditable = computed(() => {
  const item = editItem.value;
  return item && (item.owner === user.value.id || user.value.role === 'admin');
});

const folderOptions = computed(() => {
  const exclude = new Set([editItem.value?.id].filter(Boolean));
  return library.value.filter(item => item.area === area.value && item.kind === 'folder' && !exclude.has(item.id));
});

function openEditDialog(item) {
  editItem.value = item;
  editName.value = item.name;
  editParent.value = item.parent_id ?? null;
  editBody.value = item.body || '';
  editVisible.value = true;
}

async function saveEdit() {
  busy.value = true;
  try {
    await api('library', {
      action: 'edit',
      item_id: editItem.value.id,
      name: editName.value,
      parent_id: editParent.value ?? null,
      body: editBody.value,
    });
    await refresh();
    editVisible.value = false;
    ElMessage.success('已保存');
  } catch (error) {
    ElMessage.error(error.message || '保存失败');
  } finally {
    busy.value = false;
  }
}

async function removeItem() {
  try {
    await ElMessageBox.confirm('从列表移除该资料？该操作不可撤销。', '移除资料', {
      confirmButtonText: '移除', cancelButtonText: '取消', type: 'warning',
    });
  } catch {
    return;
  }
  busy.value = true;
  try {
    await api('library', { action: 'delete', item_id: editItem.value.id });
    selected.value = selected.value.filter(id => id !== editItem.value.id);
    await refresh();
    editVisible.value = false;
    ElMessage.success('已从列表移除');
  } catch (error) {
    ElMessage.error(error.message || '移除失败');
  } finally {
    busy.value = false;
  }
}

/* ---------- 批量 ---------- */
const moveVisible = ref(false);
const moveTarget = ref(null);

function openMoveDialog() {
  moveTarget.value = null;
  moveVisible.value = true;
}

async function submitMove() {
  busy.value = true;
  try {
    await api('library/batch', { action: 'move', ids: selected.value, parent_id: moveTarget.value ?? null });
    selected.value = [];
    await refresh();
    moveVisible.value = false;
    ElMessage.success('已移动');
  } catch (error) {
    ElMessage.error(error.message || '移动失败');
  } finally {
    busy.value = false;
  }
}

async function batchDelete() {
  try {
    await ElMessageBox.confirm(`确认移除选中的 ${selected.value.length} 项资料？`, '批量删除', {
      confirmButtonText: '移除', cancelButtonText: '取消', type: 'warning',
    });
  } catch {
    return;
  }
  try {
    await api('library/batch', { action: 'delete', ids: selected.value });
    const count = selected.value.length;
    selected.value = [];
    await refresh();
    ElMessage.success(`已移除 ${count} 项`);
  } catch (error) {
    ElMessage.error(error.message || '删除失败');
  }
}

/* ---------- 灯箱 ---------- */
const lightbox = ref(null);
const lightboxVisible = computed({
  get: () => Boolean(lightbox.value),
  set: value => {
    if (!value) lightbox.value = null;
  },
});
</script>
