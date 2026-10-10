use crate::api::{encode, get_json};
use crate::components::{book_card::BookCard, error_box::ErrorBox, spinner::Spinner};
use crate::models::{CatalogResponse, Category};
use leptos::*;
use leptos_router::use_query_map;
use std::time::Duration;

const PAGE_SIZE: usize = 20;

#[component]
pub fn Catalog() -> impl IntoView {
    // Initial filters can come from the URL (?category=..&search=..), e.g. Home chips.
    let query = use_query_map().get_untracked();
    let search_query = create_rw_signal(query.get("search").cloned().unwrap_or_default());
    let category_filter = create_rw_signal(query.get("category").cloned().unwrap_or_default());
    let page = create_rw_signal(1usize);

    let categories = create_local_resource(
        || (),
        |_| async { get_json::<Vec<Category>>("/api/store/categories").await },
    );

    let books = create_local_resource(
        move || (search_query.get(), category_filter.get(), page.get()),
        |(s, c, p)| async move {
            let url = format!(
                "/api/store/catalog?search={}&category={}&page={}&limit={}",
                encode(&s),
                encode(&c),
                p,
                PAGE_SIZE
            );
            get_json::<CatalogResponse>(&url).await
        },
    );

    // 300ms debounce on search input
    let pending = store_value(None);
    let on_input = move |ev| {
        let v = event_target_value(&ev);
        if let Some(h) = pending.get_value() {
            let h: leptos::leptos_dom::helpers::TimeoutHandle = h;
            h.clear();
        }
        let h = set_timeout_with_handle(
            move || {
                page.set(1);
                search_query.set(v);
            },
            Duration::from_millis(300),
        )
        .ok();
        pending.set_value(h);
    };

    view! {
        <h1>"Catalog"</h1>

        <input
            class="search"
            type="search"
            placeholder="Search books or authors…"
            value=search_query.get_untracked()
            on:input=on_input
        />

        <div class="chip-strip">
            <button
                class="chip"
                class:active=move || category_filter.get().is_empty()
                on:click=move |_| {
                    page.set(1);
                    category_filter.set(String::new());
                }
            >
                "All"
            </button>
            {move || {
                categories
                    .get()
                    .and_then(|r| r.ok())
                    .map(|list| {
                        list.into_iter()
                            .map(|c| {
                                let name = c.name.clone();
                                let name_click = c.name.clone();
                                view! {
                                    <button
                                        class="chip"
                                        class:active=move || category_filter.get() == name
                                        on:click=move |_| {
                                            page.set(1);
                                            category_filter.set(name_click.clone());
                                        }
                                    >
                                        {c.name}
                                    </button>
                                }
                            })
                            .collect_view()
                    })
            }}
        </div>

        <Suspense fallback=|| view! { <Spinner/> }>
            {move || {
                books
                    .get()
                    .map(|res| match res {
                        Ok(resp) => {
                            let total = resp.total();
                            let list = resp.books();
                            let n = list.len();
                            let has_next = match total {
                                Some(t) => ((page.get_untracked() * PAGE_SIZE) as i64) < t,
                                None => n >= PAGE_SIZE,
                            };
                            view! {
                                {if list.is_empty() {
                                    view! { <p class="muted">"No books found."</p> }.into_view()
                                } else {
                                    view! {
                                        <div class="grid">
                                            {list
                                                .into_iter()
                                                .map(|b| view! { <BookCard book=b/> })
                                                .collect_view()}
                                        </div>
                                    }
                                        .into_view()
                                }}
                                <div class="pager">
                                    <button
                                        disabled=move || page.get() <= 1
                                        on:click=move |_| page.update(|p| *p -= 1)
                                    >
                                        "← Prev"
                                    </button>
                                    <span class="muted">{move || format!("Page {}", page.get())}</span>
                                    <button disabled=!has_next on:click=move |_| page.update(|p| *p += 1)>
                                        "Next →"
                                    </button>
                                </div>
                            }
                                .into_view()
                        }
                        Err(e) => view! { <ErrorBox message=e.to_string()/> }.into_view(),
                    })
            }}
        </Suspense>
    }
}
