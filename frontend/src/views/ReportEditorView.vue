<template>
  <div v-if="report" class="editor-page">
    <div class="edit-top">
      <div class="left">
        <el-button text @click="goBack">‹ 返回</el-button>
        <strong :title="title">{{ title || report.title }}</strong>
        <StatusTag :report="report" />
        <span class="caption">v{{ report.version }}</span>
        <el-tag v-if="dirty" size="small" type="warning" effect="plain" disable-transitions>未保存</el-tag>
      </div>
      <div class="actions">
        <el-button @click="openInfo">基础信息</el-button>
        <el-button v-if="shared && creator && editable" @click="openAssignments">章节分工</el-button>
        <el-button v-if="canUseSkills && editable && report.document" type="primary" plain @click="openSkillGenerator">AI / Skill 生成</el-button>
        <el-button v-if="report.document" @click="openPreview">预览</el-button>
        <el-button @click="openPrint">打印 / PDF</el-button>
        <el-button v-if="report.can_schedule" @click="openSchedule">定时发布</el-button>
        <el-button
          v-for="action in report.allowed_actions || []"
          :key="action"
          :type="['通过', '发布'].includes(action) ? 'primary' : 'default'"
          @click="openTransition(action)"
        >
          {{ actionLabel(action) }}
        </el-button>
      </div>
    </div>

    <div v-if="aiSetup && shared && creator && editable" class="panel" style="margin:12px 0;padding:16px;display:flex;align-items:center;gap:16px;flex-wrap:wrap">
      <div style="flex:1;min-width:240px"><b>先分配章节，再开始 AI 写作</b><p class="caption" style="margin:6px 0 0">在集中分工窗口批量分配各章负责人，也可单章调整。AI 可统一生成整篇候选，各章负责人分别核对采用。</p></div>
      <el-button @click="openAssignments">设置章节分工</el-button>
      <el-button type="primary" @click="beginSharedAI">完成分工，开始 AI 生成</el-button>
    </div>

    <!-- 旧版纯文本报告 -->
    <div v-if="!report.document" class="legacy-wrap">
      <div class="panel">
        <el-alert type="warning" :closable="false" show-icon style="margin-bottom: 14px">
          此报告为旧版纯文本正文，可继续使用，或转换为组件文档后按章节协作。
        </el-alert>
        <el-form label-width="88px">
          <el-form-item label="报告标题">
            <el-input v-model="legacy.title" :disabled="!legacyEditable" maxlength="200" />
          </el-form-item>
          <el-form-item label="正文">
            <el-input v-model="legacy.body" type="textarea" :rows="18" :disabled="!legacyEditable" />
          </el-form-item>
        </el-form>
        <div class="row" style="flex-wrap: wrap">
          <template v-if="legacyEditable">
            <el-button type="primary" :loading="busy" @click="saveLegacy">保存版本</el-button>
            <el-button @click="convertLegacy">转换为组件文档</el-button>
            <el-button @click="openTransition('提交')">提交审批</el-button>
          </template>
          <el-button @click="checkLegacy">规则检查</el-button>
          <el-button @click="openHistory">版本留痕</el-button>
          <el-button @click="openPrint">打印 / PDF</el-button>
        </div>
        <div v-if="checks.length" style="margin-top: 14px">
          <p v-for="(item, index) in checks" :key="index" style="margin-bottom: 6px">
            <el-tag size="small" :type="item.level === '错误' ? 'danger' : 'info'" disable-transitions>{{ item.level }}</el-tag>
            <span style="margin-left: 8px">{{ item.message }}</span>
          </p>
        </div>
      </div>
    </div>

    <!-- 组件化编辑器 -->
    <div v-else-if="draft" class="edit-body">
      <aside class="chapter-list">
        <div v-if="report.category_id" class="chapter-template">
          <span>分类模板：{{ templateInfo?.category_name || paperCfg.category_name || '当前分类' }}</span>
          <small>章节/审批 v{{ paperCfg.revision || '—' }}<template v-if="templateInfo"> · 最新 v{{ templateInfo.revision }}</template></small>
          <el-button v-if="creator && editable" link type="primary" :loading="templateLoading" :disabled="busy" @click="openTemplateSync">同步分类章节与审批</el-button>
        </div>
        <div class="chapter-list-head">
          <b>研报章节</b>
          <el-button v-if="creator && editable" type="primary" size="small" @click="chapterStructure('add')">添加章节</el-button>
        </div>
        <div class="chapter-items">
          <template v-for="node in chapterNodes" :key="node.key">
            <p v-if="node.groupStart" class="chapter-group">{{ node.group }}</p>
            <div
              class="chapter-card"
              :class="{ active: node.index === chapterIndex }"
              @click="selectChapter(node.index)"
            >
              <button class="name">
                <span v-if="node.label" class="chapter-no">{{ node.label }}</span>
                <span v-else-if="!node.item.title" class="chapter-no">第{{ node.index + 1 }}章</span>{{ node.item.title }}
              </button>
              <div class="chapter-card-foot">
                <span>{{ node.item.state || '未提交' }}</span>
                <el-tag v-if="(meta?.retained_section_ids || []).includes(node.item.id)" size="small" type="info">保留章节</el-tag>
                <el-button
                  v-if="creator && editable"
                  link
                  size="small"
                  title="章节设置"
                  @click.stop="openChapterSettings(node.index)"
                >
                  <el-icon><Setting /></el-icon>
                </el-button>
              </div>
              <div class="editors">{{ (node.item.editors || []).map(memberName).join('、') }}</div>
            </div>
          </template>
        </div>
      </aside>

      <section class="chapter-main">
        <div class="chapter-toolbar">
          <el-input v-model="title" class="title-input" placeholder="报告标题" :readonly="!editable" />
          <span class="sep"></span>
          <template v-if="sectionEditable">
            <el-button size="small" @click="insert('text')">＋ 文字</el-button>
            <el-button size="small" @click="insert('chart')">＋ 指标图表</el-button>
            <el-button size="small" @click="insert('table')">＋ 数据表格</el-button>
            <el-button size="small" @click="insert('image')">＋ 图片</el-button>
            <span class="sep"></span>
            <el-button size="small" @mousedown.prevent="exec('bold')"><b>B</b></el-button>
            <el-button size="small" @mousedown.prevent="exec('italic')"><i>I</i></el-button>
            <el-button size="small" @mousedown.prevent="exec('underline')"><u>U</u></el-button>
            <el-button size="small" @mousedown.prevent="exec('insertUnorderedList')">•</el-button>
            <el-button size="small" @click="openSkillGenerator(section.id)">AI 生成本章候选</el-button>
          </template>
          <span v-else class="caption">本章节不可编辑（已提交或未分配给你）</span>
          <span class="grow"></span>
          <span class="caption">本章 {{ section?.state || '未提交' }} · v{{ section?.revision }}</span>
          <template v-if="sectionEditable">
            <el-button size="small" @click="clearChapter">一键清空</el-button>
            <el-button size="small" :loading="busy" @click="save(true)">刷新数据并保存</el-button>
            <el-button size="small" type="primary" :loading="busy" @click="save(false)">保存本章</el-button>
          </template>
          <template v-if="shared && editable">
            <el-button v-if="section?.state !== '已提交'" size="small" @click="chapterState('submit')">提交章节</el-button>
            <el-button v-else size="small" @click="chapterState('reopen')">撤销提交</el-button>
          </template>
        </div>

        <div class="canvas-scroll">
          <div class="canvas-paper" :class="{ 'free-paper': draft.layout === 'free' }" :style="freePaperHeight ? { minHeight: freePaperHeight + 'px' } : null">
            <h3>
              <span v-if="section?.label" class="chapter-no">{{ section.label }}</span>
              <span v-else-if="!section?.title" class="chapter-no">第{{ chapterIndex + 1 }}章</span>{{ section?.title }}
              <span v-if="section?.required" class="caption">必填</span>
            </h3>
            <div v-if="section?.group" class="canvas-meta">
              <span class="canvas-note">板块：{{ section.type }}</span>
              <span v-if="sectionCommodities.length" class="canvas-commodities">
                关联品种
                <el-tag
                  v-for="item in sectionCommodities"
                  :key="item.id"
                  size="small"
                  effect="plain"
                  type="primary"
                  disable-transitions
                >{{ commodityLabel(item) }}</el-tag>
              </span>
            </div>
            <div :class="draft.layout === 'grid' ? 'canvas-grid' : ''">
              <ReportBlock
                v-for="item in visibleBlocks"
                :key="item.block.id + ':' + (section?.revision || 0)"
                :block="item.block"
                :index="item.index"
                :editable="sectionEditable"
                :free="draft.layout === 'free'"
                :grid="draft.layout === 'grid'"
                @action="name => blockAction(item.index, name)"
                @html="value => (item.block.html = value)"
              />
              <!-- 骨架提示只给「已关联品种 + 空章节」用；其余章节保持空白，不塞占位文案 -->
              <div v-if="!sectionHasContent && sectionCommodities.length && sectionSkeleton" class="skeleton-card">
                <p class="skeleton-title">当前章节暂无内容。</p>
                <p class="caption">按合集模板补一个骨架，再逐段填写：</p>
                <p class="skeleton-tags">
                  本章覆盖：<el-tag
                    v-for="item in sectionCommodities"
                    :key="item.id"
                    size="small"
                    effect="plain"
                    disable-transitions
                  >{{ commodityLabel(item) }}</el-tag>
                </p>
                <pre class="skeleton-body">{{ sectionSkeleton }}</pre>
                <el-button v-if="sectionEditable" size="small" type="primary" plain @click="insertSkeleton">插入骨架</el-button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <aside v-if="sectionEditable" class="resource-rail">
        <button v-for="item in inserts" :key="item.kind" type="button" @click="insert(item.kind)">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </button>
      </aside>
    </div>

    <!-- 这里说明报告存在、但组件文档尚未装进草稿（打开中或解析异常），
         不能再把「报告不存在」当兜底文案，否则一离开就误报。 -->
    <div v-else class="editor-hold">
      <el-icon class="is-loading" :size="22"><Loading /></el-icon>
      <p class="caption">正在打开文档…</p>
      <el-button text @click="goBack">返回研报中心</el-button>
    </div>

    <!-- 基础信息 -->
    <el-dialog v-model="infoVisible" title="报告基础信息" width="520px">
      <el-form label-width="88px">
        <el-form-item label="标题">
          <el-input v-model="info.title" :readonly="!infoEditable" maxlength="200" />
        </el-form-item>
        <el-form-item label="摘要">
          <el-input v-model="info.summary" type="textarea" :rows="3" :readonly="!infoEditable" />
        </el-form-item>
        <el-form-item label="署名作者">
          <el-select v-model="info.byline_id" :disabled="!infoEditable" style="width: 100%">
            <el-option v-for="item in bylineOptions" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="创建日期">
          <el-date-picker v-model="info.report_date" type="date" value-format="YYYY-MM-DD" :disabled="!infoEditable" style="width: 100%" />
        </el-form-item>
        <el-form-item label="公开发布">
          <el-select v-model="info.public" :disabled="!infoEditable" style="width: 100%">
            <el-option label="发布后公开" :value="true" />
            <el-option label="非公开" :value="false" />
          </el-select>
        </el-form-item>
        <p class="caption">分类、新增方式、协作方式、布局在创建后锁定。</p>
      </el-form>
      <template #footer>
        <el-button @click="infoVisible = false">关闭</el-button>
        <el-button v-if="infoEditable" type="primary" :loading="busy" @click="saveInfo">保存</el-button>
      </template>
    </el-dialog>

    <ChapterAssignments v-model="assignmentsVisible" :report="report" @saved="skillGeneratedSaved" />
    <AiReportGenerator v-model="skillGeneratorVisible" :report="report" :focus-section-id="skillFocusSection" @saved="skillGeneratedSaved" />

    <!-- 章节设置 -->
    <el-dialog v-model="chapterVisible" title="章节设置" width="620px">
      <p class="caption" style="margin-bottom: 12px">字段与分类模板对应，本次保存仅影响当前研报。</p>
      <el-form label-width="92px">
        <el-form-item label="一级章节"><el-input v-model="chapterForm.group" maxlength="60" placeholder="如：三、金融与商品基本面展望" /></el-form-item>
        <el-form-item label="章节编号"><el-input v-model="chapterForm.label" maxlength="20" placeholder="如 01、02、一、" /><p class="caption">可直接修改编号；上下移动章节时，同组的普通数字编号会按顺序整理。</p></el-form-item>
        <el-form-item label="章节名称">
          <el-input v-model="chapterForm.title" maxlength="100" placeholder="可留空，留空时版面只显示编号" />
        </el-form-item>
        <el-form-item label="类型"><el-input v-model="chapterForm.type" maxlength="80" placeholder="如：宏观、供需" /></el-form-item>
        <el-form-item label="必填"><el-switch v-model="chapterForm.required" /></el-form-item>
        <el-form-item label="默认文字"><el-input v-model="chapterForm.default" type="textarea" :rows="3" /><p class="caption">用于章节骨架和生成提示，不会自动覆盖正文。</p></el-form-item>
        <el-form-item label="编辑人">
          <el-checkbox-group v-model="chapterForm.editors">
            <el-checkbox v-for="id in chapterPeople" :key="id" :value="id">{{ memberName(id) }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="关联品种">
          <div style="width: 100%">
            <el-select
              v-model="chapterForm.commodity_ids"
              multiple
              filterable
              clearable
              collapse-tags
              collapse-tags-tooltip
              :max-collapse-tags="5"
              placeholder="选择本章覆盖的期货品种"
              style="width: 100%"
            >
              <el-option-group v-for="group in commodityGroups" :key="group.id" :label="group.name">
                <el-option
                  v-for="item in group.items"
                  :key="item.id"
                  :label="commodityLabel(item)"
                  :value="item.id"
                >
                  <span>{{ item.name }}</span>
                  <span class="caption" style="float: right">{{ item.code || '' }}</span>
                </el-option>
              </el-option-group>
            </el-select>
            <p class="caption">章节关联品种用于选题归属与打印页的品种索引；日度策略各板块已按合集对应好，清空表示不限品种。</p>
          </div>
        </el-form-item>
      </el-form>
      <div class="chapter-workflow"><h4>本研报审批流程</h4><p class="caption">审批按整篇研报执行，来自分类模板或匹配的审批流设置。</p>
        <ol><li v-for="(node, index) in paperCfg.workflow || []" :key="index"><b>{{ node.label }}</b> · {{ MODE_NAMES[node.mode] || node.mode }}<span class="caption"> · {{ node.users?.length ? node.users.map(memberName).join('、') : '该角色启用账号' }}</span></li></ol>
        <el-button v-if="user.role === 'admin' && report.category_id" link type="primary" @click="router.push({ path: '/config/categories', query: { category: String(report.category_id) } })">打开分类章节与审批配置</el-button>
      </div>
      <template #footer>
        <el-button @click="chapterVisible = false">取消</el-button>
        <el-button @click="chapterStructure('up')">上移</el-button>
        <el-button @click="chapterStructure('down')">下移</el-button>
        <el-button type="danger" plain @click="chapterStructure('remove')">移除</el-button>
        <el-button type="primary" :loading="busy" @click="saveChapterSettings">保存设置</el-button>
      </template>
    </el-dialog>

    <!-- 预览：直接加载「打印 / PDF」同一份服务端渲染，所见即所得。
         必须在弹窗完全展开后再灌 srcdoc：iframe 在 display:none 的容器里创建时
         内部文档不布局，A4 分页脚本会读到高度 0 而把所有内容塞进一页。 -->
    <el-dialog
      v-model="previewVisible"
      title="报告预览 · 与打印完全一致"
      width="900px"
      top="2vh"
      class="paper-dialog"
      @opened="loadPreview"
      @closed="previewHtml = ''"
    >
      <div class="preview-frame">
        <iframe v-if="previewHtml" :srcdoc="previewHtml" title="研报预览" />
        <div v-else class="preview-loading">
          <el-icon class="is-loading"><Loading /></el-icon>
          <span>正在按 A4 版式分页…</span>
        </div>
      </div>
      <template #footer>
        <el-button @click="previewVisible = false">关闭</el-button>
        <el-button type="primary" @click="openPrint">打印 / 保存 PDF</el-button>
      </template>
    </el-dialog>

    <!-- 流程操作 -->
    <el-dialog v-model="transitionVisible" :title="'流程操作 · ' + (transitionAction ? actionLabel(transitionAction) : '')" width="480px">
      <p class="caption" style="margin-bottom: 12px">当前状态：{{ statusText(report) }}；操作会绑定当前版本。</p>
      <el-input
        v-if="transitionAction === '退回'"
        v-model="transitionNote"
        type="textarea"
        :rows="4"
        placeholder="请填写退回原因（必填）"
      />
      <template #footer>
        <el-button @click="transitionVisible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="submitTransition">确认{{ transitionAction ? actionLabel(transitionAction) : '' }}</el-button>
      </template>
    </el-dialog>

    <!-- 定时发布 -->
    <el-dialog v-model="scheduleVisible" title="定时发布" width="420px">
      <el-date-picker v-model="scheduleAt" type="datetime" value-format="YYYY-MM-DDTHH:mm" placeholder="选择日期与时间" style="width: 100%" />
      <p class="caption" style="margin-top: 10px">到点由服务端自动发布并写入操作留痕；留空保存则取消定时。</p>
      <template #footer>
        <el-button @click="scheduleVisible = false">取消</el-button>
        <el-button type="primary" :loading="busy" @click="saveSchedule">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="templateSyncVisible" title="同步分类章节与审批" width="680px" :close-on-click-modal="false">
      <template v-if="templateInfo">
        <p>{{ templateInfo.category_name }} · v{{ templateInfo.revision }}</p>
        <el-alert type="info" :closable="false" show-icon title="同步仅更新当前研报的章节和审批配置，保留正文与版式。同步后章节恢复未提交，需要重新确认。" style="margin: 14px 0" />
        <p>新增 {{ templateInfo.added?.length || 0 }} 章，更新 {{ templateInfo.updated?.length || 0 }} 章，移除空章节 {{ templateInfo.removed_empty?.length || 0 }} 章。</p>
        <p v-if="templateInfo.retained?.length">已有内容或自建章节将保留：{{ templateInfo.retained.map(item => item.title || item.label || '未命名章节').join('、') }}</p>
        <h4>最新章节顺序</h4><ol><li v-for="item in templateInfo.sections" :key="item.id">{{ item.group }} / {{ item.label }} {{ item.title || '未命名章节' }} <small v-if="item.required">（必填）</small></li></ol>
        <h4>审批流程{{ templateInfo.workflow_changed ? '（将更新）' : '' }}</h4><p>{{ (templateInfo.workflow || []).map(node => `${node.label}（${MODE_NAMES[node.mode] || node.mode}）`).join(' → ') }} → 发布</p>
      </template>
      <template #footer><el-button @click="templateSyncVisible = false">取消</el-button><el-button type="primary" :loading="busy" :disabled="!templateInfo?.can_sync" @click="syncTemplate">确认同步当前研报</el-button></template>
    </el-dialog>

    <!-- 插入指标 -->
    <el-dialog v-model="pickerVisible" :title="pickerKind === 'chart' ? '插入指标图表' : '插入数据表格'" width="520px">
      <el-select v-model="pickerIndex" :disabled="inserting" style="width: 100%" placeholder="选择指标">
        <el-option
          v-for="(item, index) in indicators"
          :key="index"
          :label="`${item.source} / ${item.indicator} · ${item.unit} · 最新 ${item.latest}`"
          :value="index"
        />
      </el-select>
      <p class="caption" style="margin-top: 10px">插入后立即显示指标数据；保存后固定为研报快照，之后可通过「刷新数据并保存」更新。</p>
      <template #footer>
        <el-button @click="pickerVisible = false">取消</el-button>
        <el-button type="primary" :loading="inserting" :disabled="inserting" @click="confirmInsert">插入当前章节</el-button>
      </template>
    </el-dialog>

    <!-- 插入图片 -->
    <el-dialog v-model="imageVisible" title="素材库 · 插入图片" width="780px" top="6vh">
      <div v-if="imageItems.length" class="lib-grid">
        <div v-for="item in imageItems" :key="item.id" class="lib-card">
          <div class="thumb"><img :src="fileUrl(item.id)" :alt="item.name" /></div>
          <div class="meta"><p :title="item.name">{{ item.name }}</p></div>
          <div class="ops"><el-button link type="primary" size="small" @click="pickImage(item)">插入</el-button></div>
        </div>
      </div>
      <el-empty v-else description="素材库暂无图片，请先在素材库上传" :image-size="70" />
    </el-dialog>

    <!-- 版本留痕 -->
    <el-dialog v-model="historyVisible" title="版本与留痕" width="760px" top="5vh">
      <h3>操作记录</h3>
      <p v-for="(item, index) in history.events" :key="'e' + index" style="margin-bottom: 8px">
        <b>{{ item.actor }} · {{ item.action }}</b> · v{{ item.version }}<br />
        <span class="caption">{{ localTime(item.at) }}</span><br />
        <span class="caption">{{ item.note }}</span>
      </p>
      <h3 style="margin-top: 16px">历史版本</h3>
      <el-collapse>
        <el-collapse-item v-for="item in history.versions" :key="item.id" :name="item.id" :title="`v${item.version} · ${item.actor} · ${localTime(item.at)}`">
          <pre style="white-space: pre-wrap; font-size: 12px">{{ item.body }}</pre>
        </el-collapse-item>
      </el-collapse>
    </el-dialog>
  </div>

  <el-result
    v-else
    icon="warning"
    title="报告不存在或无权访问"
    sub-title="报告可能已被删除，或当前账号没有查看权限。"
  >
    <template #extra>
      <el-button type="primary" @click="router.push('/reports')">返回研报中心</el-button>
    </template>
  </el-result>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Document, Grid, Loading, Picture, Setting, TrendCharts } from '@element-plus/icons-vue';
