import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import {
  LayoutDashboard, Truck, BarChart3, Activity,
  Search, Clock, RefreshCw, AlertTriangle,
  CheckCircle2, XCircle, ArrowUpRight, ArrowDownRight,
  TrendingUp, Package, ShieldCheck, Zap, Warehouse,
  ChevronRight, ChevronDown, Layers, Globe, X,
  Download, ArrowUpDown, SlidersHorizontal, Eye,
  Timer, Hash, MapPin, Box
} from 'lucide-react';
import { getSchedule, updateDispatchStatus, getAllSchedules } from './api';
import {
  AreaChart, Area, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ResponsiveContainer, Cell, PieChart, Pie
} from 'recharts';

/* ── Warehouse registry ─────────────────────────────────────────── */
const WAREHOUSES = [
  { id: '1', label: 'Коледино', short: 'КЛД' },
  { id: '2', label: 'Электросталь', short: 'ЭЛС' },
  { id: '3', label: 'Подольск', short: 'ПДЛ' },
  { id: '4', label: 'Тула', short: 'ТУЛ' },
  { id: '5', label: 'Казань', short: 'КЗН' },
];
const whName = (id) => WAREHOUSES.find(w => w.id === id)?.label || `Склад ${id}`;

/* ── Helpers ─────────────────────────────────────────────────────── */
const fmt = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
};
const fmtFull = (iso) => {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('ru-RU', { day: '2-digit', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' });
};
const fmtDate = (s) => {
  if (!s) return '—';
  const d = new Date(s + 'T00:00:00');
  return d.toLocaleDateString('ru-RU', { weekday: 'short', day: 'numeric', month: 'short' });
};
const statusClass = (s) => (s || '').toLowerCase();
const TRIGGER_LABELS = {
  CAPACITY_FULL: 'Полная загрузка',
  SLA_BREACH: 'Нарушение SLA',
  SLA_PREEMPTIVE: 'Превентивный SLA',
  NO_FILL_BEFORE_SLA: 'Недозагрузка до SLA',
  HORIZON_END: 'Конец горизонта',
  MANUAL: 'Ручной',
};
const triggerLabel = (r) => TRIGGER_LABELS[r] || r || '—';
const triggerClass = (r) => {
  if (!r) return '';
  const m = { CAPACITY_FULL: 'capacity', SLA_BREACH: 'sla-breach', SLA_PREEMPTIVE: 'sla-preemptive', NO_FILL_BEFORE_SLA: 'sla-preemptive', HORIZON_END: 'horizon', MANUAL: 'manual' };
  return m[r] || '';
};
const PALETTE = ['#3b82f6', '#f97316', '#10b981', '#8b5cf6', '#ec4899'];
const STATUS_LABELS = { PLANNED: 'Запланирован', CONFIRMED: 'Утверждён', COMPLETED: 'Завершён', CANCELLED: 'Отменён' };

/* ── CSV Export ──────────────────────────────────────────────────── */
function exportCSV(rows, filename) {
  if (!rows.length) return;
  const headers = Object.keys(rows[0]);
  const csv = [headers.join(';'), ...rows.map(r => headers.map(h => `"${r[h] ?? ''}"`).join(';'))].join('\n');
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename; a.click();
  URL.revokeObjectURL(url);
}

/* ── Reusable components ─────────────────────────────────────────── */

function KpiCard({ icon: Icon, iconColor, title, value, sub, trend, trendDir, delay, onClick, className }) {
  return (
    <div className={`card animate-in animate-in-delay-${delay || 1} ${className || ''}`}
      onClick={onClick} style={onClick ? { cursor: 'pointer' } : undefined}>
      <div className="card-header">
        <span className="card-title">{title}</span>
        <div className={`card-icon ${iconColor}`}><Icon /></div>
      </div>
      <div className="kpi-value">{value}</div>
      <div className="kpi-label">{sub}</div>
      {trend && (
        <span className={`kpi-trend ${trendDir}`}>
          {trendDir === 'up' ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
          {trend}
        </span>
      )}
    </div>
  );
}

function ChartTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="custom-tooltip">
      <div className="label">{label}</div>
      {payload.map((p, i) => (
        <div className="value" key={i}>
          <span className="dot" style={{ background: p.color }} />
          {p.name}: <strong>{typeof p.value === 'number' ? Math.round(p.value * 100) / 100 : p.value}</strong>
        </div>
      ))}
    </div>
  );
}

/* ── Slide-out Detail Panel ──────────────────────────────────────── */

function DispatchDetailPanel({ dispatch: d, onClose, onStatusChange }) {
  if (!d) return null;
  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="detail-panel animate-slide-in" onClick={e => e.stopPropagation()}>
        <div className="panel-header">
          <h2 className="panel-title">Детали рейса</h2>
          <button className="btn btn-ghost btn-sm" onClick={onClose}><X size={18} /></button>
        </div>

        <div className="panel-body">
          {/* Status + Actions */}
          <div className="panel-section">
            <div className="panel-row">
              <span className="panel-label">Статус</span>
              <span className={`status-badge ${statusClass(d.status)}`}>{STATUS_LABELS[d.status] || d.status}</span>
            </div>
            <div className="panel-actions">
              {d.status === 'PLANNED' && (
                <button className="btn btn-success" onClick={() => { onStatusChange(d.id, 'CONFIRMED'); onClose(); }}>
                  <CheckCircle2 size={16} /> Утвердить рейс
                </button>
              )}
              {d.status === 'CONFIRMED' && (
                <button className="btn btn-success" onClick={() => { onStatusChange(d.id, 'COMPLETED'); onClose(); }}>
                  <CheckCircle2 size={16} /> Завершить рейс
                </button>
              )}
              {(d.status === 'PLANNED' || d.status === 'CONFIRMED') && (
                <button className="btn btn-ghost" onClick={() => { onStatusChange(d.id, 'CANCELLED'); onClose(); }}>
                  <XCircle size={16} /> Отменить рейс
                </button>
              )}
            </div>
          </div>

          {/* Info grid */}
          <div className="panel-section">
            <div className="panel-section-title">Информация</div>
            <div className="panel-grid">
              <div className="panel-field">
                <div className="panel-field-icon"><MapPin size={14} /></div>
                <div>
                  <div className="panel-field-label">Склад</div>
                  <div className="panel-field-value">{d._whName || whName(d.warehouseId)}</div>
                </div>
              </div>
              <div className="panel-field">
                <div className="panel-field-icon"><Hash size={14} /></div>
                <div>
                  <div className="panel-field-label">Маршрут</div>
                  <div className="panel-field-value">{d.routeId || '—'}</div>
                </div>
              </div>
              <div className="panel-field">
                <div className="panel-field-icon"><Timer size={14} /></div>
                <div>
                  <div className="panel-field-label">Время подачи</div>
                  <div className="panel-field-value">{fmtFull(d.scheduledAt)}</div>
                </div>
              </div>
              <div className="panel-field">
                <div className="panel-field-icon"><Truck size={14} /></div>
                <div>
                  <div className="panel-field-label">Тип ТС</div>
                  <div className="panel-field-value">{d.vehicleType}</div>
                </div>
              </div>
            </div>
          </div>

          {/* Metrics */}
          <div className="panel-section">
            <div className="panel-section-title">Метрики загрузки</div>
            <div className="panel-metrics">
              <div className="panel-metric">
                <div className="panel-metric-value">{((d.fillRate || 0) * 100).toFixed(1)}%</div>
                <div className="panel-metric-label">Fill Rate</div>
                <div className="fill-rate-bar-lg">
                  <div className={`fill ${d.fillRate >= 0.7 ? 'fill-high' : d.fillRate >= 0.4 ? 'fill-mid' : 'fill-low'}`}
                    style={{ width: `${(d.fillRate || 0) * 100}%` }} />
                </div>
              </div>
              <div className="panel-metric">
                <div className="panel-metric-value">{d.expectedVolume ?? '—'}</div>
                <div className="panel-metric-label">Ожид. объём</div>
              </div>
              <div className="panel-metric">
                <div className="panel-metric-value">{d.vehicleCapacity ?? '—'}</div>
                <div className="panel-metric-label">Ёмкость ТС</div>
              </div>
            </div>
          </div>

          {/* Trigger + Priority */}
          <div className="panel-section">
            <div className="panel-section-title">Решение ML-движка</div>
            <div className="panel-row">
              <span className="panel-label">Причина вызова</span>
              <span className={`trigger-tag ${triggerClass(d.triggerReason)}`}>{triggerLabel(d.triggerReason)}</span>
            </div>
            <div className="panel-row" style={{ marginTop: 8 }}>
              <span className="panel-label">Приоритет</span>
              <div className={`priority-indicator priority-${d.priority}`}>
                <span className="dot" />{d.priority === 1 ? 'Критический' : d.priority === 2 ? 'Нормальный' : `Уровень ${d.priority}`}
              </div>
            </div>
          </div>

          {/* ID */}
          <div className="panel-section">
            <div className="panel-row">
              <span className="panel-label">ID рейса</span>
              <code className="panel-code">{d.id}</code>
            </div>
            {d.createdAt && (
              <div className="panel-row" style={{ marginTop: 4 }}>
                <span className="panel-label">Создан</span>
                <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{fmtFull(d.createdAt)}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   PAGE: Overview Dashboard (all warehouses)
   ═══════════════════════════════════════════════════════════════════ */

function OverviewDashboard({ allData, loading, onSelectWarehouse, onGoToBreaches }) {
  if (loading) return <div className="empty-state"><RefreshCw className="spin" /><h3>Загрузка всех складов…</h3></div>;

  const entries = Object.entries(allData);
  if (!entries.length) return <div className="empty-state"><Globe /><h3>Нет данных</h3><p>Данные появятся после загрузки</p></div>;

  let totalDispatches = 0, totalBreaches = 0, totalActive = 0, totalFill = 0, fillCount = 0, totalTrucks = 0;
  const perWarehouse = [];
  const triggerCounts = {};

  for (const [whId, d] of entries) {
    const dispatches = d.dispatches || [];
    const plan = d.tacticalPlan || [];
    const breaches = dispatches.filter(x => x.triggerReason === 'SLA_BREACH').length;
    const active = dispatches.filter(x => x.status === 'PLANNED' || x.status === 'CONFIRMED').length;
    const fill = dispatches.length ? dispatches.reduce((s, x) => s + (x.fillRate || 0), 0) / dispatches.length : 0;
    const trucks = plan.reduce((s, p) => s + (p.requiredTrucks || 0), 0);
    const sla = dispatches.length ? ((dispatches.length - breaches) / dispatches.length * 100).toFixed(0) : '100';

    for (const x of dispatches) {
      triggerCounts[x.triggerReason] = (triggerCounts[x.triggerReason] || 0) + 1;
    }

    totalDispatches += dispatches.length;
    totalBreaches += breaches;
    totalActive += active;
    totalFill += fill * dispatches.length;
    fillCount += dispatches.length;
    totalTrucks += trucks;

    perWarehouse.push({ whId, name: whName(whId), dispatches: dispatches.length, active, breaches, fill: (fill * 100).toFixed(0), sla, trucks });
  }

  const avgFill = fillCount ? (totalFill / fillCount * 100).toFixed(1) : '0.0';
  const globalSla = totalDispatches ? ((totalDispatches - totalBreaches) / totalDispatches * 100).toFixed(1) : '100.0';
  const pieData = Object.entries(triggerCounts).map(([name, value]) => ({ name: triggerLabel(name), value }));

  return (
    <>
      {totalBreaches > 0 && (
        <div className="alert-banner alert-danger animate-in" onClick={onGoToBreaches}>
          <div className="alert-icon"><AlertTriangle size={20} /></div>
          <div className="alert-content">
            <div className="alert-title">{totalBreaches} рейс(ов) с нарушением SLA</div>
            <div className="alert-sub">Рейсы требуют немедленного утверждения или отмены</div>
          </div>
          <button className="btn btn-sm btn-danger-outline">Перейти к нарушениям <ChevronRight size={14} /></button>
        </div>
      )}

      <div className="grid-4">
        <KpiCard icon={Layers} iconColor="purple" title="Всего рейсов" value={totalDispatches} sub={`${totalActive} активных`} delay={1} />
        <KpiCard icon={TrendingUp} iconColor="green" title="Средний Fill Rate" value={`${avgFill}%`} sub="по всей сети" delay={2} />
        <KpiCard icon={ShieldCheck} iconColor={parseFloat(globalSla) >= 90 ? 'green' : 'red'} title="SLA Health" value={`${globalSla}%`} sub="доставки в срок" delay={3} />
        <KpiCard icon={Zap} iconColor="orange" title="Потребность ТС" value={totalTrucks} sub="на неделю (все склады)" delay={4} />
      </div>

      <div className="section-header mt-24"><h2 className="section-title">Склады</h2></div>
      <div className="grid-wh">
        {perWarehouse.map((wh, i) => (
          <div className={`wh-card animate-in ${wh.breaches > 0 ? 'wh-card-danger' : ''}`}
            key={wh.whId} style={{ animationDelay: `${i * 60}ms` }}
            onClick={() => onSelectWarehouse(wh.whId)}>
            <div className="wh-card-header">
              <div className="wh-card-name"><Warehouse size={16} /><span>{wh.name}</span></div>
              {wh.breaches > 0 && <span className="wh-breach-badge">{wh.breaches} SLA</span>}
            </div>
            <div className="wh-card-stats">
              <div className="wh-stat"><div className="wh-stat-value">{wh.active}</div><div className="wh-stat-label">активных</div></div>
              <div className="wh-stat"><div className="wh-stat-value">{wh.fill}%</div><div className="wh-stat-label">fill rate</div></div>
              <div className="wh-stat"><div className={`wh-stat-value ${parseFloat(wh.sla) < 90 ? 'text-danger' : 'text-success'}`}>{wh.sla}%</div><div className="wh-stat-label">SLA</div></div>
              <div className="wh-stat"><div className="wh-stat-value">{wh.trucks}</div><div className="wh-stat-label">фур/нед</div></div>
            </div>
            <div className="wh-card-footer"><span>Подробнее</span><ChevronRight size={14} /></div>
          </div>
        ))}
      </div>

      <div className="grid-2 mt-24">
        <div className="card animate-in">
          <div className="card-header"><span className="card-title">Рейсы по складам</span></div>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={perWarehouse} barSize={32}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="dispatches" name="Всего рейсов" radius={[6, 6, 0, 0]}>
                  {perWarehouse.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card animate-in">
          <div className="card-header"><span className="card-title">Причины вызова ТС</span></div>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={60} outerRadius={100}
                  paddingAngle={3} label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  labelLine={{ stroke: '#64748b' }}>
                  {pieData.map((_, i) => <Cell key={i} fill={PALETTE[i % PALETTE.length]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   PAGE: Detail Dashboard (single warehouse)
   ═══════════════════════════════════════════════════════════════════ */

function DetailDashboard({ dispatches, plan, loading, warehouseId, onGoBack }) {
  if (loading) return <div className="empty-state"><RefreshCw className="spin" /><h3>Загрузка…</h3></div>;
  if (!dispatches?.length) return (
    <div className="empty-state">
      <Package /><h3>Нет рейсов для {whName(warehouseId)}</h3>
      <button className="btn btn-ghost mt-16" onClick={onGoBack}><ChevronRight size={14} style={{ transform: 'rotate(180deg)' }} /> Назад</button>
    </div>
  );

  const active = dispatches.filter(d => d.status === 'PLANNED' || d.status === 'CONFIRMED').length;
  const breaches = dispatches.filter(d => d.triggerReason === 'SLA_BREACH').length;
  const avgFill = (dispatches.reduce((s, d) => s + (d.fillRate || 0), 0) / dispatches.length * 100).toFixed(1);
  const slaHealth = ((dispatches.length - breaches) / dispatches.length * 100).toFixed(1);
  const totalTrucks = plan ? plan.reduce((s, p) => s + p.requiredTrucks, 0) : 0;
  const chartData = plan ? plan.map(p => ({ date: fmtDate(p.planDate), volume: p.forecastVolume, trucks: p.requiredTrucks })) : [];
  const statusCounts = [
    { name: 'Planned', count: dispatches.filter(d => d.status === 'PLANNED').length, color: '#3b82f6' },
    { name: 'Confirmed', count: dispatches.filter(d => d.status === 'CONFIRMED').length, color: '#eab308' },
    { name: 'Completed', count: dispatches.filter(d => d.status === 'COMPLETED').length, color: '#10b981' },
    { name: 'Cancelled', count: dispatches.filter(d => d.status === 'CANCELLED').length, color: '#ef4444' },
  ];

  return (
    <>
      <button className="btn btn-ghost mb-16 animate-in" onClick={onGoBack}><ChevronRight size={14} style={{ transform: 'rotate(180deg)' }} /> Назад к обзору</button>
      <div className="grid-4">
        <KpiCard icon={Truck} iconColor="blue" title="Активные рейсы" value={active} sub={`из ${dispatches.length} всего`} delay={1} />
        <KpiCard icon={TrendingUp} iconColor="green" title="Fill Rate" value={`${avgFill}%`} sub="коэффициент заполнения" delay={2} />
        <KpiCard icon={ShieldCheck} iconColor={parseFloat(slaHealth) >= 90 ? 'green' : 'red'} title="SLA Health" value={`${slaHealth}%`} sub="доставки в срок" delay={3} />
        <KpiCard icon={Zap} iconColor="orange" title="Потребность ТС" value={totalTrucks} sub="на неделю" delay={4} />
      </div>
      <div className="grid-2 mt-24">
        <div className="card animate-in">
          <div className="card-header"><span className="card-title">Прогноз объёма (7 дней)</span></div>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <defs><linearGradient id="gVol" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} /><stop offset="95%" stopColor="#3b82f6" stopOpacity={0} /></linearGradient></defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip content={<ChartTooltip />} />
                <Area type="monotone" dataKey="volume" name="Объём" stroke="#3b82f6" strokeWidth={2} fill="url(#gVol)" dot={{ r: 4, fill: '#3b82f6' }} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="card animate-in">
          <div className="card-header"><span className="card-title">Рейсы по статусу</span></div>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={statusCounts} barSize={40}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
                <Tooltip content={<ChartTooltip />} />
                <Bar dataKey="count" name="Кол-во" radius={[6, 6, 0, 0]}>{statusCounts.map((e, i) => <Cell key={i} fill={e.color} />)}</Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   PAGE: Dispatch (with Urgent section, multi-filter, sorting, export, detail panel)
   ═══════════════════════════════════════════════════════════════════ */

function DispatchPage({ allData, loading, onStatusChange, selectedWarehouse, onSelectWarehouse }) {
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [triggerFilter, setTriggerFilter] = useState('ALL');
  const [priorityFilter, setPriorityFilter] = useState('ALL');
  const [search, setSearch] = useState('');
  const [sortField, setSortField] = useState(null);
  const [sortDir, setSortDir] = useState('asc');
  const [selectedDispatch, setSelectedDispatch] = useState(null);
  const [showFilters, setShowFilters] = useState(false);

  const allDispatches = useMemo(() => {
    const result = [];
    for (const [whId, d] of Object.entries(allData)) {
      for (const disp of (d.dispatches || [])) {
        result.push({ ...disp, _whName: whName(whId) });
      }
    }
    return result;
  }, [allData]);

  const dispatches = selectedWarehouse === 'all'
    ? allDispatches
    : allDispatches.filter(d => d.warehouseId === selectedWarehouse);

  if (loading) return <div className="empty-state"><RefreshCw className="spin" /><h3>Загрузка…</h3></div>;
  if (!dispatches.length) return <div className="empty-state"><Truck /><h3>Нет рейсов</h3></div>;

  const urgent = dispatches.filter(d =>
    (d.triggerReason === 'SLA_BREACH' || d.triggerReason === 'NO_FILL_BEFORE_SLA' || d.priority === 1) &&
    (d.status === 'PLANNED' || d.status === 'CONFIRMED')
  );
  const planned = dispatches.filter(d => d.status === 'PLANNED');

  // Unique values for filters
  const triggers = [...new Set(dispatches.map(d => d.triggerReason).filter(Boolean))];
  const priorities = [...new Set(dispatches.map(d => d.priority))].sort();
  const vehicleTypes = [...new Set(dispatches.map(d => d.vehicleType).filter(Boolean))];

  let filtered = dispatches.filter(d => {
    if (statusFilter !== 'ALL' && d.status !== statusFilter) return false;
    if (triggerFilter !== 'ALL' && d.triggerReason !== triggerFilter) return false;
    if (priorityFilter !== 'ALL' && String(d.priority) !== priorityFilter) return false;
    if (search) {
      const q = search.toLowerCase();
      if (!d.warehouseId?.toLowerCase().includes(q) && !d.id?.toLowerCase().includes(q)
        && !d._whName?.toLowerCase().includes(q) && !d.vehicleType?.toLowerCase().includes(q)) return false;
    }
    return true;
  });

  // Sorting
  if (sortField) {
    filtered = [...filtered].sort((a, b) => {
      let va = a[sortField], vb = b[sortField];
      if (typeof va === 'number' && typeof vb === 'number') return sortDir === 'asc' ? va - vb : vb - va;
      if (typeof va === 'string') va = va.toLowerCase();
      if (typeof vb === 'string') vb = vb.toLowerCase();
      if (va < vb) return sortDir === 'asc' ? -1 : 1;
      if (va > vb) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
  }

  const toggleSort = (field) => {
    if (sortField === field) { setSortDir(d => d === 'asc' ? 'desc' : 'asc'); }
    else { setSortField(field); setSortDir('asc'); }
  };

  const SortIcon = ({ field }) => (
    <span className={`sort-icon ${sortField === field ? 'active' : ''}`} onClick={() => toggleSort(field)}>
      <ArrowUpDown size={11} />
    </span>
  );

  const handleBulkConfirm = () => {
    if (!planned.length || !confirm(`Утвердить ${planned.length} рейс(ов)?`)) return;
    Promise.all(planned.map(d => onStatusChange(d.id, 'CONFIRMED')));
  };

  const handleExport = () => {
    const rows = filtered.map(d => ({
      Склад: d._whName, Маршрут: d.routeId, Время: d.scheduledAt, ТС: d.vehicleType,
      'Fill Rate': ((d.fillRate || 0) * 100).toFixed(0) + '%', Причина: triggerLabel(d.triggerReason),
      Статус: d.status, Приоритет: d.priority, ID: d.id,
    }));
    exportCSV(rows, `dispatches_${new Date().toISOString().slice(0, 10)}.csv`);
  };

  const activeFilters = [statusFilter !== 'ALL', triggerFilter !== 'ALL', priorityFilter !== 'ALL', search].filter(Boolean).length;

  return (
    <>
      {selectedDispatch && (
        <DispatchDetailPanel dispatch={selectedDispatch} onClose={() => setSelectedDispatch(null)} onStatusChange={onStatusChange} />
      )}

      {/* Warehouse tabs */}
      <div className="wh-tabs animate-in">
        <button className={`wh-tab ${selectedWarehouse === 'all' ? 'active' : ''}`} onClick={() => onSelectWarehouse('all')}>
          <Globe size={14} /> Все
        </button>
        {WAREHOUSES.map(w => {
          const n = (allData[w.id]?.dispatches || []).filter(d => d.triggerReason === 'SLA_BREACH' && (d.status === 'PLANNED' || d.status === 'CONFIRMED')).length;
          return (
            <button key={w.id} className={`wh-tab ${selectedWarehouse === w.id ? 'active' : ''} ${n > 0 ? 'has-alert' : ''}`} onClick={() => onSelectWarehouse(w.id)}>
              {w.short}{n > 0 && <span className="wh-tab-badge">{n}</span>}
            </button>
          );
        })}
      </div>

      {/* Urgent section */}
      {urgent.length > 0 && (
        <div className="urgent-section animate-in">
          <div className="urgent-header">
            <div className="urgent-title"><AlertTriangle size={18} /><span>Требует внимания ({urgent.length})</span></div>
          </div>
          <div className="urgent-grid">
            {urgent.slice(0, 6).map(d => (
              <div className="urgent-card" key={d.id} onClick={() => setSelectedDispatch(d)}>
                <div className="urgent-card-top">
                  <span className={`trigger-tag ${triggerClass(d.triggerReason)}`}>{triggerLabel(d.triggerReason)}</span>
                  <span className={`status-badge ${statusClass(d.status)}`}>{d.status}</span>
                </div>
                <div className="urgent-card-info">
                  <div className="urgent-wh">{d._whName}</div>
                  <div className="urgent-meta">Маршрут {d.routeId} · {d.vehicleType} · Fill {((d.fillRate || 0) * 100).toFixed(0)}%</div>
                  <div className="urgent-time">{fmt(d.scheduledAt)}</div>
                </div>
                <div className="urgent-card-actions" onClick={e => e.stopPropagation()}>
                  {d.status === 'PLANNED' && (
                    <button className="btn btn-sm btn-success" onClick={() => onStatusChange(d.id, 'CONFIRMED')}><CheckCircle2 size={14} /> Утвердить</button>
                  )}
                  {d.status === 'CONFIRMED' && (
                    <button className="btn btn-sm btn-success" onClick={() => onStatusChange(d.id, 'COMPLETED')}><CheckCircle2 size={14} /> Завершить</button>
                  )}
                  <button className="btn btn-sm btn-ghost" onClick={() => onStatusChange(d.id, 'CANCELLED')}><XCircle size={14} /> Отменить</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Filters bar */}
      <div className="filters-bar">
        <div className="search-wrapper">
          <Search />
          <input className="search-input" placeholder="Поиск…" value={search} onChange={e => setSearch(e.target.value)} />
        </div>
        <select className="filter-select" value={statusFilter} onChange={e => setStatusFilter(e.target.value)}>
          <option value="ALL">Все статусы</option>
          <option value="PLANNED">Planned</option><option value="CONFIRMED">Confirmed</option>
          <option value="COMPLETED">Completed</option><option value="CANCELLED">Cancelled</option>
        </select>
        <button className={`btn btn-sm ${showFilters ? 'btn-primary' : 'btn-ghost'}`} onClick={() => setShowFilters(!showFilters)}>
          <SlidersHorizontal size={14} /> Фильтры {activeFilters > 0 && <span className="filter-count">{activeFilters}</span>}
        </button>
        {planned.length > 0 && (
          <button className="btn btn-sm btn-primary" onClick={handleBulkConfirm}><CheckCircle2 size={14} /> Утвердить все ({planned.length})</button>
        )}
        <button className="btn btn-sm btn-ghost" onClick={handleExport}><Download size={14} /> CSV</button>
        <span style={{ marginLeft: 'auto', fontSize: 12, color: 'var(--text-muted)' }}>{filtered.length} из {dispatches.length}</span>
      </div>

      {/* Expanded filters */}
      {showFilters && (
        <div className="filters-expanded animate-in">
          <div className="filter-group">
            <label className="filter-label">Причина вызова</label>
            <select className="filter-select" value={triggerFilter} onChange={e => setTriggerFilter(e.target.value)}>
              <option value="ALL">Все причины</option>
              {triggers.map(t => <option key={t} value={t}>{triggerLabel(t)}</option>)}
            </select>
          </div>
          <div className="filter-group">
            <label className="filter-label">Приоритет</label>
            <select className="filter-select" value={priorityFilter} onChange={e => setPriorityFilter(e.target.value)}>
              <option value="ALL">Все</option>
              {priorities.map(p => <option key={p} value={String(p)}>Приоритет {p}</option>)}
            </select>
          </div>
          {(triggerFilter !== 'ALL' || priorityFilter !== 'ALL') && (
            <button className="btn btn-sm btn-ghost" onClick={() => { setTriggerFilter('ALL'); setPriorityFilter('ALL'); }}>
              <X size={12} /> Сбросить
            </button>
          )}
        </div>
      )}

      {/* Table */}
      <div className="card" style={{ padding: 0 }}>
        <div className="data-table-wrapper" style={{ maxHeight: 'calc(100vh - 360px)', overflowY: 'auto' }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Склад <SortIcon field="_whName" /></th>
                <th>Маршрут <SortIcon field="routeId" /></th>
                <th>Время подачи <SortIcon field="scheduledAt" /></th>
                <th>Тип ТС</th>
                <th>Fill Rate <SortIcon field="fillRate" /></th>
                <th>Причина</th>
                <th>Статус</th>
                <th>Приор. <SortIcon field="priority" /></th>
                <th>Действия</th>
              </tr>
            </thead>
            <tbody>
              {filtered.length === 0 ? (
                <tr><td colSpan={9} style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>Нет рейсов по заданным фильтрам</td></tr>
              ) : filtered.map(d => (
                <tr key={d.id} className={d.triggerReason === 'SLA_BREACH' ? 'row-danger' : ''} onClick={() => setSelectedDispatch(d)} style={{ cursor: 'pointer' }}>
                  <td style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{d._whName}</td>
                  <td>{d.routeId || '—'}</td>
                  <td>{fmt(d.scheduledAt)}</td>
                  <td>{d.vehicleType}</td>
                  <td>
                    <div className="fill-rate-bar">
                      <div className={`fill ${d.fillRate >= 0.7 ? 'fill-high' : d.fillRate >= 0.4 ? 'fill-mid' : 'fill-low'}`}
                        style={{ width: `${(d.fillRate || 0) * 100}%` }} />
                    </div>
                    {((d.fillRate || 0) * 100).toFixed(0)}%
                  </td>
                  <td><span className={`trigger-tag ${triggerClass(d.triggerReason)}`}>{triggerLabel(d.triggerReason)}</span></td>
                  <td><span className={`status-badge ${statusClass(d.status)}`}>{d.status}</span></td>
                  <td><div className={`priority-indicator priority-${d.priority}`}><span className="dot" />{d.priority}</div></td>
                  <td onClick={e => e.stopPropagation()}>
                    <div className="action-buttons">
                      {d.status === 'PLANNED' && <button className="btn btn-sm btn-primary" onClick={() => onStatusChange(d.id, 'CONFIRMED')}><CheckCircle2 size={12} /></button>}
                      {d.status === 'CONFIRMED' && <button className="btn btn-sm btn-success" onClick={() => onStatusChange(d.id, 'COMPLETED')}><CheckCircle2 size={12} /></button>}
                      {(d.status === 'PLANNED' || d.status === 'CONFIRMED') && <button className="btn btn-sm btn-ghost" onClick={() => onStatusChange(d.id, 'CANCELLED')}><XCircle size={12} /></button>}
                      <button className="btn btn-sm btn-ghost" onClick={() => setSelectedDispatch(d)}><Eye size={12} /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   PAGE: Planning (all warehouses combined, with toggles)
   ═══════════════════════════════════════════════════════════════════ */

function PlanningPage({ allData, loading }) {
  const [visibleWarehouses, setVisibleWarehouses] = useState(() => new Set(WAREHOUSES.map(w => w.id)));

  if (loading) return <div className="empty-state"><RefreshCw className="spin" /><h3>Загрузка…</h3></div>;

  const entries = Object.entries(allData);
  if (!entries.length) return <div className="empty-state"><BarChart3 /><h3>Нет тактического плана</h3></div>;

  const dayMap = {};
  for (const [whId, d] of entries) {
    for (const p of (d.tacticalPlan || [])) {
      const key = p.planDate;
      if (!dayMap[key]) dayMap[key] = { date: fmtDate(p.planDate), rawDate: p.planDate, totalVolume: 0, totalTrucks: 0, byWarehouse: {} };
      dayMap[key].byWarehouse[whId] = { volume: p.forecastVolume, trucks: p.requiredTrucks };
      if (visibleWarehouses.has(whId)) {
        dayMap[key].totalVolume += p.forecastVolume || 0;
        dayMap[key].totalTrucks += p.requiredTrucks || 0;
      }
    }
  }
  const days = Object.values(dayMap).sort((a, b) => a.rawDate.localeCompare(b.rawDate));
  if (!days.length) return <div className="empty-state"><BarChart3 /><h3>Нет плана</h3></div>;

  const chartData = days.map(day => {
    const row = { date: day.date };
    for (const w of WAREHOUSES) {
      row[w.label] = visibleWarehouses.has(w.id) ? (day.byWarehouse[w.id]?.volume || 0) : 0;
    }
    return row;
  });

  const totalTrucksWeek = days.reduce((s, d) => s + d.totalTrucks, 0);
  const totalVolumeWeek = days.reduce((s, d) => s + d.totalVolume, 0);
  const peakDay = days.reduce((max, d) => d.totalTrucks > max.totalTrucks ? d : max, days[0]);

  const toggleWarehouse = (id) => {
    setVisibleWarehouses(prev => {
      const next = new Set(prev);
      if (next.has(id)) { if (next.size > 1) next.delete(id); }
      else next.add(id);
      return next;
    });
  };

  const handleExport = () => {
    const rows = days.map(day => {
      const row = { День: day.date };
      for (const w of WAREHOUSES) {
        const wd = day.byWarehouse[w.id];
        row[`${w.label} (фур)`] = wd?.trucks ?? 0;
        row[`${w.label} (объём)`] = wd?.volume?.toFixed(0) ?? 0;
      }
      row['Итого фур'] = day.totalTrucks;
      row['Итого объём'] = day.totalVolume.toFixed(0);
      return row;
    });
    exportCSV(rows, `planning_${new Date().toISOString().slice(0, 10)}.csv`);
  };

  return (
    <>
      <div className="grid-3">
        <KpiCard icon={Truck} iconColor="blue" title="Всего фур на неделю" value={totalTrucksWeek} sub="по выбранным складам" delay={1} />
        <KpiCard icon={Package} iconColor="orange" title="Общий объём" value={totalVolumeWeek.toFixed(0)} sub="единиц за неделю" delay={2} />
        <KpiCard icon={Zap} iconColor="red" title="Пиковый день" value={`${peakDay.totalTrucks} фур`} sub={peakDay.date} delay={3} />
      </div>

      {/* Warehouse toggles */}
      <div className="filters-bar">
        <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>Склады:</span>
        {WAREHOUSES.map((w, i) => (
          <button key={w.id} className={`wh-toggle ${visibleWarehouses.has(w.id) ? 'active' : ''}`}
            style={visibleWarehouses.has(w.id) ? { borderColor: PALETTE[i], color: PALETTE[i] } : {}}
            onClick={() => toggleWarehouse(w.id)}>
            <span className="wh-toggle-dot" style={{ background: visibleWarehouses.has(w.id) ? PALETTE[i] : 'var(--text-muted)' }} />
            {w.short}
          </button>
        ))}
        <button className="btn btn-sm btn-ghost" style={{ marginLeft: 'auto' }} onClick={handleExport}><Download size={14} /> CSV</button>
      </div>

      {/* Table */}
      <div className="card animate-in" style={{ padding: 0 }}>
        <div className="data-table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>День</th>
                {WAREHOUSES.filter(w => visibleWarehouses.has(w.id)).map(w => <th key={w.id}>{w.short}</th>)}
                <th style={{ background: 'var(--bg-elevated)' }}>Итого фур</th>
                <th style={{ background: 'var(--bg-elevated)' }}>Итого объём</th>
              </tr>
            </thead>
            <tbody>
              {days.map(day => (
                <tr key={day.rawDate}>
                  <td style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{day.date}</td>
                  {WAREHOUSES.filter(w => visibleWarehouses.has(w.id)).map(w => {
                    const wd = day.byWarehouse[w.id];
                    return <td key={w.id}>{wd ? <span><strong>{wd.trucks}</strong><span style={{ color: 'var(--text-muted)', fontSize: 11 }}> ({wd.volume.toFixed(0)})</span></span> : '—'}</td>;
                  })}
                  <td style={{ fontWeight: 700, color: 'var(--accent-primary)' }}>{day.totalTrucks}</td>
                  <td style={{ fontWeight: 600 }}>{day.totalVolume.toFixed(0)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Chart */}
      <div className="card mt-24 animate-in">
        <div className="card-header"><span className="card-title">Прогноз объёма по складам</span></div>
        <div className="chart-container" style={{ height: 350 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={chartData}>
              <defs>
                {WAREHOUSES.map((w, i) => (
                  <linearGradient key={w.id} id={`gPlan${w.id}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor={PALETTE[i]} stopOpacity={0.3} />
                    <stop offset="95%" stopColor={PALETTE[i]} stopOpacity={0} />
                  </linearGradient>
                ))}
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} axisLine={false} tickLine={false} />
              <Tooltip content={<ChartTooltip />} />
              {WAREHOUSES.filter(w => visibleWarehouses.has(w.id)).map((w, i) => (
                <Area key={w.id} type="monotone" dataKey={w.label} name={w.label} stackId="1"
                  stroke={PALETTE[WAREHOUSES.indexOf(w)]} strokeWidth={1.5} fill={`url(#gPlan${w.id})`} />
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </>
  );
}

/* ═══════════════════════════════════════════════════════════════════
   MAIN APP (with auto-refresh)
   ═══════════════════════════════════════════════════════════════════ */

const NAV = [
  { id: 'dashboard', label: 'Дашборд', icon: LayoutDashboard },
  { id: 'dispatch', label: 'Диспетчеризация', icon: Truck },
  { id: 'planning', label: 'Планирование', icon: BarChart3 },
];

export default function App() {
  const [page, setPage] = useState('dashboard');
  const [warehouse, setWarehouse] = useState('all');
  const [allData, setAllData] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastRefresh, setLastRefresh] = useState(null);
  const [dispatchWarehouse, setDispatchWarehouse] = useState('all');
  const [autoRefresh, setAutoRefresh] = useState(false);
  const intervalRef = useRef(null);

  const fetchAllData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getAllSchedules();
      setAllData(data);
      setLastRefresh(new Date());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchAllData(); }, [fetchAllData]);

  // Auto-refresh every 30s
  useEffect(() => {
    if (autoRefresh) {
      intervalRef.current = setInterval(fetchAllData, 30000);
    }
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [autoRefresh, fetchAllData]);

  const handleStatusChange = async (id, newStatus) => {
    try {
      await updateDispatchStatus(id, newStatus);
      fetchAllData();
    } catch (e) {
      alert('Ошибка: ' + e.message);
    }
  };

  const totalBreaches = useMemo(() => {
    let count = 0;
    for (const d of Object.values(allData)) {
      count += (d.dispatches || []).filter(x => x.triggerReason === 'SLA_BREACH' && (x.status === 'PLANNED' || x.status === 'CONFIRMED')).length;
    }
    return count;
  }, [allData]);

  const currentData = warehouse !== 'all' && allData[warehouse] ? allData[warehouse] : { dispatches: [], tacticalPlan: [] };

  const pageTitle = page === 'dashboard'
    ? (warehouse === 'all' ? 'Обзор всех складов' : `Дашборд — ${whName(warehouse)}`)
    : NAV.find(n => n.id === page)?.label || '';

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-logo"><Truck size={20} /></div>
          <div><div className="sidebar-title">WBLogistic</div><div className="sidebar-subtitle">Logistics Ops</div></div>
        </div>
        <nav className="sidebar-nav">
          <div className="nav-section-label">Навигация</div>
          {NAV.map(n => {
            const Icon = n.icon;
            return (
              <button key={n.id} className={`nav-item ${page === n.id ? 'active' : ''}`}
                onClick={() => { setPage(n.id); if (n.id === 'dashboard') setWarehouse('all'); }}>
                <Icon size={18} /><span>{n.label}</span>
                {n.id === 'dispatch' && totalBreaches > 0 && <span className="nav-badge pulse-badge">{totalBreaches}</span>}
              </button>
            );
          })}
          <div className="nav-section-label" style={{ marginTop: 16 }}>Склады</div>
          <button className={`nav-item nav-item-wh ${page === 'dashboard' && warehouse === 'all' ? 'active' : ''}`}
            onClick={() => { setPage('dashboard'); setWarehouse('all'); }}>
            <Globe size={16} /><span>Все склады</span>
          </button>
          {WAREHOUSES.map(w => {
            const n = (allData[w.id]?.dispatches || []).filter(d => d.triggerReason === 'SLA_BREACH' && (d.status === 'PLANNED' || d.status === 'CONFIRMED')).length;
            return (
              <button key={w.id} className={`nav-item nav-item-wh ${page === 'dashboard' && warehouse === w.id ? 'active' : ''}`}
                onClick={() => { setPage('dashboard'); setWarehouse(w.id); }}>
                <Warehouse size={16} /><span>{w.label}</span>
                {n > 0 && <span className="nav-badge-sm">{n}</span>}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <div className="sidebar-status"><span className="status-dot" /><span>Система онлайн</span></div>
        </div>
      </aside>

      <main className="main-content">
        <header className="main-header">
          <div className="header-left"><h1 className="header-title">{pageTitle}</h1></div>
          <div className="header-right">
            <button className={`btn btn-sm ${autoRefresh ? 'btn-success' : 'btn-ghost'}`} onClick={() => setAutoRefresh(!autoRefresh)}
              title={autoRefresh ? 'Авто-обновление: ВКЛ (30с)' : 'Авто-обновление: ВЫКЛ'}>
              <Timer size={14} />{autoRefresh ? '30с' : 'Авто'}
            </button>
            <button className="btn btn-primary" onClick={fetchAllData} disabled={loading}>
              <RefreshCw size={14} className={loading ? 'spin' : ''} />{loading ? '…' : 'Обновить'}
            </button>
            {lastRefresh && <div className="header-chip"><Clock size={12} />{lastRefresh.toLocaleTimeString('ru-RU')}</div>}
            <div className="header-chip live"><Activity size={12} />Live</div>
          </div>
        </header>

        <div className="page-content">
          {error && (
            <div className="alert-banner alert-danger animate-in" style={{ marginBottom: 16 }}>
              <div className="alert-icon"><AlertTriangle size={18} /></div>
              <div className="alert-content"><div className="alert-title">Ошибка</div><div className="alert-sub">{error}</div></div>
              <button className="btn btn-sm btn-ghost" onClick={fetchAllData}>Повторить</button>
            </div>
          )}
          {page === 'dashboard' && warehouse === 'all' && (
            <OverviewDashboard allData={allData} loading={loading} onSelectWarehouse={w => setWarehouse(w)}
              onGoToBreaches={() => { setPage('dispatch'); setDispatchWarehouse('all'); }} />
          )}
          {page === 'dashboard' && warehouse !== 'all' && (
            <DetailDashboard dispatches={currentData.dispatches || []} plan={currentData.tacticalPlan || []}
              loading={loading} warehouseId={warehouse} onGoBack={() => setWarehouse('all')} />
          )}
          {page === 'dispatch' && (
            <DispatchPage allData={allData} loading={loading} onStatusChange={handleStatusChange}
              selectedWarehouse={dispatchWarehouse} onSelectWarehouse={setDispatchWarehouse} />
          )}
          {page === 'planning' && <PlanningPage allData={allData} loading={loading} />}
        </div>
      </main>
    </div>
  );
}
