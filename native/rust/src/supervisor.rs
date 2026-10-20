//! The master agent: watches the other five and decides whether each may run.
//!
//! Stateless on purpose. The API and the Celery workers are separate
//! processes, so the supervisor's memory is the `agent_runs` table; every call
//! evaluates an agent's recent runs from scratch. A circuit breaker opens after
//! `failure_threshold` consecutive failures, stays open for `cooldown_s`, then
//! goes half-open and lets exactly one trial run decide.

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Run {
    pub ok: bool,
    pub latency_ms: f64,
    /// Seconds since the run started. Runs are given newest first.
    pub age_s: f64,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Policy {
    pub failure_threshold: u32,
    pub cooldown_s: f64,
    pub latency_budget_ms: f64,
    pub ewma_alpha: f64,
    pub degraded_error_rate: f64,
}

impl Default for Policy {
    fn default() -> Self {
        Policy { failure_threshold: 3, cooldown_s: 300.0, latency_budget_ms: 5000.0,
                 ewma_alpha: 0.3, degraded_error_rate: 0.3 }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Health {
    pub circuit: &'static str, // closed | open | half_open
    pub status: &'static str,  // idle | healthy | degraded | down
    pub consecutive_failures: u32,
    pub error_rate: f64,
    pub p95_latency_ms: f64,
    pub runs: usize,
    pub may_run: bool,
    pub reason: String,
}

pub fn p95(latencies: &[f64]) -> f64 {
    if latencies.is_empty() {
        return 0.0;
    }
    let mut v = latencies.to_vec();
    v.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let rank = (0.95 * v.len() as f64).ceil() as usize;
    v[rank.max(1) - 1]
}

pub fn evaluate(runs_newest_first: &[Run], policy: &Policy) -> Health {
    let n = runs_newest_first.len();
    if n == 0 {
        return Health { circuit: "closed", status: "idle", consecutive_failures: 0,
                        error_rate: 0.0, p95_latency_ms: 0.0, runs: 0, may_run: true,
                        reason: "no runs yet".into() };
    }
    let consecutive = runs_newest_first.iter().take_while(|r| !r.ok).count() as u32;
    let mut ewma = 0.0;
    for r in runs_newest_first.iter().rev() {
        ewma = policy.ewma_alpha * if r.ok { 0.0 } else { 1.0 } + (1.0 - policy.ewma_alpha) * ewma;
    }
    let lat: Vec<f64> = runs_newest_first.iter().map(|r| r.latency_ms).collect();
    let p = p95(&lat);
    let (circuit, may_run) = if consecutive >= policy.failure_threshold {
        if runs_newest_first[0].age_s < policy.cooldown_s { ("open", false) } else { ("half_open", true) }
    } else {
        ("closed", true)
    };
    let (status, reason) = if circuit == "open" {
        ("down", format!("{consecutive} consecutive failures; retry after {:.0}s cooldown",
                         policy.cooldown_s - runs_newest_first[0].age_s))
    } else if circuit == "half_open" {
        ("degraded", format!("{consecutive} consecutive failures; next run is a trial"))
    } else if ewma > policy.degraded_error_rate {
        ("degraded", format!("error rate {:.0}% (smoothed)", ewma * 100.0))
    } else if p > policy.latency_budget_ms {
        ("degraded", format!("p95 latency {p:.0} ms over the {:.0} ms budget", policy.latency_budget_ms))
    } else {
        ("healthy", "ok".to_string())
    };
    Health { circuit, status, consecutive_failures: consecutive, error_rate: ewma,
             p95_latency_ms: p, runs: n, may_run, reason }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ok(age: f64) -> Run { Run { ok: true, latency_ms: 10.0, age_s: age } }
    fn fail(age: f64) -> Run { Run { ok: false, latency_ms: 10.0, age_s: age } }

    #[test]
    fn idle_and_healthy() {
        let p = Policy::default();
        assert_eq!(evaluate(&[], &p).status, "idle");
        let h = evaluate(&[ok(1.0), ok(2.0)], &p);
        assert_eq!((h.status, h.circuit, h.may_run), ("healthy", "closed", true));
    }

    #[test]
    fn opens_then_half_opens_then_closes() {
        let p = Policy::default();
        let h = evaluate(&[fail(10.0), fail(20.0), fail(30.0), ok(40.0)], &p);
        assert_eq!((h.circuit, h.status, h.may_run), ("open", "down", false));
        assert_eq!(h.consecutive_failures, 3);
        let h = evaluate(&[fail(400.0), fail(410.0), fail(420.0)], &p);
        assert_eq!((h.circuit, h.may_run), ("half_open", true));
        let h = evaluate(&[ok(1.0), fail(400.0), fail(410.0), fail(420.0)], &p);
        assert_eq!(h.circuit, "closed");
        assert_eq!(h.status, "degraded"); // error rate still high right after
    }

    #[test]
    fn slow_runs_degrade() {
        let p = Policy::default();
        let runs: Vec<Run> = (0..20).map(|i| Run { ok: true, latency_ms: 9000.0, age_s: i as f64 }).collect();
        let h = evaluate(&runs, &p);
        assert_eq!(h.status, "degraded");
        assert_eq!(h.p95_latency_ms, 9000.0);
    }

    #[test]
    fn p95_rank() {
        let v: Vec<f64> = (1..=100).map(|x| x as f64).collect();
        assert_eq!(p95(&v), 95.0);
        assert_eq!(p95(&[3.0]), 3.0);
    }
}
