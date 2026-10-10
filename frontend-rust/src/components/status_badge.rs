use leptos::*;

/// Order status: pending=yellow, processing=blue, delivered=green (cancelled=red).
#[component]
pub fn StatusBadge(#[prop(into)] status: String) -> impl IntoView {
    let key = status.to_lowercase();
    let class = match key.as_str() {
        "pending" | "processing" | "delivered" | "cancelled" => format!("badge status-{key}"),
        _ => "badge badge-info".to_string(),
    };
    view! { <span class=class>{status}</span> }
}
