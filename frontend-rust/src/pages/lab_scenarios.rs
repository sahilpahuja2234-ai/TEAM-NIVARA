use crate::api::get_json;
use crate::components::{error_box::ApiErrorBox, scenario_card::ScenarioCard, spinner::Spinner};
use crate::models::ScenarioList;
use leptos::*;

#[component]
pub fn LabScenarios() -> impl IntoView {
    let scenarios = create_local_resource(
        || (),
        |_| async { get_json::<ScenarioList>("/api/lab/scenarios").await },
    );
    // empty string = all layers
    let layer = create_rw_signal(String::new());

    view! {
        <h1>"Scenario Library"</h1>
        <p class="muted">"Predefined, deterministic, safe attack scenarios."</p>

        <Suspense fallback=|| view! { <Spinner/> }>
            {move || {
                scenarios
                    .get()
                    .map(|res| match res {
                        Ok(resp) => {
                            let list = resp.into_vec();
                            let mut layers: Vec<String> = Vec::new();
                            for s in &list {
                                if !s.layer.is_empty() && !layers.contains(&s.layer) {
                                    layers.push(s.layer.clone());
                                }
                            }
                            view! {
                                <div class="chip-strip">
                                    <button
                                        class="chip"
                                        class:active=move || layer.get().is_empty()
                                        on:click=move |_| layer.set(String::new())
                                    >
                                        "All"
                                    </button>
                                    {layers
                                        .into_iter()
                                        .map(|l| {
                                            let is_sel = l.clone();
                                            let pick = l.clone();
                                            view! {
                                                <button
                                                    class="chip"
                                                    class:active=move || layer.get() == is_sel
                                                    on:click=move |_| layer.set(pick.clone())
                                                >
                                                    {l}
                                                </button>
                                            }
                                        })
                                        .collect_view()}
                                </div>
                                <div class="scn-grid">
                                    {move || {
                                        let sel = layer.get();
                                        list.iter()
                                            .filter(|s| sel.is_empty() || s.layer == sel)
                                            .cloned()
                                            .map(|s| view! { <ScenarioCard scenario=s detailed=true/> })
                                            .collect_view()
                                    }}
                                </div>
                            }
                                .into_view()
                        }
                        Err(e) => view! { <ApiErrorBox error=e/> }.into_view(),
                    })
            }}
        </Suspense>
    }
}
