const { useEffect, useMemo, useState } = React;

function App() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [paperBusy, setPaperBusy] = useState(false);
  const [activeTab, setActiveTab] = useState("overview");
  const [language, setLanguage] = useState(() => localStorage.getItem("language") || "en");
  const t = useMemo(() => createTranslator(language), [language]);

  function changeLanguage(nextLanguage) {
    localStorage.setItem("language", nextLanguage);
    setLanguage(nextLanguage);
  }

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

  async function runPaperAction(accountKind, action) {
    setPaperBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/paper/${accountKind}/${action}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const payload = await response.json();
      if (!response.ok) {
        throw new Error(payload.error || `Paper API returned ${response.status}`);
      }
      setData(payload.dashboard);
    } catch (err) {
      setError(err.message);
    } finally {
      setPaperBusy(false);
    }
  }

  async function saveSettings(payload) {
    setSaving(true);
    setError("");
    try {
      const response = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const nextData = await response.json();
      if (!response.ok) {
        throw new Error(nextData.error || `Settings API returned ${response.status}`);
      }
      setData(nextData);
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  }

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
        <div className="loading">{t("loading")}</div>
      </main>
    );
  }

  return (
    <main className="shell">
      <Header
        data={data}
        onRefresh={loadDashboard}
        language={language}
        onLanguageChange={changeLanguage}
        onStatus={() => setActiveTab("status")}
        t={t}
      />
      <section className="metricGrid">
        <MetricCard icon="◆" tone="positive" label={t("paperEquity")} value={money(data.paper_worker.equity || data.account.equity)} delta={percent(data.paper_worker.total_return || data.account.total_return)} />
        <MetricCard icon="↗" tone="neutral" label={t("promotionTarget")} value="20.00%" delta={`${Math.round(data.promotion.progress.return_to_goal * 100)}% ${t("reached")}`} />
        <MetricCard icon="⌁" tone="neutral" label={t("maxDrawdown")} value={percent(data.account.max_drawdown)} delta={`${Math.round(data.promotion.progress.drawdown_health * 100)}% ${t("buffer")}`} />
        <MetricCard icon="◉" tone="warning" label={t("riskViolations")} value={data.paper_worker.risk_violations || data.account.risk_violations} delta={t("mustStayZero")} />
      </section>
      <section className="workspace">
        <aside className="sidePanel">
          {data.paper_accounts.map((worker) => (
            <PaperWorkerPanel
              key={worker.account_kind}
              worker={worker}
              busy={paperBusy}
              onAction={runPaperAction}
              t={t}
            />
          ))}
          <PromotionPanel promotion={data.promotion} account={data.account} t={t} />
          <AgentPanel agent={data.agent} status={data.status} t={t} />
        </aside>
        <section className="mainPanel">
          <Tabs activeTab={activeTab} onChange={setActiveTab} t={t} />
          {activeTab === "overview" && <Overview data={data} t={t} />}
          {activeTab === "research" && <StockResearch />}
          {activeTab === "trades" && <Trades fills={data.paper_worker.fills.length ? data.paper_worker.fills : data.fills} t={t} />}
          {activeTab === "portfolios" && <StrategyLab data={data} saving={saving} onSave={saveSettings} t={t} />}
          {activeTab === "status" && <StatusPage data={data} t={t} />}
          {activeTab === "controls" && (
            <Controls
              data={data}
              saving={saving}
              t={t}
              onSave={saveSettings}
            />
          )}
        </section>
      </section>
    </main>
  );
}

function Header({ data, onRefresh, language, onLanguageChange, onStatus, t }) {
  return (
    <header className="topbar">
      <div className="brandBlock">
        <div className="brandMark" aria-hidden="true"><span /></div>
        <div>
          <p className="eyebrow">{t("commandCenter")}</p>
          <h1>Trading Trainer</h1>
          <p className="muted">
            {data.run_window.start
              ? `${data.run_window.start} ${t("to")} ${data.run_window.end} · `
              : `${t("waitingForPaper")} · `}
            {t("generated")} {formatTime(data.generated_at)}
          </p>
        </div>
      </div>
      <div className="topActions">
        <div className="languageToggle" aria-label={t("language")}>
          <button className={language === "en" ? "active" : ""} onClick={() => onLanguageChange("en")}>EN</button>
          <button className={language === "zh" ? "active" : ""} onClick={() => onLanguageChange("zh")}>中文</button>
        </div>
        <button className="iconButton" onClick={onStatus} aria-label={t("systemStatus")} title={t("systemStatus")}>
          ⚙
        </button>
        <span className={`statusPill ${data.status}`}>{data.status === "review_ready" ? t("reviewReady") : t("liveLocked")}</span>
        <button className="iconButton" onClick={onRefresh} aria-label={t("refresh")} title={t("refresh")}>
          ↻
        </button>
      </div>
    </header>
  );
}

function MetricCard({ icon, tone, label, value, delta }) {
  return (
    <article className="metricCard">
      <div className="metricLabel"><span className="metricIcon" aria-hidden="true">{icon}</span><span>{label}</span></div>
      <strong>{value}</strong>
      <small className={tone === "warning" ? "metricWarning" : "metricDelta"}>{delta}</small>
    </article>
  );
}

