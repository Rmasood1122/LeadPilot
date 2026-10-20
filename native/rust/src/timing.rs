//! Follow-up Timing agent: the best hour of the week to follow up.
//!
//! A 7x24 histogram of when this account's prospects actually replied (UTC),
//! smoothed with a business-hours prior so a thin history does not chase
//! noise. The next slot maximises posterior weight minus a small penalty per
//! hour of waiting, after a minimum gap since the last touch.

pub const HOURS_PER_WEEK: usize = 168;
pub const PRIOR_BUSINESS: f64 = 1.0;
pub const PRIOR_OTHER: f64 = 0.1;
pub const WAIT_PENALTY_PER_HOUR: f64 = 0.002;
pub const CONFIDENCE_HALF_N: f64 = 20.0;

/// weekday: 0 = Monday .. 6 = Sunday.
pub fn is_business(weekday: u32, hour: u32) -> bool {
    weekday < 5 && (8..18).contains(&hour)
}

/// Posterior weight per slot (index = weekday * 24 + hour), normalised to max 1.
pub fn slot_weights(replies: &[(u32, u32)]) -> Vec<f64> {
    let mut w = vec![0.0; HOURS_PER_WEEK];
    for (i, v) in w.iter_mut().enumerate() {
        let (d, h) = ((i / 24) as u32, (i % 24) as u32);
        *v = if is_business(d, h) { PRIOR_BUSINESS } else { PRIOR_OTHER };
    }
    for &(d, h) in replies {
        if d < 7 && h < 24 {
            w[(d * 24 + h) as usize] += 1.0;
        }
    }
    let max = w.iter().cloned().fold(0.0_f64, f64::max);
    w.iter().map(|v| v / max).collect()
}

#[derive(Clone, Debug, PartialEq)]
pub struct NextSlot {
    pub hours_ahead: u32,
    pub weekday: u32,
    pub hour: u32,
    pub weight: f64,
    pub confidence: f64,
}

pub fn confidence(n: usize) -> f64 {
    n as f64 / (n as f64 + CONFIDENCE_HALF_N)
}

/// The next slot at least `min_gap_hours` after now (weekday, hour), looking one
/// week ahead. Ties go to the sooner slot.
pub fn next_slot(replies: &[(u32, u32)], now_weekday: u32, now_hour: u32,
                 min_gap_hours: u32, business_only: bool) -> Option<NextSlot> {
    let w = slot_weights(replies);
    let start = (now_weekday % 7) * 24 + (now_hour % 24);
    let mut best: Option<(f64, NextSlot)> = None;
    for ahead in min_gap_hours..min_gap_hours + HOURS_PER_WEEK as u32 {
        let idx = ((start + ahead) as usize) % HOURS_PER_WEEK;
        let (d, h) = ((idx / 24) as u32, (idx % 24) as u32);
        if business_only && !is_business(d, h) {
            continue;
        }
        let score = w[idx] - WAIT_PENALTY_PER_HOUR * ahead as f64;
        if best.as_ref().map_or(true, |(s, _)| score > *s) {
            best = Some((score, NextSlot { hours_ahead: ahead, weekday: d, hour: h,
                                           weight: w[idx], confidence: confidence(replies.len()) }));
        }
    }
    best.map(|(_, slot)| slot)
}

/// The `k` heaviest slots, heaviest first; ties by slot order.
pub fn top_slots(replies: &[(u32, u32)], k: usize) -> Vec<(u32, u32, f64)> {
    let w = slot_weights(replies);
    let mut idx: Vec<usize> = (0..HOURS_PER_WEEK).collect();
    idx.sort_by(|a, b| w[*b].partial_cmp(&w[*a]).unwrap().then(a.cmp(b)));
    idx.into_iter().take(k).map(|i| ((i / 24) as u32, (i % 24) as u32, w[i])).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_history_prefers_business_hours() {
        let s = next_slot(&[], 5, 12, 0, false).unwrap(); // Saturday noon
        assert!(is_business(s.weekday, s.hour));
        assert_eq!((s.weekday, s.hour), (0, 8)); // Monday 08:00
        assert_eq!(s.confidence, 0.0);
    }

    #[test]
    fn replies_pull_the_slot() {
        let replies = vec![(2, 15); 12]; // Wednesday 15:00, many times
        let s = next_slot(&replies, 0, 9, 24, false).unwrap();
        assert_eq!((s.weekday, s.hour), (2, 15));
        assert_eq!(s.weight, 1.0);
        assert_eq!(top_slots(&replies, 1)[0], (2, 15, 1.0));
    }

    #[test]
    fn min_gap_is_respected_and_business_only_filters() {
        let s = next_slot(&[(0, 9)], 0, 9, 48, true).unwrap();
        assert!(s.hours_ahead >= 48);
        assert!(is_business(s.weekday, s.hour));
        let night = vec![(6, 2); 30];
        let s = next_slot(&night, 0, 0, 0, true).unwrap();
        assert!(is_business(s.weekday, s.hour));
    }

    #[test]
    fn out_of_range_replies_are_ignored() {
        assert_eq!(slot_weights(&[(9, 3), (1, 40)]), slot_weights(&[]));
    }
}
