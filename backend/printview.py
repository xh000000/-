"""整篇研报的服务端渲染：输出独立 HTML，浏览器「打印 → 另存为 PDF」即得到 PDF。

版式逐项照《兴业期货日度策略》合集（2026 年 11 月共 12 期）还原：
- 首页深蓝品牌条 + 浅蓝标题带，内页为小标页眉 + 蓝色细分隔线；
- 一级章节「一、」微软雅黑 14pt 蓝色，二级板块「01」12pt 黑色加粗；
- 正文宋体 10.6pt、行距 1.89、首行缩进两字、两端对齐；「▍品种：观点」整行加粗；
- 每页深蓝色页脚带「请务必阅读正文之后的免责条款部分」+ 页码；
- 尾页依次为数据来源、投资咨询部（资格证号两列）、作者承诺、免责声明三条色带。

分页在浏览器端按 A4 实测高度切页（本文件内嵌脚本），因此预览与打印看到的是同一份排版。
文本内容在保存时已通过 richtext 白名单清洗，此处只做结构与样式拼装。
"""
import json, re, math
from html import escape

SANS = '"Microsoft YaHei","PingFang SC","Source Han Sans SC","Noto Sans CJK SC",sans-serif'
SERIF = 'SimSun,"Songti SC","Source Han Serif SC","Noto Serif CJK SC",serif'
RUNHEAD = '请务必阅读正文之后的免责条款部分'

CSS = """
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{background:#e9edf2;color:#1a1a1a;font-family:%(serif)s;-webkit-print-color-adjust:exact;print-color-adjust:exact}
.toolbar{position:sticky;top:0;z-index:9;display:flex;align-items:center;justify-content:flex-end;gap:16px;padding:9px 22px;background:#1f2d3d;color:#9fb0c0;font:12px/1.5 %(sans)s}
.toolbar b{color:#fff;font-weight:600}
.toolbar button{font:600 12px/1 %(sans)s;padding:8px 18px;border:0;border-radius:4px;background:#004099;color:#fff;cursor:pointer}
#sheets{padding:18px 0 40px}
.page{position:relative;width:210mm;height:297mm;margin:0 auto 16px;background:#fff;overflow:hidden;box-shadow:0 2px 16px rgba(16,38,64,.14)}

/* 首页：深蓝品牌条 + 浅蓝标题带 */
.brand{position:absolute;left:0;right:0;top:0;height:27.5mm;background:#004099;display:flex;align-items:center;justify-content:center}
.brand .logo{display:flex;align-items:center;gap:7mm}
.brand .logo svg{display:block}
.brand .logo b{display:block;color:#fff;font:700 21pt/1.25 %(sans)s;letter-spacing:.06em}
.brand .logo span{display:block;color:#bcd3ec;font:400 6.6pt/1.5 %(sans)s;letter-spacing:.1em}
.titleband{position:absolute;left:0;right:0;top:34.5mm;height:11.7mm;background:#94b3d6;display:flex;align-items:center;justify-content:center}
.titleband h1{margin:0;color:#014099;font:700 15pt/1 %(sans)s;letter-spacing:.06em}

/* 内页页眉：小标 + 栏目名 + 细分隔线 */
.run{position:absolute;left:31.8mm;width:146.5mm;top:15mm;display:flex;align-items:flex-end;justify-content:space-between;padding-bottom:2.4mm;border-bottom:.9pt solid #004099}
.run .mini{display:flex;align-items:center;gap:2mm}
.run .mini b{color:#014099;font:700 10.5pt/1 %(sans)s;letter-spacing:.04em}
.run .mini span{color:#7d97b5;font:400 5.4pt/1 %(sans)s;letter-spacing:.08em}
.run .rh{color:#014099;font:700 9pt/1 %(sans)s;letter-spacing:.08em;font-style:italic}

/* 页脚 */
.foot{position:absolute;left:0;right:0;bottom:0;height:10mm;background:#004099;color:#fff;display:flex;align-items:center;justify-content:center;font:600 9pt/10mm %(sans)s;letter-spacing:.04em}
.foot .pn{position:absolute;right:14mm;font:600 9.5pt/10mm %(sans)s}

/* 正文 */
.body{position:absolute;overflow:hidden;font:10.6pt/1.89 %(serif)s;color:#1a1a1a}
.body p{margin:0 0 2.8mm;text-indent:2em;text-align:justify}
.body p.li{margin-left:2em;text-indent:-2em}
.body h2.h1{margin:8.5mm 0 3.5mm;color:#014099;font:700 14pt/1.55 %(sans)s;text-indent:0;letter-spacing:.02em}
.body h2.h1:first-child{margin-top:.5mm}
.body h3.h2{margin:7mm 0 3mm;color:#1a1a1a;font:700 12pt/1.6 %(sans)s;text-indent:0}
.body p.cm{margin:6.5mm 0 2mm;font:700 10pt/1.6 %(sans)s;color:#1a1a1a;text-indent:0}
.body .block-title{margin:5mm 0 2mm;font:700 10.5pt/1.6 %(sans)s;text-indent:0}
.body figure{margin:1mm 0 3mm}
.body figure img{display:block;max-width:100%%;height:auto;margin:0 auto}
.body table.data{width:100%%;border-collapse:collapse;font:9pt/1.6 %(sans)s;margin:1mm 0 2mm}
.body table.data th,.body table.data td{border:.5pt solid #cfd8e0;padding:3pt 5pt;text-align:left}
.body table.data th{background:#f3f6fa;font-weight:600}
.body .caption{margin:0 0 3mm;color:#8a8f99;font:8.5pt/1.6 %(serif)s;text-indent:0}
.body .empty{margin:2mm 0 4mm;color:#b3bac2;font:9pt/1.7 %(serif)s;text-indent:0}

/* 尾页色带：投资咨询部（浅蓝居中）、作者承诺 / 免责声明（深蓝白字） */
.body .src{margin:14mm 0 2mm;color:#595959;font:9pt/1.75 %(serif)s;text-indent:0}
.body .note{margin:8mm 0 0;font:700 10pt/1.9 %(serif)s;text-indent:2em}
.body .band{height:11mm;line-height:11mm;background:#014099;color:#fff;font:700 10.6pt/11mm %(sans)s;padding-left:5mm;margin:8mm 0 0}
.body .band.light{background:#94b3d6;color:#014099;text-align:center;padding:0;font-size:17pt;letter-spacing:.24em}
.body .signs{display:grid;grid-template-columns:1fr 1fr;column-gap:4mm;margin:4mm 0 0;padding-left:17mm}
.body .signs span{font:700 10pt/10.5mm %(sans)s;color:#014099}
.body .promise,.body .disclaimer{margin:4mm 0 0;font:700 10.6pt/1.9 %(sans)s;color:#244061;text-indent:2em;text-align:justify}

@media print{
  body{background:#fff}
  .toolbar{display:none}
  #sheets{padding:0;transform:none!important;width:auto!important}
  .page{margin:0;box-shadow:none;break-after:page;page-break-after:always}
  .page:last-child{break-after:auto;page-break-after:auto}
}
@page{size:A4;margin:0}
""" % {'sans': SANS, 'serif': SERIF}

