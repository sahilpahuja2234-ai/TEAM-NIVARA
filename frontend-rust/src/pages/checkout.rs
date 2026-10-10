use crate::api::{get_json, post_json};
use crate::components::{
    cart_summary::CartSummary, error_box::ApiErrorBox, field::Field, spinner::Spinner,
};
use crate::models::CartResponse;
use leptos::*;
use leptos_router::{use_navigate, A};

#[component]
pub fn Checkout() -> impl IntoView {
    // Server-computed summary (display only)
    let cart = create_local_resource(
        || (),
        |_| async { get_json::<CartResponse>("/api/store/cart").await },
    );

    let name = create_rw_signal(String::new());
    let address = create_rw_signal(String::new());
    let city = create_rw_signal(String::new());
    let pincode = create_rw_signal(String::new());
    let ready = move || {
        [name, address, city, pincode]
            .iter()
            .all(|s| !s.get().trim().is_empty())
    };

    let place = create_action(move |code: &Option<String>| {
        let mut payload = serde_json::json!({
            "address": {
                "name": name.get_untracked().trim(),
                "address": address.get_untracked().trim(),
                "city": city.get_untracked().trim(),
                "pincode": pincode.get_untracked().trim(),
            }
        });
        if let Some(c) = code {
            payload["coupon_code"] = serde_json::Value::String(c.clone());
        }
        async move { post_json("/api/store/orders/checkout", &payload).await }
    });

    let navigate = use_navigate();
    create_effect(move |_| {
        if matches!(place.value().get(), Some(Ok(_))) {
            navigate("/orders?success=1", Default::default());
        }
    });

    view! {
        <h1>"Checkout"</h1>
        <Suspense fallback=|| view! { <Spinner/> }>
            {move || {
                cart.get()
                    .map(|res| match res {
                        Ok(resp) => {
                            let c = resp.into_cart();
                            if c.items.is_empty() {
                                return view! {
                                    <p class="muted">
                                        "Your cart is empty. " <A href="/catalog">"Browse books"</A>
                                    </p>
                                }
                                    .into_view();
                            }
                            let code = c.coupon_code.clone().filter(|s| !s.is_empty());
                            let (subtotal, discount, total, coupon_code) = (
                                c.subtotal,
                                c.discount,
                                c.total,
                                c.coupon_code.clone(),
                            );
                            view! {
                                <div class="checkout-grid">
                                    <form
                                        class="checkout-form"
                                        on:submit=move |ev| {
                                            ev.prevent_default();
                                            place.dispatch(code.clone());
                                        }
                                    >
                                        <h2>"Shipping address"</h2>
                                        <Field label="Full name" value=name/>
                                        <Field label="Address" value=address/>
                                        <Field label="City" value=city/>
                                        <Field label="Pincode" value=pincode/>

                                        <h2>"Payment"</h2>
                                        <div class="pay-box">
                                            <span>"Card: **** **** **** 4242"</span>
                                            <span>"Exp: 12/27"</span>
                                        </div>
                                        <p class="muted small">"Demo payment — no real charge."</p>

                                        <button
                                            class="btn"
                                            type="submit"
                                            disabled=move || place.pending().get() || !ready()
                                        >
                                            "Place Order"
                                        </button>
                                        {move || {
                                            place
                                                .value()
                                                .get()
                                                .and_then(|r| r.err())
                                                .map(|e| view! { <ApiErrorBox error=e/> })
                                        }}
                                    </form>

                                    <aside class="panel">
                                        <h2>"Order summary"</h2>
                                        <ul class="plain-list">
                                            {c
                                                .items
                                                .into_iter()
                                                .map(|it| {
                                                    let title = if it.title.is_empty() {
                                                        format!("Book #{}", it.book_id)
                                                    } else {
                                                        it.title
                                                    };
                                                    view! {
                                                        <li>
                                                            <span>{title}</span>
                                                            <span class="muted">{format!("× {}", it.quantity)}</span>
                                                        </li>
                                                    }
                                                })
                                                .collect_view()}
                                        </ul>
                                        <CartSummary
                                            subtotal=subtotal
                                            discount=discount
                                            coupon_code=coupon_code
                                            total=total
                                        />
                                    </aside>
                                </div>
                            }
                                .into_view()
                        }
                        Err(e) => view! { <ApiErrorBox error=e/> }.into_view(),
                    })
            }}
        </Suspense>
    }
}
