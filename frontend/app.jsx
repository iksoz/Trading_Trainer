const { useEffect, useMemo, useState } = React;

function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("overview");

  async function loadDashboard() {
    setError("");
    try {
      const response = await fetch("/api/dashboard");
      if (!response.ok) {
        throw new Error(`Dashboard API returned ${response.status}`);
      }
      setData(await response.json());
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    loadDashboard();
  }, []);

  if (error) {
    return (
      <main className="shell">
        <div className="notice error">
          <strong>Dashboard unavailable</strong>
          <span>{error}</span>
        </div>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="shell">
        <div className="loading">Loading Trading Trainer...</div>
      </main>
    );
  }

  return (
    <main className="shell">
      <Header data={data} onRefresh={loadDashboard} />
      <section className="metricGrid">
        <MetricCard label="Paper Equity" value={money(data.account.equity)} delta={percent(data.account.total_return)} />
        <MetricCard label="Promotion Target" value="20.00%" delta={`${Math.round(data.promotion.progress.return_to_goal * 100)}% reached`} />
        <MetricCard label="Max Drawdown" value={percent(data.account.max_drawdown)} delta={`${Math.round(data.promotion.progress.drawdown_health * 100)}% buffer`} />
        <MetricCard label="Risk Violations" value={data.account.risk_violations} delta="must stay at 0" />
      </section>
      <section className="workspace">
        <aside className="sidePanel">
          <PromotionPanel promotion={data.promotion} account={data.account} />
          <AgentPanel agent={data.agent} status={data.status} />
        </aside>
        <section className="mainPanel">
          <Tabs activeTab={activeTab} onChange={setActiveTab} />
          {activeTab === "overview" && <Overview data={data} />}
          {activeTab === "trades" && <Trades fills={data.fills} />}
          {activeTab === "controls" && <Controls criteria={data.promotion.criteria} />}
        </section>
      </section>
    </main>
  );
}

function Header({ data, onRefresh }) {
  return (
    <header className="topbar">
      <div>
        <p className="eyebrow">Paper trading command center</p>
        <h1>Trading Trainer</h1>
        <p className="muted">
          {data.run_window.start} to {data.run_window.end} · generated {formatTime(data.generated_at)}
        </p>
      </div>
      <div className="topActions">
        <span className={`statusPill ${data.status}`}>{data.status === "review_ready" ? "Review ready" : "Live locked"}</span>
        <button className="iconButton" onClick={onRefresh} aria-label="Refresh dashboard" title="Refresh dashboard">
          ↻
        </button>
      </div>
    </header>
  );
}

function MetricCard({ label, value, delta }) {
  return (
    <article className="metricCard">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{delta}</small>
    </article>
  );
}

function PromotionPanel({ promotion, account }) {
  const rows = [
    ["Return", promotion.progress.return_to_goal, `${percent(account.total_return)} / 20.00%`],
    ["Paper days", promotion.progress.days_to_goal, `${account.paper_days} / ${promotion.criteria.min_calendar_days}`],
    ["Trades", promotion.progress.trades_to_goal, `${account.trade_count} / ${promotion.criteria.min_trades}`],
  ];

  return (
    <section className="panel">
      <div className="panelHeader">
        <h2>Promotion Gate</h2>
        <span className={promotion.approved_for_human_review ? "passText" : "lockText"}>
          {promotion.approved_for_human_review ? "Ready" : "Blocked"}
        </span>
      </div>
      <div className="progressList">
        {rows.map(([label, value, detail]) => (
          <div className="progressRow" key={label}>
            <div>
              <span>{label}</span>
              <small>{detail}</small>
            </div>
            <div className="bar" aria-label={`${label} progress`}>
              <span style={{ width: `${Math.round(value * 100)}%` }} />
            </div>
          </div>
        ))}
      </div>
      <ul className="reasonList">
        {promotion.reasons.length ? promotion.reasons.map((reason) => <li key={reason}>{reason}</li>) : <li>All gates passed for human review.</li>}
      </ul>
    </section>
  );
}

function AgentPanel({ agent, status }) {
  return (
    <section className="panel compact">
      <div className="panelHeader">
        <h2>Agent</h2>
        <span className="modeTag">paper</span>
      </div>
      <dl className="definitionGrid">
        <dt>Name</dt>
        <dd>{agent.name}</dd>
        <dt>Strategy</dt>
        <dd>{agent.strategy}</dd>
        <dt>State</dt>
        <dd>{agent.learning_state}</dd>
        <dt>Live path</dt>
        <dd>{status === "review_ready" ? "review required" : agent.next_live_step}</dd>
      </dl>
    </section>
  );
}

