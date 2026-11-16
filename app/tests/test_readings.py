import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
from unittest.mock import patch
import httpx
import pytest
from fastapi.testclient import TestClient
from app.errors import ApiError
from app.main import create_app
from app.services.interpreter import interpret_reading, validate_interpretation
from app.services.tarot import shuffle_deck
from app.tests.conftest import create, draw_three, result_for


def test_shuffle():
    decks = [shuffle_deck() for _ in range(20)]
    assert all(len(deck) == len({card['cardId'] for card in deck}) == 78 for deck in decks)
    assert len({json.dumps(deck) for deck in decks}) > 1
    assert {card['orientation'] for deck in decks for card in deck} == {'upright', 'reversed'}


def test_health_catalog_docs_and_images(client):
    home = client.get('/')
    assert home.status_code == 200 and '翊想樂園' in home.text
    assert client.get('/app.js').status_code == 200
    assert client.get('/assets/sunlit-park.svg').status_code == 200
    assert client.get('/api/health').json() == {'status': 'ok'}
    assert len(client.get('/api/spreads').json()['spreads']) == 4
    assert client.get('/docs').status_code == 200
    schema = client.get('/openapi.json').json()
    assert '/api/readings/{reading_id}/draw' in schema['paths']
    image = client.get('/cards/rider-waite-smith/major-00.jpg')
    assert image.status_code == 200 and image.content[:2] == b'\xff\xd8'
    assert client.get('/cards/missing.jpg').status_code == 404


def test_question_and_options(client):
    create(client, question='問' * 100)
    create(client, question='😀' * 100)
    for question in ['問' * 101, '😀' * 101]:
        response = client.post('/api/readings', json={'question': question, 'spreadId': 'past-present-future'})
        assert response.status_code == 400
        assert response.json()['error']['code'] == 'QUESTION_TOO_LONG'
    for extra in [{'question': ''}, {'question': 123}, {'spreadId': 'unknown'}, {'spreadId': 'choice-comparison'}, {'unexpected': True}]:
        assert client.post('/api/readings', json={'question': '問題', 'spreadId': 'past-present-future', **extra}).status_code == 400
    reading, _ = create(client, spreadId='choice-comparison', options={'a': '留任', 'b': '轉職'})
    assert reading['options'] == {'a': '留任', 'b': '轉職'}


def test_content_limits(client):
    assert client.post('/api/readings', content='{}').status_code == 415
    assert client.post('/api/readings', content='{', headers={'Content-Type': 'application/json'}).status_code == 400
    assert client.post('/api/readings', content=' ' * 17000, headers={'Content-Type': 'application/json'}).status_code == 413


def test_manual_shuffle_preserves_question_and_locks_after_draw(client):
    reading, headers = create(client)
    path = f'/api/readings/{reading["id"]}'
    assert client.post(path + '/shuffle').status_code == 404
    # 不以一次牌序比較作為隨機性測試，直接檢查保存在 DB 的完整牌組與狀態。
    from app.crud import reading as crud
    with client.app.state.session_factory() as db:
        before = crud.get(db, reading['id'], reading['accessToken'])['deck']
    response = client.post(path + '/shuffle', headers=headers)
    assert response.status_code == 200
    assert response.json()['question'] == reading['question']
    assert response.json()['drawnCount'] == 0 and 'deck' not in response.json()
    with client.app.state.session_factory() as db:
        after = crud.get(db, reading['id'], reading['accessToken'])['deck']
    assert len(after) == len({card['cardId'] for card in after}) == 78
    assert {card['cardId'] for card in before} == {card['cardId'] for card in after}
    assert client.post(path + '/draw', headers=headers, json={'position': 12, 'drawIndex': 0}).status_code == 200
    locked = client.post(path + '/shuffle', headers=headers)
    assert locked.status_code == 409 and locked.json()['error']['code'] == 'SHUFFLE_LOCKED'
    assert client.get(path, headers=headers).json()['cards'][0]['deckPosition'] == 12


def test_sequential_draw_auth_and_replay(client):
    reading, headers = create(client)
    path = f'/api/readings/{reading["id"]}'
    assert 'deck' not in reading and reading['drawnCount'] == 0
    assert client.get(path).status_code == 404
    assert client.get(path, headers={'Authorization': 'Bearer incorrect'}).status_code == 404
    assert client.post(path + '/interpretation', headers=headers).status_code == 409
    def draw(position, index):
        return client.post(path + '/draw', headers=headers, json={'position': position, 'drawIndex': index})
    assert draw(12, 1).status_code == 409
    assert draw(78, 0).status_code == 400
    assert draw(True, 0).status_code == 400
    first = draw(12, 0).json()
    assert len(first['cards']) == 1
    assert draw(12, 0).json() == first
    assert draw(13, 0).status_code == 409
    assert draw(12, 1).status_code == 409
    draw(45, 1)
    last = draw(7, 2).json()
    assert last['status'] == 'drawn' and 'deck' not in last
    assert len({card['cardId'] for card in last['cards']}) == 3
    assert [card['position']['label'] for card in last['cards']] == ['現況', '阻礙', '建議']


