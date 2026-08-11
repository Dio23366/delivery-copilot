import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import { Customers } from './pages/Customers';
import { Projects } from './pages/Projects';
import { Requirements } from './pages/Requirements';
import { Issues } from './pages/Issues';
import { AICopilot } from './pages/AICopilot';
import { AIEvaluation } from './pages/AIEvaluation';
import { AgentRuns } from './pages/AgentRuns';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/customers" element={<Customers />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/requirements" element={<Requirements />} />
        <Route path="/issues" element={<Issues />} />
        <Route path="/ai-copilot" element={<AICopilot />} />
        <Route path="/ai-evaluation" element={<AIEvaluation />} />
        <Route path="/agent-runs" element={<AgentRuns />} />
      </Route>
    </Routes>
  );
}