HEAD_FIRST = (
    '<div class="brand"><div class="logo">'
    '<svg width="26" height="16" viewBox="0 0 66 40" aria-hidden="true">'
    '<ellipse cx="33" cy="20" rx="29" ry="17" fill="none" stroke="#ffffff" stroke-width="5"></ellipse>'
    '<path d="M14 24c9-13 26-14 38-2-11 5-27 6-38 2z" fill="#ffffff"></path>'
    '</svg>'
    '<div><b>兴业期货有限公司</b><span>CHINA INDUSTRIAL FUTURES LIMITED</span></div>'
    '</div></div>'
)
HEAD_FIRST_BAND = '<div class="titleband"><h1>%s</h1></div>'
HEAD_RUN = (
    '<div class="run"><div class="mini">'
    '<svg width="15" height="10" viewBox="0 0 66 40" aria-hidden="true">'
    '<ellipse cx="33" cy="20" rx="29" ry="17" fill="none" stroke="#014099" stroke-width="5"></ellipse>'
    '<path d="M14 24c9-13 26-14 38-2-11 5-27 6-38 2z" fill="#014099"></path>'
    '</svg><b>兴业期货</b><span>CHINA INDUSTRIAL FUTURES</span></div>'
    '<div class="rh">%s</div></div>'
)

