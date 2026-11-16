"""手動連線檢查；會呼叫一次真實解讀 API，產生 API 費用。"""
import asyncio
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import httpx
from app.config import ROOT


async def main():
    key = os.getenv('GEMINI_API_KEY', '').strip()
    model = os.getenv('GEMINI_MODEL', 'gemini-3.8-flash').strip()
    print(f'Key configured: {bool(key)}; Model: {model}', flush=True)
    if not key or not model:
        return
    async with httpx.AsyncClient(timeout=httpx.Timeout(200, connect=10)) as client:
        response = await client.get(f'https://generativelanguage.googleapis.com/v1beta/models/{model}',
                                    headers={'x-goog-api-key': key})
        print(f'Model access HTTP: {response.status_code}', flush=True)
        if not response.is_success:
            try:
                error = response.json().get('error', {})
                print('Provider error code:', error.get('code'), '; status:', error.get('status'), flush=True)
            except ValueError:
                print('Provider returned a non-JSON error', flush=True)
            return
        base = f'http://127.0.0.1:{os.getenv("PORT", "3000")}'
        response = await client.post(base + '/api/readings', json={
            'question': '我目前工作穩定，但希望轉做軟體工程師，擔心能力不足，未來三個月該如何準備？',
            'spreadId': 'situation-obstacle-advice'})
        response.raise_for_status()
        reading = response.json()
        path = base + '/api/readings/' + reading['id']
        headers = {'Authorization': 'Bearer ' + reading['accessToken']}
        for index, position in enumerate([12, 45, 7]):
            response = await client.post(path + '/draw', headers=headers,
                                         json={'position': position, 'drawIndex': index})
            response.raise_for_status()
        print('Three sequential draws: OK; requesting real interpretation...', flush=True)
        started = time.monotonic()
        response = await client.post(path + '/interpretation', headers=headers)
        print(f'Interpretation HTTP: {response.status_code}; elapsed: {time.monotonic()-started:.1f}s', flush=True)
        if not response.is_success:
            print('Backend error:', response.json().get('error', {}).get('code'), flush=True)
            return
        result = response.json()['interpretation']
        print('Summary characters:', len(result['summary']), flush=True)
        print('Card interpretation characters:', [len(card['interpretation']) for card in result['cards']], flush=True)
        print('Advice count:', len(result['advice']), flush=True)
        print('Summary:', result['summary'], flush=True)
        response = await client.get(path, headers=headers)
        print('Saved result:', response.status_code == 200 and response.json()['status'] == 'completed', flush=True)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as error:
        # 不列印 HTTP request headers 或任何完整例外物件，以免意外洩漏憑證。
        print('Check failed:', type(error).__name__, flush=True)
        sys.exit(1)
