use crate::api::{get_json, post_json};
use crate::components::{
    error_box::ApiErrorBox, scenario_card::ScenarioCard, score_ring::ScoreRing, spinner::Spinner,
};
use crate::models::{LabStatus, ScenarioList};
use crate::util::{score_color, short_datetime};
use leptos::*;
use leptos_router::A;

#[component]
pub fn LabDashboard() -> impl IntoView {
    let status = create_local_resource(
        || (),
        |_| async { get_json::<LabStatus>("/api/lab/status").await },
    );
    let scenarios = create_local_resource(
        || (),
        |_| async { get_json::<ScenarioList>("/api/lab/scenarios").await },
    );

    let reset = create_action(move |_: &()| async move {
        let r = post_json("/api/lab/reset", &serde_json::json!({})).await;
        if r.is_ok() {
            status.refetch();
            scenarios.refetch();
        }
        r
    });

    view! {
        <div class="lab-head">
            <div>
                <h1>"Security Lab"</h1>
                <p class="muted">"Create → Attack → Observe → Fix → Replay"</p>
            </div>
            <button
                class="btn"
                disabled=move || reset.pending().get()
                on:click=move |_| reset.dispatch(())
            >
                {move || if reset.pending().get() { "Resetting…" } else { "🔄 Reset Twin" }}
            </button>
        </div>
        {move || {
            reset
                .value()
                .get()
                .map(|r| match r {
                    Ok(_) => view! { <p class="ok">"Twin reset."</p> }.into_view(),
                    Err(e) => view! { <ApiErrorBox error=e/> }.into_view(),
                })
        }}

        <Suspense fallback=|| view! { <Spinner/> }>
            {move || {
                status
                    .get()
                    .map(|res| match res {
                        Ok(s) => {
                            let running = s.twin_running;
                            let score = s.current_score.unwrap_or(0.0);
                            let score_i = score.round() as i32;
                            let rate = s.detection_rate.unwrap_or(0.0).clamp(0.0, 100.0);
                            let bar_style = format!("width:{rate:.0}%;background:{}", score_color(rate));
                            let rate_style = format!("color:{}", score_color(rate));
                            let last_reset = s
                                .last_reset
                                .as_deref()
                                .map(|d| format!("Last reset: {}", short_datetime(d)));
                            let count = s.scenario_count.map(|n| format!("across {n} scenarios"));
                            view! {
                                <div class="stat-grid">
                                    <div class="stat-card">
                                        <h3 class="stat-title">"Digital Twin Status"</h3>
                                        <div class="twin-status">
                                            <span class={if running { "dot dot-on" } else { "dot dot-off" }}></span>
                                            <span class={if running { "ok big" } else { "err big" }}>
                                                {if running { "RUNNING" } else { "STOPPED" }}
                                            </span>
                                        </div>
                                        <p class="muted small">
                                            {if s.db_seeded { "Database seeded ✓" } else { "Database not seeded" }}
                                        </p>
                                        <p class="muted small">{last_reset}</p>
                                    </div>

                                    <div class="stat-card center">
                                        <h3 class="stat-title">"Security Score"</h3>
                                        <ScoreRing score=score_i label="out of 100"/>
                                    </div>

                                    <div class="stat-card">
                                        <h3 class="stat-title">"Detection Rate"</h3>
                                        <div class="big" style=rate_style>{format!("{rate:.0}%")}</div>
                                        <div class="bar">
                                            <div class="bar-fill" style=bar_style></div>
                                        </div>
                                        <p class="muted small">{count}</p>
                                    </div>
                                </div>
                            }
                                .into_view()
                        }
                        Err(e) => view! { <ApiErrorBox error=e/> }.into_view(),
                    })
            }}
        </Suspense>

        <div class="lab-head">
            <h2>"Scenarios"</h2>
            <A href="/lab/scenarios">"View full library →"</A>
        </div>
        <Suspense fallback=|| view! { <Spinner/> }>
            {move || {
                scenarios
                    .get()
                    .map(|res| match res {
                        Ok(resp) => {
                            let list = resp.into_vec();
                            if list.is_empty() {
                                view! { <p class="muted">"No scenarios found."</p> }.into_view()
                            } else {
                                view! {
                                    <div class="scn-grid">
                                        {list
                                            .into_iter()
                                            .map(|s| view! { <ScenarioCard scenario=s/> })
                                            .collect_view()}
                                    </div>
                                }
                                    .into_view()
                            }
                        }
                        Err(e) => view! { <ApiErrorBox error=e/> }.into_view(),
                    })
            }}
        </Suspense>
    }
}
