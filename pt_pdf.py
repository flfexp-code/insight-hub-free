"""한글 PT PDF. 화면의 페이지 조각 대신 온전한 자료 단위로 조판한다."""
import base64
import gzip
import html
import io
import json
import threading
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

_lock = threading.RLock()


@lru_cache(maxsize=12)
def export_pdf(serialized, mode='practice'):
    if mode not in ('practice', 'guide'):
        raise ValueError('PDF 구분 오류')
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, Flowable, PageBreak,
    )
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from pt_learning import validate_pt

    value = json.loads(serialized)
    sources = {s['id']: s for s in value['sources']}
    pt = value['pt']
    validate_pt(pt, sources)
    with _lock:
        if 'PTKorean' not in pdfmetrics.getRegisteredFontNames():
            encoded = (Path(__file__).parent / 'assets/fonts/PTKorean.ttf.gz.b64').read_text()
            pdfmetrics.registerFont(TTFont('PTKorean', io.BytesIO(gzip.decompress(base64.b64decode(encoded)))))
        ink = colors.HexColor('#29352c')
        green = colors.HexColor('#526e33')
        line = colors.HexColor('#d6dfcd')
        width = 527.28
        styles = {
            'title': ParagraphStyle('title', fontName='PTKorean', fontSize=17, leading=23,
                                    textColor=ink, spaceAfter=10, wordWrap='CJK', keepWithNext=True),
            'body': ParagraphStyle('body', fontName='PTKorean', fontSize=10.5, leading=14,
                                   textColor=ink, spaceAfter=5, wordWrap='CJK'),
            'h': ParagraphStyle('h', fontName='PTKorean', fontSize=11.5, leading=16,
                                textColor=green, spaceBefore=8, spaceAfter=4,
                                wordWrap='CJK', keepWithNext=True),
            'small': ParagraphStyle('small', fontName='PTKorean', fontSize=9, leading=12,
                                    textColor=colors.HexColor('#617052'), spaceAfter=4, wordWrap='CJK'),
            'cell': ParagraphStyle('cell', fontName='PTKorean', fontSize=10.5, leading=13.5,
                                   textColor=ink, wordWrap='CJK'),
        }

        def p(text, style='body'):
            return Paragraph(html.escape(str(text)).replace('\n', '<br/>'), styles[style])

        def paragraphs(text, style='body'):
            return [p(part, style) for part in str(text).split('\n\n') if part.strip()]

        def unit(items):
            # 한 페이지에 들어가는 자료는 본문·표·주석을 통째로 배치한다.
            # 한 페이지보다 긴 자료만 문단·표의 행 경계에서 이어진다.
            return KeepTogether(items)

        class Bars(Flowable):
            def __init__(self, chart, rows=None, bounds=None):
                super().__init__()
                self.chart = chart
                self.rows = chart['rows'] if rows is None else rows
                vals = [x for row in chart['rows'] for x in row[1:]]
                self.bounds = bounds or (min(0, *vals), max(0, *vals))
                self.width = width
                self.row_height = 20 + len(chart['columns'][1:]) * 22
                self.height = 35 + len(self.rows) * self.row_height

            def split(self, availWidth, availHeight):
                count = int((availHeight - 35) // self.row_height)
                if count < 1:
                    return []
                return [Bars(self.chart, self.rows[:count], self.bounds),
                        Bars(self.chart, self.rows[count:], self.bounds)] if count < len(self.rows) else [self]

            def draw(self):
                c = self.canv
                lo, hi = self.bounds
                span = hi - lo or 1
                left, right = 142, width - 65

                def xx(v):
                    return left + (v - lo) / span * (right - left)

                baseline, y = xx(0), self.height - 18
                palette = ['#526e33', '#9aaf77', '#557b97', '#b57b43', '#83739e', '#aa6669', '#688f83']
                for row in self.rows:
                    c.setFont('PTKorean', 10.5)
                    c.setFillColor(ink)
                    c.drawString(0, y, str(row[0]))
                    y -= 17
                    for i, v in enumerate(row[1:]):
                        c.setFont('PTKorean', 8.3)
                        c.setFillColor(ink)
                        c.drawString(8, y, str(self.chart['columns'][i + 1]))
                        c.setStrokeColor(line)
                        c.line(baseline, y - 3, baseline, y + 13)
                        c.setFillColor(colors.HexColor(palette[i]))
                        c.rect(min(xx(v), baseline), y - 2, max(abs(xx(v) - baseline), .6), 12, fill=1, stroke=0)
                        c.setFillColor(ink)
                        c.setFont('PTKorean', 10)
                        c.drawRightString(width, y, str(v))
                        y -= 22
                    y -= 3
                c.setFont('PTKorean', 8)
                c.setFillColor(ink)
                c.drawString(left, 5, f'공통 축: {lo} ~ {hi}')

        def chart_items(chart):
            items = [p(chart['title'], 'h'),
                     p('단위: ' + chart['unit'] + ' · ' + chart['period'], 'small')]
            if chart['kind'] == 'bar':
                items.append(Bars(chart))
            # 짧은 항목 열에 절반 너비를 쓰지 않아 본문 열의 불필요한 줄바꿈을 줄인다.
            cols = len(chart['columns'])
            weights = [max(3, max(len(str(row[i])) for row in [chart['columns']] + chart['rows']) ** .55)
                       for i in range(cols)]
            col_widths = [width * w / sum(weights) for w in weights]
            rows = [[p(cell, 'cell') for cell in row] for row in [chart['columns']] + chart['rows']]
            table = Table(rows, colWidths=col_widths, repeatRows=1, hAlign='LEFT')
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#eaf1dd')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'), ('GRID', (0, 0), (-1, -1), .4, line),
                ('TOPPADDING', (0, 0), (-1, -1), 2.5), ('BOTTOMPADDING', (0, 0), (-1, -1), 2.5),
                ('LEFTPADDING', (0, 0), (-1, -1), 7), ('RIGHTPADDING', (0, 0), (-1, -1), 7),
            ]))
            return items + [table, Spacer(1, 4), p(chart['note'], 'small')]

        def source_items(source):
            url = html.escape(source['url'], quote=True)
            items = [Spacer(1, 7), p('출처 ' + source['id'] + ' · ' + source['publisher'] + ' · ' + source['published'], 'small'),
                    p(source['title'], 'small'),
                    Paragraph('<link href="' + url + '" color="#526e33">' + url + '</link>', styles['small']),
                    p('확인: ' + source['supports'], 'small'), p('한계: ' + source['limits'], 'small')]
            first_iea = next((s['id'] for s in value['sources'] if s['publisher'] == 'IEA'), None)
            if source['id'] == first_iea and value.get('reuse_notice'):
                items += paragraphs(value['reuse_notice'], 'small')
            return items

        label = '문제·자료집' if mode == 'practice' else '해설·예시 발표'
        story = [p('PT ' + label, 'small'), p(value['topic'], 'title')]
        if mode == 'practice':
            blocks = [(story + [p(f"준비 {pt['preparation_minutes']}분 · 발표 {pt['presentation_minutes']}분", 'small'),
                               p(pt['task']), p('역할·조건', 'h'), *paragraphs(pt['role']),
                               *paragraphs(pt['conditions']), p('발표에 포함할 내용', 'h'),
                               *[p('- ' + item) for item in pt['deliverables']]], [])]
            for material in pt['materials']:
                items = [p('자료 ' + material['id'] + ' | ' + material['heading'], 'h'),
                         p(material['provenance'], 'small'), *paragraphs(material['body'])]
                if material.get('chart'):
                    items += chart_items(material['chart'])
                items.append(p('근거: ' + ' · '.join(sid + ' ' + sources[sid]['publisher']
                                                   for sid in material['source_ids']), 'small'))
                blocks.append((items, material['source_ids']))
            questions = value.get('practice_questions') or value.get('questions', [])
            if questions:
                question_items = [p('생각할 질문', 'h')]
                entries = [p(str(i) + '. ' + q['question'] + ' (참조: ' + q['hint'] + ')')
                           for i, q in enumerate(questions, 1)]
                middle = (len(entries) + 1) // 2
                question_table = Table([[entries[:middle], entries[middle:]]],
                                       colWidths=[width / 2, width / 2], hAlign='LEFT')
                question_table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('LEFTPADDING', (0, 0), (-1, -1), 0),
                    ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                    ('TOPPADDING', (0, 0), (-1, -1), 0),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
                ]))
                # 유난히 긴 질문 목록은 큰 단일 표 행으로 만들지 않는다.
                question_items += [question_table] if question_table.wrap(width, 10000)[1] < 600 else entries
                blocks.append((question_items, []))

            # 자료 묶음의 실제 높이를 재어 조판한다. 다음 자료가 들어가지 않는 여백에는
            # 이미 읽은 자료의 출처를 배치한다. 자료를 쪼개거나 본문을 줄이지 않는다.
            from reportlab.pdfgen.canvas import Canvas
            measure_canvas = Canvas(io.BytesIO())
            page_height = 841.89 - 26 - 30 - 12 - 6

            def height(items):
                group = unit(items)
                group.wrapOn(measure_canvas, width, page_height)
                return group._H

            story, pending, printed = [], [], set()
            current, used_height = [], 0

            def finish_page():
                nonlocal current, used_height
                for sid in pending:
                    if sid not in printed:
                        items = source_items(sources[sid])
                        h = height(items)
                        if used_height + h <= page_height:
                            current.append(unit(items))
                            used_height += h
                            printed.add(sid)
                story.extend(current)
                current, used_height = [], 0

            for items, refs in blocks:
                h = height(items)
                if current and used_height + h > page_height:
                    finish_page()
                    story.append(PageBreak())
                current.append(unit(items))
                used_height += h
                for sid in refs:
                    if sid not in pending:
                        pending.append(sid)
            finish_page()
            remaining = [s for s in value['sources'] if s['id'] not in printed]
            if remaining:
                story.append(p('출처와 확인 범위 · 계속', 'h'))
                for source in remaining:
                    story.append(unit(source_items(source)))
            if value.get('reuse_notice') and not any(s['publisher'] == 'IEA' for s in value['sources']):
                story.append(unit(paragraphs(value['reuse_notice'], 'small')))
        else:
            guide = pt['answer_guide']
            sections = [('자료를 연결하는 방법', paragraphs(guide['reasoning'])),
                        ('다른 관점·범위 차이', [p('- ' + s) for s in guide['contrasts']]),
                        ('다른 결론이 성립하는 조건', [p('- ' + s) for s in guide['approaches']]),
                        ('예시 발표 스크립트', [p(guide['script_notes'], 'small'), *paragraphs(guide['sample_script'])]),
                        ('피드백에서 확인할 내용', [p('- ' + s) for s in guide['rubric']]),
                        ('꼬리질문 예시', [p('- ' + s) for s in guide['followups']])]
            for heading, items in sections:
                story += [p(heading, 'h'), *items]
        stream = io.BytesIO()
        doc = SimpleDocTemplate(stream, pagesize=(595.28, 841.89), leftMargin=28, rightMargin=28,
                                topMargin=26, bottomMargin=30, title=value['topic'] + ' - ' + label,
                                author='Insight Hub')
        stamp = datetime.fromisoformat(value['updated_at'].replace('Z', '+00:00'))
        date = stamp.astimezone(timezone(timedelta(hours=9))).strftime('%Y-%m-%d')

        def footer(c, doc):
            c.setFillColor(green)
            c.rect(0, 833, 595.28, 9, fill=1, stroke=0)
            c.setFillColor(ink)
            c.setFont('PTKorean', 8)
            c.drawString(36, 19, 'Insight Hub · ' + date)
            c.drawRightString(559, 19, str(doc.page))

        doc.build(story, onFirstPage=footer, onLaterPages=footer)
        return stream.getvalue()