import ReportBlock from '../components/ReportBlock.vue';
import StatusTag from '../components/StatusTag.vue';
import AiReportGenerator from '../components/AiReportGenerator.vue';
import ChapterAssignments from '../components/ChapterAssignments.vue';
import { api, fileUrl, printUrl } from '../api';
import {
  authors, commodities, library, memberName, indicators, refresh, reportById, user,
} from '../store/session';
import { localTime, escapeHtml, makeId, parseJSON, statusText, today, MODE_NAMES } from '../utils/format';

const assignmentsVisible = ref(false);
function openAssignments(){
  if(dirty.value)return ElMessage.warning('请先保存当前修改，再调整章节分工');
  assignmentsVisible.value = true;
}
const skillGeneratorVisible = ref(false);
const aiSetup = ref(false);
function beginSharedAI() {
  if (dirty.value) return ElMessage.warning('请先保存当前修改，再开始 AI 生成');
  openSkillGenerator(); aiSetup.value = false;
  router.replace({path:route.path,query:{...route.query,ai:undefined}});
}
const skillFocusSection = ref('');
function openSkillGenerator(sectionId) {
  if (dirty.value) return ElMessage.warning('请先保存当前修改，再生成 Skill 候选');
  skillFocusSection.value = typeof sectionId === 'string' ? sectionId : '';
  skillGeneratorVisible.value = true;
}
async function skillGeneratedSaved() { await refresh(); initDraft(true); }

