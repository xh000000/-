/* Menu names and hierarchy follow the supplied user manual and its sidebar screenshots. */
const menuLeaf=(label,target=null,admin=false,note='')=>({label,target,admin,note});
const RESEARCH_MENU=[
 {label:'BI看板',icon:'▣'},
 {label:'投研资源库',icon:'◈',note:'手册中的外部资源服务，尚未接入'},
 {label:'外部链接',icon:'↗'},
 {label:'研报管理',icon:'▤',children:[menuLeaf('研报中心','研报中心'),menuLeaf('分类列表','分类配置',true),menuLeaf('作者管理','作者管理',true),menuLeaf('品种管理','品种管理',true),menuLeaf('云盘','云盘'),menuLeaf('文档管理库','文档管理库'),menuLeaf('素材库','素材库')]},
 {label:'智能PPT',icon:'▧'},
 {label:'审批管理',icon:'☷',children:[menuLeaf('审批列表','审核中心')]},
 {label:'数据源',icon:'▱',children:[menuLeaf('手工数据录入','数据中心',false,'当前支持CSV导入和数据记录查看'),...['GPR地缘风险指数','美国农业部','郑商所','大商所','上期所','中金所','上期能源','广期所','期货数据库','EIA STEO报告','ICPI消费价格指数'].map(x=>menuLeaf(x))]},
 {label:'指标库',icon:'≡'},
 {label:'AI预测模型',icon:'◇'},
 {label:'量化策略',icon:'⌁',children:['信号生成','策略回测','因子库'].map(x=>menuLeaf(x))},
 {label:'预测指标',icon:'↗'},
 {label:'图库',icon:'▥'},
 {label:'我的投研',icon:'◎',children:['图库框架','我的图库','公共图库'].map(x=>menuLeaf(x))},
 {label:'表格',icon:'▦',children:['共享表格','自定义分析','时间序列表格','混合表格','平衡表'].map(x=>menuLeaf(x))},
 {label:'逻辑图',icon:'♧'},
 {label:'语义分析',icon:'▯',children:['AI纪要','文档管理','标签管理','文档对比','语音识别'].map(x=>menuLeaf(x))},
 {label:'统计分析',icon:'♙',children:['相关性分析','拟合方程曲线','统计特征','跨品种分析','区间分析','STL趋势分解','残差分析'].map(x=>menuLeaf(x))},
 {label:'供应分析',icon:'♧',children:[menuLeaf('装置检修')]},
 {label:'工具箱',icon:'▢',children:['CCF化纤信息装置','事件日历','AI问答','商品价格曲线','持仓分析','联储观察','预警管理'].map(x=>menuLeaf(x))},
 {label:'数据报表管理',icon:'▥',children:['钢联化工统计表','同花顺数据统计表','Wind数据统计表','钢联API数据统计表','数据源巡检监控','观点考核'].map(x=>menuLeaf(x))},
 {label:'系统设置',icon:'⚙',admin:true,children:[menuLeaf('部门管理'),menuLeaf('角色管理'),menuLeaf('数据刷新设置'),menuLeaf('数据操作权限'),menuLeaf('手工数据权限'),menuLeaf('基本配置','系统管理',true,'当前支持账号及外部模型配置'),menuLeaf('外部链接配置'),menuLeaf('数据源终端管理'),menuLeaf('审批流配置','审批流配置',true),menuLeaf('图表配置')]}
];
let expandedMenu=new Set(['研报管理']);
try{const saved=JSON.parse(localStorage.getItem('research.sidebar.expanded')||'null');if(Array.isArray(saved))expandedMenu=new Set(saved.filter(x=>typeof x==='string'))}catch{}
function renderSidebar(){
 const admin=state.user.role==='admin';
 const leaf=(item,child=false)=>{if(item.admin&&!admin)return '';const enabled=!!item.target;return `<button class="menu-leaf ${child?'nav-child':''} ${enabled&&page===item.target?'active':''}" ${enabled?`onclick="go('${item.target}')"`:'disabled aria-disabled="true"'} title="${esc(item.note||(!enabled?'该模块尚未接入':''))}" ${enabled&&page===item.target?'aria-current="page"':''}>${child?'<span class="menu-dash">－</span>':''}<span class="menu-name">${esc(item.label)}</span>${enabled?'':'<small class="menu-pending">未接入</small>'}</button>`};
 return RESEARCH_MENU.filter(item=>!item.admin||admin).map((item,i)=>{if(!item.children)return `<div class="menu-single"><span class="menu-icon">${item.icon}</span>${leaf(item)}</div>`;const children=item.children.filter(x=>!x.admin||admin);if(!children.length)return '';const open=expandedMenu.has(item.label);return `<section class="menu-section"><button class="menu-toggle ${children.some(x=>x.target===page)?'contains-active':''}" aria-expanded="${open}" aria-controls="sidebar-group-${i}" onclick="toggleSidebarGroup(${i})"><span class="menu-icon">${item.icon}</span><span class="menu-name">${esc(item.label)}</span><span class="menu-chevron">${open?'⌃':'⌄'}</span></button><div id="sidebar-group-${i}" class="menu-children" ${open?'':'hidden'}>${children.map(x=>leaf(x,true)).join('')}</div></section>`}).join('');
}
function toggleSidebarGroup(i){const item=RESEARCH_MENU[i];if(expandedMenu.has(item.label))expandedMenu.delete(item.label);else expandedMenu.add(item.label);try{localStorage.setItem('research.sidebar.expanded',JSON.stringify([...expandedMenu]))}catch{}const nav=document.getElementById('sidebar-nav');const scroll=nav.scrollTop;nav.innerHTML=renderSidebar();nav.scrollTop=scroll}
function menuBreadcrumb(target){for(const item of RESEARCH_MENU){const child=item.children?.find(x=>x.target===target);if(child)return item.label+' / '+child.label;if(item.target===target)return item.label}return target}
