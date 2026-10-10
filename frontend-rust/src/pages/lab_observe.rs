use crate::api::get_json;
use crate::components::{
    attack_path::AttackPath,
    badge::Badge,
    controls_matrix::{control_icon, ControlMatrix},
    error_box::ApiErrorBox,
    spinner::Spinner,
};
use crate::models::{ControlStatus, ScenarioRun};
use crate::snapshot;
use crate::util::pretty_name;
use leptos::*;
use leptos_router::{use_params_map, A};

/// DETECTED / MISSED / PARTIAL — from `status` when it says so, otherwise from the controls.
fn overall(run: &ScenarioRun) -> (&'static str, &'static str) {
    let s = run.status.to_lowercase();
    if s.contains("partial") {
        return ("PARTIAL", "banner-partial");
    }
    if s.contains("missed") || s.contains("undetected") {
        return ("MISSED", "banner-missed");
    }
    if s.contains("detected") {
        return ("DETECTED", "banner-detected");
    }
    let total = run.controls.len();
    let detected = run
        .controls
        .iter()
        .filter(|(_, c)| *c == ControlStatus::Detected)
        .count();
    if total > 0 && detected == total {
        ("DETECTED", "banner-detected")
    } else if detected == 0 {
        ("MISSED", "banner-missed")
    } else {
        ("PARTIAL", "banner-partial")
    }
}

fn observe_body(run: ScenarioRun, rid: String) -> impl IntoView {
    let (label, class) = overall(&run);
    let gaps: Vec<(String, ControlStatus)> = run
        .controls
        .iter()
        .filter(|(_, c)| *c != ControlStatus::Detected)
        .cloned()
        .collect();
    let title = if run.scenario_name.is_empty() {
        run.scenario_id.clone()
    } else {
        run.scenario_name.clone()
    };
    let fix_href = format!("/lab/fix/{rid}");

    view! {
        <div class=format!("status-banner {class}")>{label}</div>

        <div class="obs-meta">
            <h1>{title}</h1>
            <Badge severity=run.severity.clone()/>
            {(!run.affected_component.is_empty())
                .then(|| view! { <span class="tag">{run.affected_component.clone()}</span> })}
        </div>

        <div class="obs-grid">
            <section class="panel">
                <h2>"Attack Path"</h2>
                <AttackPath nodes=run.attack_path.clone() detected_at=run.detected_at.clone().unwrap_or_default()/>
            </section>
            <section class="panel">
                <h2>"Controls Matrix"</h2>
                <ControlMatrix controls=run.controls.clone()/>
            </section>
        </div>

        <section class="panel">
            <h2>"Detection Gaps"</h2>
            {if gaps.is_empty() {
                view! { <p class="ok">"No gaps — every control detected the attack."</p> }.into_view()
            } else {
                view! {
                    <ul class="gap-list">
                        {gaps
                            .into_iter()
                            .map(|(name, st)| {
                                let class = if st == ControlStatus::Missed { "gap gap-missed" } else { "gap gap-partial" };
                                view! {
                                    <li class=class>
                                        <span>{control_icon(st)}</span>
                                        <span>{pretty_name(&name)}</span>
                                    </li>
                                }
                            })
                            .collect_view()}
                    </ul>
                }
                    .into_view()
            }}
        </section>

        <div class="actions">
            <A href=fix_href class="btn">"Apply Fix →"</A>
            <A href="/lab/scenarios" class="btn btn-ghost">"← Back to Scenarios"</A>
        </div>
    }
}

#[component]
pub fn LabObserve() -> impl IntoView {
    let params = use_params_map();
    let run_id = move || params.with(|p| p.get("run_id").cloned().unwrap_or_default());

    let findings = create_local_resource(run_id, |rid| async move {
        let r = get_json::<ScenarioRun>(&format!("/api/security/findings/{rid}")).await;
        if let Ok(run) = &r {
            snapshot::save_before(&rid, &run.controls);
        }
        r
    });

    view! {
        <Suspense fallback=|| view! { <Spinner/> }>
            {move || {
                findings
                    .get()
                    .map(|res| match res {
                        Ok(run) => observe_body(run, run_id()).into_view(),
                        Err(e) => view! { <ApiErrorBox error=e/> }.into_view(),
                    })
            }}
        </Suspense>
    }
}