const route = useRoute();
const router = useRouter();

const report = computed(() => reportById(route.params.id));
const meta = computed(() => parseJSON(report.value?.metadata, null));
const paperCfg = computed(() => parseJSON(report.value?.config_snapshot, {}) || {});
const shared = computed(() => meta.value?.collaboration === 'shared');
const creator = computed(() => report.value?.author === user.value.id);
const canUseSkills = computed(() => ['admin','researcher'].includes(user.value.role) && (creator.value || (meta.value?.collaborators || []).includes(user.value.id)));
const editable = computed(
  () => Boolean(report.value) && ['草稿', '已退回'].includes(report.value.status) &&
    (shared.value ? true : report.value.author === user.value.id)
);
const legacyEditable = computed(() => creator.value && ['草稿', '已退回'].includes(report.value?.status));

const draft = ref(null);
const title = ref('');
const chapterIndex = ref(0);
const busy = ref(false);
const dirty = ref(false);
const legacy = reactive({ title: '', body: '' });
let draftId = null;
let draftVersion = 0;
let snapshot = '';

const section = computed(() => draft.value?.sections?.[chapterIndex.value] || null);
const freePaperHeight = computed(() => draft.value?.layout === 'free'
  ? Math.max(620, ...(section.value?.blocks || []).map((block, index) => (block.y ?? 70 + index * 230) + (block.height ?? 210) + 40)) : null);
