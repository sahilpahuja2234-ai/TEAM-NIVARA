use crate::util::score_color;
use leptos::*;

const RADIUS: f64 = 45.0;

/// SVG arc ring for a 0–100 score. Color: red <40, yellow 40–70, green >70.
#[component]
pub fn ScoreRing(
    score: i32,
    #[prop(optional, into)] label: String,
) -> impl IntoView {
    let s = score.clamp(0, 100);
    let circ = 2.0 * std::f64::consts::PI * RADIUS;
    let offset = circ * (1.0 - (s as f64) / 100.0);
    let color = score_color(s as f64);
    view! {
        <div class="score-ring">
            <svg viewBox="0 0 100 100" width="130" height="130">
                <circle cx="50" cy="50" r="45" fill="none" stroke="var(--border)" stroke-width="8"></circle>
                <circle
                    class="ring-arc"
                    cx="50" cy="50" r="45" fill="none"
                    stroke=color stroke-width="8" stroke-linecap="round"
                    stroke-dasharray=format!("{circ:.2}")
                    stroke-dashoffset=format!("{offset:.2}")
                    transform="rotate(-90 50 50)"
                ></circle>
                <text x="50" y="57" text-anchor="middle" fill="var(--text)" font-size="24" font-weight="700">{s}</text>
            </svg>
            <div class="score-label">{label}</div>
        </div>
    }
}
