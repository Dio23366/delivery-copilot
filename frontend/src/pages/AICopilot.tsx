import { aiEntrypoints } from '../api/mockData';

export function AICopilot() {
  const entries = aiEntrypoints ?? [];

  return (
    <div>
      <h1>AI Copilot</h1>
      {entries.length === 0 ? (
        <p className="page-status">暂无 AI 功能入口</p>
      ) : (
        <div className="ai-grid">
          {entries.map((item) => (
            <div key={item.title} className="ai-card">
              <h3>{item?.title ?? '-'}</h3>
              <p>{item?.description ?? '-'}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
