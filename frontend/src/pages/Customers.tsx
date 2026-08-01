import { useMemo, useState } from 'react';

import { api } from '../api/client';
import type { Customer, CustomerCreatePayload } from '../api/types';
import { PageStatus } from '../components/PageStatus';
import { useApi } from '../hooks/useApi';

const INDUSTRIES = ['Finance', 'Healthcare', 'Manufacturing', 'Energy', 'Technology', 'Retail', 'Other'];
const STATUSES = ['active', 'inactive', 'prospect'];

export function Customers() {
  const customersApi = useApi(api.getCustomers);
  const customers = customersApi.data ?? [];

  const [showForm, setShowForm] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const [form, setForm] = useState<CustomerCreatePayload>({
    name: '',
    industry: 'Finance',
    contact: '',
    status: 'prospect',
    owner: '',
  });

  const customerOptions = useMemo(() => customers, [customers]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setSubmitError(null);
    setSubmitSuccess(null);
    try {
      await api.createCustomer({
        ...form,
        name: form.name.trim(),
        industry: form.industry.trim(),
        contact: form.contact?.trim() || null,
        owner: form.owner.trim(),
      });
      setSubmitSuccess('Customer 创建成功');
      setShowForm(false);
      setForm({
        name: '',
        industry: 'Finance',
        contact: '',
        status: 'prospect',
        owner: '',
      });
      await customersApi.refetch();
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : '创建失败');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleStatusChange(customer: Customer, nextStatus: string) {
    if (nextStatus === customer.status) {
      return;
    }
    setUpdatingId(customer.id);
    setSubmitError(null);
    try {
      await api.updateCustomerStatus(customer.id, { status: nextStatus as 'active' | 'inactive' | 'prospect' });
      setSubmitSuccess('Customer 状态更新成功');
      await customersApi.refetch();
    } catch (err: unknown) {
      setSubmitError(err instanceof Error ? err.message : '状态更新失败');
      await customersApi.refetch();
    } finally {
      setUpdatingId(null);
    }
  }

  return (
    <div>
      <h1>Customers</h1>
      <button type="button" onClick={() => setShowForm((value) => !value)}>
        {showForm ? '关闭表单' : 'Create Customer'}
      </button>
      {submitSuccess ? <p className="page-status">{submitSuccess}</p> : null}
      {submitError ? <p className="page-status page-error">{submitError}</p> : null}
      {showForm ? (
        <form onSubmit={handleSubmit} className="data-form">
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="name" required />
          <select value={form.industry} onChange={(e) => setForm({ ...form, industry: e.target.value })}>
            {INDUSTRIES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <input value={form.contact ?? ''} onChange={(e) => setForm({ ...form, contact: e.target.value })} placeholder="contact" />
          <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
            {STATUSES.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <input value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} placeholder="owner" required />
          <div>
            <button type="submit" disabled={submitting}>
              {submitting ? '提交中...' : '提交'}
            </button>
            <button type="button" onClick={() => setShowForm(false)} disabled={submitting}>
              取消
            </button>
          </div>
        </form>
      ) : null}
      <PageStatus loading={customersApi.loading} error={customersApi.error} empty={customers.length === 0} emptyMessage="暂无客户数据">
        <table className="data-table">
          <thead>
            <tr>
              <th>ID</th>
              <th>Name</th>
              <th>Industry</th>
              <th>Status</th>
              <th>Contact</th>
              <th>Owner</th>
            </tr>
          </thead>
          <tbody>
            {customerOptions.map((customer) => (
              <tr key={customer.id}>
                <td>{customer.id}</td>
                <td>{customer?.name ?? '-'}</td>
                <td>{customer?.industry ?? '-'}</td>
                <td>
                  <select value={customer.status} disabled={updatingId === customer.id} onChange={(e) => handleStatusChange(customer, e.target.value)}>
                    {STATUSES.map((item) => (
                      <option key={item} value={item}>
                        {item}
                      </option>
                    ))}
                  </select>
                </td>
                <td>{customer?.contact ?? '-'}</td>
                <td>{customer?.owner ?? '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </PageStatus>
    </div>
  );
}
