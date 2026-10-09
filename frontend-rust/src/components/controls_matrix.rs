use crate::models::ControlStatus;
use crate::util::pretty_name;
use leptos::*;

pub fn control_icon(s: ControlStatus) -> &'static str {
    match s {
        ControlStatus::Detected => "✅",
        ControlStatus::Missed => "❌",
        ControlStatus::Partial => "⚠️",
    }
}

/// Table: control name | result icon.
#[component]
pub fn ControlMatrix(controls: Vec<(String, ControlStatus)>) -> impl IntoView {
    if controls.is_empty() {
        return view! { <p class="muted">"No control results."</p> }.into_view();
    }
    view! {
        <table class="matrix">
            <thead>
                <tr>
                    <th>"Control"</th>
                    <th>"Result"</th>
                </tr>
            </thead>
            <tbody>
                {controls
                    .into_iter()
                    .map(|(name, st)| {
                        view! {
                            <tr>
                                <td>{pretty_name(&name)}</td>
                                <td class="matrix-icon">{control_icon(st)}</td>
                            </tr>
                        }
                    })
                    .collect_view()}
            </tbody>
        </table>
    }
    .into_view()
}