function PaperWorkerPanel({ worker, busy, onAction, t }) {
  const canStart = worker.credentials_configured && worker.account_configured && worker.environment === "sandbox";
  return (
    <section className="panel compact">
      <div className="panelHeader">
        <h2><span className={`liveDot ${worker.active ? "isActive" : ""}`} />{worker.account_label} {t("webullPaper")}</h2>
        <span className={worker.active ? "passText" : "lockText"}>
          {worker.active ? t("running") : t("stopped")}
        </span>
      </div>
      <dl className="definitionGrid">
        <dt>{t("env")}</dt>
        <dd>{worker.environment}</dd>
        <dt>{t("symbols")}</dt>
        <dd>{worker.symbols.join(", ")}</dd>
        <dt>{t("poll")}</dt>
        <dd>{worker.poll_seconds}s</dd>
        <dt>{t("sdk")}</dt>
        <dd>{worker.sdk_available ? t("ready") : t("missing")}</dd>
        <dt>{t("orders")}</dt>
        <dd>{worker.orders_routed}</dd>
        <dt>{t("equity")}</dt>
        <dd>{money(worker.equity)}</dd>
        <dt>{t("return")}</dt>
        <dd>{percent(worker.total_return)}</dd>
      </dl>
      {worker.last_error && (
        <div className="notice error slim">
          <strong>{t("workerError")}</strong>
          <span>{worker.last_error}</span>
        </div>
      )}
      <div className="buttonRow">
        <button className="saveButton" disabled={busy || worker.active || !canStart} onClick={() => onAction(worker.account_kind, "start")}>
          <span aria-hidden="true">▶</span> {busy ? t("working") : t("startPaper")}
        </button>
        <button className="secondaryButton" disabled={busy || !worker.active} onClick={() => onAction(worker.account_kind, "stop")}>
          <span aria-hidden="true">■</span> {t("stop")}
        </button>
      </div>
    </section>
  );
}

function PromotionPanel({ promotion, account, t }) {
  const rows = [
    [t("return"), promotion.progress.return_to_goal, `${percent(account.total_return)} / 20.00%`],
    [t("paperDays"), promotion.progress.days_to_goal, `${account.paper_days} / ${promotion.criteria.min_calendar_days}`],
    [t("trades"), promotion.progress.trades_to_goal, `${account.trade_count} / ${promotion.criteria.min_trades}`],
  ];

  return (
    <section className="panel">
      <div className="panelHeader">
        <h2>{t("promotionGate")}</h2>
        <span className={promotion.approved_for_human_review ? "passText" : "lockText"}>
          {promotion.approved_for_human_review ? t("ready") : t("blocked")}
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
        {promotion.reasons.length ? promotion.reasons.map((reason) => <li key={reason}>{reason}</li>) : <li>{t("allGatesPassed")}</li>}
      </ul>
    </section>
  );
}

function AgentPanel({ agent, status, t }) {
  return (
    <section className="panel compact">
      <div className="panelHeader">
        <h2>{t("agent")}</h2>
        <span className="modeTag">{t("paper")}</span>
      </div>
      <dl className="definitionGrid">
        <dt>{t("name")}</dt>
        <dd>{agent.name}</dd>
        <dt>{t("strategy")}</dt>
        <dd>{agent.strategy}</dd>
        <dt>{t("state")}</dt>
        <dd>{agent.learning_state}</dd>
        <dt>{t("livePath")}</dt>
        <dd>{status === "review_ready" ? t("reviewRequired") : t("liveDisabled")}</dd>
      </dl>
    </section>
  );
}

function Tabs({ activeTab, onChange, t }) {
  const tabs = [
    ["overview", "◫", t("overview")],
    ["research", "◌", "Stock Research"],
    ["trades", "⇄", t("trades")],
    ["portfolios", "◈", t("strategyLab")],
    ["controls", "⌘", t("controls")],
  ];
  return (
    <div className="tabs" role="tablist">
      {tabs.map(([id, icon, label]) => (
        <button key={id} className={activeTab === id ? "active" : ""} onClick={() => onChange(id)} role="tab" aria-selected={activeTab === id}>
          <span aria-hidden="true">{icon}</span>{label}
        </button>
      ))}
    </div>
  );
}

function StockResearch() {
  const [symbol, setSymbol] = useState("AAPL");
  const [optionType, setOptionType] = useState("call");
  const [strike, setStrike] = useState("");
  const [premium, setPremium] = useState("");
  const [contracts, setContracts] = useState("1");
  const [expiration, setExpiration] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    setLoading(true);
    setError("");
    const hasOption = strike.trim() || premium.trim();
    const option = hasOption ? { type: optionType, strike, premium, contracts, expiration } : null;
    try {
      const response = await fetch("/api/stock-analysis", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbol, option }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Unable to analyze this symbol.");
      setResult(payload);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="researchStack">
      <section className="panel">
        <div className="panelHeader">
          <div>
            <h2>Stock research & option outcome</h2>
            <p className="muted">Uses public price history and recent news headlines. Add an option premium to model a purchased call or put through expiration.</p>
          </div>
          <span>educational</span>
        </div>
        <form className="researchForm" onSubmit={submit}>
          <label className="readOnlyControl symbolControl">
            <span>Stock symbol</span>
            <input value={symbol} maxLength="15" onChange={(event) => setSymbol(event.target.value.toUpperCase())} placeholder="AAPL" required />
          </label>
          <label className="readOnlyControl">
            <span>Option type</span>
            <select value={optionType} onChange={(event) => setOptionType(event.target.value)}>
              <option value="call">Long call</option>
              <option value="put">Long put</option>
            </select>
          </label>
          <label className="readOnlyControl">
            <span>Strike price</span>
            <input type="number" min="0.01" step="0.01" value={strike} onChange={(event) => setStrike(event.target.value)} placeholder="Optional" />
          </label>
          <label className="readOnlyControl">
            <span>Premium / share</span>
            <input type="number" min="0.01" step="0.01" value={premium} onChange={(event) => setPremium(event.target.value)} placeholder="Optional" />
          </label>
          <label className="readOnlyControl">
            <span>Contracts</span>
            <input type="number" min="1" step="1" value={contracts} onChange={(event) => setContracts(event.target.value)} />
          </label>
          <label className="readOnlyControl">
            <span>Expiration</span>
            <input type="date" value={expiration} onChange={(event) => setExpiration(event.target.value)} />
          </label>
          <button className="saveButton researchButton" disabled={loading} type="submit">{loading ? "Analyzing…" : "Analyze symbol"}</button>
        </form>
        {error && <div className="notice error"><strong>Analysis unavailable</strong><span>{error}</span></div>}
      </section>

      {result && <ResearchResults result={result} />}
    </section>
  );
}

