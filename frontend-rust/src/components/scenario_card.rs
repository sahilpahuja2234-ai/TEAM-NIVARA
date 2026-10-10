use crate::components::{badge::Badge, result_badge::ResultBadge};
use crate::models::Scenario;
use crate::util::short_datetime;
use leptos::*;
use leptos_router::A;

#[component]
pub fn ScenarioCard(
    scenario: Scenario,
    /// Show description + affected component (used on the Scenario Library page).
    #[prop(optional)]
    detailed: bool,
) -> impl IntoView {
    let sid = scenario.sid();
    let href = format!("/lab/run/{sid}");
    let name = scenario.display_name();
    let layer = scenario.layer.clone();
    let severity = scenario.severity.clone();
    let last_run = scenario.last_run.as_deref().map(short_datetime);
    let result = scenario.last_result_label();
    let desc = scenario.description.clone().filter(|_| detailed);
    let comp = scenario.affected_component.clone().filter(|_| detailed);

    view! {
        <div class="scn-card">
            <div class="scn-head">
                <span class="scn-id">{sid}</span>
                <Badge severity=severity/>
            </div>
            <h3 class="scn-name">{name}</h3>
            <p class="muted small scn-layer">{layer}</p>
            {desc.map(|d| view! { <p class="scn-desc">{d}</p> })}
            {comp
                .map(|c| {
                    view! { <p class="muted small">{format!("Affected component: {c}")}</p> }
                })}
            <div class="scn-last">
                {match last_run {
                    Some(d) => view! { <span class="muted small">{format!("Last run: {d}")}</span> }.into_view(),
                    None => view! { <span class="muted small">"Never run"</span> }.into_view(),
                }}
                {result.map(|r| view! { <ResultBadge result=r/> })}
            </div>
            <A href=href class="btn btn-sm">"▶ Run"</A>
        </div>
    }
}