def test_concurrent_draw_and_cached_interpretation(tmp_path):
    calls = 0
    async def interpret(reading):
        nonlocal calls
        calls += 1
        await asyncio.sleep(.1)
        return result_for(reading)
    with TestClient(create_app(f'sqlite:///{tmp_path / "parallel.sqlite"}', interpret)) as client:
        reading, headers = create(client)
        path = f'/api/readings/{reading["id"]}'
        def draw(position):
            return client.post(path + '/draw', headers=headers, json={'position': position, 'drawIndex': 0})
        with ThreadPoolExecutor(2) as pool:
            responses = list(pool.map(draw, [12, 13]))
        assert sorted(response.status_code for response in responses) == [200, 409]
        for index, position in [(1, 45), (2, 7)]:
            assert client.post(path + '/draw', headers=headers, json={'position': position, 'drawIndex': index}).status_code == 200
        def request(_):
            return client.post(path + '/interpretation', headers=headers)
        with ThreadPoolExecutor(2) as pool:
            responses = list(pool.map(request, [0, 1]))
        assert all(response.status_code == 200 for response in responses)
        assert calls == 1
        assert request(0).json()['status'] == 'completed' and calls == 1


def test_invalid_output_not_cached(tmp_path):
    calls = 0
    async def interpret(reading):
        nonlocal calls
        calls += 1
        return {**result_for(reading), 'summary': '   '} if calls == 1 else result_for(reading)
    with TestClient(create_app(f'sqlite:///{tmp_path / "retry.sqlite"}', interpret)) as client:
        reading, headers = create(client)
        drawn = draw_three(client, reading, headers)
        invalid = result_for(drawn)
        invalid['cards'][0]['cardId'] = 'made-up'
        with pytest.raises(ApiError):
            validate_interpretation(invalid, drawn)
        path = f'/api/readings/{reading["id"]}/interpretation'
        assert client.post(path, headers=headers).status_code == 502
        assert client.post(path, headers=headers).json()['status'] == 'completed'


def test_restart_and_original_database_compatibility(tmp_path):
    db_path = tmp_path / 'persistent.sqlite'
    url = f'sqlite:///{db_path}'
    with TestClient(create_app(url)) as client:
        reading, headers = create(client)
        drawn = draw_three(client, reading, headers)
    # 原 Node 版使用的 SQL schema 和 JSON payload 維持可讀。
    with sqlite3.connect(db_path) as db:
        payload = json.loads(db.execute('SELECT payload FROM readings WHERE id=?', (reading['id'],)).fetchone()[0])
        assert len(payload['deck']) == 78
    with TestClient(create_app(url)) as client:
        saved = client.get(f'/api/readings/{reading["id"]}', headers=headers).json()
        assert saved['cards'] == drawn['cards'] and 'deck' not in saved


def test_provider_contract_and_errors(client, monkeypatch):
    reading, headers = create(client)
    drawn = draw_three(client, reading, headers)
    monkeypatch.setenv('GEMINI_API_KEY', 'test-key')
    monkeypatch.setenv('GEMINI_MODEL', 'test-model')
    captured = {}
    payload = {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(result_for(drawn))}]}}]}
    status = 200
    class FakeClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            assert url == 'https://generativelanguage.googleapis.com/v1beta/models/test-model:generateContent'
            assert kwargs['headers'] == {'x-goog-api-key': 'test-key'}
            captured.update(kwargs['json'])
            return httpx.Response(status, json=payload)
    with patch('app.services.interpreter.httpx.AsyncClient', FakeClient):
        assert asyncio.run(interpret_reading(drawn))['summary']
        assert captured['generationConfig']['responseMimeType'] == 'application/json'
        assert captured['generationConfig']['thinkingConfig']['thinkingLevel'] == 'LOW'
        assert captured['generationConfig']['responseJsonSchema']['additionalProperties'] is False
        assert json.loads(captured['contents'][0]['parts'][0]['text'])['question'] == drawn['question']
        assert '專業、細心且客觀' in captured['systemInstruction']['parts'][0]['text']
        for bad, code in [({'candidates': [{'finishReason': 'MAX_TOKENS'}]}, 'AI_INCOMPLETE'),
                          ({'promptFeedback': {'blockReason': 'SAFETY'}}, 'AI_REFUSED'),
                          ({'candidates': [{'finishReason': 'SAFETY'}]}, 'AI_REFUSED'),
                          ({'candidates': []}, 'INVALID_MODEL_OUTPUT'),
                          ({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 'bad JSON'}]}}]}, 'INVALID_MODEL_OUTPUT')]:
            payload = bad
            with pytest.raises(ApiError) as exc:
                asyncio.run(interpret_reading(drawn))
            assert exc.value.code == code
        for http_status, code in [(403, 'AI_AUTH_ERROR'), (429, 'AI_QUOTA_EXCEEDED'), (500, 'AI_UNAVAILABLE'), (503, 'AI_UNAVAILABLE'), (400, 'AI_CONFIG_ERROR'), (404, 'AI_CONFIG_ERROR')]:
            status = http_status
            with pytest.raises(ApiError) as exc:
                asyncio.run(interpret_reading(drawn))
            assert exc.value.code == code
    monkeypatch.setenv('GEMINI_API_KEY', '')
    with pytest.raises(ApiError) as exc:
        asyncio.run(interpret_reading(drawn))
    assert exc.value.code == 'AI_NOT_CONFIGURED'

