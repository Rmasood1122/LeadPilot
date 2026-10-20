//! Lead Priority agent: which lead to work next, and what to do with it.
//!
//! Combines how well a lead fits (the existing 0-100 lead score, rescaled to
//! 0..1) with how it has engaged, decayed by recency, minus touch fatigue,
//! through a logistic. Deterministic: app/agents/reference.py implements the
//! same arithmetic and tests/test_agents_native_parity.py holds the two equal.

/// One lead's signals. `days_since_*` is negative when unknown.
#[derive(Clone, Debug, PartialEq)]
pub struct LeadSignals {
    pub fit: f64,
    pub opens: u32,
    pub clicks: u32,
    pub replied: bool,
    pub bounced: bool,
    pub unsubscribed: bool,
    pub touches: u32,
    pub days_since_last_touch: f64,
    pub days_since_last_engagement: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Priority {
    pub priority: f64,
    pub action: &'static str,
    pub engagement: f64,
    pub fatigue: f64,
}

pub const ENGAGEMENT_HALF_LIFE_DAYS: f64 = 7.0;
pub const FATIGUE_TOUCHES: f64 = 6.0;

/// Round half up to one decimal: floor(x*10 + 0.5) / 10, the same expression
/// the Python reference uses (Python's round() is banker's rounding).
fn round1(x: f64) -> f64 {
    (x * 10.0 + 0.5).floor() / 10.0
}

pub fn engagement(s: &LeadSignals) -> f64 {
    let raw = 1.0 - (-(0.35 * s.opens as f64 + 1.2 * s.clicks as f64)).exp();
    if raw > 0.0 && s.days_since_last_engagement >= 0.0 {
        raw * (-std::f64::consts::LN_2 * s.days_since_last_engagement / ENGAGEMENT_HALF_LIFE_DAYS).exp()
    } else {
        raw
    }
}

pub fn prioritize(s: &LeadSignals) -> Priority {
    if s.unsubscribed || s.bounced {
        return Priority { priority: 0.0, action: "do_not_contact", engagement: 0.0, fatigue: 0.0 };
    }
    let fit = s.fit.clamp(0.0, 1.0);
    let eng = engagement(s);
    let fatigue = (s.touches as f64 / FATIGUE_TOUCHES).min(1.0);
    let z = -2.0 + 3.0 * fit + 2.5 * eng - 1.5 * fatigue + if s.replied { 1.5 } else { 0.0 };
    let p = 1.0 / (1.0 + (-z).exp());
    let action = if s.replied {
        "respond_now"
    } else if s.touches == 0 {
        "start_sequence"
    } else if fatigue >= 1.0 {
        "rest"
    } else if eng > 0.5 && s.days_since_last_touch >= 2.0 {
        "follow_up_now"
    } else {
        "nurture"
    };
    Priority { priority: round1(100.0 * p), action, engagement: eng, fatigue }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn base() -> LeadSignals {
        LeadSignals { fit: 0.5, opens: 0, clicks: 0, replied: false, bounced: false,
                      unsubscribed: false, touches: 1, days_since_last_touch: 3.0,
                      days_since_last_engagement: -1.0 }
    }

    #[test]
    fn opted_out_or_bounced_is_never_contacted() {
        let mut s = base();
        s.unsubscribed = true;
        assert_eq!(prioritize(&s).action, "do_not_contact");
        assert_eq!(prioritize(&s).priority, 0.0);
        let mut s = base();
        s.bounced = true;
        s.replied = true;
        assert_eq!(prioritize(&s).action, "do_not_contact");
    }

    #[test]
    fn engagement_raises_priority_and_decays() {
        let cold = prioritize(&base()).priority;
        let mut warm = base();
        warm.opens = 3;
        warm.clicks = 1;
        warm.days_since_last_engagement = 0.0;
        let fresh = prioritize(&warm);
        assert!(fresh.priority > cold);
        assert_eq!(fresh.action, "follow_up_now");
        warm.days_since_last_engagement = 14.0;
        let stale = prioritize(&warm);
        assert!(stale.priority < fresh.priority);
        assert!((stale.engagement - fresh.engagement / 4.0).abs() < 1e-12);
    }

    #[test]
    fn actions() {
        let mut s = base();
        s.replied = true;
        assert_eq!(prioritize(&s).action, "respond_now");
        let mut s = base();
        s.touches = 0;
        assert_eq!(prioritize(&s).action, "start_sequence");
        let mut s = base();
        s.touches = 6;
        assert_eq!(prioritize(&s).action, "rest");
        assert_eq!(prioritize(&base()).action, "nurture");
    }

    #[test]
    fn fit_is_clamped() {
        let mut s = base();
        s.fit = 7.0;
        let mut t = base();
        t.fit = 1.0;
        assert_eq!(prioritize(&s), prioritize(&t));
    }
}
