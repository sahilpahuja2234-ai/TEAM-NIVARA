use crate::api::{post_json_as, ApiError};
use crate::components::{error_box::ApiErrorBox, progress_panel::ProgressPanel};
use crate::models::RunStarted;
use crate::poll::poll_run;
use leptos::*;
use leptos_router::{use_navigate, use_params_map, A};
use std::{cell::Cell, rc::Rc};

#[component]
pub fn LabRun() -> impl IntoView {
    let params = use_params_map();
    let scenario_id = move || params.with(|p| p.get("id").cloned().unwrap_or_default());
    let navigate = use_navigate();

    let alive = Rc::new(Cell::new(true));
    {
        let alive = alive.clone();
        on_cleanup(move || alive.set(false));
    }

    let progress = create_rw_signal(None::<f64>);
    let current = create_rw_signal(String::from("Starting scenario…"));
    let steps = create_rw_signal(Vec::<String>::new());

    // On mount: start the run, then poll until completed.
    let run = create_local_resource(scenario_id, move |sid| {
        let alive = alive.clone();
        async move {
            let started: RunStarted =
                post_json_as(&format!("/api/lab/run/{sid}"), &serde_json::json!({})).await?;
            current.set("Scenario running…".to_string());
            poll_run(
                &started.run_id,
                &alive,
                |st| {
                    steps.set(st.step_lines());
                    progress.set(st.progress);
                    if let Some(m) = &st.message {
                        current.set(m.clone());
                    }
                },
                false,
            )
            .await?;
            Ok::<String, ApiError>(started.run_id)
        }
    });

    create_effect(move |_| {
        if let Some(Ok(rid)) = run.get() {
            navigate(&format!("/lab/observe/{rid}"), Default::default());
        }
    });

    view! {
        <h1>"Running scenario"</h1>
        <p class="muted">{move || format!("Scenario {}", scenario_id())}</p>
        {move || match run.get() {
            Some(Err(e)) => {
                view! {
                    <ApiErrorBox error=e/>
                    <A href="/lab/scenarios" class="btn">"← Back to Scenarios"</A>
                }
                    .into_view()
            }
            _ => view! { <ProgressPanel progress=progress current=current steps=steps/> }.into_view(),
        }}
    }
}