SCRIPT = """
(function(){
  var U=(function(){var d=document.createElement('div');d.style.cssText='position:absolute;visibility:hidden;width:100mm;height:100mm';document.body.appendChild(d);var w=d.getBoundingClientRect().width/100;d.parentNode.removeChild(d);return w||3.7795;})();
  var LEFT=31.8, TOP1=57, TOPN=29.5, BOTTOM=286, CW=146.5;
  var src=document.getElementById('src'), sheets=document.getElementById('sheets');
  var nodes=[].slice.call(src.content.children).map(function(n){return n.cloneNode(true);});
  var pageNo=0;
  function overflow(el){return el.scrollHeight>el.clientHeight+2;}
  function newPage(){
    pageNo++;
    var page=document.createElement('section');page.className='page';
    var head=document.createElement('div');head.innerHTML=(pageNo===1?HEAD_FIRST:HEAD_RUN);
    var body=document.createElement('div');body.className='body';
    var top=(pageNo===1?TOP1:TOPN);
    body.style.left=LEFT+'mm';body.style.width=CW+'mm';body.style.top=top+'mm';body.style.height=(BOTTOM-top)+'mm';
    var foot=document.createElement('div');foot.className='foot';
    foot.innerHTML='<span>'+RUNHEAD+'</span><b class="pn">'+pageNo+'</b>';
    page.appendChild(head);page.appendChild(body);page.appendChild(foot);sheets.appendChild(page);
    return body;
  }
  function fit(){
    var w=document.documentElement.clientWidth, pw=210*U+32, s=Math.min(1,w/pw);
    sheets.style.transform=s<1?'scale('+s+')':'none';
    sheets.style.transformOrigin='top left';
    sheets.style.width=s<1?(pw*s)+'px':'auto';
    sheets.style.marginLeft=s<1?'0':'auto';
  }
  /* 分页靠 scrollHeight 与 clientHeight 的比较，前提是元素真的完成布局。
     预览弹窗尚未显示、iframe 刚挂载、标签页在后台时高度都是 0，此时
     overflow() 恒为 false，会把整篇稿子塞进一页且不再重算。
     因此这里：布局未就绪就退出，交给 ResizeObserver 在可见后重跑；
     再加一个 300ms 的有限重试兜底，最多 30 次（9 秒）后放弃。 */
  var running=false, lastHeight=0, waits=0;
  function start(){
    if(running)return;
    running=true;
    sheets.innerHTML='';pageNo=0;
    var body=newPage();
    if(!body.clientHeight){
      sheets.innerHTML='';pageNo=0;running=false;lastHeight=0;
      if(waits++<30)setTimeout(start,300);
      return;
    }
    waits=0;
    for(var i=0;i<nodes.length;i++){
      var n=nodes[i];
      body.appendChild(n);
      if(overflow(body)){
        body.removeChild(n);
        if(body.children.length)body=newPage();
        body.appendChild(n);
        continue;
      }
      if(n.tagName==='H2'||n.tagName==='H3'){
        var probe=document.createElement('div');probe.style.height=(3*21)+'px';body.appendChild(probe);
        if(overflow(body)){
          body.removeChild(probe);body.removeChild(n);
          if(body.children.length)body=newPage();
          body.appendChild(n);
        }else{body.removeChild(probe);}
      }
    }
    fit();
    var total=document.querySelectorAll('.page').length;
    var badge=document.getElementById('pcount');if(badge)badge.textContent=total;
    lastHeight=body.clientHeight;
    running=false;
  }
  if(window.ResizeObserver){
    var ro=new ResizeObserver(function(){
      if(running)return;
      var page=document.querySelector('.page');
      var h=page?page.clientHeight:0;
      if(h>0&&lastHeight===0)start();
    });
    ro.observe(document.body);
  }
  window.addEventListener('resize',fit);
  start();
})();
"""


def _decorate(html):
    """「▍品种：一句话观点」在合集里整行加粗，作者无需手动设置格式。"""
    bold = re.compile(r'<b>\s*▍([^<>\n]*?)</b>([^<>\n]*)')
    line = re.compile(r'▍[^<>\n]*(?=<br|</p|\n|$)')
    html = bold.sub(lambda m: '<b>▍%s%s</b>' % (m.group(1), m.group(2)), html)
    return line.sub(lambda m: '<span class="cm">%s</span>' % m.group(0), html)


def _paragraphs(html):
    if re.search(r'<p[\s>]', html, re.I):
        return html
    text = re.sub(r'<br\s*/?>\s*<br\s*/?>', '\n\n', html, flags=re.I)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    blocks = [block.strip() for block in re.split(r'\n+', text) if block.strip()]
    return ''.join('<p>%s</p>' % block for block in blocks)


