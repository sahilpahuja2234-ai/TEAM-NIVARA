use crate::api::{delete_req, get_json, post_json, put_json};
use crate::components::{cart_summary::CartSummary, error_box::ApiErrorBox, spinner::Spinner};
use crate::models::CartResponse;
use crate::util::money;
use leptos::*;
use leptos_router::A;

#[component]
pub fn Cart() -> impl IntoView {
    let cart = create_local_resource(
        || (),
        |_| async { get_json::<CartResponse>("/api/store/cart").await },
    );
    let coupon = create_rw_signal(String::new());

    let set_qty = create_action(move |(item_id, qty): &(i64, i32)| {
        let (item_id, qty) = (*item_id, *qty);
        async move {
            let r = put_json(
                &format!("/api/store/cart/{item_id}"),
                &serde_json::json!({ "quantity": qty }),
            )
            .await;
            cart.refetch();
            r
        }
    });

    let remove = create_action(move |item_id: &i64| {
        let item_id = *item_id;
        async move {
            let r = delete_req(&format!("/api/store/cart/{item_id}")).await;
            cart.refetch();
            r
        }
    });

    let apply = create_action(move |_: &()| {
        let code = coupon.get_untracked().trim().to_string();
        async move {
            let r = post_json("/api/store/cart/coupon", &serde_json::json!({ "code": code })).await;
            if r.is_ok() {
                cart.refetch();
            }
            r
        }
    });

    view! {
        <h1>"Your Cart"</h1>

        {move || set_qty.value().get().and_then(|r| r.err()).map(|e| view! { <ApiErrorBox error=e/> })}
        {move || remove.value().get().and_then(|r| r.err()).map(|e| view! { <ApiErrorBox error=e/> })}

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
                            let (subtotal, discount, total, code) = (
                                c.subtotal,
                                c.discount,
                                c.total,
                                c.coupon_code.clone(),
                            );
                            view! {
                                <div class="cart-list">
                                    {c
                                        .items
                                        .into_iter()
                                        .map(|it| {
                                            let item_id = it.id;
                                            let qty = it.quantity;
                                            let at_min = qty <= 1;
                                            let title = if it.title.is_empty() {
                                                format!("Book #{}", it.book_id)
                                            } else {
                                                it.title.clone()
                                            };
                                            let href = format!("/book/{}", it.book_id);
                                            view! {
                                                <div class="cart-row">
                                                    <A href=href class="cart-title">{title}</A>
                                                    <span class="muted">{money(it.price)}</span>
                                                    <div class="qty">
                                                        <button
                                                            class="qty-btn"
                                                            disabled=at_min
                                                            on:click=move |_| set_qty.dispatch((item_id, qty - 1))
                                                        >
                                                            "−"
                                                        </button>
                                                        <span>{qty}</span>
                                                        <button
                                                            class="qty-btn"
                                                            on:click=move |_| set_qty.dispatch((item_id, qty + 1))
                                                        >
                                                            "+"
                                                        </button>
                                                    </div>
                                                    <span class="line-total">{it.line_total.map(money)}</span>
                                                    <button
                                                        class="link-btn danger"
                                                        on:click=move |_| remove.dispatch(item_id)
                                                    >
                                                        "Remove"
                                                    </button>
                                                </div>
                                            }
                                        })
                                        .collect_view()}
                                </div>

                                <div class="coupon">
                                    <input
                                        class="input"
                                        placeholder="Coupon code"
                                        prop:value=move || coupon.get()
                                        on:input=move |ev| coupon.set(event_target_value(&ev))
                                    />
                                    <button
                                        class="btn"
                                        disabled=move || apply.pending().get() || coupon.get().trim().is_empty()
                                        on:click=move |_| apply.dispatch(())
                                    >
                                        "Apply"
                                    </button>
                                </div>
                                {move || {
                                    apply
                                        .value()
                                        .get()
                                        .map(|r| match r {
                                            Ok(_) => view! { <p class="ok">"Coupon applied."</p> }.into_view(),
                                            Err(e) => view! { <p class="err">{e.message()}</p> }.into_view(),
                                        })
                                }}

                                <CartSummary subtotal=subtotal discount=discount coupon_code=code total=total/>

                                <A href="/checkout" class="btn">"Proceed to Checkout"</A>
                            }
                                .into_view()
                        }
                        Err(e) => view! { <ApiErrorBox error=e/> }.into_view(),
                    })
            }}
        </Suspense>
    }
}
