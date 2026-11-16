"""Gemini 串接：固定 JSON 格式、逾時、拒絕與回應品質檢查。"""
import json
import os
import re
import httpx
from pydantic import ValidationError
from app.config import ROOT
from app.errors import ApiError
from app.schemas.reading import Interpretation

PROMPT = (ROOT / 'app/prompts/tarot.txt').read_text(encoding='utf-8')


def validate_interpretation(value: dict, reading: dict) -> dict:
    try:
        result = Interpretation.model_validate(value)
        for card, drawn in zip(result.cards, reading['cards'], strict=True):
            if card.cardId != drawn['cardId'] or card.positionId != drawn['position']['id']:
                raise ValueError('牌面或牌位不符')
    except (ValidationError, ValueError, TypeError) as error:
        raise ApiError(502, 'INVALID_MODEL_OUTPUT', '解讀格式不正確或內容過短，請稍後重試。') from error
    return result.model_dump()


async def interpret_reading(reading: dict) -> dict:
    key = os.getenv('GEMINI_API_KEY', '').strip()
    model = os.getenv('GEMINI_MODEL', 'gemini-3.8-flash').strip()
    if not key or not model:
        raise ApiError(503, 'AI_NOT_CONFIGURED', '請先在後端設定 GEMINI_API_KEY 與 GEMINI_MODEL。')
    if not re.fullmatch(r'[A-Za-z0-9._-]+', model):
        raise ApiError(503, 'AI_NOT_CONFIGURED', 'GEMINI_MODEL 必須是有效的模型名稱。')
    data = {key: reading[key] for key in ('question', 'options', 'spread', 'cards')}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(45, connect=10)) as client:
            response = await client.post(
                f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
                headers={'x-goog-api-key': key}, json={
                    'systemInstruction': {'parts': [{'text': PROMPT}]},
                    'contents': [{'role': 'user', 'parts': [{'text': json.dumps(data, ensure_ascii=False)}]}],
                    'generationConfig': {'responseMimeType': 'application/json',
                                         'thinkingConfig': {'thinkingLevel': 'LOW'},
                                         'responseJsonSchema': Interpretation.model_json_schema()}})
    except httpx.HTTPError as error:
        raise ApiError(502, 'AI_UNAVAILABLE', '解讀服務連線失敗或逾時，請稍後重試。') from error
    if not response.is_success:
        if response.status_code in (401, 403):
            raise ApiError(503, 'AI_AUTH_ERROR', 'Gemini 金鑰無效或沒有模型存取權限，請檢查後端設定。')
        if response.status_code == 429:
            raise ApiError(503, 'AI_QUOTA_EXCEEDED', 'Gemini 額度不足或請求過於頻繁，請稍後再試或確認 API 額度。')
        raise ApiError(502, 'AI_UNAVAILABLE', '解讀服務暫時無法使用，請檢查後端模型設定或稍後重試。')
    try:
        body = response.json()
        if body.get('promptFeedback', {}).get('blockReason'):
            raise ApiError(422, 'AI_REFUSED', '模型無法解讀這個問題，請調整問題後建立新的占卜。')
        candidates = body.get('candidates', [])
        if not candidates:
            raise ApiError(502, 'INVALID_MODEL_OUTPUT', '解讀服務未回傳內容。')
        candidate = candidates[0]
        reason = candidate.get('finishReason')
        if reason in ('SAFETY', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'RECITATION', 'SPII', 'IMAGE_SAFETY'):
            raise ApiError(422, 'AI_REFUSED', '模型無法解讀這個問題，請調整問題後建立新的占卜。')
        if reason != 'STOP':
            raise ApiError(502, 'AI_INCOMPLETE', '解讀尚未完整產生，請稍後重試。')
        content = candidate.get('content', {}).get('parts', [])
        result = json.loads(''.join(part['text'] for part in content if 'text' in part and not part.get('thought')))
        return validate_interpretation(result, reading)
    except (ValueError, KeyError, TypeError, AttributeError) as error:
        raise ApiError(502, 'INVALID_MODEL_OUTPUT', '解讀服務回傳無效資料。') from error
