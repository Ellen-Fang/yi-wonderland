import pytest
from fastapi.testclient import TestClient
from app.main import create_app


def result_for(reading):
    return {'summary': '綜合問題與牌陣的測試摘要。' * 12,
            'cards': [{'positionId': card['position']['id'], 'cardId': card['cardId'],
                       'interpretation': '連結牌義、牌位與個人情境的測試解讀。' * 12}
                      for card in reading['cards']],
            'advice': ['先釐清動機', '整理可用資源', '列出下一步'], 'reflection': '你最重視什麼？'}


@pytest.fixture
def client(tmp_path):
    async def interpret(reading):
        return result_for(reading)
    with TestClient(create_app(f'sqlite:///{tmp_path / "test.sqlite"}', interpret)) as client:
        yield client


def create(client, **extra):
    response = client.post('/api/readings', json={'question': '我想轉職，該如何準備？',
                           'spreadId': 'situation-obstacle-advice', **extra})
    assert response.status_code == 201, response.text
    reading = response.json()
    return reading, {'Authorization': f'Bearer {reading["accessToken"]}'}


def draw_three(client, reading, headers):
    for index, position in enumerate([12, 45, 7]):
        response = client.post(f'/api/readings/{reading["id"]}/draw', headers=headers,
                               json={'position': position, 'drawIndex': index})
        assert response.status_code == 200, response.text
    return response.json()
