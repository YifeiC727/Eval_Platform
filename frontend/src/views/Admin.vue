<template>
  <el-container style="min-height: calc(100vh - 100px);">
    <el-aside width="180px" style="background: #fff; border-right: 1px solid #e8ecf0;">
      <el-menu :default-active="activeMenu" @select="handleMenuSelect" style="border: none;">
        <el-menu-item index="overview">
          <span>总览</span>
        </el-menu-item>
        <el-menu-item index="monitor">
          <span>任务监控</span>
        </el-menu-item>
        <el-menu-item index="search">
          <span>搜索题目</span>
        </el-menu-item>
        <el-menu-item index="qc">
          <span>质检抽查</span>
        </el-menu-item>
        <el-menu-item index="annotators">
          <span>标注员</span>
        </el-menu-item>
        <el-menu-item index="import">
          <span>数据导入</span>
        </el-menu-item>
        <el-menu-item index="assign">
          <span>任务分配</span>
        </el-menu-item>
        <el-menu-item index="export">
          <span>导出结果</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-main style="padding: 24px;">
      <!-- 总览 -->
      <div v-if="activeMenu === 'overview'">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
          <h2 style="margin: 0;">项目总览</h2>
          <el-select v-model="currentProject" placeholder="选择项目" style="width: 240px;" @change="loadOverview">
            <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </div>
        <el-row :gutter="16">
          <el-col :span="6">
            <el-card shadow="hover"><el-statistic title="题目数" :value="overview.total_questions" /></el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover"><el-statistic title="视频数" :value="overview.total_videos" /></el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover"><el-statistic title="检查点总数" :value="overview.total_checkpoints" /></el-card>
          </el-col>
          <el-col :span="6">
            <el-card shadow="hover"><el-statistic title="已提交标注" :value="overview.submitted_annotations" /></el-card>
          </el-col>
        </el-row>

        <el-row :gutter="16" style="margin-top: 16px;">
          <el-col :span="12">
            <el-card shadow="hover">
              <template #header><span style="font-weight: 600;">标注进度（视频级别）</span></template>
              <div style="display: flex; flex-direction: column; gap: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span>未分配</span>
                  <el-tag type="info">{{ overview.annotation_progress?.not_started || 0 }}</el-tag>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span>标注中</span>
                  <el-tag type="warning">{{ overview.annotation_progress?.in_progress || 0 }}</el-tag>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span>A/B均已提交</span>
                  <el-tag type="success">{{ overview.annotation_progress?.both_submitted || 0 }}</el-tag>
                </div>
                <el-progress
                  :percentage="Math.round((overview.annotation_progress?.both_submitted || 0) / Math.max(overview.total_videos, 1) * 100)"
                  :stroke-width="20" style="margin-top: 8px;" />
              </div>
            </el-card>
          </el-col>
          <el-col :span="12">
            <el-card shadow="hover">
              <template #header><span style="font-weight: 600;">定案进度（检查点级别）</span></template>
              <div style="display: flex; flex-direction: column; gap: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span>已定案检查点</span>
                  <el-tag type="success">{{ overview.adjudication?.finalized || 0 }}</el-tag>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span>待第三人仲裁</span>
                  <el-tag type="warning">{{ overview.adjudication?.pending_third || 0 }}</el-tag>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span>待专家仲裁</span>
                  <el-tag type="danger">{{ overview.adjudication?.pending_expert || 0 }}</el-tag>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span>待比对检查点</span>
                  <el-tag type="info">{{ overview.adjudication?.ready_for_compare || 0 }}</el-tag>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span>不适用(NA)</span>
                  <el-tag>{{ Math.max(0, (overview.adjudication?.finalized || 0) > 0 ? overview.total_checkpoints - (overview.adjudication?.finalized || 0) - (overview.adjudication?.pending_third || 0) - (overview.adjudication?.pending_expert || 0) - (overview.adjudication?.ready_for_compare || 0) : 0) }}</el-tag>
                </div>
              </div>
            </el-card>
          </el-col>
        </el-row>

        <el-card style="margin-top: 16px;">
          <template #header><span style="font-weight: 600;">最近动态</span></template>
          <el-table :data="recentActivity" stripe size="small" v-if="recentActivity.length">
            <el-table-column prop="time" label="时间" width="160">
              <template #default="{ row }">{{ row.time?.slice(0, 16) }}</template>
            </el-table-column>
            <el-table-column prop="annotator" label="标注员" width="100" />
            <el-table-column prop="role" label="角色" width="60" />
            <el-table-column prop="question_id" label="题目" width="80" />
            <el-table-column prop="prompt_summary" label="Prompt" />
          </el-table>
          <el-empty v-else description="暂无动态" />
        </el-card>

        <el-card style="margin-top: 16px;">
          <template #header><span style="font-weight: 600;">项目操作</span></template>
          <div style="display: flex; gap: 12px;">
            <el-button type="warning" plain @click="clearAssignments" :disabled="!currentProject">
              清除任务分配
            </el-button>
            <el-button type="danger" plain @click="deleteProject" :disabled="!currentProject">
              删除当前项目
            </el-button>
          </div>
          <p style="color: #999; font-size: 12px; margin-top: 8px;">
            清除分配：删除当前项目的所有分配、标注和定案。删除项目：连同题目、检查点、视频一起彻底删除。
          </p>
        </el-card>
      </div>

      <!-- 任务监控 -->
      <div v-else-if="activeMenu === 'monitor'">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
          <h2>任务监控</h2>
          <div style="display: flex; gap: 12px;">
            <el-select v-model="monitorProject" placeholder="选择项目" style="width: 200px;" @change="loadProgress">
              <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
            <el-select v-model="monitorAnnotator" placeholder="按标注员筛选" clearable style="width: 150px;">
              <el-option v-for="u in annotators" :key="u.id" :label="u.display_name || u.username" :value="u.display_name || u.username" />
            </el-select>
            <el-select v-model="monitorFilter" placeholder="筛选状态" clearable style="width: 140px;">
              <el-option label="全部" value="" />
              <el-option label="未分配" value="未分配" />
              <el-option label="已分配待标注" value="已分配待标注" />
              <el-option label="A/B部分提交" value="A/B部分提交" />
              <el-option label="待第三人" value="待第三人" />
              <el-option label="已定案" value="已定案" />
            </el-select>
          </div>
        </div>
        <el-table :data="filteredProgress" stripe style="width: 100%;" max-height="600">
          <el-table-column prop="video_id" label="视频" width="80" />
          <el-table-column prop="question_id" label="题目" width="80" />
          <el-table-column prop="prompt_summary" label="Prompt" min-width="200" show-overflow-tooltip />
          <el-table-column prop="checkpoint_count" label="检查点" width="70" />
          <el-table-column prop="status" label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ row.status }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="annotator_a" label="A" width="80" />
          <el-table-column prop="annotator_b" label="B" width="80" />
          <el-table-column prop="annotator_third" label="第三人" width="80" />
          <el-table-column prop="finalized" label="定案数" width="70" />
          <el-table-column label="操作" width="150">
            <template #default="{ row }">
              <el-button size="small" type="primary" link @click="viewComparison(row.video_id)">详情</el-button>
              <el-button size="small" type="danger" link @click="resetSingleTask(row)">重置</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-pagination v-if="progressTotal > 50" layout="prev, pager, next"
          :total="progressTotal" :page-size="50" v-model:current-page="progressPage"
          @current-change="loadProgress" style="margin-top: 16px; justify-content: center;" />
      </div>

      <!-- 搜索题目 -->
      <div v-else-if="activeMenu === 'search'">
        <h2 style="margin-bottom: 16px;">搜索题目</h2>
        <el-card>
          <div style="display: flex; gap: 12px; margin-bottom: 16px;">
            <el-input v-model="searchQuery" placeholder="搜索 Prompt 关键词或题目ID (如 Q0035)" style="flex: 1;"
              @keyup.enter="doSearch" clearable />
            <el-select v-model="searchAbility" placeholder="按能力筛选" clearable style="width: 200px;">
              <el-option v-for="a in abilityOptions" :key="a" :label="a" :value="a" />
            </el-select>
            <el-button type="primary" @click="doSearch">搜索</el-button>
          </div>
          <el-table :data="searchResults" stripe v-if="searchResults.length">
            <el-table-column prop="question_id" label="题目ID" width="80" />
            <el-table-column prop="prompt" label="Prompt" min-width="300" show-overflow-tooltip />
            <el-table-column prop="checkpoint_count" label="检查点" width="70" />
            <el-table-column label="能力" width="150">
              <template #default="{ row }">
                <el-tag v-for="a in row.abilities" :key="a" size="small" style="margin: 2px;">{{ a }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100">
              <template #default="{ row }">
                <el-button size="small" @click="viewComparison(row.video_id)" :disabled="!row.video_id">A/B对比</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-else-if="searchDone" description="未找到匹配结果" />
          <el-pagination v-if="searchTotal > 20" layout="prev, pager, next" :total="searchTotal" :page-size="20"
            v-model:current-page="searchPage" @current-change="doSearch" style="margin-top: 12px;" />
        </el-card>
      </div>

      <!-- 质检抽查 -->
      <div v-else-if="activeMenu === 'qc'">
        <h2 style="margin-bottom: 16px;">质检抽查</h2>
        <el-card style="margin-bottom: 16px;">
          <div style="display: flex; gap: 12px; align-items: center;">
            <span>随机抽取已标注视频进行质检</span>
            <el-input-number v-model="qcSampleCount" :min="1" :max="50" size="small" />
            <el-button type="primary" @click="doSample">抽取</el-button>
          </div>
        </el-card>
        <el-table :data="qcSamples" stripe v-if="qcSamples.length">
          <el-table-column prop="video_id" label="视频" width="80" />
          <el-table-column prop="question_id" label="题目" width="80" />
          <el-table-column prop="prompt_summary" label="Prompt" min-width="250" show-overflow-tooltip />
          <el-table-column prop="annotator_a" label="A" width="80" />
          <el-table-column prop="annotator_b" label="B" width="80" />
          <el-table-column prop="checkpoint_count" label="检查点" width="70" />
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button type="primary" size="small" @click="viewComparison(row.video_id)">查看对比</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 标注详情 -->
        <el-dialog v-model="showComparison" :title="`标注详情 — ${comparisonData?.video_id} ${comparisonData?.question_id}`" width="90%" top="5vh">
          <div v-if="comparisonData">
            <div style="display: flex; gap: 16px; margin-bottom: 16px; align-items: center; flex-wrap: wrap;">
              <el-tag v-if="comparisonData.annotator_a">标注员A: {{ comparisonData.annotator_a }}</el-tag>
              <el-tag v-if="comparisonData.annotator_b" type="success">标注员B: {{ comparisonData.annotator_b }}</el-tag>
              <el-tag v-if="comparisonData.annotator_third" type="warning">第三人: {{ comparisonData.annotator_third }}</el-tag>
              <el-tag v-if="comparisonData.annotator_b" :type="comparisonData.disagree_count > 0 ? 'danger' : 'success'">
                一致: {{ comparisonData.agree_count }} | 分歧: {{ comparisonData.disagree_count }}
              </el-tag>
              <el-tag type="info">只读模式</el-tag>
            </div>
            <div style="background: #f8fafc; padding: 12px; border-radius: 6px; margin-bottom: 16px; font-size: 14px; line-height: 1.7; white-space: pre-wrap;">
              {{ comparisonData.prompt }}
            </div>
            <el-table :data="comparisonData.comparison" stripe size="small" :row-class-name="compRowClass">
              <el-table-column prop="checkpoint_id" label="检查点" width="110" />
              <el-table-column prop="text" label="要求" min-width="180" show-overflow-tooltip />
              <el-table-column prop="min_success_line" label="最低成功线" min-width="150" show-overflow-tooltip />
              <el-table-column label="A判定" width="70">
                <template #default="{ row }">
                  <span :style="{ color: scoreColor(row.a_score), fontWeight: 600 }">{{ row.a_score || '-' }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="a_note" label="A备注" width="120" show-overflow-tooltip v-if="comparisonData.comparison.some(r => r.a_note)" />
              <el-table-column label="B判定" width="70" v-if="comparisonData.annotator_b">
                <template #default="{ row }">
                  <span :style="{ color: scoreColor(row.b_score), fontWeight: 600 }">{{ row.b_score || '-' }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="b_note" label="B备注" width="120" show-overflow-tooltip v-if="comparisonData.annotator_b && comparisonData.comparison.some(r => r.b_note)" />
              <el-table-column label="第三人" width="70" v-if="comparisonData.annotator_third">
                <template #default="{ row }">{{ row.third_score || '-' }}</template>
              </el-table-column>
              <el-table-column label="定案" width="70">
                <template #default="{ row }">
                  <strong>{{ row.final_score || '-' }}</strong>
                </template>
              </el-table-column>
              <el-table-column label="一致" width="60" v-if="comparisonData.annotator_b">
                <template #default="{ row }">
                  <span v-if="row.is_agree" style="color: #67c23a;">Y</span>
                  <span v-else-if="row.a_score && row.b_score" style="color: #e6393e; font-weight: 600;">N</span>
                  <span v-else>-</span>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </el-dialog>
      </div>

      <!-- 标注员 -->
      <div v-else-if="activeMenu === 'annotators'">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
          <h2>标注员工作量</h2>
          <el-button size="small" type="primary" @click="showCreateUser = true">添加用户</el-button>
        </div>
        <el-table :data="annotatorStats" stripe>
          <el-table-column prop="username" label="用户名" width="100" />
          <el-table-column prop="display_name" label="姓名" width="80" />
          <el-table-column prop="password" label="密码" width="120">
            <template #default="{ row }">
              <span style="font-family: monospace;">{{ row.password || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="total_tasks" label="总任务" width="70" />
          <el-table-column prop="submitted_tasks" label="已提交" width="70" />
          <el-table-column prop="pending_tasks" label="待完成" width="70" />
          <el-table-column prop="total_annotations" label="标注数" width="70" />
          <el-table-column label="完成率" width="120">
            <template #default="{ row }">
              <el-progress :percentage="row.completion_rate" :stroke-width="12" :text-inside="true" />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="280">
            <template #default="{ row }">
              <el-button size="small" @click="openEditUser(row)">编辑</el-button>
              <el-button size="small" @click="openSetPassword(row)">密码</el-button>
              <el-button size="small" type="warning" @click="resetUserTasks(row)">重置任务</el-button>
              <el-button size="small" type="danger" @click="deleteUser(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 数据导入 -->
      <div v-else-if="activeMenu === 'import'">
        <h2 style="margin-bottom: 16px;">数据导入</h2>

        <el-alert type="info" :closable="false" style="margin-bottom: 20px;">
          <template #title>导入流程</template>
          <p>第①步：选择或新建项目 → 第②步：上传检查点拆解 Excel → 第③步：点击"开始导入"</p>
          <p style="margin-top: 4px; color: #666;">支持文件格式：【v6】t2v-10s_检查点拆解_含覆盖统计.xlsx（需包含"原题"和"检查点拆解"两个 sheet）</p>
        </el-alert>

        <el-steps :active="importStep" align-center style="margin-bottom: 24px;">
          <el-step title="选择项目" :status="selectedProject ? 'success' : 'process'" />
          <el-step title="上传文件" :status="selectedFile ? 'success' : (selectedProject ? 'process' : 'wait')" />
          <el-step title="执行导入" :status="importResult ? 'success' : 'wait'" />
        </el-steps>

        <el-card>
          <div style="display: flex; flex-direction: column; gap: 24px;">
            <!-- Step 1: Project -->
            <div>
              <h4 style="margin-bottom: 8px;">① 选择项目</h4>
              <div style="display: flex; gap: 12px; align-items: center;">
                <el-select v-model="selectedProject" placeholder="选择已有项目" style="width: 300px;">
                  <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
                </el-select>
                <el-button @click="showCreateProject = true">新建项目</el-button>
              </div>
            </div>

            <!-- Step 2: Upload -->
            <div>
              <h4 style="margin-bottom: 8px;">② 上传检查点拆解 Excel</h4>
              <el-upload :auto-upload="false" :limit="1" accept=".xlsx,.xls" :on-change="handleFileChange"
                :disabled="!selectedProject" drag style="width: 100%;">
                <div style="padding: 20px;">
                  <p style="font-size: 16px;">拖拽或点击选择 .xlsx 文件</p>
                  <p style="color: #999; font-size: 13px; margin-top: 4px;">文件需包含"原题"和"检查点拆解"两个 sheet</p>
                </div>
              </el-upload>
              <p v-if="selectedFile" style="margin-top: 8px; color: #67c23a;">已选择: {{ selectedFile.name }}</p>
            </div>

            <!-- Step 3: Execute -->
            <div>
              <h4 style="margin-bottom: 8px;">③ 执行导入</h4>
              <el-button type="primary" size="large" @click="doImport" :loading="importing"
                :disabled="!selectedProject || !selectedFile">
                开始导入
              </el-button>
              <span v-if="!selectedProject" style="margin-left: 12px; color: #999; font-size: 13px;">请先选择项目</span>
              <span v-else-if="!selectedFile" style="margin-left: 12px; color: #999; font-size: 13px;">请先上传文件</span>
            </div>
          </div>

          <el-alert v-if="importResult" :title="importResult" type="success" show-icon style="margin-top: 20px;" />
        </el-card>
      </div>

      <!-- 任务分配 -->
      <div v-else-if="activeMenu === 'assign'">
        <h2 style="margin-bottom: 16px;">任务分配</h2>

        <el-card style="margin-bottom: 16px;">
          <el-form label-position="top">
            <el-form-item label="项目">
              <el-select v-model="assignProject" placeholder="选择项目" style="width: 300px;">
                <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="分配方式">
              <el-radio-group v-model="assignMode">
                <el-radio-button value="round_robin">均匀轮转</el-radio-button>
                <el-radio-button value="manual">手动指派</el-radio-button>
                <el-radio-button value="ai">AI 智能分配</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="标注模式">
              <el-radio-group v-model="annotationMode">
                <el-radio-button value="dual">双人盲标（A/B + 仲裁）</el-radio-button>
                <el-radio-button value="single">单人标注</el-radio-button>
              </el-radio-group>
              <p style="color: #999; font-size: 12px; margin-top: 4px;">
                {{ annotationMode === 'dual' ? '每个视频分配2人独立标注，不一致时引入第三人仲裁' : '每个视频仅1人标注，不做比对和仲裁，适合快速出结果' }}
              </p>
            </el-form-item>

            <!-- 均匀轮转 -->
            <template v-if="assignMode === 'round_robin'">
              <el-form-item label="标注员（至少选2人，系统按顺序均匀轮转配对）">
                <el-select v-model="assignAnnotators" multiple placeholder="选择标注员" style="width: 100%;">
                  <el-option v-for="u in annotators" :key="u.id" :label="u.display_name || u.username" :value="u.id" />
                </el-select>
              </el-form-item>
              <div style="display: flex; gap: 12px;">
                <el-button @click="previewAssign" :loading="previewing" :disabled="!assignProject || assignAnnotators.length < 2">
                  预览分配
                </el-button>
                <el-button type="primary" @click="doBatchAssign" :loading="assigning" :disabled="!assignProject || assignAnnotators.length < 2">
                  确认执行
                </el-button>
              </div>
            </template>

            <!-- 手动指派 -->
            <template v-if="assignMode === 'manual'">
              <el-alert type="info" :closable="false" style="margin-bottom: 16px;">
                手动指定每个视频的 A/B 标注员。格式：选择视频范围 + 指定两人。
              </el-alert>
              <el-form-item label="视频范围（起始ID - 结束ID）">
                <div style="display: flex; gap: 8px; align-items: center;">
                  <el-input v-model="manualRange.start" placeholder="V0001" style="width: 120px;" />
                  <span>—</span>
                  <el-input v-model="manualRange.end" placeholder="V0050" style="width: 120px;" />
                </div>
              </el-form-item>
              <el-form-item label="A 标注员">
                <el-select v-model="manualA" placeholder="选择" style="width: 200px;">
                  <el-option v-for="u in annotators" :key="u.id" :label="u.display_name || u.username" :value="u.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="B 标注员">
                <el-select v-model="manualB" placeholder="选择" style="width: 200px;">
                  <el-option v-for="u in annotators" :key="u.id" :label="u.display_name || u.username" :value="u.id" />
                </el-select>
              </el-form-item>
              <el-button type="primary" @click="doManualAssign" :loading="assigning"
                :disabled="!manualRange.start || !manualRange.end || !manualA || !manualB">
                执行手动指派
              </el-button>
            </template>

            <!-- AI 智能分配 -->
            <template v-if="assignMode === 'ai'">
              <el-form-item label="标注员">
                <el-select v-model="assignAnnotators" multiple placeholder="选择标注员" style="width: 100%;">
                  <el-option v-for="u in annotators" :key="u.id" :label="u.display_name || u.username" :value="u.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="分配指令（用自然语言描述你的分配意图）">
                <el-input v-model="aiInstruction" type="textarea" :rows="3"
                  placeholder="例如：前100个给ann_01和ann_02，剩下的均匀分给其他人；或：让任务量少的人多分一些" />
              </el-form-item>
              <div style="display: flex; gap: 12px;">
                <el-button @click="doAiSuggest" :loading="aiLoading" :disabled="!assignProject || assignAnnotators.length < 2">
                  生成方案
                </el-button>
                <el-button type="primary" @click="doAiConfirm" :loading="assigning" :disabled="!aiPlan.length">
                  确认执行此方案
                </el-button>
              </div>
            </template>
          </el-form>
        </el-card>

        <!-- Preview / Result -->
        <el-card v-if="assignResult || previewData">
          <template #header><span style="font-weight: 600;">{{ aiPlan.length ? 'AI 方案预览' : '分配结果' }}</span></template>

          <div v-if="previewData" style="margin-bottom: 16px;">
            <p><strong>待分配视频:</strong> {{ previewData.total_to_assign }} 个</p>
            <p><strong>每人任务量:</strong></p>
            <div style="display: flex; gap: 8px; flex-wrap: wrap; margin: 8px 0;">
              <el-tag v-for="(count, name) in previewData.per_person" :key="name">{{ name }}: {{ count }}</el-tag>
            </div>
            <el-table v-if="previewData.preview" :data="previewData.preview" stripe size="small" max-height="300" style="margin-top: 12px;">
              <el-table-column prop="video_id_str" label="视频" width="80" />
              <el-table-column prop="annotator_a_name" label="A" width="100" />
              <el-table-column prop="annotator_b_name" label="B" width="100" />
            </el-table>
            <p v-if="previewData.preview && previewData.plan_count > 30" style="color: #999; font-size: 13px; margin-top: 8px;">
              仅显示前 30 条，共 {{ previewData.plan_count }} 条
            </p>
          </div>

          <el-alert v-if="assignResult" :title="assignResult" type="success" show-icon />
        </el-card>
      </div>

      <!-- 导出 -->
      <div v-else-if="activeMenu === 'export'">
        <h2 style="margin-bottom: 16px;">导出结果</h2>
        <el-card>
          <p style="margin-bottom: 16px; color: #666;">导出兼容「V6纯T2V外包评测标准回传模板」格式的 Excel 文件。</p>
          <el-button type="success" size="large" @click="doExport">下载评测结果 Excel</el-button>
        </el-card>
      </div>
    </el-main>
  </el-container>

  <!-- Dialogs -->
  <el-dialog v-model="showCreateProject" title="新建项目" width="400px">
    <el-form label-position="top">
      <el-form-item label="项目ID"><el-input v-model="newProject.project_id" /></el-form-item>
      <el-form-item label="项目名称"><el-input v-model="newProject.name" /></el-form-item>
      <el-form-item label="模型版本"><el-input v-model="newProject.model_version" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showCreateProject = false">取消</el-button>
      <el-button type="primary" @click="createProject">创建</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="showCreateUser" title="添加用户" width="400px">
    <el-form label-position="top">
      <el-form-item label="ERP工号（登录名）"><el-input v-model="newUser.username" /></el-form-item>
      <el-form-item label="姓名"><el-input v-model="newUser.display_name" /></el-form-item>
      <el-form-item label="角色">
        <el-select v-model="newUser.role" style="width: 100%;">
          <el-option label="标注员" value="annotator" />
          <el-option label="组长" value="lead" />
          <el-option label="管理员" value="admin" />
          <el-option label="管理员+标注员" value="admin,annotator" />
        </el-select>
      </el-form-item>
      <el-form-item label="登录密码（可选）"><el-input v-model="newUser.password" type="password" show-password placeholder="不填则无需密码" /></el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showCreateUser = false">取消</el-button>
      <el-button type="primary" @click="createUser">创建</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="showSetPassword" title="设置密码" width="400px">
    <p style="margin-bottom: 12px;">为 <strong>{{ setPasswordUser?.display_name || setPasswordUser?.username }}</strong> 设置登录密码</p>
    <el-input v-model="setPasswordValue" type="password" show-password placeholder="输入新密码（至少4位）" />
    <template #footer>
      <el-button @click="showSetPassword = false">取消</el-button>
      <el-button type="primary" @click="doSetPassword">确认设置</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="showEditUser" title="编辑用户" width="400px">
    <el-form label-position="top">
      <el-form-item label="用户名"><el-input v-model="editUserData.username" /></el-form-item>
      <el-form-item label="姓名"><el-input v-model="editUserData.display_name" /></el-form-item>
      <el-form-item label="角色">
        <el-select v-model="editUserData.role" style="width: 100%;">
          <el-option label="标注员" value="annotator" />
          <el-option label="组长" value="lead" />
          <el-option label="管理员" value="admin" />
          <el-option label="管理员+标注员" value="admin,annotator" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="showEditUser = false">取消</el-button>
      <el-button type="primary" @click="doEditUser">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api.js'

const activeMenu = ref('overview')
const currentProject = ref(null)
const overview = ref({})
const recentActivity = ref([])
const annotatorStats = ref([])
const progressItems = ref([])
const progressTotal = ref(0)
const progressPage = ref(1)
const monitorFilter = ref('')
const monitorProject = ref(null)
const monitorAnnotator = ref('')
const searchQuery = ref('')
const searchAbility = ref('')
const searchResults = ref([])
const searchTotal = ref(0)
const searchPage = ref(1)
const searchDone = ref(false)
const abilityOptions = ref([])
const qcSampleCount = ref(10)
const qcSamples = ref([])
const showComparison = ref(false)
const comparisonData = ref(null)
const projects = ref([])
const users = ref([])
const selectedProject = ref(null)
const selectedFile = ref(null)
const importing = ref(false)
const importResult = ref('')
const importStep = computed(() => {
  if (importResult.value) return 3
  if (selectedFile.value) return 2
  if (selectedProject.value) return 1
  return 0
})
const showCreateProject = ref(false)
const showCreateUser = ref(false)
const showSetPassword = ref(false)
const showEditUser = ref(false)
const editUserData = ref({ id: null, username: '', display_name: '', role: '' })
const setPasswordUser = ref(null)
const setPasswordValue = ref('')
const newProject = ref({ project_id: '', name: '', model_version: '' })
const newUser = ref({ username: '', display_name: '', password: '', role: 'annotator' })
const assignProject = ref(null)
const assignAnnotators = ref([])
const assignMode = ref('round_robin')
const annotationMode = ref('dual')
const assigning = ref(false)
const assignResult = ref('')
const previewing = ref(false)
const previewData = ref(null)
const manualRange = ref({ start: '', end: '' })
const manualA = ref(null)
const manualB = ref(null)
const aiInstruction = ref('')
const aiLoading = ref(false)
const aiPlan = ref([])

const annotators = computed(() => users.value.filter(u => u.role === 'annotator'))
const filteredProgress = computed(() => {
  let list = progressItems.value
  if (monitorFilter.value) {
    list = list.filter(p => p.status === monitorFilter.value)
  }
  if (monitorAnnotator.value) {
    list = list.filter(p => p.annotator_a === monitorAnnotator.value || p.annotator_b === monitorAnnotator.value || p.annotator_third === monitorAnnotator.value)
  }
  return list
})

function statusType(status) {
  const map = { '未分配': 'info', '已分配待标注': '', '已定案': 'success', '待第三人': 'warning', 'A/B部分提交': '', '比对完成': 'success', '第三人已提交': 'success' }
  return map[status] || ''
}

function handleMenuSelect(key) {
  activeMenu.value = key
  if (key === 'overview') loadOverview()
  if (key === 'monitor') loadProgress()
  if (key === 'annotators') loadAnnotatorStats()
  if (key === 'search') loadAbilityOptions()
}

onMounted(async () => {
  await Promise.all([loadOverview(), loadProjects(), loadUsers()])
})

async function loadAbilityOptions() {
  if (abilityOptions.value.length) return
  try {
    const { data } = await api.get('/scores/abilities')
    abilityOptions.value = data.map(a => a.ability_id)
  } catch {}
}

async function doSearch() {
  searchDone.value = false
  try {
    const { data } = await api.get('/qc/search', { params: { q: searchQuery.value, ability_id: searchAbility.value || undefined, page: searchPage.value, page_size: 20 } })
    searchResults.value = data.items
    searchTotal.value = data.total
    searchDone.value = true
  } catch (e) { ElMessage.error('搜索失败') }
}

async function doSample() {
  try {
    const { data } = await api.get('/qc/sample', { params: { count: qcSampleCount.value } })
    qcSamples.value = data.items
    if (!data.items.length) ElMessage.info('暂无已提交的标注可供抽检')
  } catch (e) { ElMessage.error('抽取失败') }
}

async function viewComparison(videoId) {
  if (!videoId) return
  try {
    const { data } = await api.get(`/qc/compare/${videoId}`)
    comparisonData.value = data
    showComparison.value = true
  } catch (e) { ElMessage.error('加载对比失败: ' + (e.response?.data?.detail || e.message)) }
}

function scoreColor(score) {
  if (score === 'C') return '#67c23a'
  if (score === 'R') return '#e6a23c'
  if (score === 'N') return '#e6393e'
  return '#999'
}

function compRowClass({ row }) {
  if (row.a_score && row.b_score && !row.is_agree) return 'disagree-row'
  return ''
}

async function loadOverview() {
  try {
    const params = currentProject.value ? { project_id: currentProject.value } : {}
    const [ovRes, actRes] = await Promise.all([
      api.get('/stats/overview', { params }),
      api.get('/stats/recent-activity'),
    ])
    overview.value = ovRes.data
    recentActivity.value = actRes.data
  } catch (e) { console.error(e) }
}

async function loadProgress() {
  try {
    const params = { page: progressPage.value, page_size: 50 }
    if (monitorProject.value) params.project_id = monitorProject.value
    const { data } = await api.get('/assignments/progress', { params })
    progressItems.value = data.items
    progressTotal.value = data.total
  } catch (e) { console.error(e) }
}

async function loadAnnotatorStats() {
  try {
    const { data } = await api.get('/stats/annotators')
    annotatorStats.value = data
  } catch (e) { console.error(e) }
}

async function loadProjects() {
  const { data } = await api.get('/projects/')
  projects.value = data
  if (data.length && !currentProject.value) {
    currentProject.value = data[0].id
    monitorProject.value = data[0].id
  }
}

async function loadUsers() {
  const { data } = await api.get('/users/')
  users.value = data
}

function handleFileChange(file) { selectedFile.value = file.raw; selectedFile.value.name = file.name }

async function doImport() {
  if (!selectedFile.value || !selectedProject.value) return
  importing.value = true
  importResult.value = ''
  const formData = new FormData()
  formData.append('file', selectedFile.value)
  formData.append('project_id', selectedProject.value)
  try {
    const { data } = await api.post('/import/checkpoints', formData)
    importResult.value = `导入成功: ${data.questions} 题, ${data.checkpoints} 检查点, ${data.skipped} 跳过`
    loadOverview()
  } catch (e) {
    ElMessage.error('导入失败: ' + (e.response?.data?.detail || e.message))
  } finally { importing.value = false }
}

async function createProject() {
  try {
    await api.post('/projects/', newProject.value)
    ElMessage.success('创建成功')
    showCreateProject.value = false
    newProject.value = { project_id: '', name: '', model_version: '' }
    await loadProjects()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '创建失败') }
}

async function createUser() {
  try {
    await api.post('/users/', { username: newUser.value.username, display_name: newUser.value.display_name, password: newUser.value.password || null, role: newUser.value.role })
    ElMessage.success('创建成功')
    showCreateUser.value = false
    newUser.value = { username: '', display_name: '', password: '', role: 'annotator' }
    await loadUsers()
    await loadAnnotatorStats()
  } catch (e) { ElMessage.error(e.response?.data?.detail || '创建失败') }
}

async function deleteUser(row) {
  try {
    await ElMessageBox.confirm(`确认删除用户「${row.display_name || row.username}」？其所有任务和标注记录也将被删除。`, '删除用户', { type: 'error' })
    await api.delete(`/users/${row.id}`)
    ElMessage.success('已删除')
    await loadUsers()
    await loadAnnotatorStats()
  } catch {}
}

async function resetUserTasks(row) {
  const projectOptions = projects.value.map(p => p.name).join(' / ')
  try {
    const { value: selectedName } = await ElMessageBox.prompt(
      `选择要重置的项目（该标注员在该项目的所有任务将被释放）：`,
      `重置「${row.display_name}」的任务`,
      {
        inputValue: projects.value.find(p => p.id === currentProject.value)?.name || '',
        confirmButtonText: '确认重置',
        cancelButtonText: '取消',
        inputPlaceholder: '输入项目名称',
        inputValidator: (val) => {
          return projects.value.some(p => p.name === val) || '请输入正确的项目名称'
        },
      }
    )
    const project = projects.value.find(p => p.name === selectedName)
    if (!project) return
    await api.post(`/users/${row.id}/reset-tasks`, { project_id: project.id })
    ElMessage.success(`已重置「${row.display_name}」在「${selectedName}」中的任务`)
    await loadAnnotatorStats()
  } catch {}
}

async function previewAssign() {
  previewing.value = true
  previewData.value = null
  try {
    const { data } = await api.post('/assignments/assign', {
      mode: 'preview',
      project_id: assignProject.value,
      annotator_ids: assignAnnotators.value,
      annotation_mode: annotationMode.value,
    })
    previewData.value = data
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '预览失败')
  } finally { previewing.value = false }
}

async function doBatchAssign() {
  assigning.value = true
  assignResult.value = ''
  try {
    const { data } = await api.post('/assignments/assign', {
      mode: 'round_robin',
      project_id: assignProject.value,
      annotator_ids: assignAnnotators.value,
      annotation_mode: annotationMode.value,
    })
    assignResult.value = `分配完成: 创建 ${data.created} 个任务, 覆盖 ${data.videos_assigned} 个视频`
    previewData.value = null
    loadOverview()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '分配失败')
  } finally { assigning.value = false }
}

async function doManualAssign() {
  assigning.value = true
  assignResult.value = ''
  try {
    // Get video IDs in range
    const { data: progressData } = await api.get('/assignments/progress', { params: { page: 1, page_size: 9999 } })
    const allVideos = progressData.items
    const start = manualRange.value.start.toUpperCase()
    const end = manualRange.value.end.toUpperCase()
    const videosInRange = allVideos.filter(v => v.video_id >= start && v.video_id <= end)

    const assignments = videosInRange.map(v => ({
      video_id: v.video_id,
      annotator_a_id: manualA.value,
      annotator_b_id: manualB.value,
    }))

    // Need video DB IDs - use a different approach
    const { data } = await api.post('/assignments/assign', {
      mode: 'manual',
      assignments: assignments,
    })
    assignResult.value = `手动指派完成: 创建 ${data.created} 个任务, 跳过 ${data.skipped} 个`
    loadOverview()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '指派失败')
  } finally { assigning.value = false }
}

async function doAiSuggest() {
  aiLoading.value = true
  previewData.value = null
  aiPlan.value = []
  try {
    const { data } = await api.post('/assignments/ai-suggest', {
      project_id: assignProject.value,
      annotator_ids: assignAnnotators.value,
      instruction: aiInstruction.value,
      annotation_mode: annotationMode.value,
    })
    previewData.value = data
    aiPlan.value = data.plan_full || []
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || 'AI建议失败')
  } finally { aiLoading.value = false }
}

