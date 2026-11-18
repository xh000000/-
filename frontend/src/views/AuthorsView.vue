<template>
  <div>
    <PageHead title="作者管理" description="署名作者用于研报版头与合规留痕；停用后不能再被选为署名，历史报告不受影响。">
      <el-button type="primary" @click="openDialog(null)">添加作者</el-button>
    </PageHead>

    <div class="panel">
      <el-table :data="authors" empty-text="暂无作者">
        <el-table-column label="作者 / 团队" min-width="200" prop="name" />
        <el-table-column label="适用报告类型" min-width="300">
          <template #default="{ row }">
            <el-tag
              v-for="one in parseTypes(row.types)"
              :key="one"
              size="small"
              effect="plain"
              class="tag-gap"
              disable-transitions
            >{{ one }}</el-tag>
            <span v-if="!parseTypes(row.types).length" class="caption">—</span>
          </template>
        </el-table-column>
        <el-table-column label="资格证号" width="130">
          <template #default="{ row }">{{ row.license || '—' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="96">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small" disable-transitions>
              {{ row.enabled ? '启用' : '停用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDialog(row)">编辑</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-dialog v-model="visible" :title="form.id ? '编辑作者' : '添加作者'" width="480px" @closed="reset">
      <el-form label-width="96px" @submit.prevent="save">
        <el-form-item label="姓名 / 团队">
          <el-input v-model="form.name" maxlength="40" placeholder="如：黑色研究组" />
        </el-form-item>
        <el-form-item label="适用类型">
          <el-checkbox-group v-model="form.types">
            <el-checkbox v-for="one in TYPE_OPTIONS" :key="one" :value="one">{{ one }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="资格证号">
          <el-input v-model="form.license" maxlength="40" placeholder="如 Z0024397，打印署名时一并输出" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <p class="caption">至少选择一种报告类型；名称不可与已有作者重复。</p>
      <template #footer>
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import PageHead from '../components/PageHead.vue';
import { api } from '../api';
import { authors, refresh } from '../store/session';
import { parseJSON } from '../utils/format';

const TYPE_OPTIONS = ['日报', '周报', '专题', '调研纪要'];

const busy = ref(false);
const visible = ref(false);
const form = reactive({ id: null, name: '', license: '', types: [...TYPE_OPTIONS], enabled: true });

const parseTypes = value => {
  const list = Array.isArray(value) ? value : parseJSON(value, []);
  return Array.isArray(list) ? list : [];
};

function openDialog(row) {
  form.id = row?.id ?? null;
  form.name = row?.name || '';
  form.license = row?.license || '';
  form.types = row ? parseTypes(row.types) : [...TYPE_OPTIONS];
  form.enabled = row ? Boolean(row.enabled) : true;
  visible.value = true;
}

function reset() {
  form.id = null;
  form.name = '';
  form.license = '';
  form.types = [...TYPE_OPTIONS];
  form.enabled = true;
}

async function save() {
  const name = form.name.trim();
  if (!name) return ElMessage.warning('请填写作者名称');
  if (!form.types.length) return ElMessage.warning('至少选择一种适用报告类型');
  busy.value = true;
  try {
    await api('catalog', { kind: 'authors', id: form.id, name, license: form.license.trim(), types: form.types, enabled: form.enabled });
    await refresh();
    visible.value = false;
    ElMessage.success('作者已保存');
  } catch (error) {
    ElMessage.error(error.message || '保存失败');
  } finally {
    busy.value = false;
  }
}
</script>

<style scoped>
.tag-gap { margin-right: 6px; }
</style>