const sectionEditable = computed(() => (section.value ? chapterEditable(section.value) : false));

/* 空组件判定：预览与「本章暂无内容」提示共用 */
const isBlankBlock = block => {
  if (block.type === 'text') {
    const plain = String(block.html ?? block.text ?? '')
      .replace(/<[^>]+>/g, '')
      .replace(/&nbsp;/g, ' ')
      .trim();
    return !plain;
  }
  if (block.type === 'image') return !block.asset_id;
  return !(block.data && block.data.length);
};

const sectionHasContent = computed(() => (section.value?.blocks || []).some(block => !isBlankBlock(block)));

/* 空文字块不渲染：空章节的版面保持干净，要写字从工具栏「＋文字」插入。
   刚插入、还没输入文字的那一块临时保留（pendingBlockId），否则点完按钮看不到输入框。 */
const pendingBlockId = ref('');
const visibleBlocks = computed(() =>
  (section.value?.blocks || [])
    .map((block, index) => ({ block, index }))
    .filter(item => !(item.block.type === 'text' && isBlankBlock(item.block) && item.block.id !== pendingBlockId.value))
);

/* 侧栏按合集体例分组：一级章节（一、二、三）下挂 01…06 板块。 */
const chapterNodes = computed(() => {
  let group = null;
  return (draft.value?.sections || []).map((item, index) => {
    const current = item.group || '';
    const groupStart = Boolean(current) && current !== group;
    group = current;
    // 名称为空时只显示编号；两者都没配时由模板退回章节序号，避免出现空白卡片
    return { key: item.id, index, item, label: item.label || '', group: current, groupStart };
  });
});