function Tabs({ activeTab, onChange }) {
  const tabs = [
    ["overview", "Overview"],
    ["trades", "Trades"],
    ["controls", "Controls"],
  ];
  return (
    <div className="tabs" role="tablist">
      {tabs.map(([id, label]) => (
        <button key={id} className={activeTab === id ? "active" : ""} onClick={() => onChange(id)} role="tab" aria-selected={activeTab === id}>
          {label}
        </button>
      ))}
    </div>
  );
}

function Overview({ data }) {
  return (
    <div className="overviewGrid">
      <section className="chartPanel">
        <div className="panelHeader">
          <h2>Equity Curve</h2>
          <span>{money(data.account.starting_cash)} start</span>
        </div>
        <EquityChart timeline={data.timeline} />
      </section>
      <section className="panel">
        <div className="panelHeader">
          <h2>Account</h2>
          <span>paper</span>
        </div>
        <dl className="accountGrid">
          <dt>Cash</dt>
          <dd>{money(data.account.cash)}</dd>
          <dt>Positions</dt>
          <dd>{money(data.account.positions_value)}</dd>
          <dt>Trades</dt>
          <dd>{data.account.trade_count}</dd>
          <dt>Window</dt>
          <dd>{data.account.paper_days} days</dd>
        </dl>
      </section>
    </div>
  );
}

function EquityChart({ timeline }) {
  const points = useMemo(() => {
    const width = 720;
    const height = 280;
    const padding = 22;
    const values = timeline.map((point) => point.equity);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const span = max - min || 1;
    return timeline.map((point, index) => {
      const x = padding + (index / Math.max(1, timeline.length - 1)) * (width - padding * 2);
      const y = height - padding - ((point.equity - min) / span) * (height - padding * 2);
      return { x, y, point };
    });
  }, [timeline]);

  const path = points.map((item, index) => `${index === 0 ? "M" : "L"} ${item.x.toFixed(1)} ${item.y.toFixed(1)}`).join(" ");
  const latest = timeline[timeline.length - 1];

  return (
    <div className="chartWrap">
      <svg viewBox="0 0 720 280" role="img" aria-label="Paper equity curve">
        <line x1="22" y1="238" x2="698" y2="238" className="axis" />
        <line x1="22" y1="22" x2="22" y2="238" className="axis" />
        <path d={path} className="equityLine" />
        {points.length > 0 && <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r="5" className="lastDot" />}
      </svg>
      <div className="chartFooter">
        <span>Latest {latest.day}</span>
        <strong>{money(latest.equity)}</strong>
      </div>
    </div>
  );
}

function Trades({ fills }) {
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>Day</th>
            <th>Symbol</th>
            <th>Side</th>
            <th>Qty</th>
            <th>Price</th>
            <th>Notional</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {fills.map((fill, index) => (
            <tr key={`${fill.day}-${fill.side}-${index}`}>
              <td>{fill.day}</td>
              <td>{fill.symbol}</td>
              <td><span className={`side ${fill.side}`}>{fill.side}</span></td>
              <td>{fill.quantity}</td>
              <td>{money(fill.price)}</td>
              <td>{money(fill.notional)}</td>
              <td>{fill.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Controls({ criteria }) {
  return (
    <section className="panel">
      <div className="panelHeader">
        <h2>Live Transition Rules</h2>
        <span>read only</span>
      </div>
      <div className="controlGrid">
        <ReadOnlyControl label="Minimum return" value={percent(criteria.min_total_return)} />
        <ReadOnlyControl label="Calendar days" value={criteria.min_calendar_days} />
        <ReadOnlyControl label="Sustained snapshots" value={criteria.sustained_return_days} />
        <ReadOnlyControl label="Max drawdown" value={percent(criteria.max_drawdown)} />
        <ReadOnlyControl label="Minimum trades" value={criteria.min_trades} />
        <ReadOnlyControl label="Risk violations" value={`≤ ${criteria.max_risk_violations}`} />
      </div>
      <div className="notice">
        <strong>Real-money execution remains disabled.</strong>
        <span>The live broker adapter is a stub until a separate approval path is implemented.</span>
      </div>
    </section>
  );
}

function ReadOnlyControl({ label, value }) {
  return (
    <label className="readOnlyControl">
      <span>{label}</span>
      <input value={value} readOnly />
    </label>
  );
}

function money(value) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(value);
}

function percent(value) {
  return new Intl.NumberFormat("en-US", { style: "percent", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
}

function formatTime(value) {
  return new Date(value).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
