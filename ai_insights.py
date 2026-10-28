"""기존 저장 초안의 검증만 유지한다. 외부 생성 API 기능은 제거했다."""


def ready(settings=None):
    return False


def _removed():
    raise ValueError('제미나이 생성 기능은 제거했습니다. 외부 AI 요청을 보내지 않습니다.')


def generate(*args, **kwargs):
    return _removed()


def request_json(*args, **kwargs):
    return _removed()


def validate_output(value, news_ids: set[str], report_ids: set[str]):
    if not isinstance(value, dict) or not isinstance(value.get('insights'), list):
        raise ValueError('AI 결과 형식이 올바르지 않습니다.')
    result = []
    for item in value['insights'][:3]:
        if not isinstance(item, dict):
            raise ValueError('AI 항목 형식 오류')
        for field in ('title', 'phenomenon', 'impact', 'response', 'counter'):
            if not isinstance(item.get(field), str) or not 1 <= len(item[field]) <= 1600:
                raise ValueError('AI 필수 항목이 누락됐습니다.')
        for field, allowed in (('news_ids', news_ids), ('report_ids', report_ids)):
            refs = item.get(field)
            if not isinstance(refs, list) or not refs or any(not isinstance(x, str) or x not in allowed for x in refs):
                raise ValueError('입력 자료에 없는 출처를 인용한 결과는 표시하지 않습니다.')
        metrics = item.get('check_metrics', [])
        if not isinstance(metrics, list) or len(metrics) > 8 or any(not isinstance(x, str) or len(x) > 150 for x in metrics):
            raise ValueError('확인 지표 형식 오류')
        result.append({k: item[k] for k in ('title', 'phenomenon', 'impact', 'response', 'counter', 'news_ids', 'report_ids')} | {'check_metrics': metrics})
    if not result:
        raise ValueError('근거를 충족하는 인사이트가 없습니다.')
    return result

