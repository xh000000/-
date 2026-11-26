import { nextTick } from 'vue';

/*
 * el-table 列宽拖拽修复（指标管理、品种管理共用）。
 *
 * 现象一：拖完列后表格右侧出现空白。
 *   原因：EP 拖拽后把该列写成固定 width；表里若再没有弹性列（只配 min-width 的列），
 *   列总宽就小于容器宽度，右侧空出来。
 * 现象二：第一列（弹性列）拖不动。
 *   原因：若把「被拖的列」改回弹性列，updateColumnsWidth 会把它重新撑满剩余空间，
 *   拖窄、拖宽都立刻弹回原宽，用户感知就是拖不动。
 *
 * 做法：被拖列保留拖后宽度（尊重用户意图），另选一列当弹性列吸收剩余宽度。
 *   1. 吸收列优先取最后一列（操作列：按钮右对齐，多余宽度落在按钮左侧最不突兀），
 *      被拖的正是它时退到剩下的最后一列（即第一列）。
 *   2. 吸收列的最小宽度取「设计宽度」而非 EP 默认的 80，否则容器不够时它会被压没；
 *      设计宽度必须在挂载时采集，绝不能取拖后宽度（否则第一列会被永久锁死）。
 *   3. 其余列固定为当前渲染宽度，保证表里只有一个弹性列，
 *      避免多弹性列按比例瓜分导致列宽乱跳。
 */

const NON_DATA_TYPES = ['selection', 'index', 'expand'];
const baselines = new WeakMap();

function isNum(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

/* 设计宽度基线：只认挂载时（尚未拖拽）的 width / min-width */
function baselineOf(column) {
  let base = baselines.get(column);
  if (!base) {
    base = {
      width: isNum(column.width) ? column.width : undefined,
      min: Number(column.minWidth) || 80,
    };
    baselines.set(column, base);
  }
  return base;
}

function designWidth(column) {
  const base = baselineOf(column);
  return base.width || base.min || 80;
}

/* 当前实际渲染宽度：固定列看 width，弹性列看 realWidth */
function currentWidth(column) {
  if (isNum(column.realWidth) && column.realWidth > 0) return column.realWidth;
  if (isNum(column.width) && column.width > 0) return column.width;
  return designWidth(column);
}

function dataColumnsOf(table) {
  const columns = table?.store?.states?.columns?.value || [];
  return columns.filter(item => !NON_DATA_TYPES.includes(item.type));
}

/* 返回是否采集完成（表格未挂载/列未注册时返回 false，由调用方重试） */
export function seedResizeBaselines(table) {
  const dataColumns = dataColumnsOf(table);
  if (!dataColumns.length) return false;
  dataColumns.forEach(baselineOf);
  return true;
}

export function createResizeHandler(tableRef) {
  /* 挂载后立刻采集设计宽度：晚于首次拖拽就会把拖后宽度当设计宽度，第一列会被锁死 */
  (function seed(attempt = 0) {
    nextTick(() => {
      if (seedResizeBaselines(tableRef.value)) return;
      if (attempt < 20) setTimeout(() => seed(attempt + 1), 50);
    });
  })();

  return function onHeaderDragend(newWidth, oldWidth, column) {
    nextTick(() => {
      const table = tableRef.value;
      const dataColumns = dataColumnsOf(table);
      if (!dataColumns.length) return;
      seedResizeBaselines(table);

      /* 被拖的列 EP 已写好 width/realWidth；按引用 + id 识别，避免把它选成吸收列 */
      const others = dataColumns.filter(item => item !== column && (!column?.id || item.id !== column.id));
      const pool = others.length ? others : dataColumns;
      const absorber = pool[pool.length - 1];

      dataColumns.forEach(item => {
        item.resizeWidth = undefined;
        if (item === absorber) {
          item.width = undefined;
          item.minWidth = designWidth(item);
        } else {
          item.width = currentWidth(item);
          item.minWidth = Math.min(designWidth(item), item.width);
        }
      });

      table.layout?.updateColumnsWidth?.();
    });
  };
}