async function doAiConfirm() {
  if (!aiPlan.value.length) return
  assigning.value = true
  assignResult.value = ''
  try {
    const { data } = await api.post('/assignments/ai-confirm', { plan: aiPlan.value })
    assignResult.value = `AI方案已确认执行: 创建 ${data.created} 个任务, 跳过 ${data.skipped} 个`
    aiPlan.value = []
    previewData.value = null
    loadOverview()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '确认失败')
  } finally { assigning.value = false }
}

function doExport() {
  window.open('/api/export/results', '_blank')
}

async function clearAssignments() {
  const projectName = projects.value.find(p => p.id === currentProject.value)?.name || ''
  try {
    await ElMessageBox.confirm(
      `将清除项目「${projectName}」下的所有任务分配、标注记录和定案结果。此操作不可撤销。`,
      '确认清除',
      { type: 'error', confirmButtonText: '确认清除', cancelButtonText: '取消' }
    )
    const { data } = await api.post('/assignments/clear', { project_id: currentProject.value })
    ElMessage.success(`已清除: ${data.deleted_assignments} 个任务, ${data.deleted_annotations} 条标注, ${data.deleted_finals} 条定案`)
    loadOverview()
  } catch {}
}

async function deleteProject() {
  const projectName = projects.value.find(p => p.id === currentProject.value)?.name || ''
  try {
    await ElMessageBox.confirm(
      `将彻底删除项目「${projectName}」及其所有题目、检查点、视频、分配和标注数据。此操作不可恢复！`,
      '删除项目',
      { type: 'error', confirmButtonText: '确认删除', cancelButtonText: '取消' }
    )
    await api.delete(`/projects/${currentProject.value}`)
    ElMessage.success(`项目「${projectName}」已删除`)
    currentProject.value = null
    await loadProjects()
    if (projects.value.length) currentProject.value = projects.value[0].id
    loadOverview()
  } catch {}
}

