use crate::api::get_json;
use crate::components::{error_box::ApiErrorBox, spinner::Spinner, status_badge::StatusBadge};
use crate::models::OrderList;
use crate::util::{money, short_date};
use leptos::*;
use leptos_router::{use_query_map, A};

#[component]
pub fn Orders() -> impl IntoView {
    let query = use_query_map();
    let success = move || query.with(|q| q.get("success").map(|v| v.as_str() == "1").unwrap_or(false));

    let orders = create_local_resource(
        || (),
        |_| async { get_json::<OrderList>("/api/store/orders").await },
    );

    view! {
        <h1>"Order History"</h1>
        {move || {
            success()
                .then(|| view! { <div class="success-banner">"Order placed successfully!"</div> })
        }}
        <Suspense fallback=|| view! { <Spinner/> }>
            {move || {
                orders
                    .get()
                    .map(|res| match res {
                        Ok(list) => {
                            let list = list.into_vec();
                            if list.is_empty() {
                                return view! {
                                    <p class="muted">
                                        "No orders yet. " <A href="/catalog">"Browse books"</A>
                                    </p>
                                }
                                    .into_view();
                            }
                            list.into_iter()
                                .map(|o| {
                                    let open = create_rw_signal(false);
                                    let id = o.id.clone();
                                    let date = o.created_at.as_deref().map(short_date).unwrap_or_default();
                                    let status = o.status.clone();
                                    let total = o.final_total.or(o.total).map(money).unwrap_or_default();
                                    let items = o.items.clone();
                                    view! {
                                        <div class="order">
                                            <button class="order-head" on:click=move |_| open.update(|v| *v = !*v)>
                                                <span class="mono">{id}</span>
                                                <span class="muted">{date}</span>
                                                <StatusBadge status=status/>
                                                <span class="price">{total}</span>
                                                <span class="caret">{move || if open.get() { "▲" } else { "▼" }}</span>
                                            </button>
                                            {move || {
                                                open.get()
                                                    .then(|| {
                                                        let items = items.clone();
                                                        if items.is_empty() {
                                                            view! { <p class="muted order-items">"No item details."</p> }
                                                                .into_view()
                                                        } else {
                                                            view! {
                                                                <ul class="plain-list order-items">
                                                                    {items
                                                                        .into_iter()
                                                                        .map(|i| {
                                                                            let title = if i.title.is_empty() {
                                                                                format!("Book #{}", i.book_id)
                                                                            } else {
                                                                                i.title
                                                                            };
                                                                            view! {
                                                                                <li>
                                                                                    <span>{title}</span>
                                                                                    <span class="muted">{format!("× {}", i.quantity)}</span>
                                                                                    <span>{money(i.price)}</span>
                                                                                </li>
                                                                            }
                                                                        })
                                                                        .collect_view()}
                                                                </ul>
                                                            }
                                                                .into_view()
                                                        }
                                                    })
                                            }}
                                        </div>
                                    }
                                })
                                .collect_view()
                        }
                        Err(e) => view! { <ApiErrorBox error=e/> }.into_view(),
                    })
            }}
        </Suspense>
    }
}