def _cm_class(html):
    """段落级标记：整段只有「▍…」的是品种小标题；以 1. / ① 开头的是编号条目。"""
    html = re.sub(r'<p>(\s*(?:<b>)?\s*▍)', lambda m: '<p class="cm">' + m.group(1), html)
    return re.sub(r'<p>(\s*(?:<b>)?\s*)(\d{1,2}[.、)])', lambda m: '<p class="li">' + m.group(1) + m.group(2), html)


def _chart(block):
    rows = [r for r in (block.get('data') or []) if isinstance(r.get('value'), (int, float)) and math.isfinite(r['value'])]
    if not rows:
        return '<p class="empty">数据引用待保存后生成图表</p>'
    rows = rows[-60:]
    values = [float(r['value']) for r in rows]
    low, high = min(values), max(values)
    if low == high:
        low -= 1
        high += 1
    step = 480 / max(1, len(rows) - 1)
    coords = [(290 if len(rows) == 1 else 50 + i * step, 175 - (v - low) / (high - low) * 135) for i, v in enumerate(values)]
    points = ' '.join('%.1f,%.1f' % point for point in coords)
    marker = '<circle cx="%.1f" cy="%.1f" r="4" fill="#014099"></circle>' % coords[0] if len(rows) == 1 else ''
    return ('<figure><svg viewBox="0 0 580 215" width="100%%" style="max-width:580px" role="img">'
            '<line x1="50" y1="175" x2="530" y2="175" stroke="#cfd8e0"></line>'
            '<line x1="50" y1="40" x2="50" y2="175" stroke="#cfd8e0"></line>'
            '<text x="4" y="45" font-size="10" fill="#9aa7b2">%s</text>'
            '<text x="4" y="178" font-size="10" fill="#9aa7b2">%s</text>'
            '<polyline points="%s" fill="none" stroke="#014099" stroke-width="2.4"></polyline>%s'
            '<text x="50" y="198" font-size="10" fill="#9aa7b2">%s</text>'
            '<text x="470" y="198" font-size="10" fill="#9aa7b2">%s</text></svg></figure>'
            % (escape('%.2f' % high), escape('%.2f' % low), points, marker,
               escape(str(rows[0].get('date', ''))), escape(str(rows[-1].get('date', '')))))


def _table(block):
    rows = (block.get('data') or [])[-12:]
    if not rows:
        return '<p class="empty">数据引用待保存后生成表格</p>'
    head = '<tr><th>日期</th><th>%s</th><th>单位</th></tr>' % escape(block.get('indicator', '数值'))
    body = ''.join('<tr><td>%s</td><td>%s</td><td>%s</td></tr>' % (
        escape(str(r.get('date', ''))), escape(str(r.get('value', ''))), escape(str(r.get('unit', '')))) for r in rows)
    return '<table class="data">%s%s</table>' % (head, body)


def _block(block):
    kind = block.get('type')
    title = '<div class="block-title">%s</div>' % escape(block.get('title', '')) if block.get('title') else ''
    if kind == 'text':
        html = block.get('html') or escape(block.get('text', '')).replace('\n', '<br>')
        return title + _cm_class(_paragraphs(_decorate(html)))
    if kind == 'image':
        return '<figure>%s<img src="/api/library/file/%d" alt="%s"></figure>' % (
            title, int(block.get('asset_id') or 0), escape(block.get('asset_name', '')))
    unit = (block.get('data') or [{}])[0].get('unit', '') if block.get('data') else ''
    caption = '<p class="caption">来源：%s · %s · %s</p>' % (
        escape(block.get('source', '')), escape(block.get('indicator', '')), escape(str(unit)))
    body = _chart(block) if kind == 'chart' else _table(block)
    return title + body + caption


def _has_content(blocks):
    for block in blocks:
        kind = block.get('type')
        if kind == 'text':
            plain = re.sub(r'<[^>]+>', '', str(block.get('html') or block.get('text') or '')).replace('&nbsp;', ' ').strip()
            if plain:
                return True
        elif kind == 'image' and block.get('asset_id'):
            return True
        elif kind in ('chart', 'table') and block.get('data'):
            return True
    return False


