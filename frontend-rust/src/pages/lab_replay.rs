use crate::api::{get_json, post_json_as, ApiError};
use crate::components::{
    controls_matrix::control_icon, error_box::ApiErrorBox, progress_panel::ProgressPanel,
    score_ring::ScoreRing,
};
use crate::models::{ControlStatus, RunStarted, ScenarioRun, ScoreInfo};
use crate::poll::poll_run;
use crate::snapshot;
use crate::util::pretty_name;
use leptos::*;
use leptos_router::{use_params_map, A};
use std::{cell::Cell, rc::Rc};

#[derive(Clone)]
struct ReplayData {
    scores: ScoreInfo,
    after: ScenarioRun,
}

fn control_list(items: Vec<(String, ControlStatus)>, empty: &'static str) -> impl IntoView {
    if items.is_empty() {
        return view! { <p class="muted small">{empty}</p> }.into_view();
    }
    view! {
        <ul class="plain-list">
            {items
                .into_iter()
                .map(|(n, s)| view! { <li><span>{pretty_name(&n)}</span><span>{control_icon(s)}</span></li> })
                .collect_view()}
        </ul>
    }
    .into_view()
}

fn replay_body(d: ReplayData, rid: String) -> impl IntoView {
    let before_controls = if d.scores.before_controls.is_empty() {
        snapshot::load_before(&rid).unwrap_or_default()
    } else {
        d.scores.before_controls.clone()
    };
    let after_controls = if d.scores.after_controls.is_empty() {
        d.after.controls.clone()
    } else {
        d.scores.after_controls.clone()
    };
    let before_gaps: Vec<_> = before_controls
        .into_iter()
        .filter(|(_, c)| *c != ControlStatus::Detected)
        .collect();
    let after_ok: Vec<_> = after_controls
        .iter()
        .filter(|(_, c)| *c == ControlStatus::Detected)
        .cloned()
        .collect();
    let after_gaps: Vec<_> = after_controls
        .into_iter()
        .filter(|(_, c)| *c != ControlStatus::Detected)
        .collect();

    let before_i = d.scores.before_score.unwrap_or(0.0).round() as i32;
    let after_i = d.scores.after_score.unwrap_or(0.0).round() as i32;
    let delta = d.scores.delta;
    let delta_class = match delta {
        Some(x) if x < 0.0 => "delta delta-neg",
        _ => "delta",
    };
    let delta_text = delta.map(|x| format!("{x:+.0} points"));
    let report_href = format!("/lab/report/{rid}");

    view! {
        <div class="compare">
            <section class="cmp-card cmp-before">
                <h2>"BEFORE"</h2>
                <ScoreRing score=before_i label="security score"/>
                <h3>"Missed controls"</h3>
                {control_list(before_gaps, "Before-run control details unavailable.")}
            </section>

            <div class=delta_class>{delta_text}</div>

            <section class="cmp-card cmp-after">
                <h2>"AFTER"</h2>
                <ScoreRing score=after_i label="security score"/>
                <h3>"Detected controls"</h3>
                {control_list(after_ok, "No controls detected yet.")}
                {(!after_gaps.is_empty())
                    .then(|| {
                        view! {
                            <h3>"Still open"</h3>
                            {control_list(after_gaps, "")}
                        }
                    })}
            </section>
        </div>
        <div class="actions">
            <A href=report_href class="btn">"📄 View Full Report"</A>
            <A href="/lab/scenarios" class="btn btn-ghost">"← Back to Scenarios"</A>
        </div>
    }
}

#[component]
pub fn LabReplay() -> impl IntoView {
    let params = use_params_map();
    let run_id = move || params.with(|p| p.get("run_id").cloned().unwrap_or_default());

    let alive = Rc::new(Cell::new(true));
    {
        let alive = alive.clone();
        on_cleanup(move || alive.set(false));
    }
    let progress = create_rw_signal(None::<f64>);
    let current = create_rw_signal(String::from("Starting replay…"));
    let steps = create_rw_signal(Vec::<String>::new());

    // On mount: POST replay, poll until done, then load scores + post-fix findings.
    let data = create_local_resource(run_id, move |rid| {
        let alive = alive.clone();
        async move {
            // The backend starts a NEW run for the replay; poll and read findings
            // from that run, but read before/after scores from the original run.
            let started: RunStarted =
                post_json_as(&format!("/api/lab/replay/{rid}"), &serde_json::json!({})).await?;
            let replay_id = started.run_id;
            current.set("Replaying scenario against the fixed twin…".to_string());
            poll_run(
                &replay_id,
                &alive,
                |st| {
                    steps.set(st.step_lines());
                    progress.set(st.progress);
                    if let Some(m) = &st.message {
                        current.set(m.clone());
                    }
                },
                true,
            )
            .await?;
            let scores = get_json::<ScoreInfo>(&format!("/api/security/scores/{rid}")).await?;
            let after =
                get_json::<ScenarioRun>(&format!("/api/security/findings/{replay_id}")).await?;
            Ok::<ReplayData, ApiError>(ReplayData { scores, after })
        }
    });

    view! {
        <h1>"Replay & Before / After"</h1>
        {move || match data.get() {
            Some(Ok(d)) => replay_body(d, run_id()).into_view(),
            Some(Err(e)) => {
                view! {
                    <ApiErrorBox error=e/>
                    <A href="/lab/scenarios" class="btn">"← Back to Scenarios"</A>
                }
                    .into_view()
            }
            None => view! { <ProgressPanel progress=progress current=current steps=steps/> }.into_view(),
        }}
    }
}
