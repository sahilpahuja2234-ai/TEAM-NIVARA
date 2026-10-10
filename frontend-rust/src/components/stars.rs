use leptos::*;

#[component]
pub fn Stars(rating: f64) -> impl IntoView {
    let n = rating.round().clamp(0.0, 5.0) as usize;
    let text = format!("{}{}", "★".repeat(n), "☆".repeat(5 - n));
    view! { <span class="stars" title=format!("{rating:.1} / 5")>{text}</span> }
}
