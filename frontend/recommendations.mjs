// Recommendations only select a viewpoint; they never affect the shuffled deck.
export function recommendSpreads(question) {
  const text = question.normalize('NFKC').toLowerCase();
  const rules = [
    { id: 'choice-comparison', pattern: /還是|或是|二選一|兩個選擇|兩份|選[擇项項].*[ab]|要不要|是否該|either|versus/, reason: '站在岔路前，看看兩條路各自的風景。' },
    { id: 'relationship-communication', pattern: /感情|關係|伴侶|交往|曖昧|分手|復合|吵架|溝通|男友|女友|朋友|家人|同事|relationship/, reason: '靠近彼此之前，也聽聽自己心裡的聲音。' },
    { id: 'career-preparation', pattern: /求職|面試|履歷|錄取|轉職|找工作|應徵|職涯|工作|offer|interview/, reason: '帶上你的光，也為下一次出發整理行囊。' },
    { id: 'self-check-in', pattern: /迷惘|迷茫|焦慮|難過|疲憊|壓力|情緒|自己|方向|低落|不安|累|自我/, reason: '停一停，陪此刻的自己坐一會兒。' },
    { id: 'past-present-future', pattern: /過去|未來|接下來|走向|發展/, reason: '回望來時的路，看看眼前與遠方的風景。' },
  ];
  const matches = rules.filter(rule => rule.pattern.test(text)).slice(0, 2);
  return matches.length ? matches.map(({ id, reason }) => ({ id, reason })) : [{
    id: 'situation-obstacle-advice', reason: '看看腳下的路，也找找下一步的小小方向。',
  }];
}
