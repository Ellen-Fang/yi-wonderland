import assert from 'node:assert/strict';
import { recommendSpreads } from '../frontend/recommendations.mjs';

for (const [question, expected] of [
  ['我們最近常吵架，如何改善？', 'relationship-communication'],
  ['我該如何準備面試？', 'career-preparation'],
  ['最近很迷惘，該從哪裡開始？', 'self-check-in'],
  ['留在原公司還是接受新工作？', 'choice-comparison'],
  ['接下來可能如何發展？', 'past-present-future'],
  ['這件事情怎麼辦？', 'situation-obstacle-advice'],
]) assert.equal(recommendSpreads(question)[0].id, expected);
assert.deepEqual(recommendSpreads('留任還是轉職？').map(item => item.id), ['choice-comparison', 'career-preparation']);
assert.equal(recommendSpreads('與伴侶吵架，工作壓力讓自己很累').length, 2);
console.log('Recommendation scenarios passed.');