/* 章节骨架来自创建时的配置快照，只在空章节里作为提示，不写入正文。 */
const sectionSkeleton = computed(() => {
  const target = section.value;
  if (!target) return '';
  const list = paperCfg.value?.sections || [];
  return list.find(item => item.id === target.id)?.default || '';
});

function insertSkeleton() {
  if (!sectionEditable.value || !sectionSkeleton.value) return;
  const text = sectionSkeleton.value;
  // 合集体例：整行「▍品种：一句话观点」作小标题，直接加粗
  const html = text
    .split('\n')
    .map(line => (line.startsWith('▍') ? `<b>${escapeHtml(line)}</b>` : escapeHtml(line)))
    .join('<br>');
  const blocks = section.value.blocks;
  const empty = blocks.findIndex(block => block.type === 'text' && isBlankBlock(block));
  // 复用空块的位置但换新 id：RichText 只在挂载时写 innerHTML，id 不变就不会重渲染
  const block = { id: makeId(), type: 'text', span: 12, title: '', text, html };
  if (empty >= 0) blocks.splice(empty, 1, block);
  else blocks.push(block);
}

const inserts = [
  { kind: 'text', label: '文字', icon: Document },
  { kind: 'chart', label: '图表', icon: TrendCharts },
  { kind: 'table', label: '表格', icon: Grid },
  { kind: 'image', label: '图片', icon: Picture },
];

const enabledCommodities = computed(() => commodities.value.filter(item => item.enabled));

/* 品种库是「板块 → 期货品种（含合约代码）」两级，章节关联的品种按板块分组展示。 */
const commodityGroups = computed(() => {
  const list = enabledCommodities.value;
  return list
    .filter(item => !item.parent_id)
    .map(sector => ({ id: sector.id, name: sector.name, items: list.filter(item => item.parent_id === sector.id) }))
    .filter(group => group.items.length);
});

const sectionCommodities = computed(() =>
  (section.value?.commodity_ids || [])
    .map(id => commodities.value.find(item => item.id === id))
    .filter(Boolean)
    .map(item => ({ id: item.id, name: item.name, code: item.code || '' }))
);

const commodityLabel = item => (item.code ? `${item.name} ${item.code}` : item.name);

/* ---------- 草稿生命周期 ---------- */

