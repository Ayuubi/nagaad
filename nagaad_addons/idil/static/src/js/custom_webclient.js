
class CustomWebClient extends WebClient {
    setup() {
        super.setup();
        this.title.setParts({ zopenerp: "Nagaad" });
    }
}

registry.category("main_components").add("WebClient", CustomWebClient);