function openSetPassword(row) {
  setPasswordUser.value = row
  setPasswordValue.value = ''
  showSetPassword.value = true
}

async function doSetPassword() {
  if (!setPasswordValue.value || setPasswordValue.value.length < 4) {
    ElMessage.warning('密码至少4位')
    return
  }
  try {
    await api.put(`/users/${setPasswordUser.value.id}/password`, { password: setPasswordValue.value })
    ElMessage.success('密码设置成功')
    showSetPassword.value = false
    await loadAnnotatorStats()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '设置失败')
  }
}

function openEditUser(row) {
  editUserData.value = { id: row.id, username: row.username, display_name: row.display_name || '', role: '' }
  showEditUser.value = true
}

async function doEditUser() {
  try {
    await api.put(`/users/${editUserData.value.id}`, {
      username: editUserData.value.username,
      display_name: editUserData.value.display_name,
      role: editUserData.value.role || undefined,
    })
    ElMessage.success('保存成功')
    showEditUser.value = false
    await loadUsers()
    await loadAnnotatorStats()
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  }
}

async function resetSingleTask(row) {
  try {
    await ElMessageBox.confirm(
      `重置视频「${row.video_id}」的标注？将删除该题的分配、标注和定案，视频变为未分配状态。`,
      '重置单题', { type: 'warning' }
    )
    await api.post('/assignments/reset-single', { video_id: row.video_id, annotator: row.annotator_a })
    ElMessage.success('已重置')
    loadProgress()
  } catch {}
}
</script>
