from html.parser import HTMLParser
from html import escape
import re

TAGS={'p','div','br','strong','b','em','i','u','s','ul','ol','li','blockquote','h2','h3','table','thead','tbody','tr','td','th','span'}
class Sanitizer(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.out=[];self.words=[];self.skip=0
    def handle_starttag(self,tag,attrs):
        if tag in ['script','style','iframe','object','svg']:self.skip+=1;return
        if self.skip or tag not in TAGS:return
        style=''
        for k,v in attrs:
            if k=='style':
                safe=[]
                for prop in (v or '').split(';'):
                    key,sep,val=prop.partition(':');key=key.strip().lower();val=val.strip().lower()
                    if key=='text-align' and val in ['left','right','center','justify']:safe.append(key+':'+val)
                    if key=='font-size' and re.fullmatch(r'(1[2-9]|2[0-9]|3[0-6])px',val):safe.append(key+':'+val)
                    if key=='color' and re.fullmatch(r'#[a-f0-9]{6}',val):safe.append(key+':'+val)
                if safe:style=' style="'+escape(';'.join(safe),quote=True)+'"'
        self.out.append('<'+tag+style+'>')
        if tag=='br':self.words.append('\n')
    def handle_endtag(self,tag):
        if tag in ['script','style','iframe','object','svg']:
            self.skip=max(0,self.skip-1);return
        if not self.skip and tag in TAGS and tag!='br':
            self.out.append('</'+tag+'>')
            if tag in ['p','div','li','tr','h2','h3']:self.words.append('\n')
    def handle_data(self,data):
        if not self.skip:self.out.append(escape(data));self.words.append(data)
def clean(value):
    parser=Sanitizer();parser.feed(value);parser.close();return ''.join(parser.out),''.join(parser.words)