function initDraft(force = false) {
  const current = report.value;
  if (!current?.document) {
    draft.value = null;
    return;
  }
  if (!force && draftId === current.id && draftVersion === current.version) return;
  const same = draftId === current.id;
  draft.value = JSON.parse(current.document);
  title.value = current.title;
  draftId = current.id;
  draftVersion = current.version;
  if (!same || chapterIndex.value >= draft.value.sections.length) chapterIndex.value = 0;
  snapshot = JSON.stringify({ title: title.value, doc: draft.value });
  dirty.value = false;
}

watch(
  () => [report.value?.id, report.value?.version],
  () => {
    if (!report.value) return;
    initDraft(false);
    legacy.title = report.value.title || '';
    legacy.body = report.value.body || '';
  },
  { immediate: true }
);

watch([title, draft], () => {
  if (!draft.value) return;
  dirty.value = JSON.stringify({ title: title.value, doc: draft.value }) !== snapshot;
}, { deep: true });

function chapterEditable(item) {
  const current = report.value;
  if (!current || !['草稿', '已退回'].includes(current.status)) return false;
  const info = parseJSON(current.metadata, null);
  if (!info || info.collaboration !== 'shared') return current.author === user.value.id;
  return item.state !== '已提交' && (item.editors || []).includes(user.value.id);
}

/* 离开确认只问一次：goBack() 里已经问过，跳转时路由守卫不能再拦一遍，
   否则会连弹两次「未保存的修改」。 */
let leaving = false;

const canLeave = async () => {
  if (!dirty.value) return true;
  try {
    await ElMessageBox.confirm('当前章节存在未保存修改，离开将丢失这些改动。', '未保存的修改', {
      confirmButtonText: '仍然离开', cancelButtonText: '继续编辑', type: 'warning',
    });
    return true;
  } catch {
    return false;
  }
};

onBeforeRouteLeave(() => (leaving ? true : canLeave()));

function beforeUnload(event) {
  if (!dirty.value) return;
  event.preventDefault();
  event.returnValue = '';
}
onMounted(() => {
  window.addEventListener('beforeunload', beforeUnload);
  if (route.query?.ai === 'setup' && shared.value && creator.value && editable.value) {
    aiSetup.value = true;
  } else if (route.query?.ai === '1' && canUseSkills.value && editable.value) {
    openSkillGenerator();
    router.replace({path:route.path,query:{...route.query,ai:undefined}});
  }
});
onBeforeUnmount(() => window.removeEventListener('beforeunload', beforeUnload));

async function goBack() {
  if (!(await canLeave())) return;
  // 不能提前把 draft 置空：一置空页面立刻退化成错误态，路由却还没跳走
  leaving = true;
  try {
    await router.push('/reports');
  } finally {
    leaving = false;
  }
}

function selectChapter(index) {
  chapterIndex.value = index;
  pendingBlockId.value = '';
}

/* ---------- 保存与章节操作 ---------- */

const actionLabel = action => ({ 提交: '提交审批', 通过: '审核通过', 退回: '退回', 发布: '发布' }[action] || action);

async function save(refreshData = false) {
  const current = report.value;
  if (!current || !draft.value) return;
  busy.value = true;
  try {
    if (shared.value) {
      const target = section.value;
      await api('chapter/save', {
        id: current.id,
        section_id: target.id,
        revision: target.revision,
        blocks: target.blocks,
        refresh: refreshData,
      });
    } else {
      await api('personal-save', {
        id: current.id,
        version: current.version,
        document: draft.value,
        refresh: refreshData,
      });
    }
    await refresh();
    initDraft(true);
    ElMessage.success(refreshData ? '数据已刷新并保存' : '已保存');
  } catch (error) {
    ElMessage.error(error.message || '保存失败');
  } finally {
    busy.value = false;
  }
}

async function chapterState(action) {
  if (dirty.value) return ElMessage.warning('请先保存本章');
  busy.value = true;
  try {
    await api('chapter/' + action, {
      id: report.value.id,
      section_id: section.value.id,
      revision: section.value.revision,
    });
    await refresh();
    initDraft(true);
    ElMessage.success(action === 'submit' ? '章节已提交并锁定' : '已撤销提交');
  } catch (error) {
    ElMessage.error(error.message || '操作失败');
  } finally {
    busy.value = false;
  }
}

async function chapterStructure(action, payload = {}) {
  if (dirty.value) return ElMessage.warning('请先保存当前章节');
  busy.value = true;
  const selectedId = section.value?.id;
  try {
    await api('chapters', {
      id: report.value.id,
      version: report.value.version,
      section_id: section.value?.id,
      action,
      ...payload,
    });
    chapterVisible.value = false;
    await refresh();
    initDraft(true);
    const selected = draft.value.sections.findIndex(item => item.id === selectedId);
    chapterIndex.value = action === 'add' ? draft.value.sections.length - 1 : selected >= 0 ? selected : Math.min(chapterIndex.value, draft.value.sections.length - 1);
    ElMessage.success('章节结构已更新');
  } catch (error) {
    ElMessage.error(error.message || '操作失败');
  } finally {
    busy.value = false;
  }
}

function clearChapter() {
  section.value.blocks = [];
}

/* ---------- 组件操作 ---------- */

function blockAction(index, action) {
  const blocks = section.value.blocks;
  if (action === 'remove') blocks.splice(index, 1);
  if (action === 'span') blocks[index].span = blocks[index].span === 6 ? 12 : 6;
  if (action === 'up' && index > 0) [blocks[index - 1], blocks[index]] = [blocks[index], blocks[index - 1]];
  if (action === 'down' && index < blocks.length - 1) [blocks[index + 1], blocks[index]] = [blocks[index], blocks[index + 1]];
}

const pickerVisible = ref(false);
const pickerKind = ref('chart');
const pickerIndex = ref(0);
const inserting = ref(false);
let insertRequest = 0;
watch(pickerVisible, visible => { if (!visible) { insertRequest++; inserting.value = false; } });
onBeforeUnmount(() => { insertRequest++; });
const imageVisible = ref(false);
const imageItems = computed(() => library.value.filter(item => item.kind === 'image'));

