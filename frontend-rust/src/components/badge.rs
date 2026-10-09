use leptos::*;

/// Severity badge: critical / high / medium / low (anything else = neutral).
#[component]
pub fn Badge(#[prop(into)] severity: String) -> impl IntoView {
    let key = severity.to_lowercase();
    let class = match key.as_str() {
        "critical" | "high" | "medium" | "low" => format!("badge badge-{key}"),
        _ => "badge badge-info".to_string(),
    };
    view! { <span class=class>{severity}</span> }
}
