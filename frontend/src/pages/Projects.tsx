import { useEffect, useMemo, useState } from 'react';

import { api } from '../api/client';
import type { Customer, Project, ProjectCreatePayload } from '../api/types';
import { PageStatus } from '../components/PageStatus';
import { useApi } from '../hooks/useApi';

const STATUSES = ['planning', 'active', 'on_hold', 'completed', 'cancelled'];
const DELIVERY_STAGES = ['Discovery', 'Implementation', 'Testing', 'Go-live', 'Support'];
const RISK_LEVELS = ['low', 'medium', 'high'];
const HEALTH_OPTIONS = ['healthy', 'at_risk', 'critical'];

const RISK_TO_HEALTH: Record<string, string> = {
  low: 'healthy',
  medium: 'at_risk',
  high: 'critical',
};

export function Projects() {
  const projectsApi = useApi(api.getProjects);
  const customersApi = useApi(api.getCustomers);
  const projects = projectsApi.data ?? [];
  const customers = customersApi.data ?? [];

  const [showForm, setShowForm] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const [rowErrorId, setRowErrorId] = useState<number | null>(null);
  const [form, setForm] = useState<ProjectCreatePayload>({
    name: '',
    customer_id: 0,
    status: 'planning',
    delivery_stage: 'Discovery',
    risk_level: 'low',
  });

  useEffect(() => {
    if (customers.length > 0 && form.customer_id === 0) {
      setForm((prev) => ({ ...prev, customer_id: customers[0].id }));
    }
  }, [customers, form.customer_id]);

  async function handleOpenForm() {
    await customersApi.refetch();
    setShowForm(true);
  }

  const customerOptions = useMemo(() => customers, [customers]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(null);
    try {
      await api.createProject({
        ...form,
        name: form.name.trim(),
      });
      setSubmitSuccess('Project 创建成功');
      setShowForm(false);
      setForm((prev) => ({
        ...prev,
        name: '',
        status: 'planning',
        delivery_stage: 'Discovery',
        risk_level: 'low',
      }));
      await projectsApi.refetch();
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : '创建失败');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleStatusChange(project: Project, nextStatus: string) {
    if (nextStatus === project.status) {
      return;
    }
    setUpdatingId(project.id);
    setRowErrorId(null);
    try {
      await api.updateProject(project.id, { status: nextStatus });
      setSubmitSuccess('Project 状态更新成功');
      await projectsApi.refetch();
    } catch (err: unknown) {
      setRowErrorId(project.id);
      setSubmitError(err instanceof Error ? err.message : '状态更新失败');
      await projectsApi.refetch();
    } finally {
      setUpdatingId(null);
    }
  }

  async function handleStageChange(project: Project, nextStage: string) {
    if (nextStage === project.delivery_stage) {
      return;
    }
    setUpdatingId(project.id);
    setRowErrorId(null);
    try {
      await api.updateProject(project.id, { delivery_stage: nextStage });
      setSubmitSuccess('Project 阶段更新成功');
      await projectsApi.refetch();
    } catch (err: unknown) {
      setRowErrorId(project.id);
      setSubmitError(err instanceof Error ? err.message : '阶段更新失败');
      await projectsApi.refetch();
    } finally {
      setUpdatingId(null);
    }
  }

  async function handleRiskChange(project: Project, nextRiskLevel: string) {
    if (nextRiskLevel === project.risk_level) {
      return;
    }
    setUpdatingId(project.id);
    setRowErrorId(null);
    try {
      await api.updateProject(project.id, { risk_level: nextRiskLevel });
      setSubmitSuccess('Project 风险等级更新成功');
      await projectsApi.refetch();
    } catch (err: unknown) {
      setRowErrorId(project.id);
      setSubmitError(err instanceof Error ? err.message : '风险等级更新失败');
      await projectsApi.refetch();
    } finally {
      setUpdatingId(null);
    }
  }

  return (
    <div>
      <h1>Projects</h1>
      <button type="button" onClick={handleOpenForm}>
        {showForm ? '关闭表单' : 'Create Project'}
      </button>
      {submitSuccess ? <p className="page-status">{submitSuccess}</p> : null}
      {submitError ? <p className="page-status page-error">{submitError}</p> : null}
      {showForm ? (
        <form onSubmit={handleSubmit} className="data-form">
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="name" required />
          <select value={form.customer_id} onChange={(e) => setForm({ ...form, customer_id: Number(e.target.value) })} disabled={customersApi.loading}>
            {customerOptions.map((customer: Customer) => (
              <option key={customer.id} value={customer.id}>{customer.name}</option>
            ))}
          </select>
          <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
            {STATUSES.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <select value={form.delivery_stage ?? ''} onChange={(e) => setForm({ ...form, delivery_stage: e.target.value })}>
            {DELIVERY_STAGES.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <select value={form.risk_level ?? ''} onChange={(e) => setForm({ ...form, risk_level: e.target.value })}>
            {RISK_LEVELS.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          {customersApi.error ? <p className="page-error">{customersApi.error}</p> : null}
          <div>
            <button type="submit" disabled={submitting || customersApi.loading || customerOptions.length === 0}>
              {submitting ? '提交中...' : '提交'}
            </button>
            <button type="button" onClick={() => setShowForm(false)} disabled={submitting}>
              取消
            </button>
          </div>
        </form>
      ) : null}
      <PageStatus loading={projectsApi.loading} error={projectsApi.error} empty={projects.length === 0} emptyMessage="暂无项目数据">
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>customer_id</th>
              <th>Status</th>
              <th>risk_level</th>
              <th>delivery_stage</th>
              <th>Health</th>
            </tr>
          </thead>
          <tbody>
            {projects.map((project) => (
              <tr key={project.id}>
                <td>{project.id}</td>
                <td>{project?.name ?? '-'}</td>
                <td>{project?.customer_id ?? '-'}</td>
                <td>
                  <select
                    value={project.status}
                    disabled={updatingId === project.id}
                    onChange={(e) => handleStatusChange(project, e.target.value)}
                  >
                    {STATUSES.map((status) => (
                      <option key={status} value={status}>{status}</option>
                    ))}
                  </select>
                </td>
                <td>
                  <select
                    value={project.risk_level ?? ''}
                    disabled={updatingId === project.id}
                    onChange={(e) => handleRiskChange(project, e.target.value)}
                  >
                    {RISK_LEVELS.map((risk) => (
                      <option key={risk} value={risk}>{risk}</option>
                    ))}
                  </select>
                </td>
                <td>
                  <select
                    value={project.delivery_stage ?? ''}
                    disabled={updatingId === project.id}
                    onChange={(e) => handleStageChange(project, e.target.value)}
                  >
                    {DELIVERY_STAGES.map((stage) => (
                      <option key={stage} value={stage}>{stage}</option>
                    ))}
                  </select>
                </td>
                <td>{project?.health ?? HEALTH_OPTIONS.find((item) => item === RISK_TO_HEALTH[project?.risk_level ?? 'medium']) ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </PageStatus>
    </div>
  );
}
