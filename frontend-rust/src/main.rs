#![allow(dead_code)] // scaffold: helpers/models are used by later tasks

mod api;
mod app;
mod auth;
mod components;
mod models;
mod poll;
mod pages;
mod snapshot;
mod util;

use app::App;
use leptos::*;
use wasm_bindgen::JsCast;

fn main() {
    console_error_panic_hook::set_once();
    let root = document()
        .get_element_by_id("app")
        .expect("#app not found in index.html")
        .unchecked_into::<web_sys::HtmlElement>();
    // keep the app mounted for the lifetime of the page
    std::mem::forget(mount_to(root, || view! { <App/> }));
}
