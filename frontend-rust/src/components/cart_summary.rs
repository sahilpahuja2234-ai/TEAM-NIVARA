use crate::util::money;
use leptos::*;

/// Displays server-computed amounts only. Never calculates anything.
#[component]
pub fn CartSummary(
    subtotal: Option<f64>,
    discount: Option<f64>,
    coupon_code: Option<String>,
    total: Option<f64>,
) -> impl IntoView {
    let label = match &coupon_code {
        Some(c) if !c.is_empty() => format!("Discount ({c})"),
        _ => "Discount".to_string(),
    };
    view! {
        <div class="summary">
            {subtotal
                .map(|v| {
                    view! {
                        <div class="sum-row">
                            <span>"Subtotal"</span>
                            <span>{money(v)}</span>
                        </div>
                    }
                })}
            {discount
                .filter(|d| *d != 0.0)
                .map(|d| {
                    view! {
                        <div class="sum-row discount">
                            <span>{label}</span>
                            <span>{format!("-{}", money(d.abs()))}</span>
                        </div>
                    }
                })}
            <div class="sum-row total">
                <span>"Total"</span>
                <span>{total.map(money).unwrap_or_else(|| "Calculated at checkout".to_string())}</span>
            </div>
            <p class="muted small">"Final total is calculated by the server."</p>
        </div>
    }
}