function insert(kind) {
  if (kind === 'text') {
    const block = { id: makeId(), type: 'text', span: 12, title: '', text: '', html: '' };
    appendBlock(block);
    // 空块默认不渲染，刚插入的这块要留着并聚焦，用户才能直接写字
    pendingBlockId.value = block.id;
    nextTick(() => {
      const host = document.querySelector(`[data-block-id="${block.id}"] .rich-area`);
      if (host) host.focus();
    });
    return;
  }
  if (kind === 'image') {
    imageVisible.value = true;
    return;
  }
  if (!indicators.value.length) return ElMessage.warning('暂无可用指标，请先在数据录入中同步或导入数据');
  insertRequest++;
  pickerKind.value = kind;
  pickerIndex.value = 0;
  pickerVisible.value = true;
}

function appendBlock(block, target = section.value) {
  const blocks = target.blocks;
  if (draft.value.layout === 'free') {
    const bottom = Math.max(54, ...blocks.map((item, index) => (item.y ?? 70 + index * 230) + (item.height ?? 210)));
    Object.assign(block, { x: 30, y: blocks.length ? bottom + 16 : 70, width: 620,
      height: block.type === 'table' ? 420 : block.type === 'chart' ? 300 : 210 });
  }
  blocks.push(block);
}

async function confirmInsert() {
  if (inserting.value || !sectionEditable.value) return;
  const item = indicators.value[pickerIndex.value];
  if (!item) return ElMessage.warning('请选择指标');
  const target = section.value;
  const document = draft.value;
  const kind = pickerKind.value;
  const request = ++insertRequest;
  inserting.value = true;
  try {
    const query = new URLSearchParams({ source: item.source, indicator: item.indicator });
    const result = await api(`data/series?${query.toString()}`);
    if (request !== insertRequest || !pickerVisible.value || section.value !== target || draft.value !== document || !sectionEditable.value) return;
    const rows = (result.points || []).slice(-500).map(point => ({ source: item.source, indicator: item.indicator,
      date: point.date, value: point.value, unit: point.unit || result.unit || item.unit || '' }));
    if (!rows.length) return ElMessage.warning('该指标暂无数据，请刷新指标或选择其他指标');
    if (new Set(rows.map(row => row.unit)).size > 1) return ElMessage.warning('该指标存在不同单位，请先统一数据单位');
    appendBlock({ id: makeId(), type: kind, span: 12, title: item.indicator, source: item.source,
      indicator: item.indicator, data: rows, preview: true, refreshed_at: '' });
    pickerVisible.value = false;
    ElMessage.success('已插入并显示数据，保存后固定为研报快照');
  } catch (error) { if (request === insertRequest) ElMessage.error(error.message || '加载指标数据失败，请重试'); }
  finally { if (request === insertRequest) inserting.value = false; }
}

function pickImage(item) {
  appendBlock({
    id: makeId(),
    type: 'image',
    span: 12,
    title: item.name,
    asset_id: item.id,
    asset_name: item.name,
  });
  imageVisible.value = false;
}

function exec(command) {
  document.execCommand(command, false, null);
}

/* ---------- 弹窗：基础信息 ---------- */

const infoVisible = ref(false);
const previewVisible = ref(false);
const previewHtml = ref('');

function openPreview() {
  previewVisible.value = true;
}

/* 由 el-dialog 的 opened 事件驱动：此时容器已完成布局，iframe 一创建就有真实高度。 */
async function loadPreview() {
  previewHtml.value = '';
  try {
    const response = await fetch('/api/report-preview', {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: report.value.id, document: draft.value, title: title.value }),
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || '预览生成失败');
    }
    previewHtml.value = await response.text();
  } catch (error) {
    ElMessage.error(error.message || '预览生成失败');
    previewVisible.value = false;
  }
}
const info = reactive({ title: '', summary: '', byline_id: null, report_date: today(), public: true });
const infoEditable = computed(() => creator.value && ['草稿', '已退回'].includes(report.value?.status));
const bylineOptions = computed(() => {
  const kind = report.value?.kind;
  const current = meta.value?.byline_id;
  return authors.value.filter(item => {
    if (!item.enabled) return item.id === current;
    try {
      return JSON.parse(item.types || '[]').includes(kind) || item.id === current;
    } catch {
      return item.id === current;
    }
  });
});

function openInfo() {
  const current = report.value;
  info.title = current.title;
  info.summary = meta.value?.summary || '';
  info.byline_id = meta.value?.byline_id || bylineOptions.value[0]?.id || null;
  info.report_date = meta.value?.report_date || today();
  info.public = meta.value?.public ?? true;
  infoVisible.value = true;
}

async function saveInfo() {
  if (dirty.value) return ElMessage.warning('请先关闭弹窗并保存当前章节');
  busy.value = true;
  try {
    await api('report-info', {
      id: report.value.id,
      version: report.value.version,
      title: info.title,
      summary: info.summary,
      byline_id: info.byline_id,
      report_date: info.report_date,
      public: info.public,
    });
    await refresh();
    initDraft(true);
    infoVisible.value = false;
    ElMessage.success('基础信息已保存');
  } catch (error) {
    ElMessage.error(error.message || '保存失败');
  } finally {
    busy.value = false;
  }
}

