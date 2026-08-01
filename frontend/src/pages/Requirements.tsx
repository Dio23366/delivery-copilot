import { useEffect, useMemo, useState } from 'react';

import { api } from '../api/client';
import type { Project, Requirement, RequirementCreatePayload } from '../api/types';
import { PageStatus } from '../components/PageStatus';
import { useApi } from '../hooks/useApi';

const PRIORITIES = ['low', 'medium', 'high', 'critical'];
const STATUSES = ['draft', 'approved', 'in_progress', 'blocked', 'delivered'];
const OWNERS = ['Delivery Team', 'Engineering Team', 'Product Team'];

export function Requirements() {
  const requirementsApi = useApi(api.getRequirements);
  const projectsApi = useApi(api.getProjects);
  const requirements = requirementsApi.data ?? [];
  const projects = projectsApi.data ?? [];

  const [showForm, setShowForm] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const [rowErrorId, setRowErrorId] = useState<number | null>(null);
  const [form, setForm] = useState<RequirementCreatePayload>({
    title: '',
    priority: 'medium',
    status: 'draft',
    owner: 'Delivery Team',
    due_date: '',
    project_id: 0,
  });

  useEffect(() => {
    if (projects.length > 0 && form.project_id === 0) {
      setForm((prev) => ({ ...prev, project_id: projects[0].id }));
    }
  }, [projects, form.project_id]);

  const projectOptions = useMemo(() => projects, [projects]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(null);
    try {
      await api.createRequirement({
        ...form,
        title: form.title.trim(),
        due_date: form.due_date || null,
      });
      setSubmitSuccess('Requirement 创建成功');
      setShowForm(false);
      setForm((prev) => ({
        ...prev,
        title: '',
        priority: 'medium',
        status: 'draft',
        owner: 'Delivery Team',
        due_date: '',
      }));
      await requirementsApi.refetch();
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : '创建失败');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleStatusChange(requirement: Requirement, nextStatus: string) {
    if (nextStatus === requirement.status) {
      return;
    }
    setUpdatingId(requirement.id);
    setRowErrorId(null);
    try {
      await api.updateRequirementStatus(requirement.id, nextStatus);
      setSubmitSuccess('Requirement 状态更新成功');
      await requirementsApi.refetch();
    } catch (err: unknown) {
      setRowErrorId(requirement.id);
      setSubmitError(err instanceof Error ? err.message : '状态更新失败');
      await requirementsApi.refetch();
    } finally {
      setUpdatingId(null);
    }
  }

  return (
    <div>
      <h1>Requirements</h1>
      <button type="button" onClick={() => setShowForm((value) => !value)}>
        {showForm ? '关闭表单' : 'Create Requirement'}
      </button>
      {submitSuccess ? <p className="page-status">{submitSuccess}</p> : null}
      {submitError ? <p className="page-status page-error">{submitError}</p> : null}
      {showForm ? (
        <form onSubmit={handleSubmit} className="data-form">
          <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="title" required />
          <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
            {PRIORITIES.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
            {STATUSES.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <select value={form.owner ?? ''} onChange={(e) => setForm({ ...form, owner: e.target.value })}>
            {OWNERS.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>
          <input type="date" value={form.due_date ?? ''} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
          <select value={form.project_id} onChange={(e) => setForm({ ...form, project_id: Number(e.target.value) })} disabled={projectsApi.loading}>
            {projectOptions.map((project: Project) => (
              <option key={project.id} value={project.id}>{project.name}</option>
            ))}
          </select>
          {projectsApi.error ? <p className="page-error">{projectsApi.error}</p> : null}
          <div>
            <button type="submit" disabled={submitting || projectsApi.loading || projectOptions.length === 0}>
              {submitting ? '提交中...' : '提交'}
            </button>
            <button type="button" onClick={() => setShowForm(false)} disabled={submitting}>
              取消
            </button>
          </div>
        </form>
      ) : null}
      <PageStatus loading={requirementsApi.loading} error={requirementsApi.error} empty={requirements.length === 0} emptyMessage="暂无需求数据">
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Title</th>
              <th>Priority</th>
              <th>Status</th>
              <th>Owner</th>
              <th>due_date</th>
              <th>project_id</th>
            </tr>
          </thead>
          <tbody>
            {requirements.map((requirement) => (
              <tr key={requirement.id}>
                <td>{requirement.id}</td>
                <td>{requirement?.title ?? '-'}</td>
                <td>{requirement?.priority ?? '-'}</td>
                <td>
                  <select
                    value={requirement.status}
                    disabled={updatingId === requirement.id}
                    onChange={(e) => handleStatusChange(requirement, e.target.value)}
                  >
                    {STATUSES.map((status) => (
                      <option key={status} value={status}>
                        {status}
                      </option>
                    ))}
                  </select>
                </td>
                <td>{requirement?.owner ?? '-'}</td>
                <td>{requirement?.due_date ?? '-'}</td>
                <td>{requirement?.project_id ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </PageStatus>
    </div>
  );
}
