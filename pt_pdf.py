"""현재 PT 자료에서 한글 폰트를 포함한 PDF를 생성한다. 네트워크를 사용하지 않는다."""
import base64
import gzip
import html
import io
import json
import threading
from functools import lru_cache
from pathlib import Path

from pt_pages import practice_pages, guide_pages

_lock=threading.RLock()


@lru_cache(maxsize=12)
def export_pdf(serialized, mode='practice'):
    if mode not in ('practice','guide'):
        raise ValueError('PDF 구분 오류')
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Flowable
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from pt_learning import validate_pt

    value=json.loads(serialized)
    validate_pt(value['pt'],{s['id']:s for s in value['sources']})
    with _lock:
        if 'PTKorean' not in pdfmetrics.getRegisteredFontNames():
            encoded=(Path(__file__).parent/'assets/fonts/PTKorean.ttf.gz.b64').read_text()
            pdfmetrics.registerFont(TTFont('PTKorean',io.BytesIO(gzip.decompress(base64.b64decode(encoded)))))
        ink=colors.HexColor('#29352c');green=colors.HexColor('#526e33');line=colors.HexColor('#d6dfcd')
        styles={
          'title':ParagraphStyle('title',fontName='PTKorean',fontSize=19,leading=27,textColor=ink,spaceAfter=12,wordWrap='CJK'),
          'body':ParagraphStyle('body',fontName='PTKorean',fontSize=10.5,leading=16.5,textColor=ink,spaceAfter=9,wordWrap='CJK'),
          'h':ParagraphStyle('h',fontName='PTKorean',fontSize=12,leading=18,textColor=green,spaceBefore=9,spaceAfter=6,wordWrap='CJK'),
          'small':ParagraphStyle('small',fontName='PTKorean',fontSize=8.4,leading=12.5,textColor=colors.HexColor('#617052'),spaceAfter=6,wordWrap='CJK')}
        def p(text,style='body'):
            return Paragraph(html.escape(str(text)).replace('\n','<br/>'),styles[style])

        class Bars(Flowable):
            def __init__(self,chart):
                super().__init__();self.chart=chart;self.width=499
                self.height=35+len(chart['rows'])*(20+len(chart['columns'][1:])*22)

            def draw(self):
                c=self.canv;chart=self.chart
                vals=[x for r in chart['rows'] for x in r[1:]];lo=min(0,*vals);hi=max(0,*vals);span=hi-lo or 1
                left,right=132,434
                def xx(v):return left+(v-lo)/span*(right-left)
                baseline=xx(0);y=self.height-18
                palette=['#526e33','#9aaf77','#557b97','#b57b43','#83739e','#aa6669','#688f83']
                for row in chart['rows']:
                    c.setFont('PTKorean',10.5);c.setFillColor(ink);c.drawString(0,y,str(row[0]));y-=17
                    for i,v in enumerate(row[1:]):
                        c.setFont('PTKorean',8.3);c.setFillColor(ink);c.drawString(8,y,str(chart['columns'][i+1]))
                        c.setStrokeColor(line);c.line(baseline,y-3,baseline,y+13)
                        c.setFillColor(colors.HexColor(palette[i]));c.rect(min(xx(v),baseline),y-2,max(abs(xx(v)-baseline),.6),12,fill=1,stroke=0)
                        c.setFillColor(ink);c.setFont('PTKorean',10);c.drawRightString(499,y,str(v));y-=22
                    y-=3
                c.setFont('PTKorean',8);c.setFillColor(ink);c.drawString(left,5,f'공통 축: {lo} ~ {hi}')

        def chart_items(chart):
            items=[p(chart['title'],'h'),p('단위: '+chart['unit']+' · '+chart['period'],'small')]
            if chart['kind']=='bar':items.append(Bars(chart))
            rows=[[p(c) for c in chart['columns']]]+[[p(c) for c in row] for row in chart['rows']]
            t=Table(rows,colWidths=[499/len(chart['columns'])]*len(chart['columns']),repeatRows=1,hAlign='LEFT')
            t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eaf1dd')),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.4,line),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),3),('LEFTPADDING',(0,0),(-1,-1),8),('RIGHTPADDING',(0,0),(-1,-1),8)]))
            return items+[t,Spacer(1,9),p(chart['note'],'small')]

        pages=practice_pages(value) if mode=='practice' else guide_pages(value)
        story=[]
        for i,page in enumerate(pages):
            if i:story.append(PageBreak())
            story += [p(value['topic'],'small'),p(page['meta'],'small'),p(page['heading'],'title')]
            if page.get('body'):story.append(p(page['body']))
            for block in page.get('blocks',[]):story += [p(block['heading'],'h'),p(block['body'])]
            if page.get('chart'):story += chart_items(page['chart'])
            if page.get('source'):story.append(p(page['source'],'small'))
        if mode=='practice':
            story += [PageBreak(),p('출처와 확인 범위','title')]
            for s in value['sources']:
                story += [p(s['id']+' · '+s['publisher']+' · '+s['published'],'h'),p(s['title']),
                          Paragraph('<link href="'+html.escape(s['url'],quote=True)+'" color="#526e33">원문 열기</link>',styles['body']),
                          p('확인: '+s['supports'],'small'),p('한계: '+s['limits'],'small')]
        stream=io.BytesIO()
        doc=SimpleDocTemplate(stream,pagesize=(595.28,841.89),leftMargin=48,rightMargin=48,topMargin=45,bottomMargin=45,title=value['topic']+(' - 문제·자료집' if mode=='practice' else ' - 해설·예시 발표'),author='Insight Hub')
        def footer(c,doc):
            c.setFillColor(green);c.rect(0,827,595.28,15,fill=1,stroke=0);c.setFillColor(ink);c.setFont('PTKorean',8)
            c.drawString(48,24,'Insight Hub · '+value['updated_at'][:10]);c.drawRightString(547,24,str(doc.page))
        doc.build(story,onFirstPage=footer,onLaterPages=footer)
        return stream.getvalue()