function ResearchResults({ result }) {
  const market = result.market || {};
  return (
    <>
      <section className="researchSummary">
        <article className="metricCard">
          <div className="metricLabel"><span className="metricIcon">$</span><span>{market.name || result.symbol}</span></div>
          <strong>{market.available ? money(market.price) : "Unavailable"}</strong>
          <small className={(market.change_pct || 0) >= 0 ? "metricDelta" : "metricWarning"}>{market.available ? `${market.change_pct >= 0 ? "+" : ""}${market.change_pct}% vs. prior close` : "Check symbol or data connection"}</small>
        </article>
        <article className="metricCard">
          <div className="metricLabel"><span className="metricIcon">≈</span><span>Trend</span></div>
          <strong>{market.trend === "above" ? "Constructive" : market.trend === "below" ? "Under pressure" : "—"}</strong>
          <small className="metricDelta">20-day {market.average_20_day ? money(market.average_20_day) : "—"} · 60-day {market.average_60_day ? money(market.average_60_day) : "—"}</small>
        </article>
        <article className="metricCard">
          <div className="metricLabel"><span className="metricIcon">◫</span><span>Research</span></div>
          <strong>{result.headlines.length} headlines</strong>
          <small className="metricDelta">{market.source || "Public sources unavailable"}</small>
        </article>
      </section>

      <section className="researchGrid">
        <section className="panel">
          <div className="panelHeader"><h2>Potential price catalysts</h2><span>{result.catalysts.length} to review</span></div>
          <div className="catalystList">
            {result.catalysts.map((catalyst, index) => (
              <article className="catalyst" key={`${catalyst.title}-${index}`}>
                <span className={`catalystTone ${catalyst.direction}`}>{catalyst.direction === "up" ? "Potential upside" : catalyst.direction === "down" ? "Potential downside" : "Watch"}</span>
                <div>
                  {catalyst.source_url ? <a href={catalyst.source_url} target="_blank" rel="noreferrer">{catalyst.title}</a> : <strong>{catalyst.title}</strong>}
                  <p>{catalyst.detail}</p>
                </div>
              </article>
            ))}
          </div>
        </section>
        <section className="panel">
          <div className="panelHeader"><h2>Recent research headlines</h2><span>{result.symbol}</span></div>
          <div className="headlineList">
            {result.headlines.length ? result.headlines.map((headline, index) => (
              <a key={`${headline.title}-${index}`} href={headline.url} target="_blank" rel="noreferrer"><strong>{headline.title}</strong><small>{headline.source}</small></a>
            )) : <div className="emptyState compactEmpty"><strong>No headlines available</strong><span>Try again shortly or use primary company filings.</span></div>}
          </div>
        </section>
      </section>

      {result.option && <OptionOutcome option={result.option} />}
      {(result.data_warnings || []).map((warning) => <div className="notice" key={warning}><strong>Data note</strong><span>{warning}</span></div>)}
      <div className="notice"><strong>Important</strong><span>{result.notice}</span></div>
    </>
  );
}

function OptionOutcome({ option }) {
  const maxGain = typeof option.max_gain === "number" ? money(option.max_gain) : option.max_gain;
  return (
    <section className="panel optionPanel">
      <div className="panelHeader"><h2>{option.type === "call" ? "Long call" : "Long put"} profit conditions</h2><span>{option.expiration || "expiration not specified"}</span></div>
      <div className="optionMetrics">
        <div><span>Break-even at expiration</span><strong>{money(option.break_even)}</strong></div>
        <div><span>Premium paid</span><strong>{money(option.cost)}</strong></div>
        <div><span>Maximum loss</span><strong>{money(option.max_loss)}</strong></div>
        <div><span>Maximum gain</span><strong>{maxGain}</strong></div>
      </div>
      <div className="notice success"><strong>{option.condition}</strong><span>{option.note}</span></div>
      {option.scenarios.length > 0 && <div className="scenarioGrid">
        {option.scenarios.map((scenario) => <div key={scenario.stock_price}><span>Stock at {money(scenario.stock_price)}</span><strong className={scenario.pnl > 0 ? "passText" : scenario.pnl < 0 ? "lockText" : ""}>{scenario.pnl >= 0 ? "+" : ""}{money(scenario.pnl)}</strong></div>)}
      </div>}
    </section>
  );
}

