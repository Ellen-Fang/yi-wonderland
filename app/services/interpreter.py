"""Gemini 串接：固定 JSON 格式、逾時、拒絕與回應品質檢查。"""
import json
import os
import re
import asyncio
import logging
import httpx
from pydantic import ValidationError
from app.config import ROOT
from app.errors import ApiError
from app.schemas.reading import Interpretation

PROMPT = (ROOT / 'app/prompts/tarot.txt').read_text(encoding='utf-8')
logger = logging.getLogger('uvicorn.error')


def validate_interpretation(value: dict, reading: dict) -> dict:
    try:
        result = Interpretation.model_validate(value)
        for card, drawn in zip(result.cards, reading['cards'], strict=True):
            if card.cardId != drawn['cardId'] or card.positionId != drawn['position']['id']:
                raise ValueError('牌面或牌位不符')
    except (ValidationError, ValueError, TypeError) as error:
        raise ApiError(502, 'INVALID_MODEL_OUTPUT', '解讀內容尚未完整產生，請稍後再試。') from error
    return result.model_dump()


async def interpret_reading(reading: dict) -> dict:
    key = os.getenv('GEMINI_API_KEY', '').strip()
    model = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite').strip()
    if not key or not model:
        raise ApiError(503, 'AI_NOT_CONFIGURED', '請先在後端設定 GEMINI_API_KEY 與 GEMINI_MODEL。')
    if not re.fullmatch(r'[A-Za-z0-9._-]+', model):
        raise ApiError(503, 'AI_NOT_CONFIGURED', 'GEMINI_MODEL 必須是有效的模型名稱。')
    data = {key: reading[key] for key in ('question', 'options', 'spread', 'cards')}
    try:
        # 自動修復最多一次，總等待時間仍以 45 秒為限，避免雙倍等待。
        async with asyncio.timeout(45):
            async with httpx.AsyncClient(timeout=httpx.Timeout(40, connect=10)) as client:
                for attempt in range(2):
                    try:
                        return await generate_interpretation(client, key, model, data, reading, repair=bool(attempt))
                    except ApiError as error:
                        if attempt or error.code not in ('INVALID_MODEL_OUTPUT', 'AI_INCOMPLETE'):
                            raise
    except (httpx.HTTPError, TimeoutError) as error:
        logger.warning('Gemini transport failure model=%s exception=%s', model, type(error).__name__)
        raise ApiError(502, 'AI_UNAVAILABLE', '解讀服務連線失敗或逾時，請稍後重試。') from error


async def generate_interpretation(client, key, model, data, reading, repair=False):
    instructions = PROMPT
    if repair:
        instructions += '\n上一回合的回覆未通過格式檢查。請重新依原問題與原牌組輸出完整 JSON：三張牌依序保留原 cardId、positionId，各欄位不可空白。務必包含整體判讀、三張逐牌分析、具體建議與反思，不輸出 Markdown 或額外欄位。'
    response = await client.post(
        f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
        headers={'x-goog-api-key': key}, json={
            'systemInstruction': {'parts': [{'text': instructions}]},
            'contents': [{'role': 'user', 'parts': [{'text': json.dumps(data, ensure_ascii=False)}]}],
            'generationConfig': {
                'responseMimeType': 'application/json',
                'thinkingConfig': {'thinkingLevel': 'LOW'},
                'responseJsonSchema': Interpretation.model_json_schema(),
            },
        },
    )
    if not response.is_success:
        # 只記錄 HTTP 狀態、模型與經白名單限制的錯誤代碼，絕不記錄金鑰、問題或完整回應。
        provider_status = 'UNKNOWN'
        try:
            candidate_status = response.json().get('error', {}).get('status', '')
            if isinstance(candidate_status, str) and re.fullmatch(r'[A-Z_]{1,60}', candidate_status):
                provider_status = candidate_status
        except (ValueError, AttributeError, TypeError):
            pass
        logger.warning('Gemini request failed http_status=%s provider_status=%s model=%s',
                       response.status_code, provider_status, model)
        if response.status_code in (401, 403):
            raise ApiError(503, 'AI_AUTH_ERROR', 'Gemini 金鑰無效或沒有模型存取權限，請檢查後端設定。')
        if response.status_code == 429:
            raise ApiError(503, 'AI_QUOTA_EXCEEDED', 'Gemini 額度不足或請求過於頻繁，請稍後再試或確認 API 額度。')
        if response.status_code in (500, 502, 503, 504):
            raise ApiError(502, 'AI_UNAVAILABLE', '解讀服務目前忙碌或暫時故障，請稍後再試。')
        if response.status_code in (400, 404):
            raise ApiError(503, 'AI_CONFIG_ERROR', '解讀服務設定需要調整，請聯絡網站管理者。')
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
