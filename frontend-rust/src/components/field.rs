use leptos::*;

/// Labeled text input bound to an RwSignal<String>.
#[component]
pub fn Field(
    label: &'static str,
    value: RwSignal<String>,
    #[prop(default = "text")] input_type: &'static str,
) -> impl IntoView {
    view! {
        <label class="field">
            <span>{label}</span>
            <input
                class="input"
                type=input_type
                prop:value=move || value.get()
                on:input=move |ev| value.set(event_target_value(&ev))
            />
        </label>
    }
}