function StatusPage({ data, t }) {
  const status = data.system_status;
  const agentic = data.agentic;
  return (
    <section className="statusStack">
      <div className="panel">
        <div className="panelHeader">
          <h2>{t("systemStatus")}</h2>
          <span className={status.overall === "ok" ? "passText" : "lockText"}>{status.overall}</span>
        </div>
        <div className="statusGrid">
          {status.checks.map((check) => (
            <article className="statusItem" key={check.name}>
              <strong>{check.name}</strong>
              <span className={check.ok ? "passText" : "lockText"}>{check.status}</span>
              <small>{check.detail}</small>
            </article>
          ))}
        </div>
      </div>

      <div className="overviewGrid">
        <section className="panel">
          <div className="panelHeader">
            <h2>{t("brokerControls")}</h2>
            <span>{agentic.policy.mode}</span>
          </div>
          <dl className="definitionGrid wide">
            <dt>{t("policy")}</dt>
            <dd>{agentic.policy.reason}</dd>
            <dt>{t("killSwitch")}</dt>
            <dd>{String(status.broker_controls.kill_switch)}</dd>
            <dt>{t("manualReview")}</dt>
            <dd>{String(status.broker_controls.manual_approval_required)}</dd>
            <dt>{t("dailyOrders")}</dt>
            <dd>{status.broker_controls.orders_today} / {status.broker_controls.max_daily_order_count}</dd>
          </dl>
        </section>
        <section className="panel">
          <div className="panelHeader">
            <h2>{t("learningStatus")}</h2>
            <span>{agentic.evaluation.decision_count || 0} {t("decisions")}</span>
          </div>
          <dl className="definitionGrid wide">
            <dt>{t("snapshots")}</dt>
            <dd>{agentic.evaluation.snapshot_count || 0}</dd>
            <dt>{t("trades")}</dt>
            <dd>{agentic.evaluation.trade_count || 0}</dd>
            <dt>{t("return")}</dt>
            <dd>{percent(agentic.evaluation.total_return || 0)}</dd>
            <dt>{t("maxDrawdown")}</dt>
            <dd>{percent(agentic.evaluation.max_drawdown || 0)}</dd>
          </dl>
        </section>
      </div>

      <section className="panel">
        <div className="panelHeader">
          <h2>{t("learnerRecommendations")}</h2>
          <span>{agentic.recommendations.length}</span>
        </div>
        <div className="recommendationList">
          {agentic.recommendations.map((item, index) => (
            <article className="recommendation" key={`${item.title}-${index}`}>
              <strong>{item.title}</strong>
              <span>{item.detail}</span>
              <small>{item.action} · {Math.round(item.confidence * 100)}%</small>
            </article>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panelHeader">
          <h2>{t("decisionJournal")}</h2>
          <span>{agentic.decisions.length}</span>
        </div>
        <div className="tableWrap embedded">
          <table>
            <thead>
              <tr>
                <th>{t("time")}</th>
                <th>{t("account")}</th>
                <th>{t("symbol")}</th>
                <th>{t("signal")}</th>
                <th>{t("action")}</th>
                <th>{t("reason")}</th>
              </tr>
            </thead>
            <tbody>
              {agentic.decisions.length ? agentic.decisions.slice().reverse().map((decision, index) => (
                <tr key={`${decision.created_at}-${index}`}>
                  <td>{formatTime(decision.created_at)}</td>
                  <td>{decision.account_label}</td>
                  <td>{decision.symbol}</td>
                  <td>{decision.signal}</td>
                  <td>{decision.action}</td>
                  <td>{decision.reason}</td>
                </tr>
              )) : (
                <tr>
                  <td colSpan="6">{t("noDecisions")}</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </section>
  );
}

function StrategyLab({ data, saving, onSave, t }) {
  const settings = data.settings;
  const [paperStrategy, setPaperStrategy] = useState(settings.paper_strategy);
  const [shadowPortfolio, setShadowPortfolio] = useState(settings.shadow_portfolio);

  useEffect(() => {
    setPaperStrategy(settings.paper_strategy);
    setShadowPortfolio(settings.shadow_portfolio);
  }, [settings]);

  const selected = settings.shadow_portfolio_options.find((portfolio) => portfolio.key === shadowPortfolio) || settings.shadow_portfolio_detail;

  function saveStrategy() {
    onSave({
      paper_strategy: paperStrategy,
      shadow_portfolio: shadowPortfolio,
    });
  }

  return (
    <section className="strategyStack">
      <div className="panel">
        <div className="panelHeader">
          <h2>{t("paperStrategy")}</h2>
          <span>{paperStrategy === "shadow_portfolio" ? t("shadow") : t("movingAverage")}</span>
        </div>
        <div className="strategyControls">
          <label className="readOnlyControl">
            <span>{t("strategy")}</span>
            <select value={paperStrategy} onChange={(event) => setPaperStrategy(event.target.value)}>
              {settings.paper_strategy_options.map((option) => (
                <option value={option} key={option}>{strategyLabel(option, t)}</option>
              ))}
            </select>
          </label>
          <label className="readOnlyControl">
            <span>{t("shadowPortfolio")}</span>
            <select value={shadowPortfolio} onChange={(event) => setShadowPortfolio(event.target.value)} disabled={paperStrategy !== "shadow_portfolio"}>
              {settings.shadow_portfolio_options.map((portfolio) => (
                <option value={portfolio.key} key={portfolio.key}>{portfolio.name}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="notice">
          <strong>{t("activeSymbols")}: {(paperStrategy === "shadow_portfolio" ? selected.symbols : data.paper_worker.symbols).join(", ")}</strong>
          <span>{t("historyDb")}: {settings.paper_history_db_path}</span>
        </div>
        <button className="saveButton" disabled={saving} onClick={saveStrategy}>
          {saving ? t("saving") : t("saveStrategy")}
        </button>
      </div>

      <section className="portfolioGrid">
        {settings.shadow_portfolio_options.map((portfolio) => (
          <article className={`panel portfolioCard ${portfolio.key === shadowPortfolio ? "selected" : ""}`} key={portfolio.key}>
            <div className="panelHeader">
              <h2>{portfolio.name}</h2>
              <span>{portfolio.monthly_change_pct.toFixed(2)}%</span>
            </div>
            <dl className="accountGrid">
              <dt>{t("value")}</dt>
              <dd>{money(portfolio.portfolio_value_millions * 1000000)}</dd>
              <dt>{t("stocks")}</dt>
              <dd>{portfolio.stock_count}</dd>
              <dt>{t("sectors")}</dt>
              <dd>{portfolio.sector_preferences.slice(0, 2).join(", ")}</dd>
            </dl>
            <div className="holdingList">
              {portfolio.holdings.map((holding) => (
                <span key={holding.symbol}>{holding.symbol} · {holding.name}</span>
              ))}
            </div>
            <button className="secondaryButton" onClick={() => {
              setPaperStrategy("shadow_portfolio");
              setShadowPortfolio(portfolio.key);
            }}>
              {t("shadowThis")}
            </button>
          </article>
        ))}
      </section>
    </section>
  );
}

function strategyLabel(option, t) {
  if (option === "shadow_portfolio") {
    return t("shadowPortfolio");
  }
  return t("movingAverage");
}

function Overview({ data, t }) {
  return (
    <div className="overviewStack">
      <div className="overviewGrid">
        <section className="chartPanel">
          <div className="panelHeader">
            <h2>{t("equityCurve")}</h2>
            <span>{money(data.account.starting_cash)} {t("start")}</span>
          </div>
          <EquityChart timeline={data.timeline} t={t} />
        </section>
        <section className="panel">
          <div className="panelHeader">
            <h2>{t("allAccounts")}</h2>
            <span>{t("paper")}</span>
          </div>
          <dl className="accountGrid">
            <dt>{t("cash")}</dt>
            <dd>{money(data.account.cash)}</dd>
            <dt>{t("positions")}</dt>
            <dd>{money(data.account.positions_value)}</dd>
            <dt>{t("trades")}</dt>
            <dd>{data.account.trade_count}</dd>
            <dt>{t("window")}</dt>
            <dd>{data.account.paper_days} {t("days")}</dd>
          </dl>
        </section>
      </div>
      <AccountBreakdown accounts={data.paper_accounts} t={t} />
    </div>
  );
}

function AccountBreakdown({ accounts, t }) {
  return (
    <section className="accountBreakdown">
      {accounts.map((account) => (
        <article className="panel" key={account.account_kind}>
          <div className="panelHeader">
            <h2>{account.account_label}</h2>
            <span className={account.active ? "passText" : "lockText"}>
              {account.active ? t("running") : t("stopped")}
            </span>
          </div>
          <dl className="accountGrid">
            <dt>{t("equity")}</dt>
            <dd>{money(account.equity)}</dd>
            <dt>{t("cash")}</dt>
            <dd>{money(account.cash)}</dd>
            <dt>{t("positions")}</dt>
            <dd>{money(account.positions_value)}</dd>
            <dt>{t("return")}</dt>
            <dd>{percent(account.total_return)}</dd>
            <dt>{t("orders")}</dt>
            <dd>{account.orders_routed}</dd>
          </dl>
        </article>
      ))}
    </section>
  );
}

function EquityChart({ timeline, t }) {
  const points = useMemo(() => {
    if (!timeline.length) {
      return [];
    }
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

  if (!timeline.length) {
    return (
      <div className="emptyState">
        <strong>{t("noWebullSnapshots")}</strong>
        <span>{t("startWorkerForCurve")}</span>
      </div>
    );
  }

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

function Trades({ fills, t }) {
  return (
    <div className="tableWrap">
      <table>
        <thead>
          <tr>
            <th>{t("day")}</th>
            <th>{t("account")}</th>
            <th>{t("symbol")}</th>
            <th>{t("side")}</th>
            <th>{t("qty")}</th>
            <th>{t("price")}</th>
            <th>{t("notional")}</th>
            <th>{t("reason")}</th>
          </tr>
        </thead>
        <tbody>
          {fills.length ? fills.map((fill, index) => (
            <tr key={`${fill.day}-${fill.side}-${index}`}>
              <td>{fill.day}</td>
              <td>{fill.account_label || t("account")}</td>
              <td>{fill.symbol}</td>
              <td><span className={`side ${fill.side}`}>{fill.side}</span></td>
              <td>{fill.quantity}</td>
              <td>{money(fill.price)}</td>
              <td>{money(fill.notional)}</td>
              <td>{fill.reason}</td>
            </tr>
          )) : (
            <tr>
              <td colSpan="8">{t("noWebullFills")}</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

function Controls({ data, saving, onSave, t }) {
  const criteria = data.promotion.criteria;
  const settings = data.settings;
  const [allowedProducts, setAllowedProducts] = useState(settings.allowed_products);
  const [liveEnabled, setLiveEnabled] = useState(settings.live_trading_enabled);
  const [operatorOverride, setOperatorOverride] = useState(settings.live_trading_operator_override);
  const [killSwitch, setKillSwitch] = useState(settings.paper_trading_kill_switch);
  const [manualApproval, setManualApproval] = useState(settings.paper_manual_approval_required);
  const [maxDailyOrders, setMaxDailyOrders] = useState(settings.max_daily_order_count);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    setAllowedProducts(settings.allowed_products);
    setLiveEnabled(settings.live_trading_enabled);
    setOperatorOverride(settings.live_trading_operator_override);
    setKillSwitch(settings.paper_trading_kill_switch);
    setManualApproval(settings.paper_manual_approval_required);
    setMaxDailyOrders(settings.max_daily_order_count);
  }, [settings]);

  const gatePassed = data.promotion.approved_for_human_review;
  const liveNeedsOverride = liveEnabled && !gatePassed;

  function toggleProduct(product) {
    setAllowedProducts((current) => {
      if (current.includes(product)) {
        return current.length === 1 ? current : current.filter((item) => item !== product);
      }
      return [...current, product];
    });
  }

  function submitSettings(confirmation = "") {
    onSave({
      allowed_products: allowedProducts,
      paper_strategy: settings.paper_strategy,
      shadow_portfolio: settings.shadow_portfolio,
      paper_trading_kill_switch: killSwitch,
      paper_manual_approval_required: manualApproval,
      max_daily_order_count: Number(maxDailyOrders),
      live_trading_enabled: liveEnabled,
      live_trading_operator_override: liveNeedsOverride ? operatorOverride : false,
      confirmation,
    });
  }

  function saveControls() {
    if (liveNeedsOverride && operatorOverride) {
      setConfirming(true);
      return;
    }
    submitSettings();
  }

  return (
    <section className="controlsStack">
      <div className="panel">
        <div className="panelHeader">
          <h2>{t("liveRules")}</h2>
          <span>{settings.live_trading_allowed ? t("enabled") : t("guarded")}</span>
        </div>
        <div className="controlGrid">
          <ReadOnlyControl label={t("minimumReturn")} value={percent(criteria.min_total_return)} />
          <ReadOnlyControl label={t("calendarDays")} value={criteria.min_calendar_days} />
          <ReadOnlyControl label={t("sustainedSnapshots")} value={criteria.sustained_return_days} />
          <ReadOnlyControl label={t("maxDrawdown")} value={percent(criteria.max_drawdown)} />
          <ReadOnlyControl label={t("minimumTrades")} value={criteria.min_trades} />
          <ReadOnlyControl label={t("riskViolations")} value={`≤ ${criteria.max_risk_violations}`} />
        </div>
        <div className="switchRow">
          <div>
            <strong>{t("liveTrading")}</strong>
            <span>
              {gatePassed
                ? t("gateReady")
                : t("blockedUnlessOverride")}
            </span>
          </div>
          <label className="switch">
            <input
              type="checkbox"
              checked={liveEnabled}
              onChange={(event) => {
                setLiveEnabled(event.target.checked);
                if (!event.target.checked) {
                  setOperatorOverride(false);
                }
              }}
            />
            <span />
          </label>
        </div>
        {liveEnabled && !gatePassed && (
          <label className="checkRow">
            <input
              type="checkbox"
              checked={operatorOverride}
              onChange={(event) => setOperatorOverride(event.target.checked)}
            />
            <span>{t("allowOverride")}</span>
          </label>
        )}
        <div className={`notice ${settings.live_trading_allowed ? "success" : ""}`}>
          <strong>{settings.live_trading_allowed ? t("liveCanArm") : t("realMoneyLocked")}</strong>
          <span>
            {t("unlockSource")}: {settings.live_unlock_source.replace("_", " ")}. {t("twoFaRequired")}
          </span>
        </div>
      </div>

      <div className="panel">
        <div className="panelHeader">
          <h2>{t("allowedProducts")}</h2>
          <span>{data.environment}</span>
        </div>
        <div className="productGrid">
          {settings.allowed_product_options.map((product) => (
            <label className="productOption" key={product}>
              <input
                type="checkbox"
                checked={allowedProducts.includes(product)}
                onChange={() => toggleProduct(product)}
              />
              <span>{productLabel(product)}</span>
            </label>
          ))}
        </div>
        <div className="notice">
          <strong>{t("marketDataPolicy")}</strong>
          <span>{t("marketDataPolicyText")}</span>
        </div>
        <button className="saveButton" disabled={saving || (liveNeedsOverride && !operatorOverride)} onClick={saveControls}>
          {saving ? t("saving") : t("saveControls")}
        </button>
      </div>

      <div className="panel">
        <div className="panelHeader">
          <h2>{t("brokerControls")}</h2>
          <span>{data.agentic.policy.mode}</span>
        </div>
        <div className="switchRow">
          <div>
            <strong>{t("killSwitch")}</strong>
            <span>{t("killSwitchText")}</span>
          </div>
          <label className="switch">
            <input type="checkbox" checked={killSwitch} onChange={(event) => setKillSwitch(event.target.checked)} />
            <span />
          </label>
        </div>
        <div className="switchRow">
          <div>
            <strong>{t("manualReview")}</strong>
            <span>{t("manualReviewText")}</span>
          </div>
          <label className="switch">
            <input type="checkbox" checked={manualApproval} onChange={(event) => setManualApproval(event.target.checked)} />
            <span />
          </label>
        </div>
        <label className="readOnlyControl numericControl">
          <span>{t("maxDailyOrders")}</span>
          <input type="number" min="1" value={maxDailyOrders} onChange={(event) => setMaxDailyOrders(event.target.value)} />
        </label>
        <button className="saveButton" disabled={saving} onClick={saveControls}>
          {saving ? t("saving") : t("saveControls")}
        </button>
      </div>

      {confirming && (
        <ConfirmLiveDialog
          phrase={settings.live_confirmation_phrase}
          onCancel={() => setConfirming(false)}
          onConfirm={(phrase) => {
            setConfirming(false);
            submitSettings(phrase);
          }}
          t={t}
        />
      )}
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

function ConfirmLiveDialog({ phrase, onCancel, onConfirm, t }) {
  const [typed, setTyped] = useState("");
  const canConfirm = typed.trim() === phrase;

  return (
    <div className="modalBackdrop" role="presentation">
      <section className="modal" role="dialog" aria-modal="true" aria-labelledby="live-confirm-title">
        <div className="panelHeader">
          <h2 id="live-confirm-title">{t("confirmLive")}</h2>
          <span>prod</span>
        </div>
        <p className="muted">
          {t("confirmLiveText")}
        </p>
        <label className="readOnlyControl">
          <span>{phrase}</span>
          <input value={typed} onChange={(event) => setTyped(event.target.value)} autoFocus />
        </label>
        <div className="modalActions">
          <button className="secondaryButton" onClick={onCancel}>{t("cancel")}</button>
          <button className="dangerButton" disabled={!canConfirm} onClick={() => onConfirm(typed.trim())}>
            {t("enableLiveOverride")}
          </button>
        </div>
      </section>
    </div>
  );
}

function productLabel(product) {
  const labels = {
    stocks: "Stocks",
    etfs: "ETFs",
    options: "Options",
    futures: "Futures",
    crypto: "Crypto",
    event_contracts: "Event contracts",
  };
  return labels[product] || product;
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

const TRANSLATIONS = {
  en: {
    account: "Account",
    allAccounts: "All Accounts",
    agent: "Agent",
    allGatesPassed: "All gates passed for human review.",
    allowedProducts: "Allowed Products",
    allowOverride: "Allow operator override before the 20% / 5-month gate passes",
    activeSymbols: "Active symbols",
    action: "Action",
    blocked: "Blocked",
    blockedUnlessOverride: "Blocked unless you explicitly override from this dashboard.",
    buffer: "buffer",
    brokerControls: "Broker Controls",
    calendarDays: "Calendar days",
    cancel: "Cancel",
    cash: "Cash",
    commandCenter: "Paper trading command center",
    confirmLive: "Confirm Live Trading",
    confirmLiveText: "This enables a real-money override before the promotion gate has passed. Type the exact confirmation phrase to continue.",
    controls: "Controls",
    day: "Day",
    days: "days",
    dailyOrders: "Daily orders",
    decisions: "decisions",
    decisionJournal: "Decision Journal",
    enabled: "enabled",
    enableLiveOverride: "Enable live override",
    env: "Env",
    equity: "Equity",
    equityCurve: "Equity Curve",
    gateReady: "Promotion gate is ready for human approval.",
    generated: "generated",
    guarded: "guarded",
    historyDb: "History DB",
    language: "Language",
    liveCanArm: "Live trading can be armed.",
    liveDisabled: "disabled until promotion review passes",
    liveLocked: "Live locked",
    livePath: "Live path",
    liveRules: "Live Transition Rules",
    liveTrading: "Live trading",
    loading: "Loading Trading Trainer...",
    learningStatus: "Learning Status",
    learnerRecommendations: "Learner Recommendations",
    killSwitch: "Kill switch",
    killSwitchText: "Immediately blocks new paper orders while still recording decisions.",
    marketDataPolicy: "Market data policy: free first.",
    marketDataPolicyText: "Use Webull data available under current OpenAPI permissions and avoid paid quote subscriptions until you choose to add them.",
    maxDrawdown: "Max Drawdown",
    maxDailyOrders: "Max daily orders",
    manualReview: "Manual review",
    manualReviewText: "Approved decisions are queued in the journal instead of routed.",
    minimumReturn: "Minimum return",
    minimumTrades: "Minimum trades",
    missing: "missing",
    movingAverage: "Moving average",
    mustStayZero: "must stay at 0",
    name: "Name",
    noDecisions: "No decisions recorded yet.",
    notional: "Notional",
    orders: "Orders",
    overview: "Overview",
    paper: "paper",
    paperDays: "Paper days",
    paperEquity: "Paper Equity",
    paperStrategy: "Paper Strategy",
    poll: "Poll",
    positions: "Positions",
    policy: "Policy",
    price: "Price",
    promotionGate: "Promotion Gate",
    promotionTarget: "Promotion Target",
    qty: "Qty",
    reached: "reached",
    ready: "Ready",
    realMoneyLocked: "Real-money execution remains locked.",
    reason: "Reason",
    refresh: "Refresh dashboard",
    return: "Return",
    reviewReady: "Review ready",
    reviewRequired: "review required",
    riskViolations: "Risk Violations",
    running: "Running",
    saveControls: "Save controls",
    saveStrategy: "Save strategy",
    saving: "Saving...",
    sdk: "SDK",
    sectors: "Sectors",
    shadow: "Shadow",
    shadowPortfolio: "Shadow Portfolio",
    shadowThis: "Shadow this",
    side: "Side",
    start: "start",
    startPaper: "Start paper",
    state: "State",
    stop: "Stop",
    stopped: "Stopped",
    signal: "Signal",
    snapshots: "Snapshots",
    status: "Status",
    stocks: "Stocks",
    strategy: "Strategy",
    strategyLab: "Strategies",
    sustainedSnapshots: "Sustained snapshots",
    symbol: "Symbol",
    symbols: "Symbols",
    systemStatus: "System Status",
    time: "Time",
    to: "to",
    trades: "Trades",
    twoFaRequired: "2FA token setup is still required before Webull live order routing.",
    unlockSource: "Unlock source",
    value: "Value",
    webullPaper: "Webull Paper",
    window: "Window",
    waitingForPaper: "waiting for Webull paper data",
    workerError: "Worker error",
    working: "Working...",
    noWebullFills: "No Webull sandbox paper fills yet.",
    noWebullSnapshots: "No Webull paper snapshots yet",
    startWorkerForCurve: "Start the Webull Paper worker to pull sandbox data and build the equity curve.",
  },
  zh: {
    account: "账户",
    allAccounts: "全部账户",
    agent: "智能体",
    allGatesPassed: "所有门槛已通过，可进入人工复核。",
    allowedProducts: "允许交易产品",
    allowOverride: "允许在 20% / 5 个月门槛前进行人工覆盖",
    activeSymbols: "当前标的",
    action: "动作",
    blocked: "已阻止",
    blockedUnlessOverride: "除非你在仪表盘明确覆盖，否则保持阻止。",
    buffer: "缓冲",
    brokerControls: "券商级控制",
    calendarDays: "日历天数",
    cancel: "取消",
    cash: "现金",
    commandCenter: "模拟交易控制台",
    confirmLive: "确认实盘交易",
    confirmLiveText: "这会在晋级门槛通过前启用真钱覆盖。请输入完全一致的确认短语继续。",
    controls: "控制",
    day: "日期",
    days: "天",
    dailyOrders: "每日订单",
    decisions: "条决策",
    decisionJournal: "决策日志",
    enabled: "已启用",
    enableLiveOverride: "启用实盘覆盖",
    env: "环境",
    equity: "权益",
    equityCurve: "权益曲线",
    gateReady: "晋级门槛已准备好进入人工批准。",
    generated: "生成于",
    guarded: "受保护",
    historyDb: "历史数据库",
    language: "语言",
    liveCanArm: "实盘交易可以进入待启用状态。",
    liveDisabled: "晋级复核通过前禁用",
    liveLocked: "实盘锁定",
    livePath: "实盘路径",
    liveRules: "实盘切换规则",
    liveTrading: "实盘交易",
    loading: "正在加载 Trading Trainer...",
    learningStatus: "学习状态",
    learnerRecommendations: "学习建议",
    killSwitch: "熔断开关",
    killSwitchText: "立即阻止新的模拟订单，同时继续记录决策。",
    marketDataPolicy: "行情策略：优先免费。",
    marketDataPolicyText: "仅使用当前 Webull OpenAPI 权限下可用的数据，暂不启用付费行情订阅。",
    maxDrawdown: "最大回撤",
    maxDailyOrders: "每日最大订单数",
    manualReview: "人工复核",
    manualReviewText: "通过风控的决策会进入日志队列，而不是直接路由。",
    minimumReturn: "最低收益",
    minimumTrades: "最低交易数",
    missing: "缺失",
    movingAverage: "移动平均",
    mustStayZero: "必须保持为 0",
    name: "名称",
    noDecisions: "还没有记录决策。",
    notional: "名义金额",
    orders: "订单",
    overview: "总览",
    paper: "模拟",
    paperDays: "模拟天数",
    paperEquity: "模拟权益",
    paperStrategy: "模拟策略",
    poll: "轮询",
    positions: "持仓",
    policy: "策略状态",
    price: "价格",
    promotionGate: "晋级门槛",
    promotionTarget: "晋级目标",
    qty: "数量",
    reached: "已达到",
    ready: "就绪",
    realMoneyLocked: "真钱执行仍然锁定。",
    reason: "原因",
    refresh: "刷新仪表盘",
    return: "收益",
    reviewReady: "可复核",
    reviewRequired: "需要复核",
    riskViolations: "风控违规",
    running: "运行中",
    saveControls: "保存控制",
    saveStrategy: "保存策略",
    saving: "保存中...",
    sdk: "SDK",
    sectors: "行业",
    shadow: "跟投",
    shadowPortfolio: "跟投组合",
    shadowThis: "跟投这个",
    side: "方向",
    start: "起始",
    startPaper: "启动模拟",
    state: "状态",
    stop: "停止",
    stopped: "已停止",
    signal: "信号",
    snapshots: "快照",
    status: "状态",
    stocks: "股票",
    strategy: "策略",
    strategyLab: "策略",
    sustainedSnapshots: "持续快照",
    symbol: "标的",
    symbols: "标的",
    systemStatus: "系统状态",
    time: "时间",
    to: "到",
    trades: "交易",
    twoFaRequired: "Webull 实盘下单前仍需完成 2FA token 设置。",
    unlockSource: "解锁来源",
    value: "价值",
    webullPaper: "Webull 模拟",
    window: "窗口",
    waitingForPaper: "等待 Webull 模拟数据",
    workerError: "工作器错误",
    working: "处理中...",
    noWebullFills: "还没有 Webull sandbox 模拟成交。",
    noWebullSnapshots: "还没有 Webull 模拟快照",
    startWorkerForCurve: "启动 Webull 模拟工作器后，会拉取 sandbox 数据并生成权益曲线。",
  },
};

function createTranslator(language) {
  const dictionary = TRANSLATIONS[language] || TRANSLATIONS.en;
  return (key) => dictionary[key] || TRANSLATIONS.en[key] || key;
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
