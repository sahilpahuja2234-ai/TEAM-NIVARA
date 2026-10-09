use crate::components::stars::Stars;
use crate::models::Book;
use leptos::*;
use leptos_router::A;

#[component]
pub fn BookCard(book: Book) -> impl IntoView {
    let hue = (book.id.rem_euclid(360) * 47) % 360;
    let cover = format!(
        "background: linear-gradient(135deg, hsl({hue},60%,38%), hsl({},60%,20%));",
        (hue + 40) % 360
    );
    let initial = book
        .title
        .chars()
        .next()
        .map(|c| c.to_uppercase().to_string())
        .unwrap_or_default();
    let href = format!("/book/{}", book.id);
    let author = book.author.clone().unwrap_or_else(|| "Unknown author".into());
    let price = format!("${:.2}", book.price);
    let rating = book.rating.unwrap_or(0.0);

    view! {
        <A href=href class="book-card">
            <div class="cover" style=cover>{initial}</div>
            <div class="card-body">
                <h3 class="card-title">{book.title}</h3>
                <p class="muted card-author">{author}</p>
                <div class="card-meta">
                    <span class="price">{price}</span>
                    <Stars rating=rating/>
                </div>
            </div>
        </A>
    }
}
