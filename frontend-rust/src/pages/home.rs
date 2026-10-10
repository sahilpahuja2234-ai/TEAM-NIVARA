use crate::api::{encode, get_json, ApiError};
use crate::components::{book_card::BookCard, error_box::ErrorBox, spinner::Spinner};
use crate::models::{CatalogResponse, Category};
use leptos::*;
use leptos_router::A;

#[component]
pub fn Home() -> impl IntoView {
    let featured = create_local_resource(
        || (),
        |_| async { get_json::<CatalogResponse>("/api/store/catalog?limit=8").await },
    );
    let categories = create_local_resource(
        || (),
        |_| async { get_json::<Vec<Category>>("/api/store/categories").await },
    );

    view! {
        <section class="hero">
            <h1>"NIVARA Bookstore"</h1>
            <p>"Demo Environment"</p>
        </section>

        <section>
            <h2>"Browse by category"</h2>
            <div class="chip-strip">
                {move || {
                    categories
                        .get()
                        .and_then(|r: Result<Vec<Category>, ApiError>| r.ok())
                        .map(|list| {
                            list.into_iter()
                                .map(|c| {
                                    let href = format!("/catalog?category={}", encode(&c.name));
                                    view! { <A href=href class="chip">{c.name}</A> }
                                })
                                .collect_view()
                        })
                }}
            </div>
        </section>

        <section>
            <h2>"Featured books"</h2>
            <Suspense fallback=|| view! { <Spinner/> }>
                {move || {
                    featured
                        .get()
                        .map(|res| match res {
                            Ok(resp) => {
                                view! {
                                    <div class="grid">
                                        {resp
                                            .books()
                                            .into_iter()
                                            .map(|b| view! { <BookCard book=b/> })
                                            .collect_view()}
                                    </div>
                                }
                                    .into_view()
                            }
                            Err(e) => view! { <ErrorBox message=e.to_string()/> }.into_view(),
                        })
                }}
            </Suspense>
        </section>
    }
}