def _statement(section):
    """数据来源与免责声明章：合集里只有灰色来源行与「（以上内容仅供参考…）」，不加标题。"""
    out = []
    for block in section.get('blocks', []):
        if block.get('type') != 'text':
            continue
        html = block.get('html') or escape(block.get('text', '')).replace('\n', '<br>')
        plain = re.sub(r'<br\s*/?>|</p\s*>|<p[^>]*>', '\n', html, flags=re.I)
        plain = re.sub(r'<[^>]+>', '', plain).replace('&nbsp;', ' ')
        for line in [x.strip() for x in plain.split('\n') if x.strip()]:
            if line.startswith('数据来源') or line.startswith('来源'):
                out.append('<p class="src">%s</p>' % escape(line))
            else:
                out.append('<p class="note">%s</p>' % escape(line))
    return ''.join(out)


def _sections(doc):
    parts, group = [], None
    for section in doc.get('sections', []):
        current = section.get('group') or ''
        blocks = section.get('blocks', [])
        if section.get('type') == '声明':
            parts.append(_statement(section) if _has_content(blocks) else '')
            continue
        if current and current != group:
            parts.append('<h2 class="h1">%s</h2>' % escape(current))
        group = current
        label = (section.get('label') or '').strip()
        title = (section.get('title') or '').strip()
        # 章节名称允许留空：有编号就只印编号，两者都空则不占一行标题。
        # 一级章节的编号自带顿号，沿用原版式不加空格；二级板块保持「编号 名称」。
        heading = (' ' if current else '').join(x for x in (label, title) if x)
        if heading:
            cls = 'h2' if current else 'h1'
            tag = 'h3' if current else 'h2'
            parts.append('<%s class="%s">%s</%s>' % (tag, cls, escape(heading), tag))
        if _has_content(blocks):
            # 空组件不占版面：只印有内容的块（或带小标题的块），避免空段落撑出多余行
            parts.extend(_block(block) for block in blocks
                         if _has_content([block]) or block.get('title'))
        else:
            parts.append('<p class="empty">本章节暂无内容</p>')
    return ''.join(parts)


def _tail(cfg, people):
    out = []
    band_people = '<div class="band light">投资咨询部</div>'
    names = [p for p in (people or []) if p.get('name')]
    if names:
        out.append('<div class="keep">' + band_people)
        parts = []
        for person in names:
            license_text = person.get('license') or ''
            parts.append('<span>%s</span>' % escape(
                ('%s ｜ 资格证号：%s' % (person['name'], license_text)) if license_text else person['name']))
        out.append('<div class="signs">%s</div></div>' % ''.join(parts))
    promise = str(cfg.get('promise') or '').strip()
    if promise:
        out.append('<div class="keep"><div class="band">作者承诺</div><p class="promise">%s</p></div>' % escape(promise))
    disclaimer = str(cfg.get('footer') or '').strip()
    if disclaimer:
        out.append('<div class="keep"><div class="band">免责声明</div><p class="disclaimer">%s</p></div>' % escape(disclaimer))
    return ''.join(out)


def _dotted(date_text):
    return str(date_text or '').replace('-', '.')


def render(report, people=None, toolbar=True):
    doc = json.loads(report['document']) if report['document'] else None
    cfg = json.loads(report['config_snapshot']) if report['config_snapshot'] else {}
    meta = json.loads(report['metadata']) if report['metadata'] else {}

    if doc:
        body = _sections(doc)
    else:
        lines = [x for x in (report['body'] or '').split('\n')]
        body = ''.join('<p>%s</p>' % escape(line) for line in lines if line.strip())

    kind = str(cfg.get('kind') or report['kind'] or '研究')
    rhythm = '日度策略' if ('日度' in kind or '日报' in kind) else kind
    if not people:
        people = [{'name': meta.get('byline') or report['author_name'],
                   'license': meta.get('byline_license') or ''}]

    title = escape(report['title'])
    head_first = HEAD_FIRST + (HEAD_FIRST_BAND % title)
    head_run = HEAD_RUN % escape(rhythm)
    script = ('<script>var HEAD_FIRST=' + json.dumps(head_first) +
              ',HEAD_RUN=' + json.dumps(head_run) +
              ',RUNHEAD=' + json.dumps(RUNHEAD) + ';' + SCRIPT + '</script>')

    return ('<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + title + '</title><style>' + CSS + '</style></head><body>'
            + ('<div class="toolbar"><span>A4 · 210×297mm · 共 <b id="pcount">–</b> 页</span>'
               '<button onclick="window.print()">打印 / 另存为 PDF</button></div>' if toolbar else '') +
            '<div id="sheets"></div>'
            '<template id="src">' + body + _tail(cfg, people) + '</template>'
            + script + '</body></html>')
