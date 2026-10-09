use leptos::*;

/// Last-run result badge: green = good (detected/pass/fixed), yellow = partial, red = missed/fail.
#[component]
pub fn ResultBadge(#[prop(into)] result: String) -> impl IntoView {
    let key = result.to_lowercase();
    let class = if ["detected", "pass", "fixed", "secure", "blocked", "success"]
        .iter()
        .any(|k| key.contains(k))
    {
        "badge badge-low"
    } else if key.contains("partial") {
        "badge badge-medium"
    } else if ["missed", "fail", "vulnerable", "exploited", "breach"]
        .iter()
        .any(|k| key.contains(k))
    {
        "badge badge-critical"
    } else {
        "badge badge-info"
    };
    view! { <span class=class>{result}</span> }
}
