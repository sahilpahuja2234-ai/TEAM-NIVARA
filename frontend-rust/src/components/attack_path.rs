use crate::util::pretty_name;
use leptos::*;

fn node_icon(n: &str) -> &'static str {
    let l = n.to_lowercase();
    let has = |ks: &[&str]| ks.iter().any(|k| l.contains(k));
    if has(&["customer", "user", "attacker"]) {
        "👤"
    } else if has(&["cart"]) {
        "🛒"
    } else if has(&["checkout", "payment"]) {
        "💳"
    } else if has(&["pricing", "price", "coupon", "discount"]) {
        "🏷️"
    } else if has(&["db", "database", "sql"]) {
        "🗄️"
    } else if has(&["login", "auth", "token", "jwt"]) {
        "🔑"
    } else if has(&["admin"]) {
        "🛡️"
    } else if has(&["rate", "limit"]) {
        "⏱️"
    } else if has(&["api", "endpoint", "gateway"]) {
        "🔌"
    } else if has(&["docker", "container", "image", "pipeline", "dependency"]) {
        "📦"
    } else {
        "⚙️"
    }
}

/// Vertical node chain. The node matching `detected_at` glows green.
#[component]
pub fn AttackPath(
    nodes: Vec<String>,
    #[prop(optional)] detected_at: Option<String>,
) -> impl IntoView {
    if nodes.is_empty() {
        return view! { <p class="muted">"No attack path recorded."</p> }.into_view();
    }
    let n = nodes.len();
    view! {
        <div class="attack-path">
            {nodes
                .into_iter()
                .enumerate()
                .map(|(i, node)| {
                    let glow = detected_at
                        .as_deref()
                        .map(|d| d.eq_ignore_ascii_case(&node))
                        .unwrap_or(false);
                    let class = if glow { "path-node glow" } else { "path-node" };
                    let icon = node_icon(&node);
                    let label = pretty_name(&node);
                    view! {
                        <div class=class>
                            <span class="node-icon">{icon}</span>
                            <span class="node-label">{label}</span>
                            {glow.then(|| view! { <span class="node-tag">"detected here"</span> })}
                        </div>
                        {(i + 1 < n).then(|| view! { <div class="path-arrow">"↓"</div> })}
                    }
                })
                .collect_view()}
        </div>
    }
    .into_view()
}
