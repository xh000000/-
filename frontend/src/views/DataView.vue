<template>
  <div class="data-entry-page">
    <PageContainer title="数据录入">
      <template #actions>
        <el-button v-if="canConfig" type="primary" @click="openSource(null)">新增数据源</el-button>
        <el-button @click="openCsv">导入 CSV</el-button>
        <el-button @click="openSyncRecords">同步记录</el-button>
        <el-button :loading="loading" @click="load">刷新</el-button>
      </template>

    <div class="entry-section-head">
      <h3>数据源管理</h3>
      <span class="hint entry-meta">{{ sources.filter(item => item.enabled).length }}/{{ sources.length }} 启用 · {{ configs.length }} 项同步配置 · 累计 {{ totalRows.toLocaleString() }} 数据点</span>
    </div>
    <div class="card-grid src-grid">
      <div v-for="source in sources" :key="source.key" class="panel src-card" :class="{ 'source-clickable': canConfig }" @click="canConfig && openSourceSettings(source)">
        <button v-if="canConfig" class="source-config-link" type="button" @click.stop="openSourceSettings(source)" :aria-label="`配置${source.name}`">配置</button>
        <div class="src-head">
          <div>
            <div class="source-identity"><span class="source-avatar">{{ source.name?.slice(0, 1) }}</span><h3>{{ source.name }}</h3></div>
            <p class="caption">{{ source.product || '—' }}</p>
          </div>
          <div class="row" style="gap: 6px">
            <el-tag v-if="!source.enabled" size="small" type="info" effect="plain" disable-transitions>已停用</el-tag>
            <el-tag :type="sourceStatus(source).type" size="small" disable-transitions>
              {{ sourceStatus(source).label }}
            </el-tag>
          </div>
        </div>
        <div v-if="healthOf(source)" class="src-health" :class="'health-' + healthOf(source).level">
          <span class="health-dot" :class="'dot-' + healthOf(source).level" />
          <span>成功率 <b>{{ healthOf(source).success_rate === null ? '—' : healthOf(source).success_rate + '%' }}</b></span>
          <span>{{ healthOf(source).jobs_30d ? `近30天 ${healthOf(source).jobs_30d} 次` : '近期无作业' }}</span>
          <span v-if="healthOf(source).bad_configs > 0" class="stale-warn">异常配置 {{ healthOf(source).bad_configs }}</span>
        </div>
        <div class="src-facts">
          <span>数据点 <b>{{ source.rows }}</b></span>
          <span>指标 <b>{{ source.indicators }}</b></span>
          <span>最新 <b>{{ source.latest || '—' }}</b></span>
          <span v-if="source.stale_days !== null && source.stale_days !== undefined" class="stale-tag" :class="{ 'stale-warn': source.stale_days > 3 }">
            滞后 {{ source.stale_days }} 天
          </span>
        </div>
        <p class="caption src-channel">{{ source.channel || '未填写取数通道说明' }}</p>
        <div class="source-actions">
          <el-button size="small" :disabled="!canSync || !source.enabled || syncingSource === source.key" :loading="syncingSource === source.key" @click.stop="openSync(source)">
            {{ sourceHasConfig(source) ? '同步数据' : '登记同步' }}
          </el-button>
          </div><div class="source-last-sync">上次同步 <span>{{ localTime(source.last_sync) }}</span>
        </div>
      </div>
    </div>


    <el-dialog v-model="syncRecordsVisible" title="同步记录" width="1200px" top="6vh" class="sync-records-dialog">
      <div class="panel-header">
        <span class="hint">共 {{ jobTotal }} 条</span>
      </div>

      <div class="filter-bar job-filter">
        <el-select v-model="jobFilter.source" clearable placeholder="全部来源" style="width: 132px" @change="queryJobs(1)">
          <el-option v-for="item in sources" :key="item.key" :label="item.name" :value="item.key" />
        </el-select>
        <el-select v-model="jobFilter.status" clearable placeholder="全部状态" style="width: 118px" @change="queryJobs(1)">
          <el-option v-for="item in jobStatuses" :key="item" :label="item" :value="item" />
        </el-select>
        <el-input
          v-model="jobFilter.q"
          placeholder="搜说明或范围"
          clearable
          style="width: 190px"
          @keyup.enter="queryJobs(1)"
          @clear="queryJobs(1)"
        />
        <el-date-picker
          v-model="jobFilter.range"
          type="daterange"
          value-format="YYYY-MM-DD"
          unlink-panels
          range-separator="至"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          style="width: 240px"
          @change="queryJobs(1)"
        />
        <el-button type="primary" @click="queryJobs(1)">查询</el-button>
        <el-button @click="resetJobFilter">重置</el-button>
      </div>

      <el-table v-loading="jobsLoading" max-height="440" :data="jobs" empty-text="没有匹配的同步记录" size="small">
        <el-table-column prop="id" label="编号" width="62" />
        <el-table-column label="来源" width="92">
          <template #default="{ row }">{{ row.source_name }}</template>
        </el-table-column>
        <el-table-column label="范围" min-width="200">
          <template #default="{ row }">
            <span class="ellipsis" style="display: block" :title="scopeText(row)">{{ scopeText(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="区间" width="82">
          <template #default="{ row }">近 {{ row.scope?.days || '—' }} 日</template>
        </el-table-column>
        <el-table-column label="状态" width="104">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)" size="small" disable-transitions>{{ row.status }}</el-tag>
            <el-tooltip v-if="row.reason_type" :content="'失败类别：' + row.reason_type + '，点击说明查看排查建议'" placement="top">
              <el-tag type="danger" size="small" effect="plain" style="margin-left: 4px" disable-transitions>
                {{ row.reason_type.slice(0, 2) }}
              </el-tag>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="数据点" width="80" align="right">
          <template #default="{ row }">
            <span v-if="row.status === '已完成'">{{ row.rows }}</span>
            <span v-else class="tiny">—</span>
          </template>
        </el-table-column>
        <el-table-column label="登记时间" width="150">
          <template #default="{ row }">{{ localTime(row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="说明" min-width="170">
          <template #default="{ row }">
            <button type="button" class="job-note" :title="row.message || ''" @click="openJob(row)">
              {{ row.message || (row.status === '待执行' ? '等待取数通道回填' : '—') }}
            </button>
          </template>
        </el-table-column>
      </el-table>

      <div class="job-pager">
        <el-pagination
          layout="prev, pager, next"
          :current-page="jobPage"
          :page-size="jobSize"
          :total="jobTotal"
          background
          @current-change="queryJobs"
        />
      </div>
    </el-dialog>

    <el-drawer v-model="sourceSettingsVisible" :title="`${settingsSource?.name || ''} · 数据源配置`" size="90%">
      <div class="panel-toolbar"><el-button @click="openSource(settingsSource)">编辑数据源</el-button></div>
      <div class="panel-header">
        <h3>接口与同步配置</h3>
        <div class="row">
          <el-button type="primary" size="small" @click="openConfig(null, settingsSource)">新建配置</el-button>
        </div>
      </div>
      <el-alert v-if="!sourceConfigs.length" type="info" :closable="false" style="margin-bottom: 14px" :title="configEmptyHint" />
      <el-table :data="sourceConfigs" empty-text="还没有取数配置" size="small">
        <el-table-column prop="name" label="名称" min-width="150">
          <template #default="{ row }">
            <span class="ellipsis" style="display: block" :title="row.name">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="96">
          <template #default="{ row }">{{ row.source_name }}</template>
        </el-table-column>
        <el-table-column label="方式" width="132">
          <template #default="{ row }">
            <span class="tiny">{{ row.kind_label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="接口" min-width="180">
          <template #default="{ row }">
            <span class="tiny ellipsis" style="display: block" :title="row.base_url">{{ row.base_url }}</span>
          </template>
        </el-table-column>
        <el-table-column label="范围" min-width="140">
          <template #default="{ row }">
            <span class="tiny ellipsis" style="display: block" :title="configScope(row)">{{ configScope(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计划" width="118">
          <template #default="{ row }">
            <span class="tiny">{{ planText(row) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上次执行" width="150">
          <template #default="{ row }">
            <span class="tiny">{{ row.last_run || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="82">
          <template #default="{ row }">
            <el-tag :type="configTag(row)" size="small" disable-transitions>{{ row.last_status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="执行说明" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.last_message || '尚未执行' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="236" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" :loading="runningId === row.id" @click="runConfig(row)">
              执行
            </el-button>
            <el-button link size="small" :loading="testingId === row.id" @click="testConfig(row)">试连</el-button>
            <el-button link size="small" @click="openConfig(row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="removeConfig(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-drawer>

    <el-dialog v-model="syncVisible" :title="`${activeSource?.name || ''} · ${syncMode === 'register' ? '登记同步' : '同步数据'}`" width="560px" @closed="resetSync">
      <el-form label-width="90px" style="margin-top: 20px">
        <template v-if="syncMode === 'run'">
          <el-form-item label="同步配置">
            <el-select v-model="syncConfigId" placeholder="选择配置" style="width: 100%">
              <el-option v-for="item in activeSyncConfigs" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
          </el-form-item>
        </template>
        <template v-else>
          <el-form-item label="品种/指标">
            <el-select v-model="regItems" multiple filterable allow-create default-first-option :placeholder="scopePlaceholder" style="width: 100%">
              <el-option v-for="item in scopeOptions" :key="item" :label="item" :value="item" />
            </el-select>
          </el-form-item>
          <el-form-item label="取数指标">
            <el-select v-model="regMetrics" multiple :placeholder="activeSource?.key === 'ifind' ? '行情至少选一个' : '可留空'" style="width: 100%">
              <el-option v-for="item in metrics" :key="item.key" :label="item.label" :value="item.key" />
            </el-select>
          </el-form-item>
          <el-form-item label="区间">
            <el-input-number v-model="regDays" :min="1" :max="120" controls-position="right" />
            <span class="caption" style="margin-left: 8px">个交易日</span>
          </el-form-item>
        </template>
      </el-form>
      <p v-if="syncMode === 'run' && selectedSyncConfig" class="caption">范围：{{ configScope(selectedSyncConfig) }}</p>
      <template #footer>
        <el-button @click="syncVisible = false">取消</el-button>
        <el-button v-if="syncMode === 'run'" type="primary" :loading="submitting" :disabled="!syncConfigId" @click="submitSync">立即同步</el-button>
        <el-button v-else type="primary" :loading="submitting" :disabled="!regItems.length" @click="submitSync">登记同步</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="csvVisible" title="导入 CSV" width="520px" @closed="resetCsv">
      <p class="caption">UTF-8 CSV，表头 source,indicator,date,value,unit；日期 YYYY-MM-DD。</p>
      <div class="csv-pick" @click="fileInput?.click()">
        <el-button @click.stop="fileInput?.click()">选择文件</el-button>
        <span v-if="fileName" class="caption ellipsis" :title="fileName">{{ fileName }}</span>
        <span v-else class="tiny">未选择文件 · 仅支持 .csv</span>
        <input ref="fileInput" type="file" accept=".csv" class="csv-native" @change="onFileChange" />
      </div>
      <p class="caption csv-sample">示例：Wind,螺纹钢库存,2026-11-16,100,万吨（仅格式示例）</p>
      <template #footer>
        <el-button @click="csvVisible = false">取消</el-button>
        <el-button type="primary" :loading="busy" :disabled="!picked" @click="submit">导入</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="sourceVisible" :title="sourceForm.id ? '编辑数据来源' : '新增数据源'" width="520px">
      <el-form label-width="96px" label-position="left" @submit.prevent>
        <el-form-item label="名称">
          <el-input v-model="sourceForm.name" maxlength="30" placeholder="入库标签，如：同花顺 / 卓创资讯" />
        </el-form-item>
        <el-form-item label="标识">
          <el-input v-model="sourceForm.key" maxlength="24" placeholder="字母数字下划线，如 ifind / zhuochuang" />
        </el-form-item>
        <el-form-item label="产品">
          <el-input v-model="sourceForm.product" maxlength="40" placeholder="如 iFinD / 金融终端" />
        </el-form-item>
        <el-form-item label="通道说明">
          <el-input v-model="sourceForm.channel" maxlength="120" placeholder="这条通道怎么取数，给同事看的" />
        </el-form-item>
        <el-form-item label="同步候选">
          <el-radio-group v-model="sourceForm.scope_mode">
            <el-radio-button label="commodity">用品种库</el-radio-button>
            <el-radio-button label="custom">自定义清单</el-radio-button>
          </el-radio-group>
          <el-button v-if="canConfig" text type="primary" size="small" style="margin-left: 8px" @click="router.push('/system/scope-library')">指标管理</el-button>
        </el-form-item>
        <el-form-item v-if="sourceForm.scope_mode === 'custom'" label="候选清单">
          <el-select
            v-model="sourceForm.scope_list"
            multiple filterable allow-create default-first-option
            :reserve-keyword="false"
            :loading="!scopeLibrary.length"
            placeholder="从常用指标里勾选，也可输入新增后回车"
            style="width: 100%"
          >
            <el-option-group v-for="group in scopeLibrary" :key="group.group" :label="group.group">
              <el-option v-for="item in group.items" :key="item" :label="item" :value="item" />
            </el-option-group>
          </el-select>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="sourceForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button v-if="sourceForm.id" type="danger" text @click="removeSource">删除</el-button>
        <el-button @click="sourceVisible = false">取消</el-button>
        <el-button type="primary" :loading="sourceSaving" @click="saveSource">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="configVisible"
      :title="configForm.id ? '编辑取数配置' : '新建取数配置'"
      width="640px"
      top="6vh"
      class="cfg-dialog"
    >
      <el-alert
        v-if="testResult"
        class="cfg-alert"
        :type="testResult.ok ? 'success' : 'error'"
        :title="testResult.message"
        :description="testResult.ok
          ? `耗时 ${(testResult.ms / 1000).toFixed(1)} 秒；样本 ${testResult.sample.length} 条，如 ${testResult.sample[0]?.indicator} ${testResult.sample[0]?.date} = ${testResult.sample[0]?.value}`
          : ''"
        show-icon
        :closable="false"
      />

      <el-form label-width="96px" label-position="left" @submit.prevent>
        <el-form-item label="名称">
          <el-input v-model="configForm.name" maxlength="40" placeholder="如：同花顺-黑色日盘" />
        </el-form-item>
        <el-form-item label="数据来源">
          <el-select v-model="configForm.source" placeholder="选择来源" style="width: 100%">
            <el-option v-for="item in sources" :key="item.key" :label="item.name" :value="item.key" />
          </el-select>
        </el-form-item>
        <el-alert v-if="configForm.kind === 'eastmoney_snapshot'" type="info" :closable="false" title="最新行情快照：每次同步更新行情当天的数据，不提供历史日线或收盘价。" style="margin-bottom: 16px" />
        <el-alert v-if="configForm.kind === 'windpy'" type="info" :closable="false" style="margin-bottom: 16px"
          title="WindPy 本机终端：需本机装有已登录的 Wind 金融终端（MAC 绑定账号），凭据留在终端侧。范围条目填「指标名|Wind代码|通道」，如：螺纹钢主连|RBZL.SHF|wsd；南华商品指数|M002122626|edb。接口地址可不填。" />
        <el-alert v-if="configForm.kind === 'ifind_http'" type="info" :closable="false" style="margin-bottom: 16px"
          title="iFinD HTTP：默认取 ft.10jqka.com.cn（也可填 quantapi.51ifind.com）。密钥填 refresh_token（超级命令客户端「工具-refresh_token 查询」获取）。注意跨品种单位不同：原油是 元/桶、白银是 元/千克，与默认 元/吨 不符时在「高级-单位」里覆盖。" />
        <el-alert v-if="configForm.kind === 'generic_json'" type="info" :closable="false" style="margin-bottom: 16px"
          title="通用 JSON 接口：适合 SMM 等自有账号的 API。把接口地址、token（放 headers 或密钥）配好，用「高级」设置响应路径与字段映射。" />
        <el-form-item label="取数方式">
          <el-select v-model="configForm.kind" style="width: 100%">
            <el-option v-for="item in kinds" :key="item.key" :label="item.label" :value="item.key" />
          </el-select>
        </el-form-item>
        <el-form-item label="接口地址">
          <el-input v-model="configForm.base_url" placeholder="https://... 可用 {code} {metric} {startdate} {enddate}" />
        </el-form-item>
        <el-form-item label="账号">
          <el-input v-model="configForm.account" placeholder="用户名 / AppID，可留空" />
        </el-form-item>
        <el-form-item label="密钥">
          <el-input
            v-model="configForm.secret"
            type="password"
            show-password
            autocomplete="new-password"
            :placeholder="configForm.secret_masked ? `已保存 ${configForm.secret_masked}，留空不改` : '密码 / refresh_token / apikey'"
          />
        </el-form-item>

        <el-divider content-position="left">同步范围</el-divider>
        <el-form-item label="品种">
          <el-select
            v-model="configForm.items"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            placeholder="选择品种或自定义项"
            style="width: 100%"
          >
            <el-option v-for="item in configOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="指标">
          <el-checkbox-group v-model="configForm.metrics">
            <el-checkbox v-for="metric in configMetrics" :key="metric.key" :label="metric.key">
              {{ metric.label }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item v-if="configForm.kind !== 'eastmoney_snapshot'" label="区间">
          <el-radio-group v-model="configForm.days">
            <el-radio-button :label="5">5 个交易日</el-radio-button>
            <el-radio-button :label="10">10 个</el-radio-button>
            <el-radio-button :label="20">20 个</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="代码后缀">
          <el-input v-model="configForm.code_suffix" placeholder="如 .SHF（请求里 {code} 会拼上），可留空" />
        </el-form-item>

        <el-divider content-position="left">执行计划</el-divider>
        <el-form-item label="频率">
          <el-select v-model="configForm.freq" style="width: 100%">
            <el-option v-for="item in freqs" :key="item.key" :label="item.label" :value="item.key" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="configForm.freq !== 'manual'" label="执行时间">
          <el-time-picker v-model="configForm.run_at" format="HH:mm" value-format="HH:mm" placeholder="08:30" />
          <el-select
            v-if="configForm.freq === 'weekly'"
            v-model="configForm.weekday"
            style="width: 120px; margin-left: 10px"
          >
            <el-option v-for="(name, index) in WEEKDAYS" :key="name" :label="name" :value="index + 1" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="configForm.enabled" />
        </el-form-item>

        <el-collapse>
          <el-collapse-item title="高级：请求模板与响应解析" name="adv">
            <el-form-item label="请求方式">
              <el-radio-group v-model="configForm.method">
                <el-radio-button label="GET">GET</el-radio-button>
                <el-radio-button label="POST">POST</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="请求头">
              <el-input v-model="configForm.headers" type="textarea" :rows="2" placeholder='{"Authorization": "Bearer {secret}"}' />
            </el-form-item>
            <el-form-item v-if="configForm.method === 'POST'" label="请求体">
              <el-input v-model="configForm.body" type="textarea" :rows="3" placeholder='{"code": "{code}", "field": "{metric}"}' />
            </el-form-item>
            <el-form-item label="数据路径">
              <el-input v-model="configForm.points_path" placeholder="响应里数组的位置，如 data.rows；留空表示响应本身就是数组" />
            </el-form-item>
            <el-form-item label="日期字段">
              <el-input v-model="configForm.date_field" placeholder="date" />
            </el-form-item>
            <el-form-item label="数值字段">
              <el-input v-model="configForm.value_field" placeholder="value" />
            </el-form-item>
            <el-form-item label="指标命名">
              <el-input v-model="configForm.indicator_template" placeholder="{item}{metric_label}" />
            </el-form-item>
            <el-form-item label="单位">
              <el-input v-model="configForm.unit" placeholder="留空按指标默认单位" />
            </el-form-item>
            <el-form-item label="字段映射">
              <el-input v-model="configForm.field_map" type="textarea" :rows="2" placeholder='{"close": "close", "open_interest": "openInterest"}' />
            </el-form-item>
          </el-collapse-item>
        </el-collapse>
      </el-form>

      <template #footer>
        <el-button :loading="testingId === 'form'" @click="testForm">试连</el-button>
        <el-button @click="configVisible = false">取消</el-button>
        <el-button type="primary" :loading="configSaving" @click="saveConfig">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="jobVisible" append-to-body title="同步记录详情" width="560px">
      <div v-if="activeJob" class="job-detail">
        <div class="job-detail-row"><span>编号</span><b>#{{ activeJob.id }}</b></div>
        <div class="job-detail-row"><span>来源</span><b>{{ activeJob.source_name }}</b></div>
        <div class="job-detail-row"><span>状态</span>
          <el-tag :type="statusType(activeJob.status)" size="small" disable-transitions>{{ activeJob.status }}</el-tag>
          <el-tag v-if="activeJob.reason_type" type="danger" size="small" effect="plain" style="margin-left: 6px" disable-transitions>
            {{ activeJob.reason_type }}
          </el-tag>
        </div>
        <div class="job-detail-row"><span>范围</span><b>{{ scopeText(activeJob) }}</b></div>
        <div class="job-detail-row"><span>区间</span><b>近 {{ activeJob.scope?.days || '—' }} 个交易日</b></div>
        <div class="job-detail-row"><span>数据点</span>
          <b>{{ activeJob.rows || 0 }} 行（新增 {{ activeJob.inserted || 0 }}、更新 {{ activeJob.updated || 0 }}）</b>
        </div>
        <div class="job-detail-row"><span>触发方式</span>
          <b>{{ activeJob.scope?.trigger === 'schedule' ? '定时自动' : activeJob.scope?.config_id ? '配置手动执行' : '页面登记' }}</b>
        </div>
        <div class="job-detail-row"><span>登记</span><b>{{ localTime(activeJob.created_at) }} · {{ activeJob.operator }}</b></div>
        <div class="job-detail-row"><span>完成</span><b>{{ localTime(activeJob.finished_at) }}</b></div>
        <p class="caption" style="margin-top: 10px">说明</p>
        <p class="job-detail-note">{{ activeJob.message || '—' }}</p>
        <template v-if="activeJob.reason_type">
          <p class="caption" style="margin-top: 10px">排查建议（{{ activeJob.reason_type }}）</p>
          <ol class="troubleshoot-list">
            <li v-for="(step, index) in activeJob.troubleshooting || []" :key="index">{{ step }}</li>
          </ol>
        </template>
      </div>
    </el-dialog>
    </PageContainer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import { useRouter } from 'vue-router';
import PageContainer from '../components/PageContainer.vue';
import { api } from '../api';
import { commodities, refresh } from '../store/session';
import { localTime } from '../utils/format';

const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
const router = useRouter();

const sources = ref([]);
const health = ref([]);
const sourceSettingsVisible = ref(false);
const settingsSource = ref(null);
const sourceConfigs = computed(() => configs.value.filter(item => item.source === settingsSource.value?.key));
// 空配置说明：不同来源的取数通道不同，缺 HTTP 配置不等于漏配
const configEmptyHint = computed(() => {
  const key = settingsSource.value?.key || '';
  if (['wind', 'ifind', 'smm'].includes(key)) {
    return '该数据源通过 WorkBuddy 连接器取数，凭据由连接器托管、平台不代持，因此没有 HTTP 取数配置。同步数据请回到数据源卡片点「登记同步」。';
  }
  if (['mysteel', 'longzhong'].includes(key)) {
    return '该数据商没有公开 HTTP 接口，数据走「终端账号导出 → 导入 CSV」入库，因此没有取数配置。后续如搭建采集中间服务，可再新建配置接入。';
  }
  return '还没有取数配置。点「新建配置」填入接口地址与凭据即可。';
});
function sourceStatus(source) {
  if (!source.enabled) return { label: '已停用', type: 'info' };
  const related = configs.value.filter(item => item.source === source.key);
  if (related.some(item => item.last_status === '失败')) return { label: '同步失败', type: 'danger' };
  return { label: source.rows ? '已同步' : '待同步', type: source.rows ? 'success' : 'info' };
}
const healthByKey = computed(() => Object.fromEntries(health.value.map(item => [item.key, item])));
function healthOf(source) {
  return healthByKey.value[source.key];
}
const totalRows = computed(() => sources.value.reduce((sum, item) => sum + Number(item.rows || 0), 0));
function openSourceSettings(source) {
  settingsSource.value = source;
  sourceSettingsVisible.value = true;
}
const metrics = ref([]);
const kinds = ref([]);
const scopeLibrary = ref([]);
const freqs = ref([]);
const configs = ref([]);
const canSync = ref(false);
const canConfig = ref(false);
const loading = ref(false);

const syncVisible = ref(false);
const submitting = ref(false);
const activeSource = ref(null);
const syncingSource = ref('');
const syncConfigId = ref(null);
/* run：来源已有接口配置，点一下直接取数；register：凭据在已授权通道，页面只登记范围 */
const syncMode = ref('run');
const regItems = ref([]);
const regMetrics = ref([]);
const regDays = ref(10);
const activeSyncConfigs = computed(() => configs.value.filter(item => item.source === activeSource.value?.key && item.enabled));
const selectedSyncConfig = computed(() => activeSyncConfigs.value.find(item => item.id === syncConfigId.value));
const configMetrics = computed(() => configForm.kind === 'eastmoney_snapshot'
  ? metrics.value.filter(item => ['index_last', 'volume'].includes(item.key))
  : ['eastmoney_index', 'sina_index'].includes(configForm.kind)
    ? metrics.value.filter(item => ['index_close', 'volume'].includes(item.key)) : metrics.value);
const scopeItems = ref([]);
const scopeMetrics = ref([]);
const scopeDays = ref(10);

const csvVisible = ref(false);
const fileInput = ref(null);
const fileName = ref('');
const busy = ref(false);
const picked = ref(null);

const sourceVisible = ref(false);
const sourceSaving = ref(false);
const sourceForm = reactive({
  id: null, key: '', name: '', product: '', channel: '',
  scope_mode: 'commodity', scope_list: [], enabled: true,
});
// 候选项规范：只允许中文、字母、数字与 | . - _ / % ( ) 等，防止把备注或乱码当品种存进清单
const SCOPE_ITEM_RE = /^[\w\u4e00-\u9fa5|.\-/%()（）·、]+$/;
function normalizeScopeItems(raw) {
  const items = [];
  for (let item of raw) {
    item = String(item).trim().slice(0, 60);
    if (!item) continue;
    if (!SCOPE_ITEM_RE.test(item)) {
      throw new Error(`候选项含不支持的字符：${item}（只允许中文、字母、数字与 | . - _ / % ( ) 等）`);
    }
    if (!items.includes(item)) items.push(item);
  }
  if (items.length > 60) throw new Error('候选项最多 60 个');
  return items;
}

const configVisible = ref(false);
const configSaving = ref(false);
const testingId = ref('');
const runningId = ref('');
const testResult = ref(null);
const configForm = reactive(emptyConfig());

const jobs = ref([]);
const jobTotal = ref(0);
const jobPage = ref(1);
const jobSize = ref(20);
const jobStatuses = ref(['待执行', '执行中', '已完成', '失败']);
const jobFilter = reactive({ source: '', status: '', q: '', range: null });
const syncRecordsVisible = ref(false);
const jobsLoading = ref(false);
function openSyncRecords() {
  syncRecordsVisible.value = true;
  queryJobs(1);
}
const jobVisible = ref(false);
const activeJob = ref(null);

const leafCommodities = computed(() =>
  commodities.value.filter(item => item.code && item.enabled !== 0).map(item => item.name)
);

const scopeOptions = computed(() => {
  const source = activeSource.value;
  if (!source) return leafCommodities.value;
  return source.scope_mode === 'custom' && source.scope_items?.length
    ? source.scope_items
    : leafCommodities.value;
});
const scopePlaceholder = computed(() =>
  activeSource.value?.scope_mode === 'custom' ? '选择指数或指标' : '选择品种'
);

/* 配置弹窗里的品种候选：跟随所选来源的范围模式 */
const configOptions = computed(() => {
  const source = sources.value.find(item => item.key === configForm.source);
  if (source?.scope_mode === 'custom' && source.scope_items?.length) return source.scope_items;
  return leafCommodities.value;
});

function emptyConfig() {
  return {
    id: null, name: '', source: '', kind: 'generic_json', base_url: '', account: '',
    secret: '', secret_masked: '', items: [], metrics: ['close'], days: 10, code_suffix: '',
    freq: 'manual', run_at: '08:30', weekday: 1, enabled: true,
    method: 'GET', headers: '{}', body: '', points_path: 'data', date_field: 'date',
    value_field: 'value', indicator_template: '{item}{metric_label}', unit: '', field_map: '',
  };
}

function scopeText(row) {
  const items = row.scope?.items || [];
  if (!items.length) return '—';
  return items.length > 6 ? `${items.slice(0, 6).join('、')} 等 ${items.length} 项` : items.join('、');
}

function configScope(row) {
  const scope = row.scope || {};
  const items = scope.items || [];
  const labels = (scope.metrics || []).map(key => metrics.value.find(m => m.key === key)?.label || key);
  const head = items.length > 3 ? `${items.slice(0, 3).join('、')} 等 ${items.length} 个` : items.join('、');
  return `${head || '—'} · ${labels.join('/') || '—'} · ${row.kind === 'eastmoney_snapshot' ? '最新快照' : `近 ${scope.days || '—'} 日`}`;
}

function planText(row) {
  if (!row.enabled) return '已停用';
  if (row.freq === 'daily') return `每日 ${row.run_at}`;
  if (row.freq === 'weekly') return `每${WEEKDAYS[row.weekday - 1] || '周'} ${row.run_at}`;
  return '仅手动';
}

function configTag(row) {
  return { 成功: 'success', 失败: 'danger', 未运行: 'info' }[row.last_status] || 'info';
}

function statusType(status) {
  return { 已完成: 'success', 未执行: 'warning', 待执行: 'warning', 执行中: 'warning', 失败: 'danger' }[status] || 'info';
}

async function load() {
  loading.value = true;
  try {
    const result = await api('data/sources');
    sources.value = result.sources || [];
    health.value = result.health || [];
    metrics.value = result.metrics || [];
    kinds.value = result.kinds || [];
    /* 候选清单不展示系统兜底的「未分组」：那一组装的是同步时自动落地的指标名，不是精心维护的候选 */
    scopeLibrary.value = (result.scope_library || []).filter(group => !group.builtin);
    freqs.value = result.freqs || [];
    configs.value = result.configs || [];
    canSync.value = Boolean(result.can_sync);
    canConfig.value = Boolean(result.can_config);
    if (canSync.value) queryJobs(jobPage.value);
  } catch (error) {
    ElMessage.error(error.message || '读取数据源状态失败');
  } finally {
    loading.value = false;
  }
}

async function queryJobs(page = 1) {
  jobsLoading.value = true;
  jobPage.value = page;
  const params = new URLSearchParams({ page: String(page), size: String(jobSize.value) });
  if (jobFilter.source) params.set('source', jobFilter.source);
  if (jobFilter.status) params.set('status', jobFilter.status);
  if (jobFilter.q) params.set('q', jobFilter.q);
  if (jobFilter.range?.[0]) params.set('start', jobFilter.range[0]);
  if (jobFilter.range?.[1]) params.set('end', jobFilter.range[1]);
  try {
    const result = await api(`data/jobs?${params.toString()}`);
    jobs.value = result.jobs || [];
    jobTotal.value = result.total || 0;
    jobStatuses.value = result.statuses || jobStatuses.value;
  } catch (error) {
    ElMessage.error(error.message || '读取同步记录失败');
  } finally {
    jobsLoading.value = false;
  }
}

function resetJobFilter() {
  jobFilter.source = '';
  jobFilter.status = '';
  jobFilter.q = '';
  jobFilter.range = null;
  queryJobs(1);
}

function openJob(row) {
  activeJob.value = row;
  jobVisible.value = true;
}

/* ---------- 同步：有接口配置直接取数，否则登记范围由已授权通道回填 ---------- */
function sourceHasConfig(source) {
  return configs.value.some(item => item.source === source.key && item.enabled);
}

function openSync(source) {
  activeSource.value = source;
  if (sourceHasConfig(source)) {
    syncMode.value = 'run';
    syncConfigId.value = activeSyncConfigs.value[0]?.id || null;
  } else {
    syncMode.value = 'register';
    syncConfigId.value = null;
    /* 默认沿用上一次同来源的登记范围，避免每次重新挑品种 */
    const last = jobs.value.find(item => item.source === source.key && item.scope?.items?.length);
    regItems.value = last ? [...last.scope.items]
      : source.scope_mode === 'custom' && source.scope_items?.length ? [...source.scope_items] : [];
    regMetrics.value = last?.scope?.metrics?.length ? [...last.scope.metrics]
      : source.key === 'ifind' ? ['close', 'settle', 'volume', 'open_interest'] : [];
    regDays.value = last?.scope?.days || 10;
  }
  syncVisible.value = true;
}

function resetSync() {
  syncMode.value = 'run';
  syncConfigId.value = null;
  regItems.value = [];
  regMetrics.value = [];
  regDays.value = 10;
}

async function submitSync() {
  if (syncMode.value === 'register') {
    if (!regItems.value.length) return ElMessage.warning('请至少选择一个品种或指标');
    if (activeSource.value?.key === 'ifind' && !regMetrics.value.length) {
      return ElMessage.warning('同花顺行情至少要选一个指标');
    }
    submitting.value = true;
    syncingSource.value = activeSource.value.key;
    try {
      await api('data/jobs', {
        source: activeSource.value.key,
        items: regItems.value,
        metrics: regMetrics.value,
        days: regDays.value,
      });
      ElMessage.success('已登记同步作业，结果见「同步记录」');
      syncVisible.value = false;
      await load();
    } catch (error) {
      ElMessage.error(error.message || '登记失败');
    } finally {
      submitting.value = false;
      syncingSource.value = '';
    }
    return;
  }
  if (!selectedSyncConfig.value) return ElMessage.warning('请选择启用的同步配置');
  submitting.value = true;
  syncingSource.value = activeSource.value.key;
  try {
    const result = await api('data/configs/run', { id: syncConfigId.value });
    if (result.ok) {
      ElMessage.success(result.message);
      syncVisible.value = false;
    } else ElMessage.error(result.message || '同步失败');
    await Promise.all([load(), refresh()]);
  } catch (error) {
    ElMessage.error(error.message || '同步失败');
  } finally {
    submitting.value = false;
    syncingSource.value = '';
  }
}

/* ---------- 数据来源维护 ---------- */
function openSource(source) {
  Object.assign(sourceForm, {
    id: source?.id || null,
    key: source?.key || '',
    name: source?.name || '',
    product: source?.product || '',
    channel: source?.channel || '',
    scope_mode: source?.scope_mode || 'commodity',
    scope_list: [...(source?.scope_items || [])],
    enabled: source ? Boolean(source.enabled) : true,
  });
  sourceVisible.value = true;
}

async function saveSource() {
  let items = [];
  if (sourceForm.scope_mode === 'custom') {
    try {
      items = normalizeScopeItems(sourceForm.scope_list);
    } catch (error) {
      ElMessage.error(error.message);
      return;
    }
  }
  const creating = !sourceForm.id;
  sourceSaving.value = true;
  try {
    await api('data/sources', {
      id: sourceForm.id || undefined,
      key: sourceForm.key, name: sourceForm.name,
      product: sourceForm.product, channel: sourceForm.channel,
      scope_mode: sourceForm.scope_mode,
      scope_items: sourceForm.scope_mode === 'custom' ? items : [],
      enabled: sourceForm.enabled,
    });
    sourceVisible.value = false;
    await load();
    ElMessage.success('数据来源已保存');
    if (creating) {
      // 一步到底：新建完直接衔接取数配置；连接器/CSV 类来源可以跳过
      const key = sourceForm.key;
      const connectorLike = ['wind', 'ifind', 'smm', 'mysteel', 'longzhong'].includes(key);
      try {
        await ElMessageBox.confirm(
          connectorLike
            ? '数据源已创建。该来源可走连接器或 CSV 导入，不建取数配置也能用；若要直连 HTTP 接口，可现在新建配置。'
            : '数据源已创建。要让它真正取数，还需一条取数配置（接口地址、凭据、范围与执行计划），现在就建吗？',
          '下一步：取数配置',
          { confirmButtonText: '新建配置', cancelButtonText: '先不用', type: 'info' },
        );
        openConfig(null, sources.value.find(item => item.key === key) || { key, name: sourceForm.name });
      } catch { /* 用户选择跳过 */ }
    }
  } catch (error) {
    ElMessage.error(error.message || '保存数据来源失败');
  } finally {
    sourceSaving.value = false;
  }
}

async function removeSource() {
  try {
    await ElMessageBox.confirm(
      `删除「${sourceForm.name}」后不可恢复；已有配置或入库数据时不能删除。`, '删除数据来源？',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    );
  } catch {
    return;
  }
  try {
    await api('data/sources/delete', { id: sourceForm.id });
    sourceVisible.value = false;
    await load();
    ElMessage.success('已删除');
  } catch (error) {
    ElMessage.error(error.message || '删除失败');
  }
}

/* ---------- 取数配置 ---------- */
function openConfig(config, source = null) {
  testResult.value = null;
  Object.assign(configForm, emptyConfig());
  if (config) {
    const options = config.options || {};
    Object.assign(configForm, {
      id: config.id, name: config.name, source: config.source, kind: config.kind,
      base_url: config.base_url, account: config.account,
      secret: '', secret_masked: config.secret_masked,
      items: config.scope?.items || [], metrics: config.scope?.metrics || ['close'],
      days: config.scope?.days || 10, code_suffix: config.scope?.code_suffix || '',
      freq: config.freq, run_at: config.run_at || '08:30', weekday: config.weekday || 1,
      enabled: Boolean(config.enabled),
      method: options.method || 'GET', headers: options.headers || '{}', body: options.body || '',
      points_path: options.points_path ?? 'data', date_field: options.date_field || 'date',
      value_field: options.value_field || 'value',
      indicator_template: options.indicator_template || '{item}{metric_label}',
      unit: options.unit || '',
      field_map: options.field_map && Object.keys(options.field_map).length
        ? JSON.stringify(options.field_map) : '',
    });
  } else if (source || sources.value.length) {
    const selected = source || sources.value[0];
    configForm.source = selected.key;
    configForm.name = `${selected.name} 自动同步`;
    if (['eastmoney', 'sina'].includes(selected.key)) {
      configForm.kind = selected.key === 'eastmoney' ? 'eastmoney_snapshot' : 'sina_index';
      configForm.base_url = selected.key === 'eastmoney'
        ? 'https://push2.eastmoney.com/api/qt/stock/get'
        : 'https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData';
      configForm.items = [...(selected.scope_items || [])];
      configForm.metrics = [selected.key === 'eastmoney' ? 'index_last' : 'index_close', 'volume'];
    }
  }
  configVisible.value = true;
}

function configPayload() {
  let fieldMap = {};
  if (configForm.field_map.trim()) {
    try {
      fieldMap = JSON.parse(configForm.field_map);
    } catch {
      throw new Error('字段映射需为 JSON，如 {"close": "close"}');
    }
  }
  const payload = {
    id: configForm.id || undefined,
    name: configForm.name, source: configForm.source, kind: configForm.kind,
    base_url: configForm.base_url, account: configForm.account,
    scope: {
      items: configForm.items, metrics: configForm.metrics,
      days: configForm.days, code_suffix: configForm.code_suffix,
    },
    options: {
      method: configForm.method, headers: configForm.headers, body: configForm.body,
      points_path: configForm.points_path, date_field: configForm.date_field,
      value_field: configForm.value_field, indicator_template: configForm.indicator_template,
      unit: configForm.unit, field_map: fieldMap,
    },
    freq: configForm.freq, run_at: configForm.run_at, weekday: configForm.weekday,
    enabled: configForm.enabled,
  };
  if (configForm.secret) payload.secret = configForm.secret;
  return payload;
}

async function saveConfig() {
  if (!configForm.items.length) return ElMessage.warning('请选择至少一个品种');
  if (!configForm.metrics.length) return ElMessage.warning('请选择至少一个指标');
  let payload;
  try {
    payload = configPayload();
  } catch (error) {
    return ElMessage.warning(error.message);
  }
  configSaving.value = true;
  try {
    await api('data/configs', payload);
    configVisible.value = false;
    await load();
    ElMessage.success('配置已保存');
  } catch (error) {
    ElMessage.error(error.message || '保存配置失败');
  } finally {
    configSaving.value = false;
  }
}

async function testForm() {
  let payload;
  try {
    payload = configPayload();
  } catch (error) {
    return ElMessage.warning(error.message);
  }
  testingId.value = 'form';
  testResult.value = null;
  try {
    testResult.value = await api('data/configs/test', payload);
    if (testResult.value.ok) ElMessage.success(testResult.value.message);
    else ElMessage.error(testResult.value.message);
  } catch (error) {
    testResult.value = { ok: false, message: error.message || '试连失败', ms: 0, sample: [] };
    ElMessage.error(testResult.value.message);
  } finally {
    testingId.value = '';
  }
}

async function testConfig(row) {
  testingId.value = row.id;
  try {
    const result = await api('data/configs/test', { id: row.id });
    if (result.ok) ElMessage.success(result.message);
    else ElMessage.error(result.message);
  } catch (error) {
    ElMessage.error(error.message || '试连失败');
  } finally {
    testingId.value = '';
  }
}

async function runConfig(row) {
  runningId.value = row.id;
  try {
    const result = await api('data/configs/run', { id: row.id });
    if (result.ok) ElMessage.success(result.message);
    else ElMessage.warning(result.message);
    await Promise.all([load(), refresh()]);
  } catch (error) {
    ElMessage.error(error.message || '执行失败');
  } finally {
    runningId.value = '';
  }
}

async function removeConfig(row) {
  try {
    await ElMessageBox.confirm(`确定删除配置「${row.name}」？已入库的数据不受影响。`, '删除取数配置？', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    });
  } catch {
    return;
  }
  try {
    await api('data/configs/delete', { id: row.id });
    await load();
    ElMessage.success('已删除');
  } catch (error) {
    ElMessage.error(error.message || '删除失败');
  }
}

/* ---------- CSV 备用通道 ---------- */
function openCsv() {
  resetCsv();
  csvVisible.value = true;
}

function resetCsv() {
  picked.value = null;
  fileName.value = '';
  if (fileInput.value) fileInput.value.value = '';
}

function onFileChange(event) {
  picked.value = event.target.files?.[0] || null;
  fileName.value = picked.value?.name || '';
}

async function submit() {
  if (!picked.value) return ElMessage.warning('请选择 CSV 文件');
  busy.value = true;
  try {
    const result = await api('import', { csv: await picked.value.text() });
    await Promise.all([refresh(), load()]);
    csvVisible.value = false;
    ElMessage.success(
      `已处理 ${result.count} 行：新增 ${result.inserted ?? 0}、更新 ${result.updated ?? 0}、重复跳过 ${result.skipped ?? 0}`
    );
  } catch (error) {
    ElMessage.error(error.message || '导入失败');
  } finally {
    busy.value = false;
  }
}

onMounted(load);
</script>

<style scoped>
.sync-records-dialog { max-width: calc(100vw - 32px); }
.data-entry-page { --entry-border: var(--line); }
.entry-section-head { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 12px; }
.entry-section-head h3 { margin: 0; font-size: 13.5px; }
.entry-meta { white-space: nowrap; }
.src-grid { grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; margin-bottom: 12px; }
.src-card { border: 1px solid var(--line); border-radius: var(--radius); padding: 16px 18px; transition: border-color .15s; }
.source-clickable { cursor: pointer; }
.source-config-link {
  align-self: flex-end; margin-bottom: 10px;
  border: 0; background: none; padding: 0;
  color: var(--ink-3); cursor: pointer; font: inherit; font-size: 12px;
}
.source-config-link:hover { color: var(--accent); }
.source-clickable:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }
.src-card:hover { border-color: var(--accent-line); }
.source-identity { display: flex; align-items: center; gap: 9px; margin-bottom: 6px; }
/* 来源标识统一成同一块灰底方块：六个不同底色会跟状态色抢注意力 */
.source-avatar {
  display: grid; place-items: center;
  width: 26px; height: 26px;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  background: #f4f7f8;
  color: var(--ink-1);
  font-size: 13px; font-weight: 600;
}
.src-health {
  display: flex; align-items: center; flex-wrap: wrap; gap: 4px 12px;
  margin: 10px 0 2px; padding: 0 0 0 9px;
  border-left: 2px solid var(--line);
  color: var(--ink-2); font-size: 12px;
}
.src-health b { color: var(--ink-1); font-weight: 600; font-variant-numeric: tabular-nums; }
.src-health.health-红 { border-left-color: var(--up); }
.src-health.health-黄 { border-left-color: var(--warn); }
.src-health.health-绿 { border-left-color: var(--down); }
.src-facts {
  display: grid; grid-template-columns: 1fr 1fr;
  padding: 12px 0; margin: 12px 0;
  border-top: 1px solid var(--line-2); border-bottom: 1px solid var(--line-2);
  font-size: 12px; color: var(--ink-3);
}
.src-facts b { display: block; margin-top: 1px; font-size: 15px; font-weight: 600; color: var(--ink-1); }
.src-facts span:last-child { grid-column: 1 / -1; }
.source-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.source-actions :deep(.el-button + .el-button) { margin-left: 0; }
.source-last-sync { display: flex; justify-content: space-between; gap: 8px; margin-top: 14px; color: var(--ink-3); font-size: 11.5px; }
.src-add { flex-direction: column; min-height: 220px; border-radius: var(--radius); background: var(--surface); border-style: dashed; gap: 10px; }
.src-add > span {
  display: grid; place-items: center;
  width: 34px; height: 34px; border-radius: var(--radius);
  background: var(--accent-soft); color: var(--accent);
  font-size: 22px; line-height: 1;
}
.src-add b { font-size: 13px; font-weight: 500; }
.src-add small { color: var(--ink-3); }
.data-entry-page > .panel { padding: 18px 20px; border-radius: var(--radius); border: 1px solid var(--line); margin-bottom: 16px; }
.job-filter { padding: 10px 12px; border-radius: var(--radius); background: var(--surface); border: 1px solid var(--line); display: flex; flex-wrap: wrap; gap: 8px; }
:deep(.el-table .el-table__cell) { padding-top: 9px; padding-bottom: 9px; }
:deep(.page-head) { align-items: flex-start; gap: 20px; margin-bottom: 16px; }
:deep(.page-head > .row) { flex-wrap: wrap; justify-content: flex-end; }
@media (max-width: 1100px) { :deep(.page-head) { flex-wrap: wrap; } }
@media (max-width: 600px) { .src-grid { grid-template-columns: minmax(0, 1fr); } .data-entry-page > .panel { padding: 14px; } :deep(.el-dialog) { max-width: calc(100vw - 24px); } .entry-meta { display: none; } }

/* 内联巡检状态点 */
.health-dot { width: 6px; height: 6px; border-radius: 50%; flex: none; }
.health-dot.dot-绿 { background: var(--down); }
.health-dot.dot-黄 { background: var(--warn); }
.health-dot.dot-红 { background: var(--up); }
.stale-warn { color: var(--warn) !important; }
.stale-tag { color: var(--ink-3); font-size: 12px; }
.stale-tag.stale-warn { font-weight: 600; }
.troubleshoot-list { margin: 6px 0 0 18px; padding: 0; color: var(--ink-2); font-size: 13px; line-height: 1.9; }
</style>
