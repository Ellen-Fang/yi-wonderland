"""有效短回覆不再失敗；壞格式自動重試，牌組與問題不改變。"""
import asyncio
import json
from unittest.mock import patch
import httpx
import pytest
from app.errors import ApiError
from app.services.interpreter import interpret_reading, validate_interpretation
from app.tests.conftest import create, draw_three


def short_result(reading):
    return {
        'summary': '這組牌提示你整理等待結果時的心情，錄取仍以正式公告為準。',
        'cards': [{'positionId': card['position']['id'], 'cardId': card['cardId'],
                   'interpretation': '這張牌提供一個觀察當前處境的角度，並非確定的預言。'}
                  for card in reading['cards']],
        'advice': ['先確認公告時間與後續準備事項。'],
        'reflection': '無論結果如何，你下一步最想做好什麼？',
    }


def completed(value):
    return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(value)}]}}]}


def test_short_valid_answer_is_returned_and_saved(client):
    reading, headers = create(client, question='這禮拜台大工乙組放榜的結果，我會正取嗎？', spreadId='past-present-future')
    drawn = draw_three(client, reading, headers)
    async def short_interpreter(reading):
        return short_result(reading)
    client.app.state.interpreter = short_interpreter
    response = client.post(f'/api/readings/{reading["id"]}/interpretation', headers=headers)
    assert response.status_code == 200
    assert response.json()['interpretation'] == short_result(drawn)
    assert response.json()['status'] == 'completed'
    assert client.get(f'/api/readings/{reading["id"]}', headers=headers).json()['interpretation'] == short_result(drawn)
    invalid = short_result(drawn)
    invalid['cards'][0]['interpretation'] = ' \n '
    with pytest.raises(ApiError):
        validate_interpretation(invalid, drawn)


def test_malformed_answer_retries_once_with_same_question_and_cards(client, monkeypatch):
    reading, headers = create(client)
    drawn = draw_three(client, reading, headers)
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setenv('GEMINI_MODEL', 'test-model')
    captured = []
    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            captured.append(kwargs['json'])
            if len(captured) == 1:
                return httpx.Response(200, json=completed({'summary': '缺少牌面資料'}))
            return httpx.Response(200, json=completed(short_result(drawn)))
    with patch('app.services.interpreter.httpx.AsyncClient', FakeClient):
        assert asyncio.run(interpret_reading(drawn)) == short_result(drawn)
    assert len(captured) == 2
    assert captured[0]['contents'] == captured[1]['contents']
    assert json.loads(captured[1]['contents'][0]['parts'][0]['text'])['cards'] == drawn['cards']
    assert '上一回合' in captured[1]['systemInstruction']['parts'][0]['text']


@pytest.mark.parametrize('http_status,expected_calls,error_code', [(200, 2, 'INVALID_MODEL_OUTPUT'), (429, 1, 'AI_QUOTA_EXCEEDED'), (403, 1, 'AI_AUTH_ERROR'), (503, 1, 'AI_UNAVAILABLE'), (400, 1, 'AI_CONFIG_ERROR')])
def test_retry_is_bounded_and_quota_or_auth_is_not_retried(client, monkeypatch, caplog, http_status, expected_calls, error_code):
    reading, headers = create(client)
    drawn = draw_three(client, reading, headers)
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setenv('GEMINI_MODEL', 'test-model')
    calls = []
    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            calls.append(1)
            payload = completed({}) if http_status == 200 else {'error': {
                'status': 'UNAVAILABLE', 'message': f'test-key {drawn["question"]}'}}
            return httpx.Response(http_status, json=payload)
    with patch('app.services.interpreter.httpx.AsyncClient', FakeClient):
        with pytest.raises(ApiError) as exc:
            asyncio.run(interpret_reading(drawn))
    assert exc.value.code == error_code
    assert len(calls) == expected_calls
    assert 'test-key' not in caplog.text
    assert drawn['question'] not in caplog.text
    if http_status != 200:
        assert f'http_status={http_status}' in caplog.text
