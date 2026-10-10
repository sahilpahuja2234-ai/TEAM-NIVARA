use crate::api::{get_json, get_token, post_json};
use crate::components::{error_box::ErrorBox, spinner::Spinner, stars::Stars};
use crate::models::{Book, ReviewList};
use leptos::*;
use leptos_router::{use_params_map, A};

#[component]
pub fn BookDetail() -> impl IntoView {
    let params = use_params_map();
    let id = move || params.with(|p| p.get("id").cloned().unwrap_or_default());
    let refresh = create_rw_signal(0u32);

    let book = create_local_resource(id, |id| async move {
        get_json::<Book>(&format!("/api/store/catalog/{id}")).await
    });
    let reviews = create_local_resource(
        move || (id(), refresh.get()),
        |(id, _)| async move {
            get_json::<ReviewList>(&format!("/api/store/catalog/{id}/reviews")).await
        },
    );

    // Add to cart
    let add = create_action(|book_id: &i64| {
        let book_id = *book_id;
        async move {
            post_json(
                "/api/store/cart/add",
                &serde_json::json!({ "book_id": book_id, "quantity": 1 }),
            )
            .await
        }
    });

    // Leave a review
    let rating = create_rw_signal(5i32);
    let body = create_rw_signal(String::new());
    let submit = create_action(move |_: &()| {
        let payload = serde_json::json!({
            "rating": rating.get_untracked(),
            "body": body.get_untracked(),
        });
        let bid = id();
        async move {
            let r = post_json(&format!("/api/store/catalog/{bid}/reviews"), &payload).await;
            if r.is_ok() {
                body.set(String::new());
                refresh.update(|n| *n += 1);
            }
            r
        }
    });
    let logged_in = get_token().is_some();

    view! {
        <Suspense fallback=|| view! { <Spinner/> }>
            {move || {
                book.get()
                    .map(|res| match res {
                        Ok(b) => {
                            let bid = b.id;
                            let hue = (bid.rem_euclid(360) * 47) % 360;
                            let cover = format!(
                                "background: linear-gradient(135deg, hsl({hue},60%,38%), hsl({},60%,20%));",
                                (hue + 40) % 360
                            );
                            let initial = b
                                .title
                                .chars()
                                .next()
                                .map(|c| c.to_uppercase().to_string())
                                .unwrap_or_default();
                            let rating_val = b.rating.unwrap_or(0.0);
                            view! {
                                <A href="/catalog" class="back">"← Back to catalog"</A>
                                <article class="detail">
                                    <div class="cover cover-lg" style=cover>{initial}</div>
                                    <div class="detail-info">
                                        <h1>{b.title}</h1>
                                        <p class="muted">
                                            {format!("by {}", b.author.unwrap_or_else(|| "Unknown author".into()))}
                                            {b.category.map(|c| format!(" · {c}"))}
                                        </p>
                                        <div class="card-meta">
                                            <Stars rating=rating_val/>
                                            <span class="muted">{format!("{rating_val:.1}")}</span>
                                        </div>
                                        <p class="price price-lg">{format!("${:.2}", b.price)}</p>
                                        <p>{b.description.unwrap_or_default()}</p>
                                        <button
                                            class="btn"
                                            disabled=move || add.pending().get()
                                            on:click=move |_| add.dispatch(bid)
                                        >
                                            "Add to Cart"
                                        </button>
                                        {move || {
                                            add.value()
                                                .get()
                                                .map(|r| match r {
                                                    Ok(_) => view! { <span class="ok">" Added to cart ✓"</span> }.into_view(),
                                                    Err(e) => view! { <span class="err">{format!(" {e}")}</span> }.into_view(),
                                                })
                                        }}
                                    </div>
                                </article>
                            }
                                .into_view()
                        }
                        Err(e) => view! { <ErrorBox message=e.to_string()/> }.into_view(),
                    })
            }}
        </Suspense>

        <section class="reviews">
            <h2>"Reviews"</h2>
            <Suspense fallback=|| view! { <Spinner/> }>
                {move || {
                    reviews
                        .get()
                        .map(|res| match res {
                            Ok(list) => {
                                let list = list.into_vec();
                                if list.is_empty() {
                                    view! { <p class="muted">"No reviews yet."</p> }.into_view()
                                } else {
                                    list.into_iter()
                                        .map(|r| {
                                            let date = r
                                                .created_at
                                                .as_deref()
                                                .map(|d| d.chars().take(10).collect::<String>())
                                                .unwrap_or_default();
                                            let rv = r.rating as f64;
                                            view! {
                                                <div class="review">
                                                    <div class="review-head">
                                                        <strong>{r.user.unwrap_or_else(|| "Anonymous".into())}</strong>
                                                        <Stars rating=rv/>
                                                        <span class="muted">{date}</span>
                                                    </div>
                                                    <p>{r.comment.unwrap_or_default()}</p>
                                                </div>
                                            }
                                        })
                                        .collect_view()
                                }
                            }
                            Err(e) => view! { <ErrorBox message=e.to_string()/> }.into_view(),
                        })
                }}
            </Suspense>

            {if logged_in {
                view! {
                    <form
                        class="review-form"
                        on:submit=move |ev| {
                            ev.prevent_default();
                            submit.dispatch(());
                        }
                    >
                        <h3>"Leave a Review"</h3>
                        <select on:change=move |ev| {
                            rating.set(event_target_value(&ev).parse().unwrap_or(5))
                        }>
                            {(1..=5)
                                .rev()
                                .map(|n| view! { <option value=n.to_string()>{format!("{n} ★")}</option> })
                                .collect_view()}
                        </select>
                        <textarea
                            rows="4"
                            placeholder="Write your review…"
                            prop:value=move || body.get()
                            on:input=move |ev| body.set(event_target_value(&ev))
                        ></textarea>
                        <button
                            class="btn"
                            type="submit"
                            disabled=move || submit.pending().get() || body.get().trim().is_empty()
                        >
                            "Submit review"
                        </button>
                        {move || {
                            submit
                                .value()
                                .get()
                                .and_then(|r| r.err())
                                .map(|e| view! { <span class="err">{format!(" {e}")}</span> })
                        }}
                    </form>
                }
                    .into_view()
            } else {
                view! {
                    <p class="muted">
                        <A href="/login">"Log in"</A>
                        " to leave a review."
                    </p>
                }
                    .into_view()
            }}
        </section>
    }
}
