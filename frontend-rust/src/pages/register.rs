use crate::api::post_public_ok;
use crate::components::{error_box::ErrorBox, field::Field};
use leptos::*;
use leptos_router::{use_navigate, A};

#[component]
pub fn Register() -> impl IntoView {
    let navigate = use_navigate();

    let email = create_rw_signal(String::new());
    let password = create_rw_signal(String::new());
    let full_name = create_rw_signal(String::new());
    let error_msg = create_rw_signal(String::new());

    let register_action = create_action(move |_: &()| {
        let payload = serde_json::json!({
            "email": email.get_untracked().trim(),
            "password": password.get_untracked(),
            "full_name": full_name.get_untracked().trim(),
        });
        async move { post_public_ok("/api/store/auth/register", &payload).await }
    });

    create_effect(move |_| match register_action.value().get() {
        Some(Ok(_)) => navigate("/login?registered=1", Default::default()),
        Some(Err(e)) => error_msg.set(e.message()),
        None => {}
    });

    let can_submit = move || {
        !register_action.pending().get()
            && !email.get().trim().is_empty()
            && !password.get().is_empty()
            && !full_name.get().trim().is_empty()
    };

    view! {
        <div class="auth-card">
            <h1>"Create account"</h1>
            <form
                class="checkout-form"
                on:submit=move |ev| {
                    ev.prevent_default();
                    error_msg.set(String::new());
                    register_action.dispatch(());
                }
            >
                <Field label="Full name" value=full_name/>
                <Field label="Email" value=email input_type="email"/>
                <Field label="Password" value=password input_type="password"/>
                <button class="btn" type="submit" disabled=move || !can_submit()>
                    {move || if register_action.pending().get() { "Creating…" } else { "Register" }}
                </button>
                {move || {
                    let m = error_msg.get();
                    (!m.is_empty()).then(|| view! { <ErrorBox message=m/> })
                }}
            </form>
            <p class="muted">"Already registered? " <A href="/login">"Log in"</A></p>
        </div>
    }
}