/* ---------- 分类模板联动 ---------- */
const templateInfo = ref(null);
const templateLoading = ref(false);
const templateSyncVisible = ref(false);
async function loadTemplate() {
  if (!report.value?.category_id) return false;
  templateLoading.value = true;
  try { templateInfo.value = await api(`report-template/${report.value.id}`); return true; }
  catch (error) { ElMessage.error(error.message || '读取分类模板失败'); return false; }
  finally { templateLoading.value = false; }
}
watch(() => report.value?.id, () => { templateInfo.value = null; if (report.value?.category_id && creator.value && editable.value) loadTemplate(); }, { immediate: true });
async function openTemplateSync() {
  if (dirty.value) return ElMessage.warning('请先保存当前章节，再同步分类配置');
  if (await loadTemplate()) templateSyncVisible.value = true;
}
async function syncTemplate() {
  if (!templateInfo.value?.can_sync || busy.value) return;
  busy.value = true;
  try {
    const result = await api('report-template-sync', { id: report.value.id, version: templateInfo.value.report_version, token: templateInfo.value.token });
    await refresh(); initDraft(true); templateSyncVisible.value = false; await loadTemplate();
    ElMessage.success(result.changed === false ? '当前研报已是最新模板' : '已同步分类章节与审批，正文已保留');
  } catch (error) { ElMessage.error(error.message || '同步失败，请重新预览后重试'); }
  finally { busy.value = false; }
}

/* ---------- 弹窗：章节设置 ---------- */

const chapterVisible = ref(false);
const chapterForm = reactive({ index: 0, title: '', group: '', label: '', type: '', required: false, default: '', editors: [], commodity_ids: [] });
const chapterPeople = computed(() => [report.value?.author, ...(meta.value?.collaborators || [])].filter(Boolean));

function openChapterSettings(index) {
  const item = draft.value.sections[index];
  chapterIndex.value = index;
  chapterForm.index = index;
  chapterForm.title = item.title || '';
  const definition = paperCfg.value.sections?.find(node => node.id === item.id) || {};
  chapterForm.group = item.group ?? definition.group ?? '';
  chapterForm.label = item.label ?? definition.label ?? '';
  chapterForm.type = item.type ?? definition.type ?? '';
  chapterForm.required = Boolean(item.required);
  chapterForm.default = definition.default || '';
  chapterForm.editors = [...(item.editors || [])];
  chapterForm.commodity_ids = [...(item.commodity_ids || [])];
  chapterVisible.value = true;
}

async function saveChapterSettings() {
  chapterIndex.value = chapterForm.index;
  await chapterStructure('edit', {
    title: chapterForm.title,
    group: chapterForm.group, label: chapterForm.label, type: chapterForm.type, required: chapterForm.required, default: chapterForm.default,
    editors: chapterForm.editors,
    commodity_ids: chapterForm.commodity_ids,
  });
}

/* ---------- 弹窗：流程 / 定时 ---------- */

const transitionVisible = ref(false);
const transitionAction = ref('');
const transitionNote = ref('');
const scheduleVisible = ref(false);
const scheduleAt = ref('');

function openTransition(action) {
  if (dirty.value) return ElMessage.warning('请先保存修改，再操作流程');
  transitionAction.value = action;
  transitionNote.value = '';
  transitionVisible.value = true;
}

async function submitTransition() {
  if (transitionAction.value === '退回' && !transitionNote.value.trim()) {
    return ElMessage.warning('请填写退回原因');
  }
  busy.value = true;
  try {
    await api('transition', {
      id: report.value.id,
      action: transitionAction.value,
      note: transitionNote.value,
      expected_status: report.value.status,
      expected_workflow: report.value.workflow_state,
    });
    await refresh();
    initDraft(true);
    transitionVisible.value = false;
    ElMessage.success('流程已更新');
  } catch (error) {
    ElMessage.error(error.message || '操作失败');
  } finally {
    busy.value = false;
  }
}

function openSchedule() {
  scheduleAt.value = '';
  scheduleVisible.value = true;
}

async function saveSchedule() {
  busy.value = true;
  try {
    await api('report-schedule', { id: report.value.id, at: scheduleAt.value || '' });
    await refresh();
    scheduleVisible.value = false;
    ElMessage.success(scheduleAt.value ? '已设置定时发布' : '已取消定时发布');
  } catch (error) {
    ElMessage.error(error.message || '设置失败');
  } finally {
    busy.value = false;
  }
}

function openPrint() {
  window.open(printUrl(report.value.id), '_blank');
}

/* ---------- 旧版纯文本报告 ---------- */

const checks = ref([]);

async function saveLegacy() {
  busy.value = true;
  try {
    await api('save', { id: report.value.id, version: report.value.version, title: legacy.title, body: legacy.body });
    await refresh();
    ElMessage.success('版本已保存');
  } catch (error) {
    ElMessage.error(error.message || '保存失败');
  } finally {
    busy.value = false;
  }
}

async function convertLegacy() {
  busy.value = true;
  try {
    await api('convert', { id: report.value.id });
    await refresh();
    initDraft(true);
    ElMessage.success('已转换为组件文档');
  } catch (error) {
    ElMessage.error(error.message || '转换失败');
  } finally {
    busy.value = false;
  }
}

async function checkLegacy() {
  try {
    const result = await api('check', { id: report.value.id });
    checks.value = result.checks || [];
  } catch (error) {
    ElMessage.error(error.message || '检查失败');
  }
}

const historyVisible = ref(false);
const history = reactive({ events: [], versions: [] });

async function openHistory() {
  try {
    const result = await api('history/' + report.value.id);
    history.events = result.events || [];
    history.versions = result.versions || [];
    historyVisible.value = true;
  } catch (error) {
    ElMessage.error(error.message || '读取失败');
  }
}
</script>

<style scoped>
.chapter-template { padding: 12px; border-bottom: 1px solid var(--el-border-color-lighter); font-size: 12px; }
.chapter-template span, .chapter-template small { display: block; overflow-wrap: anywhere; margin-bottom: 5px; }
.chapter-template small { color: var(--el-text-color-secondary); }
.chapter-workflow { padding: 12px; background: var(--el-fill-color-light); border-radius: 6px; }
.chapter-workflow h4 { margin: 0 0 8px; }
.chapter-workflow ol { margin: 10px 0; padding-left: 20px; line-height: 1.9; }
</style>
